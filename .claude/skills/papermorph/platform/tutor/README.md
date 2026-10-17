# tools/tutor — the learning platform server

Installed by `SKILL/scripts/platform_install.py <book>`; see `SKILL/references/platform.md` (what it does), `deploy.md` (running and hosting it) and `i18n.md` (languages).

```sh
tools/tutor/run-local.sh                                   # whole site + API with login on http://localhost:8765
uv run tools/tutor/users.py add you --name "You" --allow run
uv run tools/tutor/users.py list | passwd | perms | remove [--purge-data] | backup | import-local <user>
uv run tools/tutor/packs.py <book> --all                   # rebuild tutor packs (also rebuilt automatically when a chapter's files change)
uv run tools/tutor/wire_chapter.py <book> chNN             # add the platform scripts to a chapter page
```

Files: `server.py` (FastAPI: site, `/chat` SSE with tool use and prompt caching, `/cards`, `/guide`, `/run`, `/api/*`), `auth.py` (users, sessions, per-user storage, encrypted
per-user settings), `runner.py` (Python code cells), `tools.py` (BM25 source search), `packs.py` (chapter packs from narration, timings, chapter notes, glossary), `users.py`, `wire_chapter.py`, `deploy/`.
Data lives in `data/` (private, gitignored): `app.db`, `secret.key`, `backups/`, guide caches. Local single-user mode without login: `ANTHROPIC_AUTH_TOKEN=... uv run tools/tutor/server.py` (port 8780, for the login-free dev server).
