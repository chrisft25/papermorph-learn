#!/usr/bin/env python3
"""Install (or update) the learning platform in a book. Run from the project root.

    python3 SKILL/scripts/platform_install.py <book> [--lang es] [--no-wire]

What it does (safe to re-run; it only overwrites platform files, never your chapters, narration or style.json):
  1. copies the browser files into site/<book>/lib/   (lang.js tutor.js learn.js draw.js + css; es.js when the book or
     --lang is Spanish)
  2. copies the server into tools/tutor/               (server.py auth.py runner.py tools.py packs.py users.py ... deploy/)
  3. creates books/<book>/tutor.md (optional tutor guidance) and books/<book>/sources/ if missing
  4. adds the runtime folders to .gitignore (never commit tools/tutor/data, .env.local, .runner-venv, packs)
  5. wires the cover and every chapter page (script tags), and builds the tutor packs
Then follow references/platform.md: start with tools/tutor/run-local.sh, create a user, open the book.
"""
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAT = HERE.parent / "platform"
LIB = ["lang.js", "tutor.js", "tutor.css", "learn.js", "learn.css", "draw.js"]
GITIGNORE = ["tools/tutor/.env.local", "tools/tutor/data/", "tools/tutor/data-backup*/", "tools/tutor/.runner-venv/", "tools/tutor/packs/", "tools/tutor/*.log", "tools/tutor/deploy/data/"]


def insert_before(s, marker, tag):
    return s if tag in s or marker not in s else s.replace(marker, tag + "\n" + marker, 1)


def insert_after(s, marker, tag):
    if tag in s or marker not in s:
        return s
    i = s.index(marker) + len(marker)
    return s[:i] + "\n" + tag + s[i:]


def wire_cover(f, es):
    s = f.read_text()
    s = insert_before(s, '<script src="lib/units.js"></script>', '<script src="lib/lang.js"></script>')
    s = insert_after(s, '<script src="lib/contents.js"></script>', '<script src="lib/learn.js"></script>')
    if es:
        s = insert_after(s, '<script src="lib/contents.js"></script>', '<script src="lib/es.js"></script>')
        if "EsBook.contents" not in s and "Contents.book(" in s:
            i = s.index("Contents.book("); j = s.index("\n});", i) + len("\n});")
            s = s[:j] + "\nif (window.EsBook) EsBook.contents();" + s[j:]
    f.write_text(s)


def wire_chapter(f, es):
    s = f.read_text()
    s = insert_before(s, '<script src="../lib/engine.js"></script>', '<script src="../lib/lang.js"></script>')
    if es:
        s = insert_after(s, '<script src="../lib/engine.js"></script>', '<script src="../lib/es.js"></script>')
    if "lib/tutor.js" not in s:
        tags = list(re.finditer(r'<script src="[^"]+"></script>\n?', s))
        if tags:
            i = tags[-1].end()
            s = s[:i] + ("" if s[i - 1] == "\n" else "\n") + '<script src="../lib/tutor.js"></script>\n' + s[i:]
    f.write_text(s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book"); ap.add_argument("--lang"); ap.add_argument("--no-wire", action="store_true")
    a = ap.parse_args()
    root = Path.cwd(); site = root / "site" / a.book
    if not (site / "lib" / "engine.js").exists():
        sys.exit(f"{site}/lib/engine.js not found: initialize the book first (references/site.md), and run this from the project root")
    style = root / "books" / a.book / "style.json"
    lang = a.lang or (json.loads(style.read_text()).get("book", {}).get("language") if style.exists() else None) or "en"
    es = lang.split("-")[0] == "es" or a.lang == "es"
    for n in LIB:
        shutil.copy2(PLAT / "lib" / n, site / "lib" / n)
    if es:
        shutil.copy2(PLAT / "lib" / "i18n" / "es.js", site / "lib" / "es.js")
    tut = root / "tools" / "tutor"; tut.mkdir(parents=True, exist_ok=True)
    for f in (PLAT / "tutor").iterdir():
        if f.is_dir():
            shutil.copytree(f, tut / f.name, dirs_exist_ok=True)
        else:
            shutil.copy2(f, tut / f.name)
    bk = root / "books" / a.book; (bk / "sources").mkdir(parents=True, exist_ok=True)
    if not (bk / "tutor.md").exists():
        (bk / "tutor.md").write_text((PLAT / "templates" / "tutor.md").read_text().replace("<book>", a.book))
    gi = root / ".gitignore"; cur = gi.read_text() if gi.exists() else ""
    add = [l for l in GITIGNORE if l not in cur.splitlines()]
    if add:
        gi.write_text(cur.rstrip("\n") + ("\n\n" if cur else "") + "# learning platform: secrets and runtime data\n" + "\n".join(add) + "\n")
    wired = 0
    if not a.no_wire:
        if (site / "index.html").exists():
            wire_cover(site / "index.html", es)
        for f in sorted(site.glob("ch*/index.html")):
            wire_chapter(f, es); wired += 1
        subprocess.run([sys.executable, str(tut / "packs.py"), a.book, "--all"], cwd=root, capture_output=True)
    print(f"platform installed for '{a.book}' (language {lang}); {wired} chapter page(s) wired.")
    print("next:  tools/tutor/run-local.sh   then   uv run tools/tutor/users.py add <you> --allow run   and open http://localhost:8765/")
    print("optional: uv venv tools/tutor/.runner-venv && uv pip install --python tools/tutor/.runner-venv/bin/python numpy matplotlib sympy   (Python code cells)")


if __name__ == "__main__":
    main()
