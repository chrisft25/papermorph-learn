"""Papermorph learning platform: tutor backend.  Run:  uv run tools/tutor/server.py   (port 8780)

Claude through the Anthropic Messages API (streaming + tool use + prompt caching), or any gateway that speaks it.
Local single-user mode (no login): env ANTHROPIC_AUTH_TOKEN (or TUTOR_API_KEY) = key; TUTOR_BASE_URL (default
https://api.anthropic.com).

Hosted / multi-user mode: TUTOR_AUTH=on. Serves the book (site/) and the API from one origin behind a login; each user
has their own progress, notes and chats (server-side) and their own Claude API key (Settings). See README.
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["fastapi", "uvicorn", "httpx", "cryptography"]
# ///
import json, os, re, sys
from pathlib import Path
import httpx, uvicorn
from urllib.parse import quote, urlparse
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent))
import tools as T
import runner
import auth
from packs import ensure, OUT

BASE = os.environ.get("TUTOR_BASE_URL", "https://api.anthropic.com").rstrip("/")
KEY = os.environ.get("TUTOR_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or ""
MODELS = {"fast": os.environ.get("TUTOR_FAST", "claude-haiku-5-5"),
          "normal": os.environ.get("TUTOR_NORMAL", "claude-sonnet-5-5"),
          "deep": os.environ.get("TUTOR_DEEP", "claude-opus-5-5")}

AUTH = os.environ.get("TUTOR_AUTH", "off") == "on"
ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
DEFAULT_BASE = os.environ.get("TUTOR_DEFAULT_BASE", "https://api.anthropic.com")
HOME_PATH = os.environ.get("TUTOR_HOME_PATH", "")   # where "/" redirects, e.g. /my-book/ (default: the only book in site/, else a list)

app = FastAPI()
if not AUTH:   # local mode: the book is served elsewhere (serve.py on :8765) and calls this server cross-origin
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["GET", "POST", "PUT"], allow_headers=["*"])


def eff_perms(user: str) -> set:
    """Admin-granted permissions, minus anything this server cannot do (runner disabled / not installed)."""
    p = auth.get_perms(user)
    return p if (runner.ENABLED and runner.PY.exists()) else set()


def cfg(request: Request) -> dict:
    """Claude credentials for this request: the signed-in user's own (hosted) or the server environment (local)."""
    if not AUTH:
        return {"base": BASE, "key": KEY, "models": MODELS, "missing": "Set ANTHROPIC_AUTH_TOKEN (or TUTOR_API_KEY) in the server environment, or run with TUTOR_AUTH=on and save a key in Settings."}
    st = auth.get_settings(request.state.user)
    base = (st.get("claude_url") or DEFAULT_BASE).rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    models = {k: (st.get("model_" + k) or MODELS[k]) for k in MODELS}
    return {"base": base, "key": st.get("claude_key", ""), "models": models,
            "missing": "Add your Claude API key in Settings (your name menu, top) / Añade tu API key de Claude en Ajustes (menú de tu nombre, arriba)."}

LANG_NAMES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French", "de": "German", "it": "Italian", "ca": "Catalan", "nl": "Dutch", "ja": "Japanese", "zh": "Chinese"}

