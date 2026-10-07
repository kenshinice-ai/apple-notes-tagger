## Writing rules · STE-lite v1

Applies to: procedures, release and rollback steps, handoffs (HANDOFF, "等 Lee"), warnings, and notes for other sessions.

1. One action per step. Start with the verb. Put a condition first: "If …, do …".
2. Sentence length: at most 20 words in English, 40 characters in Chinese. Code, paths and commands do not count.
3. Give each step a success check: the expected output, status code or version. `healthy` or exit code 0 is not evidence unless the step says what it proves.
4. Write warnings as `> ⚠️`. First sentence: what to do or not do. Second: what happens if you don't. Then the reason. One hazard per warning.
5. Use active voice. Name the owner of each to-do.
6. One term, one meaning: use only the words in this repo's glossary. If a new word has two meanings, split it into two words first, then add them.
7. Date every value that can change: "measured 2026-10-03". Mark anything unchecked as "not verified" and say why. Never write a plan as done.
8. Keep steps, reasons and incident stories apart. An incident story never interrupts the steps.

Does not apply to:
- Explanations and reasons: no length limit, but lead with the conclusion.
- History logs (*-LOG.md, dated running entries): leave them as written.
- Product and brand copy in any language, App Store copy, AI prompts that visitors see.
- The format of "等 Lee" entries in handoff files: the global convention stands.
- TTS narration and voice-over scripts: never split sentences (qwen-tts measured 10 of 10 failures after splitting).
- Scripture, classical and cultural content.

Do not rewrite old docs in bulk. Tidy a section by these rules when you change it.

## Scope in this repo
- Applies to: `skills/apple-notes-tagger/SKILL.md`, `docs/ARCHITECTURE.md`.
- Does not apply to: the Chinese section of `README.md` (中文说明), and the runtime error text printed by the scripts.

## Glossary
| Use | Meaning (one only) | Not |
|---|---|---|
| real tag | The inline tag object that Notes' own parser creates. It reads as `U+FFFC` in `plaintext of note` and shows in the Tags sidebar. | tag object, inline tag |
| dead text | A `#word` that is only characters, not a real tag. It does not turn orange. | plain text (it also names `plaintext of note`), inert text |
| skip | The tool decides a note must not be touched. Logged as `SKIP`; does not count toward the five-consecutive-failures stop. | refusal, refuse (the docs also say "refuses" for `FAIL` cases) |
