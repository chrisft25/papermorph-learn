# Worker brief — <book>

Read this first, then `books/<book>/style.json` (whole file) and the Papermorph Skill (`SKILL/SKILL.md`, then only the references your step needs). Project root: `<ROOT>`.

## The book
- Language: `<lang>`. Readers: <who they are, what they know, what they need>. <One line on the teaching approach>.
- Curriculum and per-chapter sources: `books/<book>/curriculum.md`. Source text: `books/<book>/sources/*.txt` (page markers `=== [pN] ===`; grep ranges, never cat whole files). Re-create explanations; never copy text.
- Approved reference chapter: **<chNN>**: read `books/<book>/chapters/<chNN>.md`, `content/<book>/<chNN>/narration.<lang>.json` and `site/<book>/<chNN>/index.html`; match its look, pacing, checks and tone.

## Rules
<!-- Subject rules that cost a revision go here: notation, terms, version flags, pronunciation (only if the narration language needs respellings), what must not be shown. Keep each to one line with its why. -->
- **Terms:** <first mention convention, glossary per chapter>.
- **Browsers MUTED** in every Playwright run (`--mute-audio`, Firefox `media.volume_scale=0.0`): audio must never reach the user's speakers.
- Use the book library `site/<book>/lib/`; do not edit `engine.js`, `book.css`, `lang.js`, `tutor.*`, `learn.*`, `draw.js`: report needs instead.
- Do not edit the contents (`index.html`), `chapters.md`, `style.json` or other chapters: the coordinator registers.
- **Open questions log:** append every unconfirmed behaviour, possible bug or thing you could not determine to `books/<book>/open-questions.md` (format in that file).

## Per-chapter deliverables
1. `books/<book>/chapters/chNN.md`: scope and sources (`slug pN`), beats with trigger words, checks/build/practice with verified answers, glossary (`## Glossary` exactly), `## Notes for the tutor`, storyboard plan, errata.
2. `content/<book>/chNN/narration.<lang>.json`, audio via `uv run --with edge-tts SKILL/scripts/tts.py content/<book>/chNN/narration.<lang>.json site/<book>/chNN/audio/<lang>`.
3. `site/<book>/chNN/index.html`: reference structure; wire the platform with `uv run tools/tutor/wire_chapter.py <book> chNN`. Beat ids stable and meaningful.
4. Review: storyboard sheet and strips in `books/<book>/review/chNN/`; e2e test `tools/<book>/e2e_chNN.py`; delivery pass per `review.md` in Chromium and Firefox; leftovers in both modes.

## Model split (coordinator assigns)
Strongest model = content (chNN.md, narration, audio, storyboard plan). Coding model = page implementation, motion, delivery pass. Small model = mechanical checks, strips, tutor pack, registration. At most two chapters in flight.
