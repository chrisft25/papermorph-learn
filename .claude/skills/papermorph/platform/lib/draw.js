// Local drawing for the tutor panel. No network, no eval, nothing is executed from model output:
//   TutorDraw.svg(src)    sanitized SVG (allow-listed elements/attributes only)
//   TutorDraw.plot(spec)  function graphs {fns:[{fn:"sin(x)",label}], x:[min,max], y:[min,max], title}
//   TutorDraw.graph(spec) node-link graphs {nodes:[..], edges:[[a,b,label?]..], directed:true}
//   TutorDraw.flow(spec)  flowcharts with a layered layout {direction:'LR'|'TB', nodes:[{id,label,kind?,color?}], edges:[[a,b,label?]..]}
//   TutorDraw.parse(str)  safe expression -> f(x) (tokenizer + recursive descent; whitelisted functions only)
// Each returns an HTML/SVG string ('' + error text on bad input). Works in the browser and, except svg(), in Node.
(function (root) {
'use strict';
const C = { ink: '#ece8dc', dim: '#9aa89f', line: '#34493f', cols: ['#86c9e8', '#f4a48c', '#bba8ee', '#f0b45a', '#8fd6b0'] };
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const FONT = 'font-family="Avenir Next, Arial, sans-serif"';
const fmt = v => (Math.abs(v) >= 1e4 || (Math.abs(v) < 1e-3 && v !== 0) ? v.toExponential(1) : +v.toPrecision(3)) + '';

/* ---------- safe expression parser ---------- */
const FUNCS = {
  sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan, sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh,
  exp: Math.exp, ln: Math.log, log: Math.log10, log2: Math.log2, sqrt: Math.sqrt, abs: Math.abs, floor: Math.floor, ceil: Math.ceil, round: Math.round, sign: Math.sign,
  min: Math.min, max: Math.max, pow: Math.pow,
};
const CONSTS = { pi: Math.PI, e: Math.E, tau: 2 * Math.PI };
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);   // never reach inherited names (constructor, __proto__...)

function tokenize(src) {
  const out = [], re = /\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(.))/gy;
  let m;
  while (re.lastIndex < src.length && (m = re.exec(src))) {
    if (m[1] !== undefined) out.push({ t: 'num', v: parseFloat(m[1]) });
    else if (m[2] !== undefined) out.push({ t: 'id', v: m[2].toLowerCase() });
    else if (m[3] !== undefined && /[-+*/^(),]/.test(m[3])) out.push({ t: 'op', v: m[3] });
    else if (m[3] !== undefined && /\S/.test(m[3])) throw new Error('unexpected "' + m[3] + '"');
    if (out.length > 160) throw new Error('expression too long');
  }
  return out;
}

function parse(src) {
  src = String(src).replace(/−/g, '-').replace(/×|·/g, '*').replace(/π/g, 'pi');
  if (src.length > 240) throw new Error('expression too long');
  const tk = tokenize(src); let i = 0;
  const peek = () => tk[i], eat = () => tk[i++];
  const isOp = v => peek() && peek().t === 'op' && peek().v === v;
  function expr() { let l = term(); while (isOp('+') || isOp('-')) { const o = eat().v, r = term(), a = l; l = o === '+' ? x => a(x) + r(x) : x => a(x) - r(x); } return l; }
  function startsPrimary() { const p = peek(); return p && (p.t === 'num' || p.t === 'id' || (p.t === 'op' && p.v === '(')); }
  function term() {
    let l = unary();
    for (;;) {
      if (isOp('*') || isOp('/')) { const o = eat().v, r = unary(), a = l; l = o === '*' ? x => a(x) * r(x) : x => a(x) / r(x); }
      else if (startsPrimary()) { const r = unary(), a = l; l = x => a(x) * r(x); }   // implicit multiplication: 2x, 3(x+1), x sin(x)
      else return l;
    }
  }
  function unary() { if (isOp('-')) { eat(); const f = unary(); return x => -f(x); } if (isOp('+')) { eat(); return unary(); } return power(); }
  function power() { const b = primary(); if (isOp('^')) { eat(); const e = unary(); return x => Math.pow(b(x), e(x)); } return b; }
  function primary() {
    const t = eat(); if (!t) throw new Error('unexpected end');
    if (t.t === 'num') { const v = t.v; return () => v; }
    if (t.t === 'op' && t.v === '(') { const f = expr(); if (!isOp(')')) throw new Error('missing )'); eat(); return f; }
    if (t.t === 'id') {
      if (isOp('(') && own(FUNCS, t.v)) {
        eat(); const args = [];
        if (!isOp(')')) { args.push(expr()); while (isOp(',')) { eat(); args.push(expr()); } }
        if (!isOp(')')) throw new Error('missing )'); eat();
        const fn = FUNCS[t.v]; return x => fn(...args.map(a => a(x)));
      }
      if (t.v === 'x') return x => x;
      if (own(CONSTS, t.v)) { const v = CONSTS[t.v]; return () => v; }
      throw new Error('unknown name "' + t.v + '"');
    }
    throw new Error('unexpected "' + t.v + '"');
  }
  const f = expr(); if (i < tk.length) throw new Error('unexpected "' + tk[i].v + '"');
  return f;
}

