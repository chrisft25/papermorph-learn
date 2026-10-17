# Content task — one chapter

You are the content worker for chapter NN of the Papermorph book <book>. Read `books/<book>/worker-brief.md` first and follow it; then `style.json`, the curriculum (teaching approach + your chapter's row, and the rows just before and after so you know what is assumed and what comes next), the approved reference chapter (`chapters/<chNN>.md` + its narration), and the notes of the chapters already written (skim their "Notes for the tutor" and glossary to stay consistent and avoid re-teaching). Find exact source pages with grep (page markers `=== [pN] ===`).

Deliver (content only; another worker builds the page):
1. `books/<book>/chapters/chNN.md` with every section of the reference chapter (heading `## Glossary` exactly), `## Notes for the tutor`, and `## Storyboard plan`: per beat 1-3 key frames described precisely (elements, positions on the 1600x900 stage, colours by meaning, what moves on which `[[mark]]`), checks as on-picture interactions with verified answers, one build exercise, practice questions, fixed sample data for anything random. Prefer existing library elements; list genuinely new ones.
2. `content/<book>/chNN/narration.<lang>.json` (written for the ear, `[[marks]]`, `say` respellings only if the language needs them), then the audio with `tts.py`. Target the book's chapter length including checks. Beat ids final, ASCII, meaningful.

Decide small open questions yourself and record them under "Errata / notes"; escalate only what changes the book's direction. Reply in at most 10 lines: files, narration duration, new respellings, new library elements needed, decisions taken, escalations.
