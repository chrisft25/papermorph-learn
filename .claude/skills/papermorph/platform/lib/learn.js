// Learning layer: progress, streak + daily goals, XP/levels/badges, spaced-repetition review, mastery map, stuck detector.
// Loaded by the cover (<script src="lib/learn.js">) and by tutor.js on lessons. State: localStorage 'learn:<book>', mirrored
// to the tutor server (tools/tutor/data/<book>.json) when it runs, so it survives a browser switch. No audio here.
(() => {
'use strict';
if (window.Learn) return;
const SRC = document.currentScript.src;
const API = window.TUTOR_URL || 'http://localhost:8780';
const UI = window.UILang?.get?.() || 'en';
const tr = (es, en) => (window.UILang ? UILang.t(es, en) : (UI === 'es' ? es : en));   // see references/i18n.md for more languages
const mb = location.pathname.match(/^\/([^/]+)\//);
const BOOK = mb ? mb[1] : 'book';
const CH = (location.pathname.match(/\/(ch\d+[a-z]?)\//) || [])[1] || '';
const KEY = `learn:${BOOK}`;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const DAY = 86400000;
const ymd = (t = Date.now()) => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const shift = (d, n) => { const [y, m, dd] = d.split('-').map(Number); return ymd(new Date(y, m - 1, dd + n).getTime()); };
const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = new URL('learn.css', SRC).href; document.head.append(css);

/* ---------- state ---------- */
const EPOCH = window.LEARN_EPOCH || '';
const blank = () => ({ v: 1, epoch: EPOCH, updated: 0, xp: 0, days: {}, freezes: 0, freezeAt: 0, badges: {}, seen: {}, cards: {}, asks: {}, rewinds: {}, practice: {} });
let S = (() => { try { const r = JSON.parse(localStorage.getItem(KEY) || '{}'); return r.epoch === EPOCH ? Object.assign(blank(), r) : blank(); } catch { return blank(); } })();
let mirrorT = 0;
// The tutor server is optional. To keep the console quiet when it is off, nothing calls it unless the flag
// 'tutor:up' is set (tutor.js sets it after a successful contact) and any failure clears it again.
const up = () => { try { return localStorage.getItem('tutor:up') === '1'; } catch { return false; } };
const setUp = v => { try { v ? localStorage.setItem('tutor:up', '1') : localStorage.removeItem('tutor:up'); } catch {} };
// Persisting is deferred: save() only marks the state dirty; the JSON stringify + localStorage write + server mirror
// run once, when the browser is idle (never inside an animation frame), and again when the page is hidden/closed.
const idle = f => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 2500 }) : setTimeout(f, 50));
let dirty = false, flushQ = false;
function flush() {
  flushQ = false; if (!dirty) return; dirty = false;
  try { localStorage.setItem(KEY, JSON.stringify(S)); } catch {}
  clearTimeout(mirrorT);
  if (up()) mirrorT = setTimeout(() => fetch(`${API}/state/${BOOK}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(S) }).catch(() => setUp(false)), 1500);
}
function save() {
  S.updated = Date.now(); dirty = true; paintChip();
  if (!flushQ) { flushQ = true; setTimeout(() => idle(flush), 700); }
}
addEventListener('pagehide', flush); document.addEventListener('visibilitychange', () => { if (document.hidden) flush(); });
function pull() {
  if (!up()) return;
  fetch(`${API}/state/${BOOK}`).then(r => r.ok ? r.json() : null).then(r => { if (r && r.epoch === EPOCH && r.updated > S.updated) { S = Object.assign(blank(), r); try { localStorage.setItem(KEY, JSON.stringify(S)); } catch {} rollover(); paintChip(); } }).catch(() => setUp(false));
}
pull();

/* ---------- days, streak, XP ---------- */
const day = (d = ymd()) => (S.days[d] ??= { xp: 0, watch: 0, pips: {} });
const counted = d => { const r = S.days[d]; return !!(r && (r.frozen || Object.values(r.pips || {}).some(Boolean))); };
const pipCount = d => Object.values(S.days[d]?.pips || {}).filter(Boolean).length;
function rollover() {   // a single missed day inside a streak is covered by a freeze
  const y = shift(ymd(), -1);
  if (!counted(y) && counted(shift(y, -1)) && S.freezes > 0) { day(y).frozen = true; S.freezes--; save(); toast(tr('❄️ Usaste un día de congelación: tu racha sigue viva.', '❄️ A freeze day kept your streak alive.')); }
}
function streak() {
  let n = 0, d = ymd();
  if (counted(d) && !S.days[d].frozen) n++;
  for (d = shift(d, -1); counted(d); d = shift(d, -1)) if (!S.days[d].frozen) n++;
  return n;
}
const level = xp => Math.floor(Math.sqrt(xp / 50)) + 1;
const levelXp = L => 50 * (L - 1) ** 2;
function xp(n, why) {
  const before = level(S.xp); S.xp += n; day().xp += n; save();
  toast(`+${n} XP${why ? ' · ' + why : ''}`, null, 'xp');
  const after = level(S.xp);
  if (after > before) { toast(tr(`⭐ ¡Nivel ${after}!`, `⭐ Level ${after}!`), null, 'big'); confetti(); }
  badges();
}
function pip(name) {
  const r = day(); if (r.pips[name]) return;
  const had = pipCount(ymd());
  r.pips[name] = true; save();
  const lab = { watch: tr('Ver', 'Watch'), review: tr('Repasar', 'Review'), practice: tr('Practicar', 'Practice') }[name];
  const n = pipCount(ymd());
  if (had === 0) { const s = streak(); toast(tr(`🔥 Racha de ${s} día${s === 1 ? '' : 's'}: ${lab} cumplido`, `🔥 ${s}-day streak: ${lab} done`), null, 'big'); if (s % 7 === 0 && S.freezeAt !== s) { S.freezeAt = s; S.freezes = Math.min(2, S.freezes + 1); toast(tr('❄️ Ganaste un día de congelación', '❄️ You earned a freeze day')); } }
  else toast(`✓ ${lab}`, null, 'big');
  if (n === 3) { toast(tr('🌟 ¡Día completo! Ver + Repasar + Practicar', '🌟 Full day! Watch + Review + Practice'), null, 'big'); confetti(); }
  badges();
}

/* ---------- badges ---------- */
const BADGES = [
  ['first-scene', '▶', tr('Primera escena', 'First scene'), () => Object.values(S.seen).some(c => Object.values(c.beats || {}).some(b => b.done))],
  ['chapter-1', '📖', tr('Primer capítulo', 'First chapter'), () => Object.values(S.seen).some(c => c.done)],
  ['streak-3', '🔥', tr('Racha de 3', '3-day streak'), () => streak() >= 3],
  ['streak-7', '🔥', tr('Racha de 7', '7-day streak'), () => streak() >= 7],
  ['streak-30', '🏆', tr('Racha de 30', '30-day streak'), () => streak() >= 30],
  ['xp-100', '✨', '100 XP', () => S.xp >= 100], ['xp-500', '💫', '500 XP', () => S.xp >= 500], ['xp-1000', '🌠', '1000 XP', () => S.xp >= 1000],
  ['cards-10', '🧠', tr('10 tarjetas repasadas', '10 cards reviewed'), () => (S.practice.reviews || 0) >= 10],
  ['cards-50', '🧠', tr('50 tarjetas repasadas', '50 cards reviewed'), () => (S.practice.reviews || 0) >= 50],
  ['perfect-quiz', '🎯', tr('Quiz perfecto', 'Perfect quiz'), () => (S.practice.perfectQuiz || 0) >= 1],
  ['explainer', '🗣', tr('Explicador', 'Explainer'), () => (S.practice.feynman5 || 0) >= 1],
  ['full-day', '🌟', tr('Día completo', 'Full day'), () => Object.keys(S.days).some(d => pipCount(d) === 3)],
];
function badges() {
  for (const [id, icon, name, ok] of BADGES) if (!S.badges[id] && ok()) { S.badges[id] = Date.now(); save(); toast(`${icon} ${tr('Insignia', 'Badge')}: ${name}`, null, 'big'); confetti(); }
}

/* ---------- toasts + confetti (visual only, no sound) ---------- */
let toasts;
function toast(msg, action, kind = '') {
  if (!toasts) { toasts = document.createElement('div'); toasts.id = 'lToasts'; document.body.append(toasts); }
  const t = document.createElement('div'); t.className = 'lToast ' + kind; t.append(msg);
  if (action) { const b = document.createElement('button'); b.textContent = action[0]; b.onclick = () => { action[1](); t.remove(); }; t.append(b); }
  toasts.append(t); while (toasts.children.length > 4) toasts.firstChild.remove();
  setTimeout(() => t.remove(), action ? 12000 : kind === 'xp' ? 2600 : 5000);
}
function confetti() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const c = document.createElement('canvas'); c.id = 'lConf'; c.width = innerWidth; c.height = innerHeight; document.body.append(c);
  const g = c.getContext('2d'), cols = ['#f4a48c', '#86c9e8', '#bba8ee', '#f0b45a', '#8fd6b0'];
  const ps = Array.from({ length: 90 }, () => ({ x: innerWidth / 2 + (Math.random() - .5) * 200, y: innerHeight * .35, vx: (Math.random() - .5) * 11, vy: -Math.random() * 11 - 3, r: Math.random() * 5 + 3, c: cols[Math.random() * 5 | 0], a: Math.random() * 6 }));
  let f = 0; (function tick() { g.clearRect(0, 0, c.width, c.height); ps.forEach(p => { p.vy += .35; p.x += p.vx; p.y += p.vy; p.a += .2; g.fillStyle = p.c; g.fillRect(p.x, p.y, p.r, p.r * .6); }); if (++f < 110) requestAnimationFrame(tick); else c.remove(); })();
}

/* ---------- lesson tracking (watching, rewinds, chapter completion) ---------- */
const chRec = ch => (S.seen[ch] ??= { title: '', beats: {}, order: [] });
const askBeats = {}, rewoundNow = {}, nudged = {};
function startTracking() {
  let P0, B0; try { P0 = P; B0 = BEATS; } catch { return; }
  const cr = chRec(CH);
  try { cr.title = CHAPTER.title; } catch {}
  cr.order = B0.map(b => b.id);
  B0.forEach(b => { cr.beats[b.id] ??= { title: b.title, dur: TIMINGS[b.id]?.dur || 10, ask: !!b.ask, sec: 0, done: false }; cr.beats[b.id].title = b.title; });
  let li = P0.i, lt = P0.t;
  setInterval(() => {
    if (!P0.started || document.hidden) return;
    const b = B0[P0.i], rec = cr.beats[b.id], dt = P0.t - lt;
    if (P0.i === li) {
      if (P0.playing && !P0.waiting && !P0.done && dt > 0 && dt < 1.2) {
        rec.sec += dt; day().watch += .25;
        if (day().watch >= 600 && !day().pips.watch) pip('watch');
        if (!rec.done && !rec.ask && rec.sec >= .7 * rec.dur) { rec.done = true; save(); xp(5, tr('escena vista', 'scene watched')); chapterCheck(); }
      } else if (dt < -2.5) rewound(b.id);
    } else {
      if (P0.i === li + 1 && B0[li] && cr.beats[B0[li].id].ask && !cr.beats[B0[li].id].done) { cr.beats[B0[li].id].done = true; save(); chapterCheck(); }
      if (P0.i < li) rewound(b.id);
    }
    li = P0.i; lt = P0.t;
  }, 250);
}
function rewound(id) {
  const r = (S.rewinds[CH] ??= {}); r[id] = (r[id] || 0) + 1;
  rewoundNow[id] = (rewoundNow[id] || 0) + 1; save(); stuck(id);
}
function noteAsk(id) { if (!id) return; const r = (S.asks[CH] ??= {}); r[id] = (r[id] || 0) + 1; askBeats[id] = (askBeats[id] || 0) + 1; save(); stuck(id); }
function stuck(id) {
  if (nudged[id] || ((rewoundNow[id] || 0) < 2 && (askBeats[id] || 0) < 2)) return;
  nudged[id] = 1;
  toast(tr('¿Esta parte se atora? Te la explico de otra forma.', 'Stuck on this part? Let me explain it another way.'), [tr('Sí, explícame', 'Yes, explain'), () => window.Tutor?.ask(tr('Explícame esta escena de otra forma, distinta a la del video, con una analogía y un ejemplo con números.', 'Explain this scene a different way from the video, with an analogy and a worked example with numbers.'))]);
}
function chapterCheck() {
  const cr = chRec(CH), bs = Object.values(cr.beats);
  if (cr.done || bs.filter(b => b.done).length < Math.ceil(.85 * bs.length)) return;
  cr.done = Date.now(); save(); xp(100, tr('capítulo completo', 'chapter complete')); pip('watch'); confetti(); badges();
  toast(tr('🎓 Capítulo completo. ¿Genero tarjetas de repaso?', '🎓 Chapter complete. Generate review cards?'), [tr('Generar', 'Generate'), () => generateCards(CH)]);
}

/* ---------- spaced repetition ---------- */
const hash = s => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0; return 'c' + (h >>> 0).toString(36); };
function addCard(c, first) {
  const id = hash(c.front + '|' + (c.ch || ''));
  if (S.cards[id]) return S.cards[id];
  const card = S.cards[id] = { id, ef: 2.5, int: 0, reps: 0, due: Date.now(), n: 0, ok: 0, ...c };
  if (first !== undefined) schedule(card, first);
  save(); return card;
}
function addCards(a) { let k = 0; a.forEach(c => { const id = hash(c.front + '|' + (c.ch || '')); if (!S.cards[id]) { addCard(c); k++; } }); return k; }
function schedule(c, q) {   // SM-2, q: 0 again · 3 hard · 4 good · 5 easy
  c.n++; if (q >= 3) c.ok++;
  if (q < 3) { c.reps = 0; c.int = 0; c.due = Date.now() + 10 * 60000; }
  else {
    c.reps++; c.int = c.reps === 1 ? 1 : c.reps === 2 ? 3 : Math.round(c.int * c.ef);
    c.ef = Math.max(1.3, c.ef + .1 - (5 - q) * (.08 + (5 - q) * .02));
    const d = new Date(); d.setHours(0, 0, 0, 0); c.due = d.getTime() + c.int * DAY;
  }
}
// chapter ids like ch06, ch24b: natural order (24 < 24b < 25)
const chKey = c => { const m = /^ch(\d+)([a-z]?)$/.exec(c) || []; return +m[1] * 100 + (m[2] ? m[2].charCodeAt(0) - 96 : 0) || 0; };
const chEntries = () => Object.entries(S.seen).sort((a, b) => chKey(a[0]) - chKey(b[0]));
const due = () => Object.values(S.cards).filter(c => c.due <= Date.now()).sort((a, b) => a.due - b.due);
async function generateCards(ch) {
  toast(tr('Generando tarjetas…', 'Generating cards…'));
  try {
    const r = await fetch(`${API}/cards`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ book: BOOK, chapter: ch, ui: UI, n: 10 }) }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    const k = addCards(r.cards.map(c => ({ front: c.front, back: c.back, ch, beat: c.beat || '', kind: 'gen' })));
    toast(tr(`🧠 ${k} tarjetas nuevas para repasar`, `🧠 ${k} new cards to review`), null, 'big'); paintChip(); rv = null; if (ov && !ov.hidden && tab === 'review') draw();
  } catch (e) { toast(tr('No pude generar tarjetas (¿está encendido el tutor?)', 'Could not generate cards (is the tutor running?)')); }
}

/* ---------- mastery ---------- */
function mastery(ch, id) {
  const b = S.seen[ch]?.beats?.[id]; if (!b) return 0;
  const watched = Math.min(1, b.sec / (.7 * b.dur)) || 0, done = b.done || b.ask && b.sec > 0;
  const cs = Object.values(S.cards).filter(c => c.ch === ch && c.beat === id);
  const strength = cs.length ? cs.reduce((a, c) => a + Math.min(1, c.int / 21) * (c.n ? c.ok / c.n : 0), 0) / cs.length : null;
  let m = .4 * (done ? 1 : watched) + (strength === null ? (done ? .25 : 0) : .45 * strength + .15);
  m -= Math.min(.2, .05 * ((S.asks[ch]?.[id] || 0) + (S.rewinds[ch]?.[id] || 0)));
  return Math.max(0, Math.min(1, m));
}

/* ---------- rich text for cards (math via the book's MathJax, loaded on demand) ---------- */
let mathP = null;
function ensureMath() {
  if (window.MathJax?.tex2svg) return Promise.resolve();
  return mathP ??= new Promise(ok => { const s = document.createElement('script'); s.src = new URL('mathjax.js', SRC).href; s.onload = () => ok(); s.onerror = () => ok(); document.head.append(s); });
}
const rich = s => {
  const keep = [];
  s = String(s).replace(/\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g, (_, a, b) => { const t = (a || b).trim(); let h; try { if (!document.getElementById('MJX-SVG-styles') && MathJax.svgStylesheet) document.head.append(MathJax.svgStylesheet()); h = `<span class="lmj">${MathJax.tex2svg(t, { display: !!a }).querySelector('svg').outerHTML}</span>`; } catch { h = `<code>${esc(t)}</code>`; } return `\u0000${keep.push(h) - 1}\u0000`; });
  s = esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>');
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => keep[+i]);
};

/* ---------- study guide (Markdown download / print to PDF) ---------- */
const mmss = t => `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
async function guideData(ch) {
  const r = await fetch(`${API}/guide`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ book: BOOK, chapter: ch, ui: UI }) }).then(r => r.json());
  if (r.error) throw new Error(r.error);
  const rec = S.seen[ch] || { beats: {}, order: [] };
  let notes = []; try { notes = JSON.parse(localStorage.getItem(`tutor-notes:${BOOK}`) || '[]').filter(n => n.ch === ch); } catch {}
  const missed = Object.values(S.cards).filter(c => c.ch === ch && c.n > c.ok);
  const weak = (rec.order || []).map((id, i) => [id, i, mastery(ch, id)]).filter(([id, , m]) => (rec.beats[id]?.done || rec.beats[id]?.sec > 0) && m < .55).map(([id, i, m]) => ({ title: rec.beats[id].title, i, m }));
  return { ch, title: r.title, summary: r.summary, glossary: r.glossary || [], notes, missed, weak };
}
function guideMd(g) {
  const L = [`# ${g.ch} · ${g.title}`, `_${new Date().toLocaleDateString(UI === 'en' ? 'en-US' : 'es-MX')}_`, '', g.summary, ''];
  if (g.glossary.length) L.push(`## ${tr('Glosario', 'Glossary')}`, '', `| ${tr('Término', 'Term')} | ${tr('Traducción', 'Translation')} |`, '|---|---|', ...g.glossary.map(([a, b]) => `| ${a} | ${b} |`), '');
  if (g.notes.length) L.push(`## ${tr('Mis notas', 'My notes')}`, '', ...g.notes.flatMap(n => [`### ${n.title || n.beat || ''}${n.t ? ' (' + mmss(n.t) + ')' : ''}`, '', n.q ? `**${tr('Pregunta', 'Question')}:** ${n.q}` : '', '', n.a, '']));
  if (g.missed.length) L.push(`## ${tr('Para repasar (tarjetas falladas)', 'To review (missed cards)')}`, '', ...g.missed.map(c => `- **${c.front.replace(/\n/g, ' ')}** — ${String(c.back || c.why || '').replace(/\n/g, ' ')}`), '');
  if (g.weak.length) L.push(`## ${tr('Escenas por reforzar', 'Scenes to reinforce')}`, '', ...g.weak.map(w => `- ${w.title} (${Math.round(w.m * 100)}%) — ${g.ch}/?beat=${w.i}`), '');
  return L.join('\n');
}
function mdLite(md) {
  const out = [], ls = md.split('\n'); let i = 0;
  while (i < ls.length) {
    const l = ls[i];
    if (/^#{1,3} /.test(l)) { const n = l.match(/^#+/)[0].length; out.push(`<h${n}>${rich(l.replace(/^#+ /, ''))}</h${n}>`); i++; }
    else if (/^- /.test(l)) { const it = []; while (i < ls.length && /^- /.test(ls[i])) it.push(`<li>${rich(ls[i++].slice(2))}</li>`); out.push(`<ul>${it.join('')}</ul>`); }
    else if (/^\|/.test(l)) { const rows = []; while (i < ls.length && /^\|/.test(ls[i])) rows.push(ls[i++]); const cell = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => rich(c.trim())); out.push(`<table><tr>${cell(rows[0]).map(c => `<th>${c}</th>`).join('')}</tr>${rows.slice(2).map(r => `<tr>${cell(r).map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`); }
    else if (!l.trim()) i++;
    else { const p = []; while (i < ls.length && ls[i].trim() && !/^(#{1,3} |- |\|)/.test(ls[i])) p.push(ls[i++]); out.push(`<p>${rich(p.join(' '))}</p>`); }
  }
  return out.join('');
}
async function exportGuide(ch, mode = 'md') {
  toast(tr('Preparando la guía…', 'Preparing the guide…'));
  try {
    const g = await guideData(ch), md = guideMd(g);
    if (mode === 'md') {
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' })); a.download = `study-guide-${BOOK}-${ch}.md`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } else {
      await ensureMath();
      const d = document.createElement('div'); d.id = 'lPrint'; d.innerHTML = mdLite(md); document.body.append(d);
      addEventListener('afterprint', () => d.remove(), { once: true }); setTimeout(() => print(), 150);
    }
    window.Learn?.practice('guide');
  } catch (e) { toast(tr('No pude crear la guía (¿está encendido el tutor?)', 'Could not build the guide (is the tutor running?)')); }
}

/* ---------- chip + overlay ---------- */
let chip, ov, tab = 'today', rv = null;
function mountChip() {
  if (chip) return; chip = document.createElement('button'); chip.id = 'learnChip'; chip.type = 'button';
  chip.className = CH ? 'inlesson' : ''; chip.onclick = () => open('today'); document.body.append(chip); paintChip();
  // sit next to the ES|EN (+ user) pill, whatever its width
  const place = () => { const pill = document.querySelector('[data-uilang]'); if (!pill) return; const r = pill.getBoundingClientRect();
    if (CH) { chip.style.left = Math.round(r.right + 8) + 'px'; chip.style.right = 'auto'; } else { chip.style.right = Math.round(innerWidth - r.left + 8) + 'px'; chip.style.left = 'auto'; } };
  [0, 300, 1200].forEach(ms => setTimeout(place, ms)); addEventListener('resize', place);
}
let chipQ = false, chipHtml = '';
const dueN = () => { const t = Date.now(); let n = 0; for (const k in S.cards) if (S.cards[k].due <= t) n++; return n; };
function paintChip() {
  if (!chip || chipQ) return; chipQ = true;
  idle(() => {
    chipQ = false;
    const p = S.days[ymd()]?.pips || {}, d = dueN(), s = streak();
    const h = `<span class="f ${s ? 'on' : ''}">🔥${s}</span><span>${tr('Nv', 'Lv')}${level(S.xp)}</span><span class="pips"><i class="${p.watch ? 'on' : ''}"></i><i class="${p.review ? 'on' : ''}"></i><i class="${p.practice ? 'on' : ''}"></i></span>${d ? `<span class="due">🧠${d}</span>` : ''}`;
    if (h !== chipHtml) { chipHtml = h; chip.innerHTML = h; }
    chip.title = tr('Progreso, racha y repaso', 'Progress, streak and review');
  });
}
function open(t = 'today') {
  try { if (typeof P !== 'undefined' && P.playing) togglePlay(); } catch {}
  if (!ov) {
    ov = document.createElement('div'); ov.id = 'learnOv'; document.body.append(ov);
    ov.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Escape') close(); }); ov.addEventListener('keyup', e => e.stopPropagation());
    ov.onclick = e => { if (e.target === ov || e.target.closest('.lx')) close(); const b = e.target.closest('[data-tab]'); if (b) { tab = b.dataset.tab; rv = null; draw(); } onAct(e); };
  }
  tab = t; rv = null; ov.hidden = false; draw();
}
function close() { if (ov) ov.hidden = true; }
function draw() {
  const tabs = [['today', tr('Hoy', 'Today')], ['review', `${tr('Repaso', 'Review')}${due().length ? ' (' + due().length + ')' : ''}`], ['map', tr('Mapa', 'Map')]];
  ov.innerHTML = `<div class="lbox"><div class="lhead"><b>${tr('Tu progreso', 'Your progress')}</b><nav>${tabs.map(([k, l]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${l}</button>`).join('')}</nav><button class="lx" aria-label="${tr('Cerrar', 'Close')}">✕</button></div><div class="lbody">${tab === 'today' ? viewToday() : tab === 'review' ? viewReview() : viewMap()}</div></div>`;
  if (tab === 'review') ensureMath().then(() => { const f = ov.querySelector('.rcard'); if (f && rv) f.innerHTML = cardHtml(); });
}
function viewToday() {
  const s = streak(), L = level(S.xp), lo = levelXp(L), hi = levelXp(L + 1), pc = Math.round(100 * (S.xp - lo) / (hi - lo)), p = S.days[ymd()]?.pips || {}, n = pipCount(ymd());
  const goals = [['watch', '📺', tr('Ver', 'Watch'), tr('Termina un capítulo o acumula 10 min reales de lección', 'Finish a chapter or log 10 real minutes of lesson')],
    ['review', '🧠', tr('Repasar', 'Review'), tr('Termina una sesión de repaso (mín. 3 tarjetas)', 'Finish a review session (3+ cards)')],
    ['practice', '🛠', tr('Practicar', 'Practice'), tr('Quiz ≥2/3, reto de debug o explicar con tus palabras', 'Quiz ≥2/3, a debug challenge or a Feynman explanation')]];
  let cal = ''; const start = shift(ymd(), -83);
  for (let i = 0; i < 84; i++) { const d = shift(start, i), c = pipCount(d), fr = S.days[d]?.frozen; cal += `<i title="${d}" class="c${fr ? 'f' : c}"></i>`; }
  return `<div class="lhero"><div class="big"><span class="flame ${s ? 'on' : ''}">🔥</span><b>${s}</b><small>${tr('días de racha', 'day streak')}</small></div>
<div class="lvl"><b>${tr('Nivel', 'Level')} ${L}</b><div class="bar"><i style="width:${pc}%"></i></div><small>${S.xp} XP · ${hi - S.xp} ${tr('para el nivel', 'to level')} ${L + 1}</small></div><div class="frz">❄️ ${S.freezes}<small>${tr('congelaciones', 'freezes')}</small></div></div>
<h4>${tr('Metas de hoy', 'Today’s goals')} <small>${tr('cualquiera mantiene la racha; las tres = día completo 🌟', 'any one keeps the streak; all three = full day 🌟')}</small></h4>
<div class="goals">${goals.map(([k, ic, l, h]) => `<div class="goal ${p[k] ? 'on' : ''}"><span>${p[k] ? '✓' : ic}</span><div><b>${l}</b><small>${h}</small></div></div>`).join('')}</div>
<h4>${tr('Últimas 12 semanas', 'Last 12 weeks')}</h4><div class="cal">${cal}</div>
${Object.keys(S.seen).length ? `<h4>${tr('Guía de estudio', 'Study guide')} <small>${tr('resumen + glosario + tus notas y tarjetas falladas', 'summary + glossary + your notes and missed cards')}</small></h4>${chEntries().map(([c, r]) => `<div class="goal"><div style="flex:1"><b>${c}</b> · ${esc(r.title || '')}</div><button data-guide="${c}" data-mode="md">.md</button><button data-guide="${c}" data-mode="pdf">PDF</button></div>`).join('')}` : ''}
<h4>${tr('Insignias', 'Badges')} <small>${Object.keys(S.badges).length}/${BADGES.length}</small></h4><div class="badges">${BADGES.map(([id, ic, nm]) => `<div class="bdg ${S.badges[id] ? 'on' : ''}" title="${esc(nm)}"><span>${ic}</span><small>${esc(nm)}</small></div>`).join('')}</div>`;
}
function viewReview() {
  const d = due();
  if (!rv) rv = { queue: d.map(c => c.id), i: 0, done: 0, show: false, start: d.length, picked: null };
  if (rv.i >= rv.queue.length) {
    const fin = rv.done > 0;
    if (fin && !rv.rewarded) { rv.rewarded = true; if (rv.done >= Math.min(3, rv.start)) { xp(20, tr('sesión de repaso', 'review session')); pip('review'); } }
    const chs = chEntries().map(e => e[0]), total = Object.keys(S.cards).length;
    return `<div class="lempty"><div class="big">${fin ? '🎉' : '🧠'}</div><p><b>${fin ? tr('¡Repaso terminado!', 'Review finished!') : tr('Nada pendiente por ahora', 'Nothing due right now')}</b></p><p><small>${total} ${tr('tarjetas en tu mazo', 'cards in your deck')}</small></p>
${chs.map(c => `<button class="gen" data-gen="${c}">${tr('Generar tarjetas de', 'Generate cards for')} ${c}</button>`).join('') || `<p><small>${tr('Termina un capítulo o responde un quiz con el tutor para crear tarjetas.', 'Finish a chapter or answer a tutor quiz to create cards.')}</small></p>`}</div>`;
  }
  return `<div class="rprog">${rv.i + 1} / ${rv.queue.length}</div><div class="rcard">${cardHtml()}</div>`;
}
function cardHtml() {
  const c = S.cards[rv.queue[rv.i]]; if (!c) return '';
  let h = `<div class="rf">${rich(c.front)}</div>`;
  if (c.opts) {
    h += c.opts.map((o, oi) => `<button class="ropt ${rv.picked === null ? '' : oi === c.answer ? 'ok' : oi === rv.picked ? 'bad' : ''}" data-opt="${oi}" ${rv.picked !== null ? 'disabled' : ''}>${rich(o)}</button>`).join('');
    if (rv.picked !== null) h += `<div class="rb">${c.why ? rich(c.why) : ''}</div><div class="rgr"><button data-next="1">${tr('Siguiente', 'Next')}</button></div>`;
    return h;
  }
  if (!rv.show) return h + `<div class="rgr"><button data-show="1">${tr('Mostrar respuesta', 'Show answer')}</button></div>`;
  return h + `<div class="rb">${rich(c.back)}</div><div class="rgr">${[[0, tr('Otra vez', 'Again')], [3, tr('Difícil', 'Hard')], [4, tr('Bien', 'Good')], [5, tr('Fácil', 'Easy')]].map(([q, l]) => `<button data-g="${q}" class="g${q}">${l}</button>`).join('')}</div>`;
}
function viewMap() {
  const chs = chEntries();
  if (!chs.length) return `<div class="lempty"><div class="big">🗺</div><p>${tr('Mira una lección y aquí verás qué tan sólido tienes cada concepto.', 'Watch a lesson and you will see here how solid each concept is.')}</p></div>`;
  const weak = [];
  const grids = chs.map(([ch, r]) => {
    const cells = (r.order || []).map((id, i) => { const m = mastery(ch, id), b = r.beats[id]; if (m < .55 && (b.done || b.sec > 0)) weak.push([ch, id, i, b.title, m]); return `<a class="mc" href="../${ch}/?beat=${i}&t=0" style="--m:${m.toFixed(2)}" title="${esc(b.title)} · ${Math.round(m * 100)}%"></a>`; }).join('');
    const avg = (r.order || []).reduce((a, id) => a + mastery(ch, id), 0) / Math.max(1, (r.order || []).length);
    return `<h4>${ch} · ${esc(r.title || '')} <small>${Math.round(avg * 100)}% ${r.done ? '· ✓' : ''}</small></h4><div class="mgrid">${cells}</div>`;
  }).join('');
  weak.sort((a, b) => a[4] - b[4]);
  return `${grids}<div class="mleg"><span>${tr('sin ver', 'unseen')}</span><i></i><span>${tr('sólido', 'solid')}</span></div>
<h4>${tr('Para reforzar', 'To reinforce')}</h4>${weak.slice(0, 6).map(([ch, id, i, t, m]) => `<a class="mw" href="../${ch}/?beat=${i}&t=0"><b>${esc(t)}</b><small>${ch} · ${Math.round(m * 100)}%</small></a>`).join('') || `<p><small>${tr('Nada débil por ahora 👌', 'Nothing weak right now 👌')}</small></p>`}`;
}
function onAct(e) {
  const g = e.target.closest('[data-g]');
  if (g && rv) { const c = S.cards[rv.queue[rv.i]]; schedule(c, +g.dataset.g); if (+g.dataset.g >= 4) xp(2); S.practice.reviews = (S.practice.reviews || 0) + 1; rv.done++; rv.i++; rv.show = false; save(); draw(); return; }
  if (e.target.closest('[data-show]')) { rv.show = true; draw(); return; }
  const o = e.target.closest('[data-opt]');
  if (o && rv) { const c = S.cards[rv.queue[rv.i]]; rv.picked = +o.dataset.opt; const ok = rv.picked === c.answer; schedule(c, ok ? 4 : 0); if (ok) xp(2); S.practice.reviews = (S.practice.reviews || 0) + 1; rv.done++; save(); draw(); return; }
  if (e.target.closest('[data-next]')) { rv.i++; rv.picked = null; draw(); return; }
  const gen = e.target.closest('[data-gen]'); if (gen) generateCards(gen.dataset.gen);
  const gd = e.target.closest('[data-guide]'); if (gd) exportGuide(gd.dataset.guide, gd.dataset.mode);
}

/* ---------- boot ---------- */
/* ---------- cover: finished chapters also come from the learning state (the mastery map's data) ---------- */
function reconcileCover() {
  const done = Object.entries(S.seen).filter(([, r]) => r.done).map(([c]) => c);
  if (!done.length) return;
  const key = 'animebook:progress:' + new URL('.', location.href).pathname;   // the contents page's own key (see contents.js)
  try {
    const p = JSON.parse(localStorage.getItem(key) || '{}') || {}, ids = JSON.parse(localStorage.getItem(key + ':ids') || '{}') || {};
    p.done = Array.isArray(p.done) ? p.done : []; ids.done = Array.isArray(ids.done) ? ids.done : []; let ch = 0;
    for (const c of done) {
      const m = /^ch(\d+)([a-z]?)$/.exec(c); if (!m) continue;
      if (!m[2]) { if (!p.done.includes(+m[1])) { p.done.push(+m[1]); ch++; } } else if (!ids.done.includes(m[1] + m[2])) { ids.done.push(m[1] + m[2]); ch++; }
    }
    if (ch) { localStorage.setItem(key, JSON.stringify(p)); localStorage.setItem(key + ':ids', JSON.stringify(ids)); }
  } catch {}
  let marked = 0;
  for (const c of done) { const el = document.getElementById(c); if (el && el.classList.contains('ch') && !el.classList.contains('done')) { el.classList.add('done'); marked++; } }
  const prog = document.getElementById('prog');
  if (marked && prog) { const cards = document.querySelectorAll('#units a.ch'), n = document.querySelectorAll('#units a.ch.done').length; prog.innerHTML = tr(`<b>${n}</b> de ${cards.length} terminados`, `<b>${n}</b> of ${cards.length} finished`); }
}
function boot() { rollover(); mountChip(); if (CH) startTracking(); else reconcileCover(); badges(); }
if (document.body) boot(); else addEventListener('DOMContentLoaded', boot);
window.Learn = {
  xp, pip, toast, confetti, noteAsk, open, generateCards, exportGuide, pull, addCards, addCard,
  practice(k) { S.practice[k] = (S.practice[k] || 0) + 1; save(); badges(); },
  cardFromQuiz(q, ch, beat, correct) { addCard({ front: q.q, opts: q.options, answer: q.answer, why: q.why || '', ch, beat, kind: 'quiz' }, correct ? 4 : 0); },
  state: () => S,
};
})();
