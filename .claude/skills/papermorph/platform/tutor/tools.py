"""Tutor tools: BM25 search over the book's private sources (books/<book>/sources/*.txt|md) and a page reader.
Sources use page markers like "=== [p61] ===" (see references/platform.md); files without markers are chunked by size."""
import math, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_MARK = re.compile(r"^=== \[p(\d+)\] ===\s*$", re.M)
_tok = lambda s: re.findall(r"[a-záéíóúñü0-9]+", s.lower())
_index: dict[str, dict] = {}


def _load(book):
    if book in _index:
        return _index[book]
    docs, files = [], {}
    for f in sorted((ROOT / "books" / book / "sources").glob("*")):
        if f.suffix not in (".txt", ".md"):
            continue
        txt = f.read_text(errors="ignore")
        pages = {}
        parts = _MARK.split(txt)
        if len(parts) > 1:
            for n, body in zip(parts[1::2], parts[2::2]):
                pages[int(n)] = body.strip()
        else:  # no page markers: ~1800-char chunks, numbered 1..n
            paras, cur, n = txt.split("\n\n"), "", 1
            for p in paras:
                if len(cur) + len(p) > 1800 and cur:
                    pages[n] = cur.strip(); n += 1; cur = ""
                cur += p + "\n\n"
            if cur.strip():
                pages[n] = cur.strip()
        files[f.stem] = pages
        for n, body in pages.items():
            if body:
                t = _tok(body)
                docs.append((f.stem, n, Counter(t), len(t)))
    df = Counter(w for d in docs for w in d[2])
    avg = sum(d[3] for d in docs) / max(1, len(docs))
    _index[book] = {"docs": docs, "files": files, "df": df, "avg": avg}
    return _index[book]


def search_sources(book, query, k=6):
    ix = _load(book); N = len(ix["docs"]); q = _tok(query); res = []
    for slug, n, tf, ln in ix["docs"]:
        s = 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (N - ix["df"][w] + .5) / (ix["df"][w] + .5))
                s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (.25 + .75 * ln / ix["avg"]))
        if s:
            res.append((s, slug, n))
    res.sort(reverse=True)
    out = []
    for s, slug, n in res[:k]:
        body = ix["files"][slug][n]
        out.append({"cite": f"{slug} p{n}", "score": round(s, 1), "excerpt": body[:700]})
    return out


def read_source(book, slug, pages):
    ix = _load(book); f = ix["files"].get(slug)
    if not f:
        return {"error": f"unknown source '{slug}'", "sources": sorted(ix["files"])}
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(pages).strip())
    if not m:
        return {"error": "pages like '61' or '61-63'"}
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    b = min(b, a + 3)  # cap
    txt = "\n\n".join(f"[{slug} p{n}]\n{f[n][:3500]}" for n in range(a, b + 1) if n in f)
    return {"text": txt or "(no such pages)"}