BASE_PROMPT = """You are the tutor of an animated, narrated lesson book that the learner is watching right now.

LANGUAGE: reply in the language of the learner's LAST message and switch when they switch. If the message is ambiguous or very short, use the interface language given in [UI: xx]. The lessons are narrated in <<LANG>>: when you answer in another language, add the term used in the lesson in parentheses the first time you use it, then keep to the learner's language.

LEARNER: <<READERS>>

HOW TO EXPLAIN: practical meaning first (analogies to things the learner already knows, concrete numbers), then the formal statement if needed. Short and direct by default (the learner paused the video); expand only when asked or at the "expert" level.

LEVELS (given as [Level: ...] in the message): "plain" = default, intuition and examples first, light formalism; "detailed" = step-by-step derivations with concrete values; "expert" = precise notation, assumptions, caveats and cited sources.

FORMAT: Markdown; put the JSON or SVG of a visual block on the lines AFTER the opening fence (never on the fence line); maths with $...$ or $$...$$ (LaTeX); code in fenced blocks. To visualize, use these fenced blocks (they are rendered locally in the panel):
- ```flow {"direction":"LR","title":"...","nodes":[{"id":"a","label":"Start","kind":"start"},{"id":"b","label":"Step"},{"id":"c","label":"Ok?","kind":"decision"},{"id":"d","label":"Done","kind":"end"}],"edges":[["a","b"],["b","c"],["c","d","yes"],["c","b","no"]]}``` flowcharts and processes, laid out automatically (direction LR or TB; kind start|end|decision|data; optional color blue|coral|violet|amber|green). PREFER this over mermaid.
- ```mermaid ...``` only for diagram types flow cannot do (sequence, class, state, gantt); needs internet.
- ```chart {"type":"bar","title":"...","labels":["a","b"],"values":[1,2],"ylabel":"..."}``` (type bar or line).
- ```plot {"title":"...","fns":[{"fn":"sin(x)","label":"sin"}],"x":[-6.3,6.3],"y":[-1.5,1.5]}``` function graphs; fn may use x, numbers, + - * / ^ ( ), sin cos tan asin acos atan sinh cosh tanh exp ln (natural log) log (base 10) log2 sqrt abs floor ceil round sign min max pow, and the constants pi, e and tau. Implicit multiplication (2x) is fine. y is optional.
- ```graph {"nodes":["a","b","c"],"edges":[["a","b","label"],["b","c"]],"directed":true}``` small node-link graphs.
- ```svg <svg viewBox="0 0 400 240">...</svg>``` your own drawing: shapes, paths, text and gradients only; scripts, event handlers, images, foreign objects and external references are removed. Palette for the dark board: ink #ece8dc, coral #f4a48c, blue #86c9e8, violet #bba8ee, amber #f0b45a, no background.
Never invent numbers: compute them (python cell) or label them as illustrative.

GROUNDING: use the "chapter pack" below for what the lesson says; for detail or verification use search_sources / read_source and cite like (hundt p61). If something is not in the pack or the sources, say so and mark it as general knowledge. Do not cite what you did not consult.

SCENE LINKS: to send the learner to a moment of the lesson write [text](scene:ID@SECONDS) with a scene id from the pack (seconds are optional; at most 3 per answer).

QUIZ: if asked for a quiz, answer with one short sentence and a ```quiz block with JSON [{"q":"...","options":["...","...","...","..."],"answer":0,"why":"..."}] (3 questions of rising difficulty about the current scene or chapter; answer = 0-based index of the right option; short options; never reveal answers outside the JSON).

CODE CELLS: you decide which Python blocks can run, in the opening line: ```python run = self-contained (imports and variables defined, runs as is; numpy, matplotlib and sympy are available; plt.show() is captured as an image) -> editable cell with a Run button; plain ```python = a fragment that depends on other code -> shown as code only. Never mark a fragment as run. Say in one sentence what the output should show.

FEYNMAN MODE: if the message contains [Feynman:pedir], pick ONE concept from the current scene and ask the learner to explain it in their own words in 2-4 sentences (do not explain it yourself), and include ```feynman {"concept":"name"}```. If it contains [Feynman:evaluar concepto=...], grade their explanation (do not correct it before grading): reply with ```grade {"score":1-5,"ok":["what is right"],"gaps":["what is missing or wrong"]}``` and then 2-4 kind sentences with the correct explanation of what is missing.

CONTEXT: the message may start with [Watching: ...] giving the chapter, scene id and title, second and the caption on screen: use it to resolve "this", "here", "what it just said".
"""

_system_cache: dict = {}


def system_for(book: str) -> list:
    """System prompt for a book: the generic tutor prompt + books/<book>/style.json (title, readers, language) + optional
    books/<book>/tutor.md (anything specific to the subject: terminology, notation, house rules, how to cite)."""
    st_p, tm_p = ROOT / "books" / book / "style.json", ROOT / "books" / book / "tutor.md"
    key = (book, st_p.stat().st_mtime if st_p.exists() else 0, tm_p.stat().st_mtime if tm_p.exists() else 0)
    if key not in _system_cache:
        try:
            b = json.loads(st_p.read_text()).get("book", {}) if st_p.exists() else {}
        except ValueError:
            b = {}
        lg = b.get("language", "en")
        text = (BASE_PROMPT.replace("<<LANG>>", LANG_NAMES.get(lg, lg)).replace("<<READERS>>", b.get("readers") or "a curious learner with no assumed background")
                + (f"\nBOOK: {b['title']}\n" if b.get("title") else ""))
        if tm_p.exists():
            text += "\nBOOK-SPECIFIC GUIDANCE (from tutor.md):\n" + tm_p.read_text() + "\n"
        _system_cache[key] = text
    return [{"type": "text", "text": _system_cache[key]}]


