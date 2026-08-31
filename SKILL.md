---
name: apple-notes-tagger
description: Create, repair, list, and remove real Apple Notes hashtag tags on macOS — the inline tag objects that appear in the Tags sidebar and drive Smart Folders. Use when the user wants to tag notes in Apple Notes, bulk-tag or auto-tag a Notes library, fix hashtags that are stuck as plain text (typed by a script, pasted, or written via `set body`) and do not turn orange, add tags to many notes at once, remove a tag from notes, or organise Apple Notes with tags and Smart Folders. Also use when AppleScript `set body` produced dead-text hashtags, or when non-ASCII (Chinese, Japanese, Korean, emoji) tags need to be created programmatically.
---

# Apple Notes Tagger

Apple Notes hashtags are **not text**. Each one is an inline object
(`com.apple.notes.inlinetextattachment.hashtag`) that only the editor's own input
parser can create. So the obvious automation routes all fail:

| Approach | Result |
|---|---|
| `set body of note to "…#tag…"` | Plain text. **Also destroys existing attachments** — never use it. |
| Paste a whole line containing `#tag ` | Plain text. Pasting does not trigger the parser. |
| `keystroke "#tag "` | Real tag ✅ — but the input method eats non-ASCII (`#旅行` → `#aa`). |

The working method, and the whole point of this skill:

**Activate existing text** — put the caret immediately after the tag's last
character, type one space (the parser fires), then backspace (removes the space).
Net edit: zero characters. Nothing is retyped, so Chinese/Japanese/Korean tags survive.

**Add a new tag** — paste the tag text (clipboard bypasses the input method),
then type one space to trigger the parser.

## Before doing anything

1. **macOS only**, and the Notes app must be running.
2. Permissions needed — both are usually already granted if the user has scripted
   Notes before; nothing else is required:
   - **Automation → Notes** (Apple Events). Test: `osascript -e 'tell application "Notes" to count notes'`
   - **Accessibility** for the process running the scripts (this is what allows
     synthetic keystrokes and AX reads).
   - **Full Disk Access is NOT needed.** Never read or write `NoteStore.sqlite`;
     the body is gzipped protobuf with CRDT sync encoding, and a bad write
     propagates to every device.
3. **Back up first**: `python3 scripts/notes_tags.py scan --out backup-before.txt`
   dumps every note's full plaintext, id, folder, creation date and attachment
   count. Read-only.
4. Tell the user the machine is unusable while a batch runs — Notes must stay
   frontmost and they must not touch the keyboard or mouse. Roughly **8 seconds
   per note**. Suggest `caffeinate -dis` in front of the command so the display
   never sleeps mid-run.

## Verifying — no special permissions needed

A real tag shows up as **U+FFFC (`￼`)** in both `plaintext of note` (AppleScript)
and the accessibility `AXValue`. Dead text still reads as `#tag`. That gives a
read-only ground truth for any check, before or after. Tag *names* are readable
too: each inline tag exposes `AXDescription = "Tag <name>"`, in document order.

Caveat: **attachments also render as `￼`**. When counting tags, subtract
`count of attachments of note`.

## Commands

All of these live in `scripts/notes_tags.py` (it drives `scripts/engine.applescript`).

```bash
# Read-only inventory: real-tag counts, and which notes still have dead-text tag lines
python3 scripts/notes_tags.py scan --out notes-scan.txt --dead-ids dead.ids

# List the real tag names on one note
python3 scripts/notes_tags.py tags --id "x-coredata://…/ICNote/p123"

# Repair: turn dead-text tag lines into real tags, in place
python3 scripts/notes_tags.py activate --ids dead.ids --vocab tags.txt

# Add tags to the end of each note (Chinese works — it pastes rather than types)
python3 scripts/notes_tags.py add --ids some.ids --tags "#travel,#旅行"

# Remove specific tags
python3 scripts/notes_tags.py remove --ids some.ids --tags "#draft"
```

`--vocab` is a file of allowed tag words, one per line. **Pass it whenever the
notes might contain other hashtag-only lines in the body** (social-media topic
tags such as `#二手闲置[话题]#`), otherwise those get converted too. Without a
vocab the tool only considers the last non-empty line (or the line above it if
the last one is a date line).

## Auto-tagging a library

The skill supplies the mechanics; **you supply the judgment**. Three steps:

```bash
# 1. Export the notes that have no tags yet, as JSONL
python3 scripts/notes_tags.py export --out to-tag.jsonl
```

Read `to-tag.jsonl` (one object per line: `id`, `folder`, `title`, `text`) and
decide the tags. Then write a plain assignment table — one line per note,
note id, a TAB, then the tags:

```
x-coredata://…/ICNote/p123	#travel #旅行
x-coredata://…/ICNote/p124	#money #财务 #ref
```

```bash
# 2. Check what would happen
python3 scripts/notes_tags.py apply --map tags.tsv --dry-run
# 3. Apply
caffeinate -dis python3 scripts/notes_tags.py apply --map tags.tsv
```

**Privacy — raise this with the user before exporting.** Classification means
note content goes to the model. `export` skips notes that look like they hold
credentials (API keys, BSB/IBAN/SWIFT, card numbers, TFN, password/密码), and
skips notes that already have tags, but the heuristic is not a guarantee. Offer
`--exclude-folder` for anything sensitive, and let the user look at
`to-tag.jsonl` before you read it. `--include-sensitive` overrides the skip —
only use it if the user explicitly asks.

## Safety rules

1. **Never `set body`.** It rewrites the note's HTML and drops inline attachment
   references — it has destroyed 94 attachments in one run in the field.
2. **Never keystroke without verifying the caret first.** Every action in
   `engine.applescript` reads `AXSelectedTextRange` and refuses to type if the
   offset is not exactly what was predicted.
3. Every note is verified character-by-character against a precomputed expected
   body. On any mismatch the script sends Cmd+Z, confirms the note is fully
   restored, and skips it. Five consecutive failures stop the run.
4. `engine.applescript` checks that Notes is the frontmost process before every
   keystroke, so a stray keypress can never land in another app.
5. Work in batches and verify with `scan` between them. Resume is built in —
   `<log>.done` records completed note ids, so re-running skips them.
6. **Modification dates get bumped** to today for every note touched. If the
   user cares about them, capture them first (`scan` records them) and, if they
   want them visible, write them into the body as text — the property is
   read-only.

## Gotchas that will bite you

- **AX offsets are UTF-16** (an emoji counts 2); **arrow keys move by character**
  (an emoji is 1 press). Keep the two counts separate, and verify the resulting
  offset after every move.
- `AXFocusedUIElement` on Notes occasionally hangs. Wrap every `osascript` call
  in a timeout and `pkill -9 osascript` on expiry — `notes_tags.py` does.
- Don't click into the body to focus it; you may open an attachment. Use
  `set focused of <text area> to true`.
- Note ids can go stale after an iCloud sync. Re-run `scan` if a batch starts
  failing on `show note id`.
- Converting tags right-to-left along a line keeps earlier offsets stable —
  each `#tag` collapses to one character, which shifts everything after it.
