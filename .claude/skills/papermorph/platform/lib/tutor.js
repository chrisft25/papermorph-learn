// Tutor side panel: ask questions about the lesson you are watching. Needs the local backend (tools/tutor/server.py);
// without it the lesson works as always and the button just says the tutor is offline. Load AFTER engine.js:
//   <script src="../lib/tutor.js"></script>
(() => {
'use strict';
const SRC = document.currentScript.src, SRC_BASE = SRC.slice(0, SRC.lastIndexOf('/') + 1);
const API = window.TUTOR_URL || 'http://localhost:8780';
// Hosted mode: the admin grants 'run' (Python code cells) per user; locally everything is allowed.
const can = k => !window.TUTOR_PERMS || window.TUTOR_PERMS.includes(k);
const setUp = v => { try { v ? localStorage.setItem('tutor:up', '1') : localStorage.removeItem('tutor:up'); } catch {} };
const probe = () => fetch(API + '/health').then(r => { if (!r.ok) throw 0; setUp(true); window.Learn?.pull?.(); }).catch(() => setUp(false));
const PANEL_W = 440;
const m = location.pathname.match(/\/([^/]+)\/(ch\d+[a-z]?)\//);
if (!m) return;
const [, BOOK, CH] = m;
const KEY = `tutor:${BOOK}/${CH}`;
const COLOR = { ink: '#ece8dc', dim: '#9aa89f', coral: '#f4a48c', blue: '#86c9e8', violet: '#bba8ee', amber: '#f0b45a', red: '#f08c7a', line: '#34493f' };
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const UI = window.UILang?.get?.() || 'en';
// tr(spanish, english): UILang.t also consults window.UI_STRINGS[lang][spanish] so more interface languages can be added without editing this file
const tr = (es, en) => (window.UILang ? UILang.t(es, en) : (UI === 'es' ? es : en));
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = new URL('tutor.css', document.currentScript.src).href; document.head.append(css);
const QUICK = [
  ['simple', tr('Más simple', 'Simpler'), tr('Explícamelo más simple, con una analogía de programación.', 'Explain this more simply, with a programming analogy.')],
  ['example', tr('Ejemplo', 'Example'), tr('Dame un ejemplo concreto con números (simúlalo si ayuda).', 'Give me a concrete example with numbers (simulate it if that helps).')],
  ['diagram', tr('Diagrama', 'Diagram'), tr('Muéstramelo como diagrama o gráfica.', 'Show me this as a diagram or chart.')],
  ['apply', tr('Aplicarlo', 'Apply it'), tr('¿Cómo aplicaría esto en la práctica? Dame un ejemplo corto.', 'How would I apply this in practice? Give me a short example.')],
  ['feynman', tr('Explícalo tú', 'You explain'), tr('Quiero explicarlo yo con mis palabras: pregúntame un concepto de esta escena.', 'I want to explain it in my own words: ask me about one concept from this scene.'), '[Feynman:pedir]'],
  ['quiz', tr('Quiz', 'Quiz me'), tr('Hazme un quiz de 3 preguntas sobre lo que acabo de ver.', 'Quiz me with 3 questions on what I just watched.')],
];
document.body.insertAdjacentHTML('beforeend', `<button id="tutorBtn" title="${tr('Preguntar al tutor', 'Ask the tutor')}">Tutor</button>
<aside id="tutor" aria-label="Tutor"><header><b>Tutor · ${esc(CH)}</b>
<button id="tPlay" title="${tr('Continuar la lección', 'Resume the lesson')}">▶</button><button id="tNotesBtn" title="${tr('Notas guardadas', 'Saved notes')}">${tr('Notas', 'Notes')}</button><button id="tClear" title="${tr('Borrar historial de este capítulo', 'Clear this chapter’s history')}"></button><button id="tClose" title="${tr('Cerrar', 'Close')}">✕</button></header>
<div id="tOpts"><label>${tr('Nivel', 'Level')} <select id="tLevel"><option value="plain">${tr('Intuitivo', 'Plain')}</option><option value="detailed">${tr('Detallado', 'Detailed')}</option><option value="expert">${tr('Experto', 'Expert')}</option></select><button type="button" class="info" data-i="level" aria-label="${tr('¿Qué significa cada nivel?', 'What does each level mean?')}">i</button></label>
<label title="${tr('Leer las respuestas en voz alta', 'Read answers aloud')}"><input type="checkbox" id="tTTS"> 🔊</label>
<label>${tr('Modelo', 'Model')} <select id="tMode"><option value="fast">${tr('Rápido', 'Fast')}</option><option value="normal" selected>Normal</option><option value="deep">${tr('A fondo', 'Deep')}</option></select><button type="button" class="info" data-i="model" aria-label="${tr('¿Qué significa cada modelo?', 'What does each model mean?')}">i</button></label></div><div id="tInfo" hidden></div>
<div id="tChip"></div><div id="tLog"></div><div id="tNotes" hidden></div>
<div id="tQuick">${QUICK.map(([k, l]) => `<button type="button" data-k="${k}">${esc(l)}</button>`).join('')}</div>
<form id="tForm"><button type="button" id="tMic" hidden title="${tr('Preguntar con la voz', 'Ask by voice')}">🎤</button><textarea id="tIn" rows="1" placeholder="${tr('Pregunta sobre lo que estás viendo…', 'Ask about what you are watching…')}"></textarea><button id="tSend"></button></form>
<div id="tHint">${tr('Enter envía · Shift+Enter nueva línea · Responde en el idioma en que escribas · La lección se pausa al preguntar', 'Enter sends · Shift+Enter new line · Answers in the language you write in · The lesson pauses when you ask')}</div></aside>`);
const panel = $('tutor'), log = $('tLog'), input = $('tIn');
panel.addEventListener('keydown', e => e.stopPropagation());   // the lesson's shortcuts (space, arrows, c, f…) must not fire while typing
panel.addEventListener('keyup', e => e.stopPropagation());

/* ---------- lesson hooks (engine globals; all optional) ---------- */
const player = () => { try { return { P, BEATS, TIMINGS }; } catch { return null; } };
function now() {
  const p = player(); if (!p) return null;
  const b = p.BEATS[p.P.i] || {};
  const cap = ($('caption') || {}).textContent || '';
  return { beat: b.id || '', title: b.title || '', t: Math.round(p.P.t * 10) / 10, caption: cap };
}
const mmss = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
function chip() {
  const n = now(); if (!n) return;
  const txt = `${tr('Viendo', 'Watching')}: ${CH} · ${n.title || n.beat} · ${mmss(n.t)}` + (n.caption ? ` · «${n.caption}»` : '');
  if (txt !== chip._t) { chip._t = txt; $('tChip').textContent = txt; }
  const paused = player() && !player().P.playing;
  $('tPlay').disabled = !paused || !player().P.started;
}
function pauseLesson() { const p = player(); if (p && p.P.playing) { try { togglePlay(); } catch { $('bPlay')?.click(); } } }

/* ---------- layout: make room for the panel without touching the engine ---------- */
function layout() {
  const f = $('frame'); if (!f) return;
  const open = panel.classList.contains('open') && innerWidth > 700;
  f.style.left = open ? `calc(50% - ${PANEL_W / 2}px)` : '';
  if (open) {
    const extra = parseFloat(getComputedStyle(f).getPropertyValue('--phone-extra')) || 0;
    document.documentElement.style.setProperty('--k', Math.min((innerWidth - PANEL_W) / 1640, (innerHeight - (innerWidth <= 700 ? 120 + extra : 0)) / (f.offsetHeight + 40)));
  }
}
addEventListener('resize', layout);
function setOpen(on, fromUser = true) {
  panel.classList.toggle('open', on); $('tutorBtn').style.display = on ? 'none' : '';
  if (on) { pauseLesson(); chip(); input.focus(); if (fromUser) probe(); }
  dispatchEvent(new Event('resize'));   // engine refits, then layout() above adjusts
  try { localStorage.setItem('tutor:open', on ? '1' : '0'); } catch {}
}
$('tutorBtn').onclick = () => setOpen(true); $('tClose').onclick = () => setOpen(false);
$('tPlay').onclick = () => { try { togglePlay(); } catch { $('bPlay')?.click(); } };
setInterval(() => panel.classList.contains('open') && chip(), 500);

/* ---------- rendering: tiny markdown + MathJax + mermaid + chart / svg / plot / graph ---------- */
const mathCache = new Map();
function tex(src, display) {
  const k = (display ? 'D' : 'I') + src;
  if (!mathCache.has(k)) {
    let h;
    try {
      if (!document.getElementById('MJX-SVG-styles') && window.MathJax?.svgStylesheet) document.head.append(MathJax.svgStylesheet());
      h = MathJax.tex2svg(src, { display }).querySelector('svg').outerHTML;
    } catch { h = `<code>${esc(src)}</code>`; }
    mathCache.set(k, display ? `<span class="mjd mj">${h}</span>` : `<span class="mj">${h}</span>`);
  }
  return mathCache.get(k);
}
function inline(s) {
  const keep = [];
  s = s.replace(/\[([^\]]+)\]\(scene:([\w-]+)(?:@([\d.]+))?\)/g, (_, t, id, at) => `\u0000${keep.push(`<a href="#" class="jump" data-id="${esc(id)}" data-t="${esc(at || '0')}">▶ ${esc(t)}</a>`) - 1}\u0000`);
  s = s.replace(/`([^`]+)`/g, (_, c) => `\u0000${keep.push(`<code>${esc(c)}</code>`) - 1}\u0000`);
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => `\u0000${keep.push(tex(t.trim(), true)) - 1}\u0000`);
  s = s.replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => `\u0000${keep.push(tex(t.trim(), true)) - 1}\u0000`);
  s = s.replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => `\u0000${keep.push(tex(t.trim(), false)) - 1}\u0000`);
  s = s.replace(/\$([^$\n]+?)\$/g, (_, t) => `\u0000${keep.push(tex(t.trim(), false)) - 1}\u0000`);
  s = esc(s).replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>')
    .replace(/\(((?:[A-Za-z][\w-]*)(?: [A-Za-z][\w-]*)? p\d+(?:[–-]\d+)?)\)/g, '(<span class="cite">$1</span>)');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => keep[+i]);
}

// Markdown table row -> cells. A '|' inside $math$ or `code` stays in its cell (kets like $|0\rangle$), '\|' is a literal bar; if a
// stray '$' leaves math open at the end of the row, fall back to a plain split so one odd cell cannot swallow the others.
function splitRow(r) {
  r = r.trim(); if (r.startsWith('|')) r = r.slice(1); if (r.endsWith('|') && !r.endsWith('\\|')) r = r.slice(0, -1);
  const run = smart => {
    const out = []; let cur = '', math = false, code = false;
    for (let i = 0; i < r.length; i++) {
      const c = r[i];
      if (c === '\\' && r[i + 1] === '|') { cur += math ? '\\|' : '|'; i++; continue; }   // inside math '\\|' is LaTeX's double bar
      if (c === '\\' && i + 1 < r.length) { cur += c + r[i + 1]; i++; continue; }
      if (smart) { if (c === '`') code = !code; else if (c === '$' && !code) math = !math; }
      if (c === '|' && !math && !code) { out.push(cur); cur = ''; } else cur += c;
    }
    out.push(cur); return { out, open: math || code };
  };
  const a = run(true); return (a.open ? run(false) : a).out;
}
function md(src) {
  const out = [], lines = src.split('\n'); let i = 0, para = [];
  const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; } };
  while (i < lines.length) {
    const l = lines[i];
    let f = l.match(/^```(\w*)[ \t]*(.*)$/);
    if (f) {
      let j = i + 1; const body = [];
      while (j < lines.length && !/^```/.test(lines[j])) body.push(lines[j++]);
      flush();
      if (j >= lines.length) out.push(`<pre><code>${esc(body.join('\n'))}</code></pre>`);   // still streaming: show raw
      else out.push(fence(f[1], body.join('\n'), f[2] || ''));
      i = j + 1; continue;
    }
    if (/^\$\$\s*$/.test(l)) {   // display math across lines
      let j = i + 1; const body = [];
      while (j < lines.length && !/^\$\$\s*$/.test(lines[j])) body.push(lines[j++]);
      flush(); if (j < lines.length) out.push(tex(body.join('\n'), true)); else out.push(`<p>${esc(l)}</p>`);
      i = j + 1; continue;
    }
    if (/^\s*$/.test(l)) { flush(); i++; continue; }
    let h = l.match(/^(#{1,4})\s+(.*)/);
    if (h) { flush(); out.push(`<h${h[1].length < 3 ? 3 : 4}>${inline(h[2])}</h${h[1].length < 3 ? 3 : 4}>`); i++; continue; }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      flush(); const ord = /^\s*\d+\./.test(l), items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(inline(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, '')));
      out.push(`<${ord ? 'ol' : 'ul'}>${items.map(x => `<li>${x}</li>`).join('')}</${ord ? 'ol' : 'ul'}>`); continue;
    }
    if (/^\|.*\|\s*$/.test(l) && /^\|[\s:|-]+\|\s*$/.test(lines[i + 1] || '')) {
      flush(); const rows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => splitRow(r).map(c => inline(c.trim()));
      out.push(`<table><tr>${cells(rows[0]).map(c => `<th>${c}</th>`).join('')}</tr>${rows.slice(2).map(r => `<tr>${cells(r).map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`); continue;
    }
    para.push(l); i++;
  }
  flush(); return out.join('');
}
let mmId = 0, mermaidP = null;
function loadMermaid() {
  return mermaidP ??= new Promise((ok, no) => {
    if (window.mermaid) return ok(window.mermaid);
    const s = document.createElement('script'); s.src = 'https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js';
    s.onload = () => { mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'strict' }); ok(mermaid); }; s.onerror = no; document.head.append(s);
  });
}
const mmCache = new Map();
function fence(lang, body, attrs = '') {
  if (!body.trim() && /^[{[<]/.test(attrs.trim())) { body = attrs; attrs = ''; }   // models sometimes write the JSON/SVG on the opening-fence line
  if (lang === 'mermaid') {
    const id = 'mm' + (++mmId);
    if (mmCache.has(body)) return `<div class="viz">${mmCache.get(body)}</div>`;
    setTimeout(() => loadMermaid().then(mm => mm.render('r' + id, body)).then(r => { mmCache.set(body, r.svg); const el = $(id); if (el) el.innerHTML = r.svg; })
      .catch(() => { const el = $(id); if (el) el.innerHTML = `<pre><code>${esc(body)}</code></pre><div class="cap">(sin conexión al renderizador de diagramas)</div>`; }), 0);
    return `<div class="viz" id="${id}"><div class="cap">dibujando diagrama…</div></div>`;
  }
  if (lang === 'quiz') return quiz(body);
  if (lang === 'python' || lang === 'py') return cell(body, attrs);
  if (lang === 'feynman') { try { const o = JSON.parse(body); return `<div class="viz fey">🗣 ${tr('Explícalo con tus palabras', 'Explain in your own words')}: <b>${esc(o.concept)}</b><div class="cap">${tr('Escribe (o dicta) tu explicación y envíala: te doy una calificación.', 'Type (or dictate) your explanation and send it: I will grade it.')}</div></div>`; } catch { return ''; } }
  if (lang === 'grade') return gradeCard(body);
  if (lang === 'chart') { try { return `<div class="viz">${chart(JSON.parse(body))}</div>`; } catch { return `<pre><code>${esc(body)}</code></pre>`; } }
  if (lang === 'plot' || lang === 'graph' || lang === 'svg' || lang === 'flow') {
    const D = window.TutorDraw;
    if (!D) return `<div class="viz"><div class="cap">…</div></div>`;   // draw.js still loading: redraw() runs when it arrives
    let h;
    try { h = lang === 'svg' ? D.svg(body) : lang === 'plot' ? D.plot(JSON.parse(body)) : lang === 'flow' ? D.flow(JSON.parse(body)) : D.graph(JSON.parse(body)); } catch { h = ''; }
    return h ? `<div class="viz">${h}</div>` : `<pre><code>${esc(body)}</code></pre>`;
  }
  return `<pre><code>${esc(body)}</code></pre>`;
}
let curMsg = null, curIdx = -1, curCell = 0;
function gradeCard(body) {
  let o; try { o = JSON.parse(body); } catch { return ''; }
  const li = a => (a || []).map(x => `<li>${inline(String(x))}</li>`).join('');
  return `<div class="viz fey grade"><b class="s">${'★'.repeat(o.score | 0)}${'☆'.repeat(5 - (o.score | 0))}</b> ${o.score}/5${o.ok?.length ? `<ul class="gok">${li(o.ok)}</ul>` : ''}${o.gaps?.length ? `<ul class="ggap">${li(o.gaps)}</ul>` : ''}</div>`;
}
/* ---------- editable code cells, run by the local tutor server on click ---------- */
function cellOut(o) {
  if (!o) return '';
  if (o.error) return `<pre class="cout err">${esc(o.error)}</pre>`;
  return `<pre class="cout">${esc(o.output || tr('(sin salida)', '(no output)'))}</pre>` + (o.images || []).map(b => `<img class="cimg" alt="" src="data:image/png;base64,${b}">`).join('')
    + `<div class="cap">${o.timeout ? tr('⏱ tiempo agotado', '⏱ timed out') : o.code ? `exit ${o.code}` : '✓'} · ${o.secs}s </div>`;
}
function cell(body, attrs = '') {
  // The agent decides (python run / plain); the admin's permission ('run') decides whether anything may execute.
  const code = body.replace(/\n$/, ''), tags = new Set(attrs.toLowerCase().split(/[\s,]+/));
  const st = ((curMsg.cells ??= [])[curCell] ??= { code, orig: code, out: null });
  const n = curCell++, show = can('run') && (tags.has('run') || st.force);
  if (!show) return `<pre><code>${esc(code)}</code></pre>` + (can('run') ? `<div class="circ-open"><button type="button" class="cforce" data-m="${curIdx}" data-c="${n}">${tr('Abrir como celda editable', 'Open as editable cell')}</button></div>` : '');
  const rows = Math.min(18, st.code.split('\n').length + 1);
  return `<div class="viz cell" data-m="${curIdx}" data-c="${n}"><textarea class="ccode" spellcheck="false" rows="${rows}">${esc(st.code)}</textarea>
<div class="cbar"><button type="button" class="crun" data-t="local">▶ ${tr('Ejecutar', 'Run')}</button><button type="button" class="creset" title="${tr('Restaurar el código original', 'Restore the original code')}">↺</button></div>
<div class="cres">${cellOut(st.out)}</div></div>`;
}
function quiz(body) {
  let qs; try { qs = JSON.parse(body); } catch { return `<pre><code>${esc(body)}</code></pre>`; }
  const qa = (curMsg.qa ??= {}); curMsg.qdata = qs;
  let right = 0, answered = 0;
  const html = qs.map((q, qi) => {
    const got = qa[qi]; if (got !== undefined) { answered++; if (got === q.answer) right++; }
    return `<div class="quiz"><div class="qq">${qi + 1}. ${inline(String(q.q))}</div>` + q.options.map((o, oi) => {
      const cls = got === undefined ? '' : oi === q.answer ? ' ok' : oi === got ? ' bad' : '';
      return `<button type="button" class="qopt${cls}" data-m="${curIdx}" data-q="${qi}" data-o="${oi}" ${got !== undefined ? 'disabled' : ''}>${inline(String(o))}</button>`;
    }).join('') + (got !== undefined ? `<div class="why">${got === q.answer ? '✓ ' : '✗ '}${inline(String(q.why || ''))}</div>` : '') + '</div>';
  }).join('');
  return `<div class="viz">${html}${answered === qs.length ? `<div class="cap"><b>${tr('Resultado', 'Score')}: ${right}/${qs.length}</b></div>` : ''}</div>`;
}
function chart(o) {
  const W = 400, H = 220, L = 44, B = 32, T = 26, R = 12;
  const v = (o.values || []).map(Number), lab = (o.labels || []).map(String), mx = Math.max(...v, 1e-9) * 1.1;
  const col = o.color && COLOR[o.color] || COLOR.blue, y = x => H - B - (H - B - T) * x / mx, n = v.length, bw = (W - L - R) / n;
  let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" font-family="Avenir Next, Arial" font-size="12">`;
  if (o.title) s += `<text x="${L}" y="16" fill="${COLOR.ink}" font-size="13" font-weight="600">${esc(o.title)}</text>`;
  for (let k = 0; k <= 4; k++) { const t = mx * k / 4 / 1.1 * 1.1, yy = y(t); s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="${COLOR.line}" stroke-width=".5"/><text x="${L - 5}" y="${yy + 4}" text-anchor="end" fill="${COLOR.dim}" font-size="10">${+t.toPrecision(3)}</text>`; }
  if (o.type === 'line') {
    s += `<polyline fill="none" stroke="${col}" stroke-width="2.5" points="${v.map((x, k) => `${L + bw * (k + .5)},${y(x)}`).join(' ')}"/>` + v.map((x, k) => `<circle cx="${L + bw * (k + .5)}" cy="${y(x)}" r="3.5" fill="${col}"/>`).join('');
  } else {
    s += v.map((x, k) => `<rect x="${L + bw * k + bw * .15}" y="${y(x)}" width="${bw * .7}" height="${H - B - y(x)}" rx="2" fill="${col}"/><text x="${L + bw * (k + .5)}" y="${y(x) - 4}" text-anchor="middle" fill="${COLOR.ink}" font-size="10.5">${+x.toPrecision(3)}</text>`).join('');
  }
  s += lab.map((t, k) => `<text x="${L + bw * (k + .5)}" y="${H - B + 15}" text-anchor="middle" fill="${COLOR.ink}" font-family="ui-monospace, Menlo, monospace" font-size="${n > 8 ? 9 : 12}">${esc(t)}</text>`).join('');
  if (o.ylabel) s += `<text x="10" y="${(H - B + T) / 2}" fill="${COLOR.dim}" font-size="10" transform="rotate(-90 10 ${(H - B + T) / 2})" text-anchor="middle">${esc(o.ylabel)}</text>`;
  return s + '</svg>';
}

/* ---------- chat ---------- */
let hist = []; try { hist = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch {}
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(hist.slice(-40), (k, v) => (k === 'images' ? undefined : v))); } catch {} };
let busy = false, ctrl = null;
function bubble(role) { const d = document.createElement('div'); d.className = 'm ' + (role === 'user' ? 'u' : 'a'); log.append(d); return d; }
function renderMsg(d, mm, idx = hist.indexOf(mm), final = true) {
  if (mm.role === 'user') { d.textContent = mm.content.replace(/^\[Feynman:[^\]]*\]\n?/, '').replace(/\n\[Feynman:pedir\]$/, ''); return; }
  curMsg = mm; curIdx = idx; curCell = 0;
  d.innerHTML = (mm.vizPre || []).join('') + md(mm.content) + (mm.err ? `<p class="err">${esc(mm.err)}</p>` : '')
    + (final && mm.content ? `<div class="foot"><button type="button" class="save" data-i="${idx}">${mm.saved ? tr('📌 Guardada', '📌 Saved') : tr('📌 Guardar', '📌 Save')}</button></div>` : '');
}
function redraw() { log.innerHTML = ''; hist.forEach((mm, i) => renderMsg(bubble(mm.role), mm, i)); log.scrollTop = log.scrollHeight; }
let fey = null;   // concept the tutor asked me to explain (Feynman mode)
async function ask(q, tag = '') {
  if (busy || !q.trim()) return;
  pauseLesson(); speechSynthesis?.cancel?.();
  if (fey) { tag = `[Feynman:evaluar concepto=${fey.concept}]\n`; }
  const n = now(); window.Learn?.noteAsk(n?.beat); q = tag.startsWith('[Feynman:evaluar') ? tag + q : q + (tag ? '\n' + tag : '');
  hist.push({ role: 'user', content: q }); const mm = { role: 'assistant', content: '', vizPre: [], now: n }; hist.push(mm);
  const ub = bubble('user'); renderMsg(ub, hist[hist.length - 2], hist.length - 2); const ab = bubble('assistant'); ab.innerHTML = `<p class="note">${tr('pensando…', 'thinking…')}</p>`;
  log.scrollTop = log.scrollHeight; busy = true; setUi(); ctrl = new AbortController();
  let raf = 0; const paint = () => { raf = 0; renderMsg(ab, mm, hist.length - 1, false); log.scrollTop = log.scrollHeight; };
  const sched = () => raf || (raf = requestAnimationFrame(paint));
  try {
    const msgs = hist.slice(0, -1).filter(h => h.content).map(h => ({ role: h.role, content: h.content })).slice(-10);
    const res = await fetch(API + '/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, signal: ctrl.signal,
      body: JSON.stringify({ book: BOOK, chapter: CH, mode: $('tMode').value, level: $('tLevel').value, ui: UI, now: n, messages: msgs }) });
    if (!res.ok) throw new Error('El tutor respondió ' + res.status);
    setUp(true);
    const rd = res.body.getReader(), dec = new TextDecoder(); let buf = '';
    for (;;) {
      const { done, value } = await rd.read(); if (done) break;
      buf += dec.decode(value, { stream: true }); let k;
      while ((k = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, k).trim(); buf = buf.slice(k + 2); if (!line.startsWith('data:')) continue;
        const e = JSON.parse(line.slice(5));
        if (e.type === 'text') mm.content += e.text;
        else if (e.type === 'tool') mm.vizPre.push(`<p class="note">🔎 ${esc(e.name === 'search_sources' ? tr('buscando en las fuentes: ', 'searching the sources: ') + (e.input.query || '') : e.name === 'read_source' ? tr(`leyendo ${e.input.slug} p${e.input.pages}`, `reading ${e.input.slug} p${e.input.pages}`) : tr('trabajando', 'working'))}</p>`);
        else if (e.type === 'error') mm.err = e.message;
        sched();
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') mm.err = err instanceof TypeError ? (setUp(false), 0) || tr('El tutor está apagado. Inicia el servidor: uv run tools/tutor/server.py (la lección sigue funcionando).', 'The tutor is offline. Start the server: uv run tools/tutor/server.py (the lesson keeps working).') : String(err.message || err);
  }
  cancelAnimationFrame(raf); raf = 0;   // a queued streaming paint would overwrite the final render (and its Save button)
  busy = false; setUi(); renderMsg(ab, mm, hist.length - 1); save();
  const fm = mm.content.match(/```feynman\s*(\{[\s\S]*?\})\s*```/);
  if (fm) { try { fey = JSON.parse(fm[1]); input.placeholder = tr('Explica con tus palabras…', 'Explain in your own words…'); } catch {} }
  const gm = mm.content.match(/```grade\s*(\{[\s\S]*?\})\s*```/);
  if (gm && fey && !mm.graded) { mm.graded = true; fey = null; setUi(); try { const sc = JSON.parse(gm[1]).score | 0; if (sc >= 4) { window.Learn?.xp(15, tr('explicaste bien', 'well explained')); window.Learn?.practice('feynman'); if (sc >= 5) window.Learn?.practice('feynman5'); window.Learn?.pip('practice'); } else window.Learn?.xp(3); } catch {} save(); }
  speak(mm.content);
}
$('tForm').onsubmit = e => { e.preventDefault(); if (busy) { ctrl?.abort(); return; } const q = input.value; input.value = ''; input.style.height = ''; ask(q); };
input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('tForm').requestSubmit(); } });
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; });
$('tClear').onclick = () => { if (!hist.length || confirm(tr('¿Borrar la conversación de este capítulo?', 'Clear this chapter’s conversation?'))) { hist = []; save(); redraw(); } };
function setUi() { if (!fey) input.placeholder = tr('Pregunta sobre lo que estás viendo…', 'Ask about what you are watching…'); $('tSend').textContent = busy ? tr('Parar', 'Stop') : tr('Enviar', 'Send'); $('tClear').textContent = tr('Borrar', 'Clear'); }
setUi();
const pref = (k, el, d) => { try { el.value = localStorage.getItem('tutor:' + k) || d; } catch { el.value = d; } el.addEventListener('change', () => { try { localStorage.setItem('tutor:' + k, el.value); } catch {} }); };
pref('level', $('tLevel'), 'plain'); pref('mode', $('tMode'), 'normal');
$('tQuick').onclick = e => { const b = e.target.closest('button'); if (b) { setNotes(false); log.hidden = false; const q = QUICK.find(q => q[0] === b.dataset.k); fey = null; ask(q[2], q[3] || ''); } };

const INFO = {
  level: [tr('Nivel de explicación', 'Explanation level'), [
    [tr('Intuitivo', 'Plain'), tr('Por defecto. Primero la idea y ejemplos concretos, con poco formalismo.', 'Default. The idea and concrete examples first, light formalism.')],
    [tr('Detallado', 'Detailed'), tr('Deducciones paso a paso, siempre con valores concretos.', 'Step-by-step derivations, always with concrete values.')],
    [tr('Experto', 'Expert'), tr('Notación precisa, supuestos, matices y fuentes citadas.', 'Precise notation, assumptions, caveats and cited sources.')]]],
  model: [tr('Modelo de IA', 'AI model'), [
    [tr('Rápido', 'Fast'), tr('Claude Haiku: respuestas veloces y baratas para aclaraciones cortas y seguimientos.', 'Claude Haiku: quick, cheap answers for short clarifications and follow-ups.')],
    ['Normal', tr('Claude Sonnet: el equilibrio recomendado entre calidad, herramientas (fuentes, simulador) y velocidad.', 'Claude Sonnet: the recommended balance of quality, tools (sources, simulator) and speed.')],
    [tr('A fondo', 'Deep'), tr('Claude Opus: el más cuidadoso para conceptos difíciles, derivaciones largas o dudas sutiles; más lento y caro.', 'Claude Opus: the most careful, for hard concepts, long derivations or subtle doubts; slower and costlier.')]]],
};
$('tOpts').addEventListener('click', e => {
  const b = e.target.closest('.info'); if (!b) return;
  const box = $('tInfo'), k = b.dataset.i;
  if (!box.hidden && box.dataset.k === k) { box.hidden = true; return; }
  const [title, rows] = INFO[k]; box.dataset.k = k; box.hidden = false;
  box.innerHTML = `<b>${esc(title)}</b>` + rows.map(([n, d]) => `<div><span>${esc(n)}</span> ${esc(d)}</div>`).join('');
});

/* ---------- clicks inside answers: jump to scene, save note, quiz options ---------- */
function jump(id, t) {
  try {
    const i = BEATS.findIndex(b => b.id === id); if (i < 0) return;
    hideCover(); seekInto(i, Math.min(1, (+t || 0) / (TIMINGS[id]?.dur || 1)));
  } catch {}
}
log.addEventListener('click', e => {
  const j = e.target.closest('.jump'); if (j) { e.preventDefault(); jump(j.dataset.id, j.dataset.t); return; }
  const sv = e.target.closest('.save');
  if (sv) {
    const i = +sv.dataset.i, mm = hist[i]; if (!mm || mm.saved) return;
    const q = hist.slice(0, i).reverse().find(h => h.role === 'user'), n = mm.now || {};
    const notes = loadNotes(); notes.push({ id: Date.now(), ch: CH, title: n.title || '', beat: n.beat || '', t: n.t || 0, q: q?.content || '', a: mm.content });
    saveNotes(notes); mm.saved = true; save(); sv.textContent = tr('📌 Guardada', '📌 Saved'); return;
  }
  const cf = e.target.closest('.cforce'); if (cf) { const mm = hist[+cf.dataset.m]; (mm.cells ??= [])[+cf.dataset.c].force = true; save(); renderMsg(cf.closest('.m'), mm, +cf.dataset.m); return; }
  const rb = e.target.closest('.crun'); if (rb) { runCell(rb.closest('.cell')); return; }
  const rs = e.target.closest('.creset');
  if (rs) { const c = rs.closest('.cell'), st = hist[+c.dataset.m].cells[+c.dataset.c]; st.code = st.orig; c.querySelector('.ccode').value = st.orig; save(); return; }
  const o = e.target.closest('.qopt');
  if (o) {
    const i = +o.dataset.m, mm = hist[i], qi = +o.dataset.q; (mm.qa ??= {})[qi] = +o.dataset.o;
    const qs = mm.qdata || [], q = qs[qi], ok = q && +o.dataset.o === q.answer;
    if (q) { window.Learn?.cardFromQuiz(q, CH, mm.now?.beat || '', ok); if (ok) window.Learn?.xp(5); }
    if (qs.length && Object.keys(mm.qa).length === qs.length && !mm.qDone) {
      mm.qDone = true; const right = qs.filter((x, k) => mm.qa[k] === x.answer).length;
      if (right === qs.length) { window.Learn?.practice('perfectQuiz'); window.Learn?.xp(15, tr('quiz perfecto', 'perfect quiz')); window.Learn?.confetti(); }
      if (right * 3 >= qs.length * 2) window.Learn?.pip('practice');
    }
    save(); const d = o.closest('.m'); renderMsg(d, mm, i);
  }
});

log.addEventListener('input', e => {
  const t = e.target.closest('.ccode'); if (!t) return;
  const c = t.closest('.cell'); hist[+c.dataset.m].cells[+c.dataset.c].code = t.value; save();
  t.rows = Math.min(18, t.value.split('\n').length + 1);
});
log.addEventListener('keydown', e => {
  const t = e.target.closest?.('.ccode'); if (!t) return;
  if (e.key === 'Tab') { e.preventDefault(); const a = t.selectionStart; t.setRangeText('    ', a, t.selectionEnd, 'end'); t.dispatchEvent(new Event('input', { bubbles: true })); }
  else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); t.closest('.cell').querySelector('[data-t="local"]').click(); }
});
async function runCell(c) {
  const st = hist[+c.dataset.m].cells[+c.dataset.c], res = c.querySelector('.cres');
  c.querySelectorAll('button').forEach(b => b.disabled = true); res.innerHTML = `<div class="cap">${tr('ejecutando…', 'running…')}</div>`;
  try {
    const r = await fetch(API + '/run', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ code: st.code }) });
    st.out = await r.json();
  } catch { st.out = { error: tr('El tutor está apagado: no se puede ejecutar.', 'The tutor is offline: cannot run.') }; }
  res.innerHTML = cellOut(st.out); c.querySelectorAll('button').forEach(b => b.disabled = false); save();
}
/* ---------- notes (per book, in the browser; export as Markdown) ---------- */
const NKEY = `tutor-notes:${BOOK}`;
const loadNotes = () => { try { return JSON.parse(localStorage.getItem(NKEY) || '[]'); } catch { return []; } };
const saveNotes = n => { try { localStorage.setItem(NKEY, JSON.stringify(n)); } catch {} };
function setNotes(on) { $('tNotes').hidden = !on; log.hidden = on; if (on) drawNotes(); }
function drawNotes() {
  const notes = loadNotes();
  $('tNotes').innerHTML = `<div class="nbar"><b>${tr('Notas', 'Notes')} (${notes.length})</b> <button type="button" id="nExport" ${notes.length ? '' : 'disabled'}>${tr('Exportar .md', 'Export .md')}</button> <button type="button" id="nGuide" title="${tr('Resumen + glosario + tus notas y tarjetas falladas', 'Summary + glossary + your notes and missed cards')}">${tr('Guía de estudio', 'Study guide')}</button> <button type="button" id="nBack">${tr('Volver al chat', 'Back to chat')}</button></div>`
    + (notes.length ? notes.map(n => `<div class="note-card" data-id="${n.id}"><div class="nh">${esc(n.ch)} · ${esc(n.title || n.beat)}${n.beat ? ` · <a href="#" class="jump" data-id="${esc(n.beat)}" data-t="${n.t}">▶ ${mmss(n.t)}</a>` : ''} <button type="button" class="ndel" title="${tr('Borrar', 'Delete')}">✕</button></div>${n.q ? `<div class="nq">${esc(n.q)}</div>` : ''}<div class="a">${md(n.a)}</div></div>`).join('') : `<p class="note">${tr('Aún no hay notas. Usa “Guardar” bajo una respuesta.', 'No notes yet. Use “Save” under an answer.')}</p>`);
}
$('tNotesBtn').onclick = () => setNotes($('tNotes').hidden);
$('tNotes').addEventListener('click', e => {
  if (e.target.closest('#nBack')) return setNotes(false);
  const j = e.target.closest('.jump'); if (j) { e.preventDefault(); return jump(j.dataset.id, j.dataset.t); }
  const del = e.target.closest('.ndel'); if (del) { const id = +del.closest('.note-card').dataset.id; saveNotes(loadNotes().filter(n => n.id !== id)); return drawNotes(); }
  if (e.target.closest('#nGuide')) { window.Learn?.exportGuide(CH, 'md'); return; }
  if (e.target.closest('#nExport')) {
    const md0 = `# ${tr('Notas del tutor', 'Tutor notes')} · ${BOOK}\n\n` + loadNotes().map(n => `## ${n.ch} · ${n.title || n.beat} (${mmss(n.t)})\n\n**${tr('Pregunta', 'Question')}:** ${n.q}\n\n${n.a}\n`).join('\n---\n\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([md0], { type: 'text/markdown' })); a.download = `tutor-notes-${BOOK}.md`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
});
/* ---------- lab, learning layer, voice ---------- */
const loadJs = src => new Promise(ok => { const e = document.createElement('script'); e.src = src; e.onload = ok; e.onerror = ok; document.head.append(e); });
loadJs(SRC_BASE + 'learn.js');
loadJs(SRC_BASE + 'draw.js').then(() => window.TutorDraw && redraw());   // svg / plot / graph / flow blocks
window.Tutor = { open: () => setOpen(true), ask: q => { setOpen(true); fey = null; ask(q); } };
const TTS = $('tTTS'); try { TTS.checked = localStorage.getItem('tutor:tts') === '1'; } catch {} TTS.onchange = () => { try { localStorage.setItem('tutor:tts', TTS.checked ? '1' : '0'); } catch {} if (!TTS.checked) speechSynthesis?.cancel?.(); };
function speak(md0) {
  if (!TTS.checked || !window.speechSynthesis) return;
  const t = md0.replace(/```[\s\S]*?```/g, ' ').replace(/\$\$?[^$]+\$\$?/g, ' ').replace(/[*_`#>\[\]()]/g, '').replace(/\s+/g, ' ').trim(); if (!t) return;
  const u = new SpeechSynthesisUtterance(t), es = (t.match(/[áéíóúñ¿¡]|\b(el|la|que|de|en|es|los|una)\b/gi) || []).length > t.split(' ').length / 12;
  u.lang = es ? 'es-MX' : (window.UILang ? UILang.speech() : 'en-US'); speechSynthesis.cancel(); speechSynthesis.speak(u);
}
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  const mic = $('tMic'); mic.hidden = false; let rec = null;
  mic.onclick = () => {
    if (rec) { rec.stop(); return; }
    pauseLesson(); speechSynthesis?.cancel?.();
    rec = new SR(); rec.lang = window.UILang ? UILang.speech() : 'en-US'; rec.interimResults = true; rec.continuous = false; mic.classList.add('rec');
    rec.onresult = e => { input.value = Array.from(e.results).map(r => r[0].transcript).join(' '); };
    rec.onerror = () => {}; rec.onend = () => { mic.classList.remove('rec'); rec = null; if (input.value.trim()) $('tForm').requestSubmit(); };
    rec.start();
  };
}
redraw();
try { if (localStorage.getItem('tutor:open') === '1') setOpen(true, false); } catch {}
})();