TOOLS = [
    {"name": "search_sources", "description": "BM25 search over the book's private sources (books, papers, notes). Returns excerpts with a citation 'slug pN'. Query in the language of the sources.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "k": {"type": "integer"}}, "required": ["query"]}},
    {"name": "read_source", "description": "Read whole pages of a source: slug (e.g. hundt) and pages '61' or '61-63' (max 4).",
     "input_schema": {"type": "object", "properties": {"slug": {"type": "string"}, "pages": {"type": "string"}}, "required": ["slug", "pages"]}},
]


def pack_text(book, ch):
    pk = json.loads(ensure(book, ch).read_text())   # rebuilt automatically when its sources changed
    lines = [f"# CHAPTER PACK {pk['number']}: {pk['title']}", pk["curriculum_row"], "", "## Chapter notes (scenes, glossary, errata)", pk["chapter_notes"], "", "## Narration per scene (id · title · start s)"]
    for b in pk["beats"]:
        lines.append(f"### {b['id']} · {b['title']} · t={b['start']}s dur={b['dur']}s\nOn screen: {b['on_screen']}\nNarration: {b['narration']}")
    return "\n".join(lines)


def sse(o):
    return f"data: {json.dumps(o, ensure_ascii=False)}\n\n"


def run_tool(book, name, inp):
    try:
        if name == "search_sources":
            return T.search_sources(book, inp["query"], min(int(inp.get("k", 6)), 10))
        if name == "read_source":
            return T.read_source(book, inp["slug"], inp["pages"])
    except Exception as e:  # tool errors go back to the model
        return {"error": f"{type(e).__name__}: {e}"}
    return {"error": "unknown tool"}


@app.get("/health")
def health(request: Request):
    c = cfg(request)
    packs = sorted(str(p.relative_to(OUT)) for p in OUT.glob("*/*.json")) if OUT.exists() else []
    return {"ok": True, "key": bool(c["key"]), "models": c["models"], "packs": packs, "runner": runner.status(),
            "perms": sorted(eff_perms(request.state.user)) if AUTH else None}


STATE = Path(os.environ.get("TUTOR_DATA_DIR") or Path(__file__).parent / "data")


@app.get("/state/{book}")
def get_state(book: str):
    if AUTH:
        return {}   # hosted: progress is synced per user through /api/kv
    f = STATE / f"{book}.json"
    return json.loads(f.read_text()) if f.exists() else {}


@app.put("/state/{book}")
async def put_state(book: str, req: dict, request: Request):
    if AUTH:
        return {"ok": True}
    # state is plain data: any loopback page may save it (code execution, /run, stays on the strict ORIGINS list)
    if not re.fullmatch(r"http://(localhost|127\.0\.0\.1)(:\d+)?", request.headers.get("origin") or "") or not book.replace("-", "").isalnum():
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    STATE.mkdir(exist_ok=True)
    (STATE / f"{book}.json").write_text(json.dumps(req, ensure_ascii=False))
    return {"ok": True}


@app.post("/cards")
async def cards(req: dict, request: Request):
    """Generate review cards for a chapter from its pack (non-streaming)."""
    book, ch, n = req["book"], req["chapter"], min(int(req.get("n", 8)), 15)
    lang = LANG_NAMES.get(req.get("ui"), "the book's language")
    ask = (f"Write {n} spaced-repetition review cards about this chapter for the learner described above. Card language: {lang} (key terms of the lesson may stay as the lesson says them). "
           "Mix: definitions of the mechanism, 'what comes out if...' questions with concrete values, and 2-3 about applying it in practice. "
           "EXACT format, one card per block, nothing else (LaTeX with plain $..$, unescaped):\n"
           "@@\nQ: short question\nA: short answer (1-3 sentences)\nB: id of the scene in the pack that explains it\n")
    c = cfg(request)
    if not c["key"]:
        return JSONResponse({"error": c["missing"]}, status_code=400)
    body = {"model": c["models"]["normal"], "max_tokens": 3000, "system": system_for(book) + [{"type": "text", "text": pack_text(book, ch), "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": ask}]}
    err = ""
    for _ in range(2):   # the model occasionally breaks the format: one retry
        try:
            async with httpx.AsyncClient(timeout=120) as cx:
                r = await cx.post(f"{c['base']}/v1/messages", json=body, headers={"x-api-key": c["key"], "anthropic-version": "2023-06-01"})
            txt = "".join(b.get("text", "") for b in r.json()["content"])
            out = []
            for blk in re.split(r"(?m)^\s*(?:@@\s*)?Q:", txt)[1:]:
                m = re.search(r"(.+?)\n\s*A:\s*(.+?)(?:\n\s*B:\s*(\S+))?\s*(?:@@\s*)?$", blk.strip(), re.S)
                if m:
                    out.append({"front": m.group(1).strip(), "back": m.group(2).strip(), "beat": (m.group(3) or "").strip()})
            if out:
                return {"cards": out[:n]}
            err = "no cards parsed: " + repr(txt[:200])
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return JSONResponse({"error": err}, status_code=502)


@app.post("/guide")
async def guide(req: dict, request: Request):
    """Study-guide text for a chapter (summary, pitfalls, work connection), cached per chapter+language."""
    book, ch, ui = req["book"], req["chapter"], "en" if req.get("ui") == "en" else "es"
    pk_path = ensure(book, ch); pk = json.loads(pk_path.read_text())
    cache = STATE / f"guide-{book}-{ch}-{ui}.md"
    if cache.exists() and cache.stat().st_mtime >= pk_path.stat().st_mtime:
        return {"title": pk["title"], "summary": cache.read_text(), "glossary": pk.get("glossary", [])}
    lang = LANG_NAMES.get(ui, "the book's language")
    ask = (f"Write the study guide of this chapter in {lang}, for revising before an exam or before applying it. Markdown, NO top-level title, with exactly these sections: "
           "## Key ideas (6-8 bullets with concrete values and LaTeX $..$ where it helps), ## Common mistakes (3-4 bullets), ## In practice (2-4 bullets on applying it). "
           "Write ALL THREE sections completely (do not stop after the first). Only what the chapter teaches; each bullet at most 2 lines; dense and brief.")
    c = cfg(request)
    if not c["key"]:
        return JSONResponse({"error": c["missing"]}, status_code=400)
    body = {"model": c["models"]["normal"], "max_tokens": 6000, "system": system_for(book) + [{"type": "text", "text": pack_text(book, ch), "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": ask}]}
    err = ""
    for _ in range(2):   # the model sometimes stops after the first section: require all three
        try:
            async with httpx.AsyncClient(timeout=120) as cx:
                r = await cx.post(f"{c['base']}/v1/messages", json=body, headers={"x-api-key": c["key"], "anthropic-version": "2023-06-01"})
            txt = "".join(b.get("text", "") for b in r.json()["content"]).strip()
            if txt.count("\n## ") + txt.startswith("## ") >= 3:
                STATE.mkdir(exist_ok=True); cache.write_text(txt)
                return {"title": pk["title"], "summary": txt, "glossary": pk.get("glossary", [])}
            err = "incomplete guide"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return JSONResponse({"error": err}, status_code=502)


ORIGINS = set(os.environ.get("TUTOR_ORIGINS", "http://localhost:8765,http://127.0.0.1:8765").split(","))


@app.post("/run")
async def run_cell(req: dict, request: Request):
    if not AUTH and request.headers.get("origin") not in ORIGINS:   # hosted mode checks the origin in the gate
        return JSONResponse({"error": "origin not allowed"}, status_code=403)
    if AUTH:   # permissions are set by the admin (users.py perms ...)
        perms = eff_perms(request.state.user)
        if "run" not in perms:
            return JSONResponse({"error": "Your account is not allowed to run code / Tu cuenta no puede ejecutar código"}, status_code=403)

    return await runner.run(str(req.get("code", "")))


@app.post("/chat")
async def chat(req: dict, request: Request):
    book, ch = req["book"], req["chapter"]
    c = cfg(request)
    model = c["models"].get(req.get("mode", "normal"), c["models"]["normal"])
    system = system_for(book) + [{"type": "text", "text": pack_text(book, ch), "cache_control": {"type": "ephemeral"}}]
    msgs = [{"role": m["role"], "content": m["content"]} for m in req["messages"][-12:]]
    ui = req.get("ui") if isinstance(req.get("ui"), str) and 2 <= len(req.get("ui")) <= 5 else "en"
    meta = f"[UI: {ui}] [Level: {req.get('level') if req.get('level') in ('plain', 'detailed', 'expert') else 'plain'}]\n"
    msgs[-1]["content"] = meta + msgs[-1]["content"]
    if req.get("now"):
        n = req["now"]
        msgs[-1]["content"] = meta + f"[Watching: {ch} · scene «{n.get('beat','')}» ({n.get('title','')}) · {n.get('t','')}s · caption: «{n.get('caption','')}»]\n\n" + msgs[-1]["content"][len(meta):]

    async def gen():
        nonlocal msgs
        if not c["key"]:
            yield sse({"type": "error", "message": c["missing"]}); return
        async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as cx:
            for _round in range(7):
                body = {"model": model, "max_tokens": 6000 if req.get("mode") == "deep" else 3500, "system": system,
                        "messages": msgs, "tools": TOOLS, "stream": True}
                blocks, stop, usage = {}, None, {}
                try:
                    async with cx.stream("POST", f"{c['base']}/v1/messages", json=body,
                                         headers={"x-api-key": c["key"], "anthropic-version": "2023-06-01"}) as r:
                        if r.status_code != 200:
                            yield sse({"type": "error", "message": f"API {r.status_code}: {(await r.aread()).decode()[:300]}"}); return
                        async for line in r.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            ev = json.loads(line[5:])
                            t = ev.get("type")
                            if t == "content_block_start":
                                cb = ev["content_block"]
                                blocks[ev["index"]] = {"type": cb["type"], "text": "", "json": "", "id": cb.get("id"), "name": cb.get("name")}
                            elif t == "content_block_delta":
                                d, b = ev["delta"], blocks[ev["index"]]
                                if d["type"] == "text_delta":
                                    b["text"] += d["text"]; yield sse({"type": "text", "text": d["text"]})
                                elif d["type"] == "input_json_delta":
                                    b["json"] += d["partial_json"]
                            elif t == "message_start":
                                usage.update(ev["message"].get("usage", {}))
                            elif t == "message_delta":
                                stop = ev["delta"].get("stop_reason"); usage.update(ev.get("usage", {}))
                            elif t == "error":
                                yield sse({"type": "error", "message": str(ev.get("error"))}); return
                except httpx.HTTPError as e:
                    yield sse({"type": "error", "message": f"Could not reach the model API: {e}"}); return
                yield sse({"type": "usage", "usage": {k: v for k, v in usage.items() if isinstance(v, int)}})
                if stop != "tool_use":
                    yield sse({"type": "done"}); return
                content, results = [], []
                for i in sorted(blocks):
                    b = blocks[i]
                    if b["type"] == "text" and b["text"]:
                        content.append({"type": "text", "text": b["text"]})
                    elif b["type"] == "tool_use":
                        inp = json.loads(b["json"] or "{}")
                        content.append({"type": "tool_use", "id": b["id"], "name": b["name"], "input": inp})
                        yield sse({"type": "tool", "name": b["name"], "input": inp})
                        res = run_tool(book, b["name"], inp)
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(res, ensure_ascii=False)[:12000]})
                msgs = msgs + [{"role": "assistant", "content": content}, {"role": "user", "content": results}]
            yield sse({"type": "error", "message": "Too many tool rounds."})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ hosted mode: login, per-user storage, settings, static site
