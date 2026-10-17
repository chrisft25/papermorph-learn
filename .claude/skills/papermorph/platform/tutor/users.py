"""Manage tutor users (hosted mode).

    uv run tools/tutor/users.py add ana --name "Ana García" [--allow run]   # prompts for a password
    uv run tools/tutor/users.py passwd ana
    uv run tools/tutor/users.py perms ana run           # run = Python code cells · "none" = no permissions
    uv run tools/tutor/users.py remove ana [--purge-data]   # removes the login; progress/notes/settings are KEPT unless --purge-data
    uv run tools/tutor/users.py list
    uv run tools/tutor/users.py import-local ana [--force]   # copy THIS machine's local progress (data/<book>.json) into ana's account
    uv run tools/tutor/users.py backup                  # snapshot of data/app.db into data/backups/ (also done at every server start)

New users can NOT run code by default; you grant it per person with --allow / perms.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["cryptography"]
# ///
import getpass, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import auth

a = sys.argv[1:]
if not a or a[0] not in ("add", "passwd", "perms", "remove", "list", "backup", "import-local"):
    sys.exit(__doc__)
if a[0] == "list":
    for n, d, t, p in auth.list_users():
        print(f"{n:20} {d:24} perms: {p or '-'}")
    sys.exit()
if a[0] == "backup":
    print("backup:", auth.backup_db() or "nothing to back up yet"); sys.exit()
name = a[1] if len(a) > 1 else sys.exit(__doc__)
try:
    if a[0] == "import-local":
        import json, re
        if not any(x[0] == name.lower() for x in auth.list_users()): sys.exit(f"error: no such user '{name}'")
        lang_js = next((Path(__file__).resolve().parents[2] / "site").glob("*/lib/lang.js"))
        epoch = re.search(r"EPOCH = '([^']+)'", lang_js.read_text()).group(1)
        auth.backup_db(); have = auth.kv_all(name.lower()); n = 0
        for f in sorted((Path(__file__).parent / "data").glob("*.json")):   # this checkout's local single-user state
            if f.name.startswith("backup"): continue
            key = f"learn:{f.stem}"
            if key in have and "--force" not in a: print(f"skip {f.stem}: {name} already has progress (use --force to overwrite)"); continue
            auth.kv_put(name.lower(), {key: f.read_text(), f"learn-epoch:{f.stem}": epoch}); n += 1; print("imported", f.stem)
        sys.exit(0 if n else "nothing imported")
    if a[0] == "remove":
        auth.remove_user(name, purge="--purge-data" in a)
        print("login removed" + (" and data purged (backup in data/backups/)" if "--purge-data" in a else "; progress, notes and settings kept")); sys.exit()
    if a[0] == "perms":
        want = [] if (a[2:3] or ["none"])[0] == "none" else a[2].split(",")
        bad = [p for p in want if p not in auth.PERMS]
        if bad: sys.exit(f"unknown permission {bad}; use {auth.PERMS}")
        auth.set_perms(name, want); print(name, "->", ",".join(want) or "no permissions"); sys.exit()
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Again: "):
        sys.exit("passwords differ")
    if a[0] == "passwd":
        auth.set_password(name, pw)
    else:
        display = a[a.index("--name") + 1] if "--name" in a else ""
        allow = a[a.index("--allow") + 1].split(",") if "--allow" in a else []
        auth.add_user(name, pw, display, allow)
    print("ok", name)
except ValueError as e:
    sys.exit(f"error: {e}")
