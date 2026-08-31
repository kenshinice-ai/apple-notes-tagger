# Architecture

Two layers, deliberately. AppleScript can press keys and read the accessibility
tree but is a miserable language for arithmetic; Python can do the arithmetic but
cannot touch the UI. So the AppleScript layer knows nothing about tags, and the
Python layer never presses a key it hasn't first predicted the outcome of.

```
notes_tags.py            decides WHAT to do, and verifies every result
      │  argv in, "OK<tab>caret<tab>sel\n<full note text>" out
      ▼
engine.applescript       does ONE mechanical thing per invocation
      │  System Events
      ▼
Notes.app                the only thing that can actually create a tag
```

Every engine call returns the caret offset, the selection length, and the note's
entire text. Python compares that against what it predicted. If they differ, it
undoes and refuses to continue. There is no step where the code presses a key and
hopes.

## Why a subprocess per action

One `osascript` invocation per action costs ~300 ms, which is why a note takes
~8 seconds. A long-lived process would be faster, but each invocation is also a
clean boundary: if Notes' accessibility API hangs — which it does, occasionally
and unpredictably — the Python side times out, `pkill -9 osascript`, and the run
continues at the next note. A persistent connection would have to be rebuilt
anyway, and a hang inside it would take the whole batch down.

## engine.applescript

Stateless. Each invocation re-finds the window and the text area, so nothing is
cached across a hang or a window change.

| Command | Does |
|---|---|
| `open <id>` | Show the note, focus the body, `Cmd+↓` to the end |
| `value` | Report caret + text, touching nothing |
| `elements` | List inline elements in document order as `role⇥subrole⇥description` |
| `left <n>` | Press Left n times |
| `tagseq p1 e1 p2 e2 …` | For each pair: move left `p`, **verify caret == `e`**, space, backspace |
| `back <n>` | Press Backspace n times |
| `ret` / `space` | One Return / one space |
| `addseq <tag> …` | For each tag: paste the text, then space |
| `undo <n>` | `Cmd+Z` n times |

Three rules hold across all of them:

- **Locate Notes by bundle identifier**, never by process name — `"Notes"` is
  `"备忘录"` on a Chinese system and `"Notizen"` on a German one.
- **`ensureFront()` before any key.** Focus gets stolen constantly. Rather than
  failing the batch, take it back once and re-check; if Notes still isn't front,
  return an error without pressing anything.
- **Never interpret localised strings.** `elements` hands back raw
  role/subrole/description triples and lets Python decide what they mean.

### Focusing without clicking

`set focused of <text area> to true`, not a click. Clicking into a note body can
land on an attachment and open it. The text area is found by walking the window's
three scroll areas for the one that contains a text area — not by a hard-coded
index, which changes when the sidebar is hidden.

## notes_tags.py

### The two offset systems

This is where the bugs live, so they are kept apart explicitly:

- `AXSelectedTextRange` counts **UTF-16 code units** — `📅` is 2.
- Arrow keys move by **character** — `📅` is 1 press.

`u16()` and `idx_of_u16()` convert between them, and the caret is re-read and
compared after every move. Non-BMP characters are covered by tests; RTL is not
convertible at all (below).

### Predict, act, compare

`plan_activate()` computes the whole sequence *and the exact final text* before
anything happens, walking tags right-to-left so that each `#tag` collapsing to
one character never shifts a position that hasn't been visited yet. After
`tagseq` runs, the returned text is compared to that prediction character by
character. Anything else → `Cmd+Z`, confirm the note is byte-identical to how it
started, skip it.

`add_tags()` is atomic in the same spirit: once it has modified anything, every
failure path rolls back and reports whether the restore succeeded. Without that,
a failure after the tags landed would leave them in place while the log said
`FAIL` — and a re-run would add them a second time.

### Inline elements ↔ `￼`

Both tags and attachments render as `￼` in the note text, so position alone
cannot tell them apart. `elements` returns them in document order, one per `￼`;
attachments are `AXLink`/`AXTextAttachment`, tags are `AXUnknown`. Zipping the
two lists is what lets `remove` find the right occurrence on a note that has
both. If the counts disagree, `remove` refuses rather than guessing.

### Which line is the tag line

`tagline_candidate()` looks only at the last non-empty line — or the one above it
if the last is a date line. That narrowness is deliberate: notes contain other
hashtag-only lines (pasted social-media topic tags), and an earlier, greedier
version converted one of those by accident. `--vocab` narrows it further to a
known word list; `--scan-back` widens it when tags span several lines.

### Failure vs. refusal

`Fail` means something went wrong. `Skip` means *this note should not be
touched* — an RTL tag line, a note whose element counts don't line up. Skips are
logged separately and don't count toward the five-consecutive-failures stop,
because a hundred RTL notes in a row is not a malfunction.

## Right-to-left

Arrow keys move by visual position in bidirectional text, not logical order, so
`Left × n` stops corresponding to n characters and the whole predict-then-verify
scheme loses its footing. This was found by experiment: Arabic and Hebrew tag
lines failed the caret check — correctly caught and undone, but only after keys
had been pressed. So `activate` now detects RTL characters and skips the note
before pressing anything.

`add` and `remove` are unaffected: `add` appends at the end of the document and
`remove` only walks left across text it has already verified is RTL-free.

## Verification is read-only

A real tag is `U+FFFC` in `plaintext of note` (AppleScript) and in `AXValue`;
dead text is still `#tag`. So a whole library can be audited without touching it
and **without Full Disk Access**. `NoteStore.sqlite` is never read or written —
the body is gzipped protobuf with CRDT sync encoding, no writer exists outside
Apple, and a bad write would replicate to every device.

## What is never done

- **`set body`** — rewrites the note's HTML and drops inline attachment
  references. It destroyed 94 attachments across 59 notes in the run this tool
  was built for.
- **Typing a tag's text** — `keystroke` goes through the input method, which
  turns `#旅行` into `#aa`. Tags are pasted; existing ones are never retyped.
- **Clicking into the body** — may open an attachment.
- **Pressing a key without checking the caret first.**