/* ---------- plot ---------- */
function ticks(lo, hi, n = 5) {
  const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0))), r = step0 / mag;
  const step = (r < 1.5 ? 1 : r < 3.5 ? 2 : r < 7.5 ? 5 : 10) * mag, out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(+v.toPrecision(12));
  return out;
}
function plot(spec) {
  try {
    const fns = (spec.fns || (spec.fn ? [spec.fn] : [])).slice(0, 5).map(f => (typeof f === 'string' ? { fn: f } : f));
    if (!fns.length) throw new Error('no functions');
    const [x0, x1] = Array.isArray(spec.x) && spec.x.length === 2 && spec.x[0] < spec.x[1] ? spec.x.map(Number) : [-10, 10];
    const N = 480, xs = Array.from({ length: N + 1 }, (_, k) => x0 + (x1 - x0) * k / N);
    const data = fns.map(f => { const g = parse(f.fn); return xs.map(x => { const y = g(x); return Number.isFinite(y) ? y : NaN; }); });
    let [y0, y1] = Array.isArray(spec.y) && spec.y.length === 2 && spec.y[0] < spec.y[1] ? spec.y.map(Number) : [NaN, NaN];
    if (!Number.isFinite(y0)) {
      const all = data.flat().filter(Number.isFinite).sort((a, b) => a - b);
      if (!all.length) throw new Error('nothing to draw in this range');
      const lo = all[Math.floor(all.length * .02)], hi = all[Math.ceil(all.length * .98) - 1], pad = (hi - lo || 1) * .08;
      y0 = lo - pad; y1 = hi + pad;
    }
    const W = 420, H = 270, L = 46, R = 14, T = spec.title ? 30 : 14, B = 30, px = x => L + (W - L - R) * (x - x0) / (x1 - x0), py = y => T + (H - T - B) * (1 - (y - y0) / (y1 - y0));
    let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" ${FONT} font-size="11">`;
    if (spec.title) s += `<text x="${L}" y="18" fill="${C.ink}" font-size="13" font-weight="600">${esc(spec.title)}</text>`;
    for (const t of ticks(y0, y1)) s += `<line x1="${L}" x2="${W - R}" y1="${py(t)}" y2="${py(t)}" stroke="${C.line}" stroke-width=".5"/><text x="${L - 5}" y="${py(t) + 4}" text-anchor="end" fill="${C.dim}" font-size="10">${fmt(t)}</text>`;
    for (const t of ticks(x0, x1)) s += `<line y1="${T}" y2="${H - B}" x1="${px(t)}" x2="${px(t)}" stroke="${C.line}" stroke-width=".5"/><text x="${px(t)}" y="${H - B + 14}" text-anchor="middle" fill="${C.dim}" font-size="10">${fmt(t)}</text>`;
    if (y0 < 0 && y1 > 0) s += `<line x1="${L}" x2="${W - R}" y1="${py(0)}" y2="${py(0)}" stroke="${C.dim}" stroke-width="1"/>`;
    if (x0 < 0 && x1 > 0) s += `<line y1="${T}" y2="${H - B}" x1="${px(0)}" x2="${px(0)}" stroke="${C.dim}" stroke-width="1"/>`;
    data.forEach((ys, k) => {
      let d = '', pen = false;
      ys.forEach((y, j) => { if (!Number.isFinite(y) || y < y0 - (y1 - y0) || y > y1 + (y1 - y0)) { pen = false; return; } d += (pen ? 'L' : 'M') + px(xs[j]).toFixed(1) + ' ' + Math.max(T - 4, Math.min(H - B + 4, py(y))).toFixed(1); pen = true; });
      s += `<path d="${d}" fill="none" stroke="${C.cols[k % 5]}" stroke-width="2.2" stroke-linejoin="round"/>`;
    });
    fns.forEach((f, k) => { s += `<text x="${L + 6 + k * 110}" y="${H - 6}" fill="${C.cols[k % 5]}" font-size="11">● ${esc(f.label || f.fn)}</text>`; });
    return s + '</svg>';
  } catch (e) { return `<div class="cap err">plot: ${esc(e.message)}</div>`; }
}

