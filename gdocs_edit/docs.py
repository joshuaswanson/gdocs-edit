"""Logic for extracting text + indices from a Google Doc and locating substrings."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DocText:
    """Flat text of the document plus a map from flat-text offset to absolute doc index."""
    text: str
    # index_map[i] == absolute Google Docs character index for text[i]
    index_map: list[int]
    # Absolute index just past the last character of the body (exclusive).
    # Google Docs bodies always end with a trailing newline; the body end index
    # is one past that newline. For inserts "at the end", use body_end - 1.
    body_end: int


def _walk_text_runs(content: list[dict]):
    """Yield (start_index, content_string) for every textRun in structural content."""
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


def extract_text(doc: dict) -> DocText:
    body = doc.get("body", {})
    content = body.get("content", [])

    text_parts: list[str] = []
    index_map: list[int] = []
    for start, s in _walk_text_runs(content):
        for i, ch in enumerate(s):
            text_parts.append(ch)
            index_map.append(start + i)

    body_end = 1
    if content:
        last = content[-1]
        if "endIndex" in last:
            body_end = last["endIndex"]

    return DocText(text="".join(text_parts), index_map=index_map, body_end=body_end)


def find_unique_range(doc_text: DocText, target: str) -> tuple[int, int]:
    """Locate `target` as a substring of the doc's flat text.

    Returns (start_index, end_index) as absolute Google Docs indices, where
    end_index is exclusive (suitable for Range.endIndex in the API).

    Raises ValueError if the target is empty, not found, or found more than once.
    """
    if not target:
        raise ValueError("Target text must be non-empty.")

    text = doc_text.text
    first = text.find(target)
    if first == -1:
        raise ValueError(f"Target text not found in document: {target!r}")

    second = text.find(target, first + 1)
    if second != -1:
        raise ValueError(
            f"Target text found multiple times in document; must be unique: {target!r}"
        )

    abs_start = doc_text.index_map[first]
    abs_end = doc_text.index_map[first + len(target) - 1] + 1
    return abs_start, abs_end
