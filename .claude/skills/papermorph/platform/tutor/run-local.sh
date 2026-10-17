#!/usr/bin/env bash
# Run the platform locally exactly like the hosted one: login, per-user data, Settings, permissions.
# Serves the whole site (site/) and the API on http://localhost:8765. Data: tools/tutor/data/app.db (gitignored).
# While building chapters you can use a plain, login-free dev server instead: python3 SKILL/scripts/serve.py 8766 site
cd "$(dirname "$0")"
export TUTOR_AUTH=on TUTOR_PORT="${TUTOR_PORT:-8765}"
exec uv run server.py
