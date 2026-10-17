# Deploying the platform

## Locally, like production

```sh
tools/tutor/run-local.sh          # login, per-user data and Settings, the whole site + API on http://localhost:8765
uv run tools/tutor/users.py add you --name "You" --allow run
```
Data: `tools/tutor/data/app.db` (SQLite, private, snapshotted into `data/backups/` at every start). While building chapters use the login-free dev server instead:
`python3 SKILL/scripts/serve.py 8766 site` (it also answers HTTP Range requests, which browsers need to seek inside audio) and, if you want the tutor there,
`ANTHROPIC_AUTH_TOKEN=... uv run tools/tutor/server.py` on :8780 (no login; the pages call it cross-origin).

## Users and permissions

No registration page: you create people with `tools/tutor/users.py` (`add`, `passwd`, `perms`, `remove`, `list`, `backup`, `import-local`). `add` never overwrites an existing user; `remove` keeps the person's
data unless `--purge-data` (which backs up first). New users get no permissions; `--allow run` grants Python cells. Each user opens Settings (their name, top bar) to save their own Claude API URL and key.
Server-wide fallback (local mode only): `ANTHROPIC_AUTH_TOKEN` / `TUTOR_API_KEY`, `TUTOR_BASE_URL`.

## A small VPS

`tools/tutor/deploy/` has a Dockerfile, a compose file (app + Caddy with automatic HTTPS) and a Caddyfile.

```sh
cd tools/tutor/deploy && DOMAIN=learn.example.com docker compose up -d --build
docker compose exec app python tools/tutor/users.py add you --name "You" --allow run
```
Back up `deploy/data` (users, progress, notes, chats, encrypted keys, `secret.key`). On 512 MB - 1 GB add swap, keep `TUTOR_RUNNER_SLOTS=1`, or build with `--build-arg WITH_RUNNER=0` and set
`TUTOR_RUNNER=off` to drop the Python environment. Behind an existing reverse proxy (another Caddy/nginx), run only the app container on its network and proxy to `app:8780`; `flush_interval -1` keeps
the tutor's answers streaming. Behind Cloudflare use SSL mode Full. Environment: `TUTOR_AUTH=on`, `TUTOR_COOKIE_SECURE=1`, `TUTOR_DATA_DIR=/data`, `TUTOR_HOST`, `TUTOR_PORT`, `TUTOR_TRUSTED_PROXY`,
`TUTOR_DEFAULT_BASE` (default `https://api.anthropic.com`), `TUTOR_HOME_PATH`, `TUTOR_RUNNER`, `TUTOR_SECRET`.

## Before you share

- Python cells = code execution on the server: see [platform.md](platform.md#security-notes). Prefer `TUTOR_RUNNER=off` unless you trust the people you grant `run`.
- Source texts ship in the image (`books/*/sources/`, never served as files); the tutor quotes short excerpts. Check the licence of what you include.
- Never commit `tools/tutor/data/`, `.env.local`, `.runner-venv/`, `packs/` (the installer adds them to `.gitignore`). Change default passwords, use HTTPS.
- Updating: re-send the project (for example `git archive HEAD | ssh server 'tar -x -C /srv/app/src'`), rebuild, restart; the data folder is untouched.
