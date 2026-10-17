# Learning platform

An optional layer around a finished (or in-progress) book: per-user login, an AI tutor next to every lesson, daily goals and streaks, review cards, a
mastery map, runnable Python cells, local diagrams, and a multi-language interface. Everything lives in `SKILL/platform/` and is installed into the
project by `scripts/platform_install.py`; the book itself is untouched except for a few `<script>` tags.

## Install

```sh
python3 SKILL/scripts/platform_install.py <book>      # from the project root; safe to re-run
tools/tutor/run-local.sh                              # the book + API on http://localhost:8765 with login
uv run tools/tutor/users.py add you --name "You" --allow run
```

It copies `lang.js tutor.js tutor.css learn.js learn.css draw.js` (+ `es.js` for Spanish books) into `site/<book>/lib/`, the server into
`tools/tutor/`, creates `books/<book>/tutor.md` and `books/<book>/sources/` if missing, adds the private runtime folders to `.gitignore`, wires the cover
and every chapter page (`lang.js` before the engine, `tutor.js` after the timings script) and builds the tutor packs. New chapters:
`uv run tools/tutor/wire_chapter.py <book> chNN` (the installer's wiring, one chapter).
Python cells need a small environment once: `uv venv tools/tutor/.runner-venv && uv pip install --python tools/tutor/.runner-venv/bin/python numpy matplotlib sympy`.

## What the book must provide (the tutor is only as good as these)

- `books/<book>/style.json` → `book.title`, `book.language` (narration language code), `book.readers` (who the learner is; drives the tutor's level).
- `books/<book>/chapters/chNN.md` with a beat table (`| id | seconds | what changes | marks |`), `## Glossary` (a two-column table), and
  `## Notes for the tutor` (dense facts the narration does not say: definitions, formulas with a one-line reading, worked examples with numbers,
  misconceptions, links to practice, source citations like `slug p61`). Beat ids are stable, ASCII and meaningful: scene links, mastery and quizzes key on them.
- `content/<book>/chNN/narration.<lang>.json` and `.timings.json` (made by `tts.py`): the tutor reads what each scene says and when.
- `books/<book>/sources/*.txt|md`: private source text. Page markers `=== [p61] ===` make citations exact (`hundt p61`); files without markers are
  chunked by size. Never copy sources into `site/` (only `site/` is delivered). `tutor.md` (optional): subject conventions, notation, how to explain,
  what to keep out of answers; it is appended to the tutor's prompt.

## What the learner gets

- **Tutor panel** (button, bottom right): streams answers in the language of the question (switch mid-conversation), knows the scene, second and caption on
  screen, pauses the lesson, searches the sources and cites them, remembers the conversation per chapter. Quick buttons (simpler, example, diagram, apply it,
  quiz, "you explain"), level dial (plain / detailed / expert), model choice (fast / normal / deep), voice input and optional read-aloud, notes with
  Markdown export, scene-jump links (`[text](scene:ID@SECONDS)`), clickable quizzes with scoring, Feynman mode (the learner explains, the tutor grades 1-5),
  a study guide (Markdown or print-to-PDF with summary, glossary, notes, missed cards, weak scenes).
- **Drawing blocks the tutor can use** (all rendered locally, no network, nothing executed from model output): `flow` (layered flowcharts, the default instead of
  mermaid), `plot` (function graphs through a safe expression parser, no `eval`), `graph` (node-link), `svg` (sanitized: allow-listed tags and attributes, no
  scripts, handlers, images, foreign objects or external references), `chart` (bar/line), `mermaid` (only for sequence/class/state/gantt; loaded from a CDN,
  needs internet; vendor it yourself for offline use), and `python run` cells (matplotlib figures are captured).
- **Progress layer**: daily goals (watch / review / practice; any one keeps the streak, all three is a full day), streak with freeze days, XP, levels, badges,
  SM-2 review cards (from quizzes and generated per chapter), mastery map per scene (watching, card strength, asks and rewinds), stuck detector
  (offers another explanation after repeated rewinds or questions). Visual only; no sound.
- **Accounts** (hosted/login mode): each user's progress, notes, chats and preferences live on the server and follow them across devices; each user saves their own
  Claude API URL and key (and optional model names) in Settings; keys are Fernet-encrypted at rest and never sent back to the browser. Permissions are set by the
  admin only (`users.py perms <user> run`): `run` = Python cells. Locally without login (`tools/tutor/server.py` on :8780 with `ANTHROPIC_AUTH_TOKEN`), everything is allowed.

## How it fits together

`lang.js` runs first on every page: interface language, and in login mode it pulls the user's stored data into `localStorage` (one synchronous request) and mirrors
later changes to the synced keys back to the server, so the engine, tutor and learning code just use `localStorage`. First login in a browser adopts what is already
there (keys the server lacks are uploaded; for learning state the newer copy wins); a different account in the same browser clears the previous user's keys.
`tutor.js` loads `learn.js` and `draw.js`. The server (`tools/tutor/server.py`, FastAPI) serves the site and `/chat` (SSE, tool use: `search_sources`, `read_source`,
prompt caching), `/cards`, `/guide`, `/run`, `/api/*`. Data: `tools/tutor/data/app.db` (SQLite) + `secret.key`, snapshotted into `data/backups/` at every start.
Bump `EPOCH` in `lang.js` to reset everyone's learning data on next load.

## Security notes

Python cells run as the server's user (CPU limit, timeout, one at a time, fresh temp dir): grant `run` only to people you trust with the server, or run the server in a
container with nothing else in reach (see [deploy.md](deploy.md)), or set `TUTOR_RUNNER=off`. Login is throttled per IP, sessions are signed cookies, mutating requests
must be same-origin. Nothing private is ever served as a file (`site/` only). The tutor quotes short excerpts of your sources: check their licence before sharing a deployment.

## Known limits

Interface text is bilingual (Spanish/English) out of the box; more languages through `UI_STRINGS` ([i18n.md](i18n.md)). Inserted chapters (ids like `ch24b`) are supported by the
tutor, learning layer and packs; `register.py` does not insert them into the contents (edit by hand). Cards, guides and answers depend on the model you configure.
