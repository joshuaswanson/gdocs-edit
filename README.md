# gdocs-edit

A small CLI for reading and editing Google Docs from the terminal.

`gdocs` wraps the [Google Workspace CLI](https://github.com/googleworkspace/google-workspace-cli) (`gws`), so it reuses the OAuth setup you already have and adds no credentials of its own. Commands like find-and-replace, insert-before, insert-after, append, delete, and style are expressed in terms of text you can see, not opaque document indices.

## Why

The Google Docs API speaks in absolute character indices: to replace a sentence you need its `startIndex` and `endIndex`. Computing those by hand is tedious and easy to get wrong by one. `gdocs` does the index math for you. You give it the exact text to find, and it finds the range and builds the right `batchUpdate` request.

## Install

Requires Python 3.10+ and the `gws` CLI already authenticated.

```bash
# 1. Install gws and log in once.
#    https://github.com/googleworkspace/google-workspace-cli
gws auth login

# 2. Install gdocs.
git clone https://github.com/joshuaswanson/gdocs-edit.git
cd gdocs-edit
uv tool install .
```

`gdocs` is then available on your `PATH`.

## Quick reference

| Command                                | What it does                      |
| -------------------------------------- | --------------------------------- |
| `gdocs read DOC`                       | Print the plain text content      |
| `gdocs tabs DOC`                       | List tabs in a multi-tab document |
| `gdocs replace DOC --old X --new Y`    | Find-and-replace                  |
| `gdocs insert DOC --after X --text Y`  | Insert `Y` after anchor `X`       |
| `gdocs insert DOC --before X --text Y` | Insert `Y` before anchor `X`      |
| `gdocs append DOC --text Y`            | Append to the end                 |
| `gdocs delete DOC --text X`            | Delete exact text                 |
| `gdocs style DOC --text X --bold`      | Restyle existing text             |

## Selecting which match to target

For `replace`, `insert`, `delete`, and `style`, the target text must be unique by default. If it appears more than once, pick one of:

- `-n N` / `--occurrence N` to target the Nth match (1-indexed).
- `--all` (on `replace`, `delete`, `style`) to apply the edit to every occurrence.

```bash
# Replace only the second "TODO" in the document.
gdocs replace $DOC --old "TODO" --new "Done" --occurrence 2

# Delete every occurrence.
gdocs delete $DOC --text "DRAFT " --all
```

When `--all` edits multiple ranges, `gdocs` sorts them back-to-front before sending so the indices remain valid within the single atomic `batchUpdate`.

## Working with tabs

Multi-tab documents are fully supported. List the tabs:

```bash
$ gdocs tabs $DOC
t.0     Intro
t.1     Draft
t.1.0     Appendix A
t.1.1     Appendix B
```

Then target a specific tab on any command:

```bash
gdocs read    $DOC --tab t.1
gdocs replace $DOC --tab t.1 --old "foo" --new "bar"
gdocs append  $DOC --tab t.1.0 --text "\nSee also."
```

`gdocs read --all-tabs DOC` prints every tab with a header between them.

## Formatting

`insert`, `append`, `replace` (the new text), and the dedicated `style` command accept formatting flags. Each one has a `--no-*` counterpart to explicitly clear a style:

- `--bold` / `--no-bold`
- `--italic` / `--no-italic`
- `--underline` / `--no-underline`
- `--strikethrough` / `--no-strikethrough`
- `--link URL` / `--no-link`

```bash
# Insert a bold, italicized note.
gdocs insert $DOC --after "Status:" --text " shipped" --bold --italic

# Turn every occurrence of "Google Docs API" into a link.
gdocs style $DOC --text "Google Docs API" --all \
  --link https://developers.google.com/docs/api

# Append an underlined heading.
gdocs append $DOC --text "\nChangelog\n" --underline
```

## Dry-run

Every edit command accepts `--dry-run`. It computes the full `batchUpdate` request and prints it to stdout instead of sending it. Useful for sanity-checking index math and composing complex edits in a script.

```bash
gdocs replace $DOC --old "TODO" --new "Done" --all --underline --dry-run
```

## Exit codes

- `0` on success
- `1` on runtime errors (text not found, ambiguous match, `gws` failure, tab not found)
- `2` on argument errors

## How it works

1. Call `gws docs documents get` for the doc (passing `includeTabsContent=true` when a tab is targeted).
2. Walk `body.content` (paragraphs and tables) and collect every `textRun`, building two parallel structures: a flat string of the document text, and an `index_map` where `index_map[i]` is the absolute Google Docs character index of the `i`-th flat-text character.
3. Use Python's `str.find` to locate the target substring (with support for `--occurrence` and `--all`), then look up the corresponding absolute `[start, end)` ranges in `index_map`.
4. Compose a `batchUpdate` with `deleteContentRange`, `insertText`, and/or `updateTextStyle` requests. Multi-match edits are emitted back-to-front so indices stay valid within the atomic batch. Tab-scoped edits thread `tabId` through every `location` and `range`.

Because `gdocs` shells out to `gws`, it inherits whatever auth scopes and account `gws` has. There is no separate OAuth flow, token store, or client secret to manage.

## Caveats

- `gdocs` only touches textual content and its character-level formatting. It does not author images, tables, comments, suggestions, or paragraph-level styles (headings, alignment, bullets). Existing rich content is preserved but not created or modified.
- Matching is exact-string only. There is no regex or case-insensitive mode yet; make anchors longer until they are unambiguous.

## Support

If you find this useful, [buy me a coffee](https://buymeacoffee.com/swanson).

<img src="assets/bmc_qr.png" alt="Buy Me a Coffee QR" width="200">
