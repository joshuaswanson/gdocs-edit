# gdocs-edit

A tiny CLI for reading and editing Google Docs from the terminal.

`gdocs` wraps the [Google Workspace CLI](https://github.com/googleworkspace/google-workspace-cli) (`gws`), so it reuses the OAuth setup you already have and adds no extra credentials of its own. Commands like find-and-replace, insert-before, insert-after, append, and delete are expressed in terms of text you can see, not opaque document indices.

## Why

The Google Docs API speaks in absolute character indices: to replace a sentence you need its `startIndex` and `endIndex`. That is tedious to do by hand, and wrong-by-one if you do it wrong. `gdocs` does the index math for you: you give it the exact text to find, and it finds the range and builds the right `batchUpdate` request.

## Install

Requires Python 3.10+ and the `gws` CLI already authenticated.

```bash
# 1. Install gws and log in once (see https://github.com/googleworkspace/google-workspace-cli)
brew install google-workspace-cli   # or follow the gws README
gws auth login

# 2. Install gdocs
git clone https://github.com/joshuaswanson/gdocs-edit.git
cd gdocs-edit
uv tool install .
```

`gdocs` is then available on your `PATH`.

## Commands

Every command takes a document ID as its first positional argument. You can get the ID from a Doc URL: `https://docs.google.com/document/d/<DOC_ID>/edit`.

### `gdocs read <doc_id>`

Print the full plain-text content of the doc to stdout. Walks paragraphs and table cells and concatenates every `textRun`.

```bash
gdocs read 1aUD7m9LSMWRPhEEWDje-CHd6VfcKmleOJzJ3FjhfbQg
```

### `gdocs replace <doc_id> --old ... --new ...`

Find the exact string `--old` in the document and replace it with `--new`. The old text must appear **exactly once**, otherwise the command aborts and nothing is modified.

```bash
gdocs replace $DOC --old "TODO: write intro" --new "The intro goes here."
```

Pass an empty `--new` to delete; or just use `gdocs delete`.

### `gdocs insert <doc_id> --after ... --text ...`

### `gdocs insert <doc_id> --before ... --text ...`

Insert `--text` immediately before or after a unique anchor string.

```bash
gdocs insert $DOC --after "Dear reviewer," --text " thank you for your time."
gdocs insert $DOC --before "## Appendix"    --text "## Conclusion\n\nThe end.\n\n"
```

`--after` and `--before` are mutually exclusive. The anchor must occur exactly once.

### `gdocs append <doc_id> --text ...`

Append text to the end of the document (inserted just before the body's trailing newline, so it becomes part of the content rather than orphaned after it).

```bash
gdocs append $DOC --text $'\n## Changelog\n- Initial release.\n'
```

### `gdocs delete <doc_id> --text ...`

Find the exact string `--text` and remove it. Must occur exactly once.

```bash
gdocs delete $DOC --text "DRAFT "
```

## Exit codes

- `0` on success
- `1` on runtime errors (text not found, text not unique, `gws` failure)
- `2` on argument errors

## How it works

1. Call `gws docs documents get` to fetch the document JSON.
2. Walk `body.content` (paragraphs and tables) and collect every `textRun`, building two parallel structures: a flat string of the document text, and an `index_map` where `index_map[i]` is the absolute Google Docs character index of the `i`-th character of the flat string.
3. Use Python's `str.find` to locate the target substring (enforcing uniqueness), then look up the corresponding absolute `[start, end)` range in `index_map`.
4. Send a `batchUpdate` with a `deleteContentRange`, `insertText`, or both.

Because `gdocs` shells out to `gws`, it inherits whatever auth scopes and account `gws` has. There is no separate OAuth flow, token store, or client secret to manage.

## Limitations

- Only plain-text edits. Formatting, styles, images, comments, and suggestions are read-only: `gdocs` will not preserve or author them.
- Anchor strings must be unique. If the text you want to target appears more than once, make the anchor longer until it is unambiguous.
- Tabs: `gdocs` reads from the first tab only (the legacy `body` field). Multi-tab documents work but additional tabs are ignored.
- No dry-run flag yet. Edits are applied immediately.

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
