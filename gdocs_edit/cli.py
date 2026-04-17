from __future__ import annotations

import argparse
import sys

from . import docs as docs_mod
from . import gws


def _load_doc_text(doc_id: str) -> tuple[dict, docs_mod.DocText]:
    doc = gws.get_document(doc_id)
    return doc, docs_mod.extract_text(doc)


def cmd_read(args: argparse.Namespace) -> int:
    _, dt = _load_doc_text(args.doc_id)
    sys.stdout.write(dt.text)
    if not dt.text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_replace(args: argparse.Namespace) -> int:
    _, dt = _load_doc_text(args.doc_id)
    start, end = docs_mod.find_unique_range(dt, args.old)

    requests = [
        {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}},
    ]
    if args.new:
        requests.append({"insertText": {"location": {"index": start}, "text": args.new}})

    gws.batch_update(args.doc_id, requests)
    print(f"Replaced {len(args.old)} chars at [{start}, {end}) with {len(args.new)} chars.")
    return 0


def cmd_insert(args: argparse.Namespace) -> int:
    if bool(args.after) == bool(args.before):
        print("error: exactly one of --after or --before is required", file=sys.stderr)
        return 2

    _, dt = _load_doc_text(args.doc_id)
    anchor = args.after if args.after is not None else args.before
    start, end = docs_mod.find_unique_range(dt, anchor)
    index = end if args.after is not None else start

    gws.batch_update(
        args.doc_id,
        [{"insertText": {"location": {"index": index}, "text": args.text}}],
    )
    where = "after" if args.after is not None else "before"
    print(f"Inserted {len(args.text)} chars at index {index} ({where} anchor).")
    return 0


def cmd_append(args: argparse.Namespace) -> int:
    _, dt = _load_doc_text(args.doc_id)
    # Google Docs body always ends with a trailing newline. Insert before it
    # so the appended text becomes part of the document content.
    index = max(1, dt.body_end - 1)
    gws.batch_update(
        args.doc_id,
        [{"insertText": {"location": {"index": index}, "text": args.text}}],
    )
    print(f"Appended {len(args.text)} chars at index {index}.")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    _, dt = _load_doc_text(args.doc_id)
    start, end = docs_mod.find_unique_range(dt, args.text)
    gws.batch_update(
        args.doc_id,
        [{"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}}],
    )
    print(f"Deleted {end - start} chars at [{start}, {end}).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gdocs",
        description="Edit Google Docs via the Google Workspace CLI (gws).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_read = sub.add_parser("read", help="Print the full plain text content of a doc.")
    p_read.add_argument("doc_id")
    p_read.set_defaults(func=cmd_read)

    p_replace = sub.add_parser("replace", help="Find-and-replace exact text (must be unique).")
    p_replace.add_argument("doc_id")
    p_replace.add_argument("--old", required=True, help="Exact text to find (must occur exactly once).")
    p_replace.add_argument("--new", required=True, help="Replacement text (may be empty).")
    p_replace.set_defaults(func=cmd_replace)

    p_insert = sub.add_parser("insert", help="Insert text before or after a unique anchor string.")
    p_insert.add_argument("doc_id")
    group = p_insert.add_mutually_exclusive_group(required=True)
    group.add_argument("--after", help="Anchor text; insert immediately after its last character.")
    group.add_argument("--before", help="Anchor text; insert immediately before its first character.")
    p_insert.add_argument("--text", required=True, help="Text to insert.")
    p_insert.set_defaults(func=cmd_insert)

    p_append = sub.add_parser("append", help="Append text to the end of the doc.")
    p_append.add_argument("doc_id")
    p_append.add_argument("--text", required=True, help="Text to append.")
    p_append.set_defaults(func=cmd_append)

    p_delete = sub.add_parser("delete", help="Delete exact text (must be unique).")
    p_delete.add_argument("doc_id")
    p_delete.add_argument("--text", required=True, help="Exact text to delete (must occur exactly once).")
    p_delete.set_defaults(func=cmd_delete)

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
