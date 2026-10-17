"""Add the tutor/learning scripts to a chapter page (idempotent), so new chapters get the panel, language switch,
progress and review automatically.

    uv run tools/tutor/wire_chapter.py <book> ch07       # one chapter
    uv run tools/tutor/wire_chapter.py <book> --all      # every site/<book>/chNN/index.html

Inserts  ../lib/lang.js  BEFORE ../lib/engine.js  and  ../lib/tutor.js  after the last script src (tutor.js loads
learn.js, circuit-lab.js by itself). Also rebuilds the chapter's tutor pack.
"""
# /// script
# requires-python = ">=3.10"
# ///
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from packs import ROOT, ensure

def wire(book, ch):
    f = ROOT / "site" / book / ch / "index.html"
    s = f.read_text()
    if "lib/lang.js" not in s:
        s = s.replace('<script src="../lib/engine.js"></script>', '<script src="../lib/lang.js"></script>\n<script src="../lib/engine.js"></script>', 1)
    if "lib/tutor.js" not in s:
        i = [m.end() for m in re.finditer(r'<script src="[^"]+"></script>\n?', s)][-1]
        s = s[:i] + ('' if s[i-1] == "\n" else "\n") + '<script src="../lib/tutor.js"></script>\n' + s[i:]
    f.write_text(s)
    try: ensure(book, ch)
    except Exception as e: print("  pack not built:", e)
    print("wired", book, ch)

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(__doc__)
    book = sys.argv[1]
    chs = sorted(p.parent.name for p in (ROOT / "site" / book).glob("ch*/index.html")) if sys.argv[2] == "--all" else sys.argv[2:]
    for ch in chs: wire(book, ch)
