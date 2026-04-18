from __future__ import annotations

import argparse
import sys

from . import docs as docs_mod
from . import gws
from .styles import add_style_flags, build_text_style, update_text_style_request


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def _unescape(s: str) -> str:
    """Interpret the common backslash escapes (\\n, \\t, \\r, \\\\) in a string.

    Other backslash sequences are left as-is so users who need a literal
    backslash before an unknown letter don't have to double-escape it.
    """
    if s is None or "\\" not in s:
        return s
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] in _ESCAPES:
            out.append(_ESCAPES[s[i + 1]])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _prepare_text(value: str, raw: bool) -> str:
    """Apply escape interpretation unless --raw was passed."""
    if raw:
        return value
    return _unescape(value)


def _location(index: int, tab_id: str | None) -> dict:
    loc: dict = {"index": index}
    if tab_id:
        loc["tabId"] = tab_id
    return loc


def _range(start: int, end: int, tab_id: str | None) -> dict:
    r: dict = {"startIndex": start, "endIndex": end}
    if tab_id:
        r["tabId"] = tab_id
    return r


def _load_tab_text(doc_id: str, tab_id: str | None) -> docs_mod.DocText:
    """Fetch the doc and extract text for the requested tab (or body if None)."""
    include_tabs = tab_id is not None
    doc = gws.get_document(doc_id, include_tabs=include_tabs)
    if tab_id is not None:
        return docs_mod.extract_text(doc, tab_id=tab_id)
    return docs_mod.extract_text(doc, tab_id=None)


def _resolve_ranges(
    dt: docs_mod.DocText,
    target: str,
    occurrence: int | None,
    all_matches: bool,
) -> list[tuple[int, int]]:
    if all_matches:
        ranges = docs_mod.find_ranges(dt, target)
        if not ranges:
            raise ValueError(f"Target text not found: {target!r}")
        return ranges
    return [docs_mod.pick_range(dt, target, occurrence=occurrence)]


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_read(args: argparse.Namespace) -> int:
    if args.all_tabs:
        doc = gws.get_document(args.doc_id, include_tabs=True)
        tabs = docs_mod.list_tabs(doc)
        if not tabs:
            dt = docs_mod.extract_text(doc, tab_id=None)
            sys.stdout.write(dt.text)
            if not dt.text.endswith("\n"):
                sys.stdout.write("\n")
            return 0
        for i, t in enumerate(tabs):
            dt = docs_mod.extract_text(doc, tab_id=t.tab_id)
            indent = "  " * t.depth
            header = f"===== Tab: {indent}{t.title or '(untitled)'} [{t.tab_id}] ====="
            if i > 0:
                sys.stdout.write("\n")
            sys.stdout.write(header + "\n")
            sys.stdout.write(dt.text)
            if not dt.text.endswith("\n"):
                sys.stdout.write("\n")
        return 0

    dt = _load_tab_text(args.doc_id, args.tab)
    sys.stdout.write(dt.text)
    if not dt.text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_tabs(args: argparse.Namespace) -> int:
    doc = gws.get_document(args.doc_id, include_tabs=True)
    tabs = docs_mod.list_tabs(doc)
    if not tabs:
        print("(document has no tabs; it is a single-body document)")
        return 0
    for t in tabs:
        indent = "  " * t.depth
        print(f"{t.tab_id}\t{indent}{t.title or '(untitled)'}")
    return 0


def cmd_replace(args: argparse.Namespace) -> int:
    args.old = _prepare_text(args.old, args.raw)
    args.new = _prepare_text(args.new, args.raw)
    dt = _load_tab_text(args.doc_id, args.tab)
    ranges = _resolve_ranges(dt, args.old, args.occurrence, args.all)

    style_spec = build_text_style(args)
    requests: list[dict] = []
    # Process from the end of the document backwards so earlier indices stay valid.
    for start, end in sorted(ranges, reverse=True):
        requests.append(
            {"deleteContentRange": {"range": _range(start, end, args.tab)}}
        )
        if args.new:
            requests.append(
                {"insertText": {"location": _location(start, args.tab), "text": args.new}}
            )
            if style_spec is not None:
                style, fields = style_spec
                requests.append(
                    update_text_style_request(
                        style, fields, start, start + len(args.new), args.tab
                    )
                )

    gws.batch_update(args.doc_id, requests, dry_run=args.dry_run)
    action = "Would replace" if args.dry_run else "Replaced"
    print(f"{action} {len(ranges)} occurrence(s) of {args.old!r}.")
    return 0


