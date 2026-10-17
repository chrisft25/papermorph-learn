"""Build per-chapter "packs" (the context the tutor gets) from the book's files.

    uv run tools/tutor/packs.py <book> ch06      # one chapter
    uv run tools/tutor/packs.py <book> --all     # every chapter that has narration + timings

Output: tools/tutor/packs/<book>/<chNN>.json (private, never under site/).
"""
# /// script
# requires-python = ">=3.10"
# ///
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def lang_of(book: str, ch: str = "") -> str:
    """Narration language of a book: style.json book.language, else the first narration.<lang>.json found."""
    st = ROOT / "books" / book / "style.json"
    if st.exists():
        try:
            lg = json.loads(st.read_text()).get("book", {}).get("language")
            if lg: return lg
        except ValueError:
            pass
    for f in sorted((ROOT / "content" / book).glob("*/narration.*.json")):
        parts = f.name.split(".")
        if len(parts) == 3: return parts[1]
    return "en"
OUT = Path(__file__).resolve().parent / "packs"


def build(book: str, ch: str) -> Path:
    content = ROOT / "content" / book / ch
    lg = lang_of(book)
    narr = json.loads((content / f"narration.{lg}.json").read_text())
    tim = json.loads((content / f"narration.{lg}.timings.json").read_text())
    html = (ROOT / "site" / book / ch / "index.html").read_text() if (ROOT / "site" / book / ch / "index.html").exists() else ""
    titles = dict(re.findall(r"^\s*\[\s*'([\w-]+)',\s*'((?:[^'\\]|\\.)*)'", html, re.M))
    m = re.search(r"CHAPTER\s*=\s*\{[^}]*number:\s*['\"]?([\w.]+)['\"]?,\s*title:\s*'((?:[^'\\]|\\.)*)'", html)
    num = lambda x: int(x) if x.isdigit() else x   # inserted chapters have ids like ch24b (number may be '24b' or 24.5)
    number, title = (num(m.group(1)), m.group(2)) if m else (num(ch[2:]), ch)
    md_path = ROOT / "books" / book / "chapters" / f"{ch}.md"
    md = md_path.read_text() if md_path.exists() else ""
    # beat table rows: | id | s | eye watches | marks |
    rows = {}
    for line in md.splitlines():
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 3 and re.fullmatch(r"[\w-]+", c[0]) and re.fullmatch(r"[\d.]+", c[1]):
            rows[c[0]] = c[2]
    beats, t0 = [], 0.0
    for bid, text in narr["beats"].items():
        tm = tim.get(bid, {})
        dur = tm.get("dur", 0)
        clean = re.sub(r"\[\[\w+\]\]", "", text).strip()
        cues = [[round(a, 2), b] for a, b in _cues(tm, clean)]
        beats.append({"id": bid, "title": titles.get(bid, bid), "start": round(t0, 1), "dur": dur,
                      "on_screen": rows.get(bid, ""), "narration": clean, "cues": cues})
        t0 += dur
    cur = ""
    cm = ROOT / "books" / book / "curriculum.md"
    if cm.exists():
        for line in cm.read_text().splitlines():
            if re.match(rf"\|\s*{re.escape(str(number))}\s*\|", line):
                cur = line
    gloss, ing = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            ing = "glossary" in line.lower() or "glosario" in line.lower()
        elif ing and line.startswith("|"):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) == 2 and not set(c[0]) <= set("-: ") and c[0].lower() not in ("español", "spanish"):
                gloss.append(c)
    pack = {"book": book, "glossary": gloss, "chapter": ch, "number": number, "title": title,
            "curriculum_row": cur, "chapter_notes": md, "beats": beats}
    p = OUT / book / f"{ch}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pack, ensure_ascii=False, indent=1))
    return p


def sources(book: str, ch: str):
    lg = lang_of(book)
    return [ROOT / "content" / book / ch / f"narration.{lg}.json", ROOT / "content" / book / ch / f"narration.{lg}.timings.json",
            ROOT / "books" / book / "chapters" / f"{ch}.md", ROOT / "site" / book / ch / "index.html"]


def ensure(book: str, ch: str) -> Path:
    """Pack path; (re)built when missing or older than any of its source files."""
    p = OUT / book / f"{ch}.json"
    if p.exists() and all(not f.exists() or f.stat().st_mtime <= p.stat().st_mtime for f in sources(book, ch)):
        return p
    return build(book, ch)


def _cues(tm, clean):
    # timings.js has cues in the site folder only; the content timings file has word times. Group words into
    # sentences using the narration text (sentence ends) to get coarse "what is being said at t".
    words = tm.get("words", [])
    if not words:
        return []
    sents = [s for s in re.split(r"(?<=[.!?:])\s+", clean) if s]
    out, i = [], 0
    for s in sents:
        n = len(s.split())
        if i < len(words):
            out.append((words[min(i, len(words) - 1)][0], s))
        i += n
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    book = sys.argv[1]
    if sys.argv[2] == "--all":
        chs = sorted(p.name for p in (ROOT / "content" / book).iterdir() if (p / f"narration.{lang_of(book)}.timings.json").exists())
    else:
        chs = sys.argv[2:]
    for ch in chs:
        print("wrote", build(book, ch).relative_to(ROOT))
