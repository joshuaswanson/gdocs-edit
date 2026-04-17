"""Extract text + indices from a Google Doc, locate substrings, and enumerate tabs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DocText:
    """Flat text of a document segment plus a map from flat-text offset to absolute doc index.

    `tab_id` is the tab this text was extracted from, or None if it was read from the legacy
    top-level body field (i.e. the first/only tab of a non-tabbed document).
    """
    text: str
    index_map: list[int]  # index_map[i] == absolute Google Docs character index of text[i]
    body_end: int         # one past the last index of the segment; trailing newline lives at body_end-1
    tab_id: str | None = None


@dataclass
class TabInfo:
    tab_id: str
    title: str
    depth: int  # 0 for top-level tabs, 1 for child tabs, etc.


def _walk_text_runs(content: list[dict]):
    """Yield (absolute_start_index, content_string) for every textRun in structural content.

    Recurses into tables so that table cell text is included.
    """
    for element in content:
        paragraph = element.get("paragraph")
        if paragraph:
            for el in paragraph.get("elements", []):
                text_run = el.get("textRun")
                if text_run and "startIndex" in el:
                    yield el["startIndex"], text_run.get("content", "")
            continue

        table = element.get("table")
        if table:
            for row in table.get("tableRows", []):
                for cell in row.get("tableCells", []):
                    yield from _walk_text_runs(cell.get("content", []))
            continue

        # tableOfContents, sectionBreak, etc. contribute no readable text runs.


def _extract_from_body(body: dict, tab_id: str | None) -> DocText:
    content = body.get("content", [])
    text_parts: list[str] = []
    index_map: list[int] = []
    for start, s in _walk_text_runs(content):
        for i, ch in enumerate(s):
            text_parts.append(ch)
            index_map.append(start + i)

    body_end = 1
    if content and "endIndex" in content[-1]:
        body_end = content[-1]["endIndex"]

    return DocText(
        text="".join(text_parts),
        index_map=index_map,
        body_end=body_end,
        tab_id=tab_id,
    )


def _iter_tabs(tabs: list[dict], depth: int = 0):
    """Yield (Tab dict, depth) for every tab, recursing into childTabs."""
    for tab in tabs:
        yield tab, depth
        yield from _iter_tabs(tab.get("childTabs", []) or [], depth + 1)


def list_tabs(doc: dict) -> list[TabInfo]:
    """Return all tabs in a document, depth-first. Empty if the doc is not tabbed."""
    out: list[TabInfo] = []
    for tab, depth in _iter_tabs(doc.get("tabs", []) or []):
        props = tab.get("tabProperties", {}) or {}
        out.append(
            TabInfo(
                tab_id=props.get("tabId", ""),
                title=props.get("title", ""),
                depth=depth,
            )
        )
    return out


def _find_tab(doc: dict, tab_id: str) -> dict | None:
    for tab, _ in _iter_tabs(doc.get("tabs", []) or []):
        if (tab.get("tabProperties", {}) or {}).get("tabId") == tab_id:
            return tab
    return None


def extract_text(doc: dict, tab_id: str | None = None) -> DocText:
    """Extract flat text for a document.

    If `tab_id` is provided, reads from that tab's documentTab.body. Otherwise reads from the
    legacy top-level `body` field (which mirrors the first tab's content for single-tab docs).
    """
    if tab_id is None:
        return _extract_from_body(doc.get("body", {}) or {}, tab_id=None)

    tab = _find_tab(doc, tab_id)
    if tab is None:
        raise ValueError(f"Tab not found: {tab_id!r}")
    doc_tab = tab.get("documentTab", {}) or {}
    body = doc_tab.get("body", {}) or {}
    return _extract_from_body(body, tab_id=tab_id)


def extract_all_tabs(doc: dict) -> list[DocText]:
    """Extract text for every tab in the document.

    If the document is not tabbed, returns a single DocText read from the legacy body.
    """
    tabs = list_tabs(doc)
    if not tabs:
        return [extract_text(doc, tab_id=None)]
    return [extract_text(doc, tab_id=t.tab_id) for t in tabs]


def find_ranges(doc_text: DocText, target: str) -> list[tuple[int, int]]:
    """Return absolute [start, end) ranges for every occurrence of `target`.

    Matches are returned in document order (lowest start index first).
    """
    if not target:
        raise ValueError("Target text must be non-empty.")

    out: list[tuple[int, int]] = []
    text = doc_text.text
    n = len(target)
    pos = 0
    while True:
        hit = text.find(target, pos)
        if hit == -1:
            break
        abs_start = doc_text.index_map[hit]
        abs_end = doc_text.index_map[hit + n - 1] + 1
        out.append((abs_start, abs_end))
        pos = hit + n
    return out


def pick_range(
    doc_text: DocText,
    target: str,
    occurrence: int | None = None,
) -> tuple[int, int]:
    """Pick a single [start, end) range for `target`.

    - If `occurrence` is None: the target must appear exactly once.
    - If `occurrence` is a positive int N: returns the Nth match (1-indexed).

    Raises ValueError if the target is missing, ambiguous (when unique is required),
    or the requested occurrence is out of range.
    """
    ranges = find_ranges(doc_text, target)
    if not ranges:
        raise ValueError(f"Target text not found: {target!r}")

    if occurrence is None:
        if len(ranges) > 1:
            raise ValueError(
                f"Target text found {len(ranges)} times; use --occurrence N (1-indexed) "
                f"or --all to disambiguate: {target!r}"
            )
        return ranges[0]

    if occurrence < 1 or occurrence > len(ranges):
        raise ValueError(
            f"--occurrence {occurrence} out of range; {len(ranges)} match(es) found for {target!r}"
        )
    return ranges[occurrence - 1]