def cmd_insert(args: argparse.Namespace) -> int:
    if bool(args.after) == bool(args.before):
        print("error: exactly one of --after or --before is required", file=sys.stderr)
        return 2

    anchor_is_after = args.after is not None
    anchor_raw: str = args.after if anchor_is_after else args.before
    anchor = _prepare_text(anchor_raw, args.raw)
    args.text = _prepare_text(args.text, args.raw)
    dt = _load_tab_text(args.doc_id, args.tab)
    ranges = _resolve_ranges(dt, anchor, args.occurrence, all_matches=False)
    start, end = ranges[0]
    index = end if anchor_is_after else start

    style_spec = build_text_style(args)
    requests: list[dict] = [
        {"insertText": {"location": _location(index, args.tab), "text": args.text}}
    ]
    if style_spec is not None:
        style, fields = style_spec
        requests.append(
            update_text_style_request(
                style, fields, index, index + len(args.text), args.tab
            )
        )

    gws.batch_update(args.doc_id, requests, dry_run=args.dry_run)
    where = "after" if anchor_is_after else "before"
    action = "Would insert" if args.dry_run else "Inserted"
    print(f"{action} {len(args.text)} chars at index {index} ({where} anchor).")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    args.text = _prepare_text(args.text, args.raw)
    dt = _load_tab_text(args.doc_id, args.tab)
    # Google Docs body always ends with a trailing newline; insert just before it.
    index = max(1, dt.body_end - 1)

    style_spec = build_text_style(args)
    requests: list[dict] = [
        {"insertText": {"location": _location(index, args.tab), "text": args.text}}
    ]
    if style_spec is not None:
        style, fields = style_spec
        requests.append(
            update_text_style_request(
                style, fields, index, index + len(args.text), args.tab
            )
        )

    gws.batch_update(args.doc_id, requests, dry_run=args.dry_run)
    action = "Would append" if args.dry_run else "Appended"
    print(f"{action} {len(args.text)} chars at index {index}.")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    args.text = _prepare_text(args.text, args.raw)
    dt = _load_tab_text(args.doc_id, args.tab)
    ranges = _resolve_ranges(dt, args.text, args.occurrence, args.all)

    requests = [
        {"deleteContentRange": {"range": _range(start, end, args.tab)}}
        for start, end in sorted(ranges, reverse=True)
    ]

    gws.batch_update(args.doc_id, requests, dry_run=args.dry_run)
    action = "Would delete" if args.dry_run else "Deleted"
    print(f"{action} {len(ranges)} occurrence(s) of {args.text!r}.")
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    args.text = _prepare_text(args.text, args.raw)
    dt = _load_tab_text(args.doc_id, args.tab)
    ranges = _resolve_ranges(dt, args.text, args.occurrence, args.all)

    style_spec = build_text_style(args)
    if style_spec is None:
        print("error: at least one style flag is required "
              "(--bold, --italic, --underline, --strikethrough, --link)", file=sys.stderr)
        return 2

    style, fields = style_spec
    requests = [
        update_text_style_request(style, fields, start, end, args.tab)
        for start, end in sorted(ranges, reverse=True)
    ]

    gws.batch_update(args.doc_id, requests, dry_run=args.dry_run)
    action = "Would style" if args.dry_run else "Styled"
    print(f"{action} {len(ranges)} occurrence(s) of {args.text!r} with [{fields}].")
    return 0


# ---------------------------------------------------------------------------
# Parser wiring
# ---------------------------------------------------------------------------

def _add_common_edit_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tab", metavar="TAB_ID", help="Operate on a specific tab (see `gdocs tabs`).")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the batchUpdate request that would be sent, without sending it.")
    p.add_argument("--raw", action="store_true",
                   help=r"Do not interpret \n, \t, \r, \\ escapes in text arguments.")


def _add_match_flags(p: argparse.ArgumentParser, allow_all: bool) -> None:
    p.add_argument("-n", "--occurrence", type=int, metavar="N",
                   help="Pick the Nth occurrence of the target (1-indexed).")
    if allow_all:
        p.add_argument("--all", action="store_true",
                       help="Apply to every occurrence of the target.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gdocs",
        description="Edit Google Docs via the Google Workspace CLI (gws).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="Print the full plain text content of a doc.")
    p_read.add_argument("doc_id")
    p_read.add_argument("--tab", metavar="TAB_ID",
                        help="Read only the named tab (see `gdocs tabs`).")
    p_read.add_argument("--all-tabs", action="store_true",
                        help="Read every tab, with headers between them.")
    p_read.set_defaults(func=cmd_read)

    p_tabs = sub.add_parser("tabs", help="List tabs in a multi-tab document.")
    p_tabs.add_argument("doc_id")
    p_tabs.set_defaults(func=cmd_tabs)

    p_replace = sub.add_parser("replace", help="Find-and-replace exact text.")
    p_replace.add_argument("doc_id")
    p_replace.add_argument("--old", required=True, help="Exact text to find.")
    p_replace.add_argument("--new", required=True, help="Replacement text (may be empty).")
    _add_match_flags(p_replace, allow_all=True)
    _add_common_edit_flags(p_replace)
    add_style_flags(p_replace)
    p_replace.set_defaults(func=cmd_replace)

    p_insert = sub.add_parser("insert", help="Insert text before or after a unique anchor.")
    p_insert.add_argument("doc_id")
    group = p_insert.add_mutually_exclusive_group(required=True)
    group.add_argument("--after", help="Anchor text; insert immediately after its last character.")
    group.add_argument("--before", help="Anchor text; insert immediately before its first character.")
    p_insert.add_argument("--text", required=True, help="Text to insert.")
    _add_match_flags(p_insert, allow_all=False)
    _add_common_edit_flags(p_insert)
    add_style_flags(p_insert)
    p_insert.set_defaults(func=cmd_insert)

    p_append = sub.add_parser("append", help="Append text to the end of the doc.")
    p_append.add_argument("doc_id")
    p_append.add_argument("--text", required=True, help="Text to append.")
    _add_common_edit_flags(p_append)
    add_style_flags(p_append)
    p_append.set_defaults(func=cmd_append)

    p_delete = sub.add_parser("delete", help="Delete exact text.")
    p_delete.add_argument("doc_id")
    p_delete.add_argument("--text", required=True, help="Exact text to delete.")
    _add_match_flags(p_delete, allow_all=True)
    _add_common_edit_flags(p_delete)
    p_delete.set_defaults(func=cmd_delete)

    p_style = sub.add_parser(
        "style",
        help="Apply text style (bold/italic/underline/strikethrough/link) to matched text.",
    )
    p_style.add_argument("doc_id")
    p_style.add_argument("--text", required=True, help="Exact text to restyle.")
    _add_match_flags(p_style, allow_all=True)
    _add_common_edit_flags(p_style)
    add_style_flags(p_style)
    p_style.set_defaults(func=cmd_style)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except gws.GwsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