/* ---------- node-link graph ---------- */
function graph(spec) {
  try {
    const nodes = (spec.nodes || []).slice(0, 30).map(n => (typeof n === 'object' ? { id: String(n.id), label: String(n.label ?? n.id) } : { id: String(n), label: String(n) }));
    if (!nodes.length) throw new Error('no nodes');
    const idx = Object.fromEntries(nodes.map((n, k) => [n.id, k]));
    const edges = (spec.edges || []).slice(0, 80).map(e => (Array.isArray(e) ? { a: String(e[0]), b: String(e[1]), l: e[2] } : { a: String(e.from), b: String(e.to), l: e.label })).filter(e => e.a in idx && e.b in idx);
    const W = 420, H = 300, cx = W / 2, cy = H / 2, R0 = Math.min(W, H) / 2 - 40, n = nodes.length;
    const pos = nodes.map((_, k) => [cx + R0 * Math.cos(2 * Math.PI * k / n - Math.PI / 2), cy + R0 * Math.sin(2 * Math.PI * k / n - Math.PI / 2)]);
    if (n > 8) {   // deterministic force layout from the circular start
      for (let it = 0; it < 140; it++) {
        const f = pos.map(() => [0, 0]);
        for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) { const dx = pos[i][0] - pos[j][0], dy = pos[i][1] - pos[j][1], d2 = dx * dx + dy * dy + .01, k = 2600 / d2; f[i][0] += dx * k; f[i][1] += dy * k; f[j][0] -= dx * k; f[j][1] -= dy * k; }
        for (const e of edges) { const i = idx[e.a], j = idx[e.b], dx = pos[j][0] - pos[i][0], dy = pos[j][1] - pos[i][1], k = .02; f[i][0] += dx * k; f[i][1] += dy * k; f[j][0] -= dx * k; f[j][1] -= dy * k; }
        pos.forEach((p, i) => { p[0] = Math.max(24, Math.min(W - 24, p[0] + Math.max(-8, Math.min(8, f[i][0] + (cx - p[0]) * .01)))); p[1] = Math.max(24, Math.min(H - 24, p[1] + Math.max(-8, Math.min(8, f[i][1] + (cy - p[1]) * .01)))); });
      }
    }
    const r = 17;
    let s = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" ${FONT} font-size="12"><defs><marker id="ga" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.dim}"/></marker></defs>`;
    for (const e of edges) {
      const [x1, y1] = pos[idx[e.a]], [x2, y2] = pos[idx[e.b]], d = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / d, uy = (y2 - y1) / d;
      if (e.a === e.b) { s += `<path d="M${x1 - 6} ${y1 - r} a14 14 0 1 1 12 0" fill="none" stroke="${C.dim}" stroke-width="1.6"${spec.directed ? ' marker-end="url(#ga)"' : ''}/>`; continue; }
      s += `<line x1="${x1 + ux * r}" y1="${y1 + uy * r}" x2="${x2 - ux * (r + (spec.directed ? 2 : 0))}" y2="${y2 - uy * (r + (spec.directed ? 2 : 0))}" stroke="${C.dim}" stroke-width="1.6"${spec.directed ? ' marker-end="url(#ga)"' : ''}/>`;
      if (e.l !== undefined && e.l !== null) s += `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 4}" text-anchor="middle" fill="${C.ink}" font-size="11">${esc(e.l)}</text>`;
    }
    nodes.forEach((nd, k) => { s += `<circle cx="${pos[k][0]}" cy="${pos[k][1]}" r="${r}" fill="#1b2a25" stroke="${C.cols[k % 5]}" stroke-width="2"/><text x="${pos[k][0]}" y="${pos[k][1] + 4}" text-anchor="middle" fill="${C.ink}">${esc(nd.label.length > 6 ? nd.label.slice(0, 5) + '…' : nd.label)}</text>`; });
    return s + '</svg>';
  } catch (e) { return `<div class="cap err">graph: ${esc(e.message)}</div>`; }
}