LOGIN_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Login</title>
<style>:root{color-scheme:dark}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1613;color:#ece8dc;font:15px/1.5 "Avenir Next",Arial,sans-serif}
form{width:min(340px,90vw);background:#121b18;border:1px solid #2a3b35;border-radius:14px;padding:26px}h1{margin:0 0 4px;font-size:20px}p{margin:0 0 18px;color:#9aa89f;font-size:13px}
input{width:100%;box-sizing:border-box;margin:0 0 12px;padding:10px 12px;background:#1b2a25;color:#ece8dc;border:1px solid #34493f;border-radius:8px;font:inherit}
button{width:100%;padding:10px;background:#f0b45a;color:#0f1613;border:0;border-radius:8px;font:700 15px inherit;cursor:pointer}#e{color:#f08c7a;min-height:20px;font-size:13px;margin-top:8px}</style></head>
<body><form id="f"><h1>El stack cuántico</h1><p>Inicia sesión / Sign in</p><input name="u" placeholder="Usuario / Username" autocomplete="username" autofocus required>
<input name="p" type="password" placeholder="Contraseña / Password" autocomplete="current-password" required><button>Entrar / Sign in</button><div id="e"></div></form>
<script>f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({user:f.u.value,password:f.p.value})});
const d=await r.json().catch(()=>({}));if(r.ok){const n=new URLSearchParams(location.search).get('next')||'/';location.href=(n[0]==='/'&&n[1]!=='/')?n:'/'}else e_.textContent=d.error||'Error'};const e_=document.getElementById('e')</script></body></html>"""
OPEN_PATHS = {"/login", "/api/login", "/favicon.ico"}
API_PREFIXES = ("/api/", "/chat", "/run", "/cards", "/guide", "/health", "/state/")
COOKIE_SECURE = os.environ.get("TUTOR_COOKIE_SECURE", "0") == "1"


def _set_session(resp, user: str):
    resp.set_cookie("tutor_session", auth.make_token(user), max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=COOKIE_SECURE, path="/")
    resp.set_cookie("tutor_hosted", "1", max_age=auth.SESSION_DAYS * 86400, samesite="lax", secure=COOKIE_SECURE, path="/")   # tells the page to sync


if AUTH:
    @app.middleware("http")
    async def gate(request: Request, call_next):
        p = request.url.path
        if p not in OPEN_PATHS:
            user = auth.verify(request.cookies.get("tutor_session"))
            if not user:
                if p.startswith(API_PREFIXES):
                    return JSONResponse({"error": "login required"}, status_code=401)
                q = request.url.query
                return RedirectResponse("/login?next=" + quote(p + ("?" + q if q else "")))
            request.state.user = user
        if request.method in ("POST", "PUT", "DELETE"):   # same-origin only
            o = request.headers.get("origin")
            if o and urlparse(o).netloc != request.headers.get("host"):
                return JSONResponse({"error": "cross-origin request refused"}, status_code=403)
        resp = await call_next(request)
        if not p.startswith(API_PREFIXES) and "cache-control" not in resp.headers:
            resp.headers["Cache-Control"] = "private, max-age=86400" if p.rsplit(".", 1)[-1] in ("mp3", "png", "jpg", "svg", "woff2", "webp") else "no-cache"
        return resp

    @app.get("/login")
    def login_page():
        return HTMLResponse(LOGIN_HTML)

    @app.post("/api/login")
    async def api_login(req: dict, request: Request):
        ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
        if auth.throttled(ip):
            return JSONResponse({"error": "Demasiados intentos; espera 10 minutos / Too many attempts, wait 10 minutes"}, status_code=429)
        r = auth.login(str(req.get("user", "")), str(req.get("password", "")))
        if not r:
            auth.note_fail(ip)
            return JSONResponse({"error": "Usuario o contraseña incorrectos / Wrong username or password"}, status_code=401)
        resp = JSONResponse({"ok": True, "user": r[0], "name": r[1]})
        _set_session(resp, r[0])
        return resp

    @app.post("/api/logout")
    def api_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie("tutor_session", path="/"); resp.delete_cookie("tutor_hosted", path="/")
        return resp

    @app.get("/api/kv")
    def kv_get(request: Request):
        u = request.state.user
        return {"user": u, "name": auth.display(u), "perms": sorted(eff_perms(u)), "items": auth.kv_all(u)}

    @app.put("/api/kv")
    @app.post("/api/kv")   # navigator.sendBeacon on page hide uses POST
    async def kv_put(req: dict, request: Request):
        return {"ok": True, "n": auth.kv_put(request.state.user, req.get("items", {}))}

    @app.get("/api/settings")
    def settings_get(request: Request):
        return {**auth.public_settings(request.state.user), "perms": sorted(eff_perms(request.state.user)), "defaults": {"claude_url": DEFAULT_BASE, **{"model_" + k: v for k, v in MODELS.items()}}, "runner": runner.ENABLED}

    @app.put("/api/settings")
    async def settings_put(req: dict, request: Request):
        auth.put_settings(request.state.user, req)
        return {"ok": True, **auth.public_settings(request.state.user)}

    @app.get("/")
    def home():
        books = sorted(p.parent.parent.name for p in SITE.glob("*/lib/engine.js"))
        if HOME_PATH:
            return RedirectResponse(HOME_PATH)
        if len(books) == 1:
            return RedirectResponse(f"/{books[0]}/")
        return HTMLResponse("<!doctype html><meta charset=utf-8><body style='font:16px system-ui;background:#0f1613;color:#ece8dc;padding:2rem'><h1>Books</h1>" + "".join(f"<p><a style='color:#f0b45a' href='/{b}/'>{b}</a></p>" for b in books))

    app.mount("/", StaticFiles(directory=SITE, html=True), name="site")   # last: API routes win


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("TUTOR_HOST", "127.0.0.1"), port=int(os.environ.get("TUTOR_PORT", 8780)), log_level="warning",
                proxy_headers=True, forwarded_allow_ips=os.environ.get("TUTOR_TRUSTED_PROXY", "127.0.0.1"))
