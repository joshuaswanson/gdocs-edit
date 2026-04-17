"""Helpers for turning CLI style flags into Google Docs API textStyle updates."""
from __future__ import annotations

import argparse


STYLE_FIELDS = ["bold", "italic", "underline", "strikethrough", "link"]


def add_style_flags(parser: argparse.ArgumentParser) -> None:
    """Attach --bold/--no-bold, --italic, --underline, --strikethrough, --link/--no-link."""
    for name in ("bold", "italic", "underline", "strikethrough"):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            f"--{name}",
            dest=name,
            action="store_const",
            const=True,
            help=f"Apply {name} to the affected range.",
        )
        group.add_argument(
            f"--no-{name}",
            dest=name,
            action="store_const",
            const=False,
            help=f"Clear {name} on the affected range.",
        )
        parser.set_defaults(**{name: None})

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--link",
        dest="link",
        metavar="URL",
        help="Turn the affected range into a hyperlink pointing at URL.",
    )
    group.add_argument(
        "--no-link",
        dest="link",
        action="store_const",
        const="",
        help="Clear any hyperlink on the affected range.",
    )
    parser.set_defaults(link=None)


def build_text_style(args: argparse.Namespace) -> tuple[dict, str] | None:
    """Return (textStyle, fields_mask) for the Docs API, or None if no style flags were set.

    The fields mask is a comma-separated list of textStyle keys the request should touch.
    """
    style: dict = {}
    fields: list[str] = []

    for name in ("bold", "italic", "underline", "strikethrough"):
        val = getattr(args, name, None)
        if val is not None:
            style[name] = val
            fields.append(name)

    link = getattr(args, "link", None)
    if link is not None:
        if link == "":
            style["link"] = {}  # clearing: empty link object + link in fields mask
        else:
            style["link"] = {"url": link}
        fields.append("link")

    if not fields:
        return None
    return style, ",".join(fields)


def update_text_style_request(
    style: dict,
    fields: str,
    start: int,
    end: int,
    tab_id: str | None,
) -> dict:
    """Build an updateTextStyle batchUpdate request for the given absolute range."""
    range_obj: dict = {"startIndex": start, "endIndex": end}
    if tab_id:
        range_obj["tabId"] = tab_id
    return {
        "updateTextStyle": {
            "range": range_obj,
            "textStyle": style,
            "fields": fields,
        }
    }