/* ---------- flowchart (layered layout, drawn locally; the default instead of mermaid) ---------- */
// {direction:"LR"|"TB", nodes:[{id,label,kind?:"start"|"end"|"decision"|"data", color?:"blue|coral|violet|amber|green"}|"label"],
//  edges:[[from,to,label?]|{from,to,label}]}
const NAMED = { blue: '#86c9e8', coral: '#f4a48c', violet: '#bba8ee', amber: '#f0b45a', green: '#8fd6b0' };
function wrapLabel(t, n = 16) {
  const words = String(t).split(/\s+/), lines = []; let cur = '';
  for (const w of words) { if (cur && (cur + ' ' + w).length > n) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
  if (cur) lines.push(cur); return lines.slice(0, 3);
}
function flow(spec) {
  try {
    const nodes = (spec.nodes || []).slice(0, 24).map((n, k) => (typeof n === 'object' ? { id: String(n.id ?? k), label: String(n.label ?? n.id ?? k), kind: n.kind, color: n.color } : { id: String(n), label: String(n) }));
    if (!nodes.length) throw new Error('no nodes');
    const idx = Object.fromEntries(nodes.map((n, k) => [n.id, k])), N = nodes.length;
    const edges = (spec.edges || []).slice(0, 60).map(e => (Array.isArray(e) ? { a: String(e[0]), b: String(e[1]), l: e[2] } : { a: String(e.from), b: String(e.to), l: e.label })).filter(e => e.a in idx && e.b in idx && e.a !== e.b);
    const LR = (spec.direction || 'LR').toUpperCase() !== 'TB';
    // break cycles: DFS marks back edges (drawn as arcs, ignored for layering)
    const out = nodes.map(() => []); edges.forEach((e, k) => out[idx[e.a]].push([idx[e.b], k]));
    const state = new Array(N).fill(0), back = new Set();
    const dfs = u => { state[u] = 1; for (const [v, k] of out[u]) { if (state[v] === 1) back.add(k); else if (state[v] === 0) dfs(v); } state[u] = 2; };
    for (let u = 0; u < N; u++) if (!state[u]) dfs(u);
    const fwd = edges.map((e, k) => [idx[e.a], idx[e.b], k]).filter(x => !back.has(x[2]));
    const layer = new Array(N).fill(0);
    for (let it = 0; it < N; it++) for (const [a, b] of fwd) if (layer[b] < layer[a] + 1) layer[b] = layer[a] + 1;
    const L = Math.max(...layer) + 1, rows = Array.from({ length: L }, () => []);
    nodes.forEach((_, k) => rows[layer[k]].push(k));
    const posIn = new Array(N); rows.forEach(r => r.forEach((k, i) => (posIn[k] = i)));
    for (let sweep = 0; sweep < 6; sweep++) {   // barycenter ordering, alternating direction
      const order = sweep % 2 ? [...rows.keys()].reverse() : [...rows.keys()];
      for (const li of order) {
        const bary = k => { const nb = fwd.filter(([a, b]) => (sweep % 2 ? a === k : b === k)).map(([a, b]) => posIn[sweep % 2 ? b : a]); return nb.length ? nb.reduce((x, y) => x + y, 0) / nb.length : posIn[k]; };
        rows[li].sort((x, y) => bary(x) - bary(y)); rows[li].forEach((k, i) => (posIn[k] = i));
      }
    }
    const lines = nodes.map(n => wrapLabel(n.label)), w = lines.map((l, k) => Math.max(84, 8 * Math.max(...l.map(x => x.length)) + 28) + (nodes[k].kind === 'decision' ? 30 : 0)), h = lines.map((l, k) => 22 + 17 * l.length + (nodes[k].kind === 'decision' ? 18 : 0));
    const GAPL = 70, GAPN = 26, pos = new Array(N);
    const layerSize = rows.map(r => r.reduce((s, k) => s + (LR ? h[k] : w[k]) + GAPN, -GAPN)), maxSize = Math.max(...layerSize);
    let off = 0;
    rows.forEach((r, li) => {
      const thick = Math.max(...r.map(k => (LR ? w[k] : h[k]))); let q = (maxSize - layerSize[li]) / 2;
      r.forEach(k => { const cx = off + thick / 2, cy = q + (LR ? h[k] : w[k]) / 2; pos[k] = LR ? [cx, cy] : [cy, cx]; q += (LR ? h[k] : w[k]) + GAPN; });
      off += thick + GAPL;
    });
    const pad = 22, minX = Math.min(...pos.map((p, k) => p[0] - w[k] / 2)) - pad, minY = Math.min(...pos.map((p, k) => p[1] - h[k] / 2)) - pad - (spec.title ? 18 : 0);
    const maxX = Math.max(...pos.map((p, k) => p[0] + w[k] / 2)) + pad, maxY = Math.max(...pos.map((p, k) => p[1] + h[k] / 2)) + pad + (back.size ? 22 : 0);
    const col = k => NAMED[nodes[k].color] || (nodes[k].kind === 'start' ? NAMED.green : nodes[k].kind === 'end' ? NAMED.coral : nodes[k].kind === 'decision' ? NAMED.amber : nodes[k].kind === 'data' ? NAMED.violet : C.cols[layer[k] % 3]);
    let s = `<svg viewBox="${minX.toFixed(0)} ${minY.toFixed(0)} ${(maxX - minX).toFixed(0)} ${(maxY - minY).toFixed(0)}" xmlns="http://www.w3.org/2000/svg" ${FONT} font-size="12"><defs><marker id="fa" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="${C.dim}"/></marker></defs>`;
    if (spec.title) s += `<text x="${minX + pad}" y="${minY + 18}" fill="${C.ink}" font-size="13" font-weight="600">${esc(spec.title)}</text>`;
    const edge = (a, b, label, isBack) => {
      const [x1, y1] = pos[a], [x2, y2] = pos[b];
      const sa = LR ? [x1 + w[a] / 2, y1] : [x1, y1 + h[a] / 2], ea = LR ? [x2 - w[b] / 2 - 2, y2] : [x2, y2 - h[b] / 2 - 2];
      let d, mx, my;
      if (isBack) {   // arc under the chart, back to an earlier node
        const lowY = maxY - 14, sx = LR ? x1 : x1, ex = LR ? x2 : x2;
        const sy = LR ? y1 + h[a] / 2 : y1 + h[a] / 2, ey = LR ? y2 + h[b] / 2 + 2 : y2 + h[b] / 2 + 2;
        d = `M${sx} ${sy} C${sx} ${lowY} ${ex} ${lowY} ${ex} ${ey}`; mx = (sx + ex) / 2; my = lowY - 3;
      } else if (LR) { const dx = Math.max(24, (ea[0] - sa[0]) / 2); d = `M${sa[0]} ${sa[1]} C${sa[0] + dx} ${sa[1]} ${ea[0] - dx} ${ea[1]} ${ea[0]} ${ea[1]}`; mx = (sa[0] + ea[0]) / 2; my = (sa[1] + ea[1]) / 2; }
      else { const dy = Math.max(24, (ea[1] - sa[1]) / 2); d = `M${sa[0]} ${sa[1]} C${sa[0]} ${sa[1] + dy} ${ea[0]} ${ea[1] - dy} ${ea[0]} ${ea[1]}`; mx = (sa[0] + ea[0]) / 2; my = (sa[1] + ea[1]) / 2; }
      s += `<path d="${d}" fill="none" stroke="${C.dim}" stroke-width="1.6" marker-end="url(#fa)"${isBack ? ' stroke-dasharray="5 4"' : ''}/>`;
      if (label !== undefined && label !== null && label !== '') { const t = esc(label); s += `<rect x="${mx - 4 * String(label).length - 4}" y="${my - 9}" width="${8 * String(label).length + 8}" height="16" rx="4" fill="#0f1613" opacity=".85"/><text x="${mx}" y="${my + 3}" text-anchor="middle" fill="${C.ink}" font-size="11">${t}</text>`; }
    };
    edges.forEach((e, k) => edge(idx[e.a], idx[e.b], e.l, back.has(k)));
    nodes.forEach((n, k) => {
      const [cx, cy] = pos[k], c = col(k), x = cx - w[k] / 2, y = cy - h[k] / 2;
      if (n.kind === 'decision') s += `<path d="M${cx} ${y} L${cx + w[k] / 2} ${cy} L${cx} ${y + h[k]} L${x} ${cy} Z" fill="#1b2a25" stroke="${c}" stroke-width="2"/>`;
      else s += `<rect x="${x}" y="${y}" width="${w[k]}" height="${h[k]}" rx="${n.kind === 'start' || n.kind === 'end' ? h[k] / 2 : 9}" fill="#1b2a25" stroke="${c}" stroke-width="2"/>`;
      lines[k].forEach((ln, i) => { s += `<text x="${cx}" y="${cy - (lines[k].length - 1) * 8.5 + i * 17 + 4}" text-anchor="middle" fill="${C.ink}">${esc(ln)}</text>`; });
    });
    return s + '</svg>';
  } catch (e) { return `<div class="cap err">flow: ${esc(e.message)}</div>`; }
}

/* ---------- sanitized SVG ---------- */
const OK_TAGS = new Set('svg g path rect circle ellipse line polyline polygon text tspan defs lineargradient radialgradient stop marker title desc clippath'.split(' '));
const OK_ATTRS = new Set(('viewbox preserveaspectratio width height x y x1 x2 y1 y2 cx cy r rx ry d points transform fill stroke stroke-width stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin ' +
  'opacity fill-opacity stroke-opacity fill-rule font-size font-family font-weight font-style text-anchor dominant-baseline letter-spacing offset stop-color stop-opacity gradientunits gradienttransform ' +
  'marker-start marker-mid marker-end markerwidth markerheight refx refy orient markerunits clip-path dx dy rotate textlength xmlns').split(' '));
function svg(src) {
  if (typeof DOMParser === 'undefined') return '';
  src = String(src).trim();
  if (src.length > 30000) return '<div class="cap err">svg: too large</div>';
  const doc = new DOMParser().parseFromString(src, 'image/svg+xml');
  if (doc.querySelector('parsererror') || doc.documentElement.localName !== 'svg') return `<pre><code>${esc(src.slice(0, 600))}</code></pre><div class="cap err">svg: not valid SVG</div>`;
  let count = 0;
  const NS = 'http://www.w3.org/2000/svg';
  const safeVal = (name, v) => !/javascript:|data:|expression\(|@import|<|&#/i.test(v) && (!/url\(/i.test(v) || /^url\(#[\w-]+\)$/.test(v.trim()));
  function clone(n) {
    if (n.nodeType === 3) return document.createTextNode(n.nodeValue);
    if (n.nodeType !== 1 || !OK_TAGS.has(n.localName.toLowerCase()) || ++count > 800) return null;
    const out = document.createElementNS(NS, n.localName);
    for (const a of n.attributes) {
      const nm = a.localName.toLowerCase();
      if (a.prefix && a.prefix !== 'xmlns') continue;
      if (nm.startsWith('on') || !OK_ATTRS.has(nm) || !safeVal(nm, a.value)) continue;
      out.setAttribute(a.localName, a.value);
    }
    for (const c of n.childNodes) { const k = clone(c); if (k) out.append(k); }
    return out;
  }
  const el = clone(doc.documentElement); if (!el) return '';
  if (!el.getAttribute('viewBox')) el.setAttribute('viewBox', `0 0 ${parseFloat(el.getAttribute('width')) || 400} ${parseFloat(el.getAttribute('height')) || 240}`);
  el.removeAttribute('width'); el.removeAttribute('height');
  return el.outerHTML;
}

const api = { svg, plot, graph, flow, parse };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.TutorDraw = api;
})(typeof window !== 'undefined' ? window : globalThis);
