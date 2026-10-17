#!/usr/bin/env python3
"""Leftover finder: things drawn in one beat that are still on the stage (or still moving) after a scene change.

    # serve the site first:  python3 .claude/skills/papermorph/scripts/serve.py 8766 site
    uv run --with playwright SKILL/scripts/leftovers.py --book <book> --ch ch01     # run from the project root
    uv run --with playwright SKILL/scripts/leftovers.py --book <book> --all          # every chapter with a finished page
    ... --browser firefox | --url http://localhost:8766/<book>/ | --times 1 3 | --no-shots
    --book may be omitted when site/ holds exactly one book.

How it works. A lesson beat that calls panel() declares "new picture": the engine retires the previous panel group.
Anything that was visible at the end of beat k, is NOT inside that retired panel (appended to #scene, S.line, S.list,
S.venn, a camera or another persistent layer, or never hidden) and is still visible 1 s and 3 s into beat k+1 is a leftover.
The page is driven in-process like the live player: seek(k) to the end of beat k, then start(k+1) on the same DOM
(no rebuild), so node identity survives the boundary. The last panel() time of the beat is respected
(sampling waits 0.8 s after it). Survivors are grouped by their top-level layer under #scene and also flagged
"moving" if their box shifts between the samples. Visible = opacity (attribute x style x ancestors) >= .05, no
display:none / visibility:hidden, painted (fill or stroke), >= 4 stage px, intersecting the 1600x900 stage.

Not leftovers (by design):
  * nodes (or their ancestors/descendants) that beat k+1 itself brings back: a tween in k+1 with a target o/s/d > 0;
  * nodes inside, or marked with, data-keep (convention below);
  * full-stage backgrounds (>= 95% of the stage), question cards (#ui, .qlayer), beats k+1 that are questions.
Beats that do not call panel() continue the picture on purpose, so they are not checked.

Persistent-on-purpose convention: set  el.setAttribute('data-keep', 'why')  on the element or any ancestor
(e.g. a stack-map strip carried through the scene change). Everything else that survives a panel() is reported.

Within-beat mode (--within): ordinary playback, not scene changes. Each beat is replayed from a fresh seek and stepped through the
beat clock like the live player (--dt, default 1/60 s: some bugs only show at frame boundaries), sampled every --step s (default
.25) plus at every [[mark]] time of timings.js. Per visible element: lifetime, "actor" (nearest ancestor with an opacity tween),
"cohort" (actors with the same parent and same shape: siblings created by one helper). Findings:
  HIDE-IGNORED  a scheduled hide(o:0) is over (>= .3 s ago) and nothing re-shows it later, but it is still visible. Typical cause: an
                earlier, longer tween on the same property finishing AFTER the hide (e.g. pop() 0.45 s + hide() starting at +.34).
  TWEEN-INVERSION  (static, frame independent) two tweens on one element and key overlap, the earlier one ends last with another
                value: its final write wins whenever a frame lands between the two ends. The root-cause pattern of HIDE-IGNORED.
  ORPHAN        >= 60% of a cohort (>= 3) has faded, a member is still visible 1.5 s later to the end of the beat and nothing is
                scheduled to hide it.
  REAPPEAR      hidden >= .4 s then visible again with no tween that shows it.
  STRAY         visible outside every panel() group (never data-keep), or inside a panel replaced mid-beat, 1.2 s after the replacement.
  MOVING        still moving >= 1.5 s after >= 70% of its cohort stopped, in a motion that began before they stopped.
data-keep (element or ancestor) is skipped. Output: books/<book>/review/chNN/leftovers-within/ (annotated PNG per finding
cluster: *_after.png at the flagged time, *_before.png earlier), books/<book>/review/leftovers-within.json, and with --all
leftovers-within-summary.md. Exit 1 on any finding. Usage:  leftovers.py --within --ch ch01  |  --within --all  [--url ... | BASE env]

Output: per-chapter report on stdout; annotated PNG per boundary in books/<book>/review/chNN/leftovers/
(red boxes numbered as in the report; orange = moving). Exit status 1 when any finding exists. Browsers are muted
(Chromium --mute-audio, Firefox media.volume_scale=0.0).
"""
import argparse, ast, asyncio, json, os, re, sys, urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path.cwd()   # run from the project root (the folder with site/, books/, content/, tools/)


def _book():
    for i, a in enumerate(sys.argv):
        if a == "--book" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith("--book="):
            return a.split("=", 1)[1]
    found = [p.parent.parent.name for p in (ROOT / "site").glob("*/lib/engine.js")] if (ROOT / "site").is_dir() else []
    if os.environ.get("BOOK"):
        return os.environ["BOOK"]
    if len(found) == 1:
        return found[0]
    sys.exit("give --book <book> (books found in site/: %s)" % (", ".join(found) or "none; run from the project root"))


BOOK = _book()
SITE = ROOT / "site" / BOOK
REVIEW = ROOT / "books" / BOOK / "review"

INSTALL = r"""
() => {
  if (window.__lf) return;
  window.__lf = true;
  const op = window.panel;
  window.__pts = [];
  window.__pnl = [];
window.panel = function (t0) { window.__pts.push(t0 ?? 0); const el = op.apply(this, arguments); window.__pnl.push({ el, t0: t0 ?? 0, run: window.__run }); return el; };
  const orr = window.runBeat;
  window.runBeat = function (i) { window.__run = i; return orr.apply(this, arguments); };
}
"""

HELP = r"""
() => {
window.__lfH = (() => {
  const stage = document.getElementById('stage');
  const LEAF = 'text,path,circle,rect,ellipse,line,polygon,polyline,image,use';
  const op = el => {
    let o = 1;
    for (let e = el; e && e !== stage; e = e.parentNode) {
      if (e.nodeType !== 1) break;
      if (e.style) {
        if (e.style.display === 'none' || e.style.visibility === 'hidden') return 0;
        if (e.style.opacity !== '') o *= +e.style.opacity;
      }
      const a = e.getAttribute('opacity'); if (a !== null) o *= +a;
      if (e.getAttribute('display') === 'none') return 0;
      if (o < .05) return 0;
    }
    return o;
  };
  const layerOf = e => { let x = e; while (x.parentNode && x.parentNode !== scene) x = x.parentNode; return x; };
  const kept = e => !!e.closest('[data-keep]');
  const box = e => {
    const sr = stage.getBoundingClientRect(), r = e.getBoundingClientRect(), k = 1600 / sr.width;
    return { x: (r.left - sr.left) * k, y: (r.top - sr.top) * k, w: r.width * k, h: r.height * k };
  };
  const painted = e => {
    if (e.tagName === 'image') return true;
    const cs = getComputedStyle(e), f = cs.fill, s = cs.stroke;
    const hasF = f && f !== 'none' && !/rgba\(.*, 0\)/.test(f);
    const hasS = s && s !== 'none' && parseFloat(cs.strokeWidth) > 0 && !/rgba\(.*, 0\)/.test(s);
    return hasF || hasS;
  };
  const visible = () => {
    const out = new Map();
    for (const e of scene.querySelectorAll(LEAF)) {
      if (e.closest('.qlayer') || e.closest('defs,clipPath,mask,marker')) continue;
      if (e.tagName === 'text' && !e.textContent.trim()) continue;
      if (op(e) < .05) continue;
      const b = box(e);
      if (b.w < 4 && b.h < 4) continue;
      if (b.x + b.w < 0 || b.y + b.h < 0 || b.x > 1600 || b.y > 900) continue;
      if (b.w >= 1520 && b.h >= 855) continue;   // full-stage background
      if (!painted(e)) continue;
      out.set(e, b);
    }
    return out;
  };
  return { op, layerOf, kept, box, visible };
})();
}
"""

# Phase 1 for a lesson beat k: play it to its end, remember what is visible, begin beat k+1 on the same DOM.
PRE_LESSON = r"""
(k) => {
  const H = window.__lfH;
  seeking = false;
  seek(k, false);
  evalTo(Infinity);
  window.__A = H.visible();                    // visible at the end of beat k
  window.__oldPanel = S.panel;
  window.__pts = [];
  seeking = true;                              // an old panel goes at once, as its 150 ms wall-clock fade would
  start(k + 1, false);
  seeking = false;
}
"""

# Phase 1a/1b for a question beat k: open the card; once answered, remember the picture and clear the pts.
ASK_OPEN = "(k) => { seeking = false; seek(k, true); }"
ASK_REMEMBER = """() => {
  const H = window.__lfH;
  finishFx(); evalTo(Infinity);                // answer effects done, as when the reader moves on
  window.__A = H.visible(); window.__oldPanel = S.panel; window.__pts = [];
}"""

# Phase 2: sample beat k+1 at the given times and report survivors of the scene change.
POST = r"""
([k, times]) => {
  const H = window.__lfH, A = window.__A, oldPanel = window.__oldPanel;
  setPlaying(false);
  const pre = BEATS[k + 1];
  seeking = true;
  const clears = !!S.cleared && !pre.ask && pre.id !== 'finish' && P.i === k + 1;
  const res = { k, id: BEATS[k].id, next: pre.id, clears, dur: P.end, groups: [] };
  if (!clears) { seeking = false; return res; }
  const pts = window.__pts.filter(t => t >= 0);
  const lastPanel = pts.length ? Math.max(...pts) : 0;
  const owned = new Set();   // elements the new beat deliberately brings back
  for (const w of TW) if (w.e && ((w.to.o > 0) || (w.to.s > 0) || (w.to.d > 0))) owned.add(w.e);
  const ownedHit = e => {
    for (let x = e; x && x !== scene; x = x.parentNode) if (owned.has(x)) return true;
    for (const o of owned) if (e.contains(o)) return true;
    return false;
  };
  const ts = times.map(t => Math.min(Math.max(t, lastPanel + .8), Math.max(P.end - .2, 0.2)));
  const seen = new Map();
  const bySample = [];
  for (const t of ts) {
    P.t = t; evalTo(t);
    const V = H.visible(), hit = [];
    for (const [e, b] of V) {
      if (!A.has(e) || H.kept(e) || ownedHit(e)) continue;
      hit.push(e);
      if (!seen.has(e)) seen.set(e, []);
      seen.get(e).push(b);
    }
    bySample.push({ t, els: hit });
  }
  seeking = false;
  const groups = new Map();
  for (const e of seen.keys()) {
    const L = H.layerOf(e);
    if (!groups.has(L)) groups.set(L, []);
    groups.get(L).push(e);
  }
  let gi = 0;
  for (const [L, els] of groups) {
    const bb = els.map(e => seen.get(e)[0]);
    const x0 = Math.min(...bb.map(b => b.x)), y0 = Math.min(...bb.map(b => b.y));
    const x1 = Math.max(...bb.map(b => b.x + b.w)), y1 = Math.max(...bb.map(b => b.y + b.h));
    let moving = 0, dist = 0;
    for (const e of els) {
      const s = seen.get(e); if (s.length < 2) continue;
      const a = s[0], b = s[s.length - 1];
      const d = Math.hypot((a.x + a.w / 2) - (b.x + b.w / 2), (a.y + a.h / 2) - (b.y + b.h / 2));
      if (d > 3) { moving++; dist = Math.max(dist, d); }
    }
    const texts = [...new Set(els.filter(e => e.tagName === 'text').map(e => e.textContent.trim()).filter(Boolean))].slice(0, 6);
    res.groups.push({
      gi: gi++, leaves: els.length, texts, kinds: [...new Set(els.map(e => e.tagName))].join(','),
      box: [Math.round(x0), Math.round(y0), Math.round(x1 - x0), Math.round(y1 - y0)],
      moving, dist: Math.round(dist), times: bySample.filter(s => s.els.some(e => L.contains(e))).map(s => +s.t.toFixed(2)),
      inOldPanel: oldPanel ? oldPanel.contains(L) : false,
      layer: L.tagName + `#${[...scene.children].indexOf(L)}`,
    });
  }
  res.shotTimes = bySample.filter(s => s.els.length).map(s => +s.t.toFixed(2));
  return res;
}
"""

ANNOT = r"""
([t, groups]) => {
  P.t = t; evalTo(t);
  document.querySelectorAll('.__lfa').forEach(n => n.remove());
  const sr = document.getElementById('stage').getBoundingClientRect(), k = sr.width / 1600;
  groups.forEach((g, i) => {
    const [x, y, w, h] = g.box;
    const d = document.createElement('div'); d.className = '__lfa';
    const c = g.moving ? '#ff9f1a' : '#ff2d55';
    d.style.cssText = `position:fixed;pointer-events:none;z-index:99999;border:3px solid ${c};left:${sr.left + x * k - 3}px;top:${sr.top + y * k - 3}px;width:${w * k + 6}px;height:${h * k + 6}px;`;
    const l = document.createElement('div');
    l.textContent = `${i + 1}`;
    l.style.cssText = `position:absolute;left:-3px;top:-24px;background:${c};color:#fff;font:700 16px sans-serif;padding:1px 7px;border-radius:3px`;
    d.appendChild(l); document.body.appendChild(d);
  });
}
"""


# ---- within-beat mode ----------------------------------------------------------------------------------------------
# Replays beat k from a fresh seek, stepping the beat clock like the player; samples visibility; returns clustered findings.
WITHIN = r"""
([k, dt, step]) => {
  const H = window.__lfH;
  seeking = false; seek(k, false); setPlaying(false);
  const b = BEATS[k], tm = TIMINGS[b.id], end = P.end;
  const LEAF = 'text,path,circle,rect,ellipse,line,polygon,polyline,image,use';
  // ---- tween index
  const byE = new Map();
  for (const w of TW) if (w.e) { if (!byE.has(w.e)) byE.set(w.e, []); byE.get(w.e).push(w); }
  const oEls = new Set(); for (const w of TW) if (w.e && 'o' in w.to) oEls.add(w.e);
  const uidM = new Map(); const uid = e => { if (!uidM.has(e)) uidM.set(e, uidM.size); return uidM.get(e); };
  const chainM = new Map();
  const chain = e => { let c = chainM.get(e); if (!c) { c = []; for (let x = e; x && x !== scene; x = x.parentNode) c.push(x); chainM.set(e, c); } return c; };
  const twsM = new Map();
  const tws = e => { let r = twsM.get(e); if (!r) { r = []; for (const x of chain(e)) if (byE.has(x)) r.push(...byE.get(x)); twsM.set(e, r); } return r; };
  const actorM = new Map();
  const actorOf = e => { let a = actorM.get(e); if (a) return a; a = e; for (const x of chain(e)) if (oEls.has(x)) { a = x; break; } actorM.set(e, a); return a; };
  const leafSig = a => a.tagName + ':' + [...(a.matches && a.matches(LEAF) ? [a] : a.querySelectorAll(LEAF))].map(x => x.tagName).sort().join(',');
  const panels = (window.__pnl || []).filter(p => p.run === k);
  const allPanels = new Set((window.__pnl || []).map(p => p.el));
  const lastPanel = panels.length ? panels[panels.length - 1] : null;
  const painted = e => {
    if (e.tagName === 'image') return true;
    const cs = getComputedStyle(e), f = cs.fill, s = cs.stroke;
    return (f && f !== 'none' && !/rgba\(.*, 0\)/.test(f)) || (s && s !== 'none' && parseFloat(cs.strokeWidth) > 0 && !/rgba\(.*, 0\)/.test(s));
  };
  const paintM = new Map();
  // ---- static: overlapping tweens whose earlier one ends last with a different value
  const inversions = [];
  for (const [e, L] of byE) {
    if (e.closest && e.closest('[data-keep]')) continue;
    for (let i = 0; i < L.length; i++) for (let j = 0; j < L.length; j++) {
      const u = L[i], w = L[j];
      if (u === w || !(u.t0 < w.t0) || !(u.t0 + u.dur > w.t0) || !(u.t0 + u.dur > w.t0 + w.dur + 1e-6)) continue;
      const keys = Object.keys(w.to).filter(kk => kk in u.to && typeof w.to[kk] === 'number' && Math.abs(w.to[kk] - u.to[kk]) > .01);
      if (!keys.length) continue;
      inversions.push({ e, keys, uEnd: u.t0 + u.dur, wEnd: w.t0 + w.dur, wT0: w.t0, uT0: u.t0, uto: keys.map(kk => u.to[kk]), wto: keys.map(kk => w.to[kk]) });
    }
  }
  // ---- sampling
  const marks = Object.values(tm.marks).filter(x => x >= 0 && x <= end);
  const want = new Set();
  for (let t = 0; t <= end + 1e-9; t += step) want.add(+t.toFixed(3));
  marks.forEach(m => { want.add(+m.toFixed(3)); want.add(+(m + .2).toFixed(3)); });
  want.add(+(Math.max(0, end - .45)).toFixed(3));
  const times = [...want].sort((a, c) => a - c).filter((x, i, A) => i === 0 || x - A[i - 1] > .06);
  const recs = new Map(); const samples = [];
  const stage = document.getElementById('stage');
  const sample = (t, j) => {
    const vis = new Set(); const sr = stage.getBoundingClientRect(), kk = 1600 / sr.width;
    for (const e of scene.querySelectorAll(LEAF)) {
      if (e.closest('.qlayer') || e.closest('defs,clipPath,mask,marker')) continue;
      const rec0 = recs.get(e);
      let on = false, bx = null;
      if (!(e.tagName === 'text' && !e.textContent.trim()) && H.op(e) >= .05) {
        let pt = paintM.get(e); if (pt === undefined) { pt = painted(e); paintM.set(e, pt); }
        if (pt) {
          const r = e.getBoundingClientRect(); bx = { x: (r.left - sr.left) * kk, y: (r.top - sr.top) * kk, w: r.width * kk, h: r.height * kk };
          on = !(bx.w < 4 && bx.h < 4) && !(bx.w >= 1520 && bx.h >= 855);
        }
      }
      if (!on) { if (rec0 && rec0.on) { rec0.on = false; rec0.ivs[rec0.ivs.length - 1][1] = rec0.lastT; } continue; }
      if (H.kept(e)) continue;
      let rec = rec0;
      if (!rec) { rec = { e, on: false, ivs: [], boxes: [], first: t, text: e.tagName === 'text' ? e.textContent : null, dyn: false }; recs.set(e, rec); }
      if (e.tagName === 'text' && rec.text !== e.textContent) rec.dyn = true;
      if (!rec.on) { rec.on = true; rec.ivs.push([t, t]); }
      rec.lastT = t; rec.ivs[rec.ivs.length - 1][1] = t;
      rec.boxes[j] = bx;
      rec.onscreen = !(bx.x + bx.w < 0 || bx.y + bx.h < 0 || bx.x > 1600 || bx.y > 900);
      vis.add(e);
    }
    samples.push({ t, vis });
  };
  { let ji = 0;
    P.t = 0; evalTo(0);
    for (let t = 0; t <= end + 1e-9 && ji < times.length; t += dt) {
      P.t = t; evalTo(t);
      while (ji < times.length && times[ji] <= t + 1e-9) { sample(t, ji); ji++; }
    }
  }
  const NS = samples.length, T = samples.map(s => s.t);
  const lastJ = NS - 1;
  const visAt = (e, j) => samples[j].vis.has(e);
  const actVis = new Map();   // actor -> bool[]
  for (const [e] of recs) { const a = actorOf(e); if (!actVis.has(a)) actVis.set(a, new Array(NS).fill(false)); }
  for (let j = 0; j < NS; j++) for (const e of samples[j].vis) actVis.get(actorOf(e))[j] = true;
  const findings = [];
  const unionBox = els => {
    const bb = els.map(e => { const r = recs.get(e); if (!r) return null; for (let j = lastJ; j >= 0; j--) if (r.boxes[j]) return r.boxes[j]; return null; }).filter(Boolean);
    if (!bb.length) return [0, 0, 10, 10];
    const x0 = Math.min(...bb.map(q => q.x)), y0 = Math.min(...bb.map(q => q.y)), x1 = Math.max(...bb.map(q => q.x + q.w)), y1 = Math.max(...bb.map(q => q.y + q.h));
    return [Math.round(x0), Math.round(y0), Math.round(x1 - x0), Math.round(y1 - y0)];
  };
  const boxAt = (els, j) => {
    const bb = els.map(e => recs.get(e) && recs.get(e).boxes[j]).filter(Boolean);
    if (!bb.length) return null;
    const x0 = Math.min(...bb.map(q => q.x)), y0 = Math.min(...bb.map(q => q.y)), x1 = Math.max(...bb.map(q => q.x + q.w)), y1 = Math.max(...bb.map(q => q.y + q.h));
    return [Math.round(x0), Math.round(y0), Math.round(x1 - x0), Math.round(y1 - y0)];
  };
  const texts = els => [...new Set(els.filter(e => e.tagName === 'text').map(e => e.textContent.trim()).filter(Boolean))].slice(0, 6);
  const kinds = els => [...new Set(els.map(e => e.tagName))].join(',');
  // cluster by (kind, parent of actor)
  const clusters = new Map();
  const add = (kind, leaf, t, extra = {}) => {
    const a = actorOf(leaf), key = kind + '|' + uid(a.parentNode || a);
    if (!clusters.has(key)) clusters.set(key, { kind, t, leaves: [], actors: new Set(), ...extra });
    const c = clusters.get(key); c.leaves.push(leaf); c.actors.add(a); c.t = Math.min(c.t, t);
    if (extra.before !== undefined) c.before = Math.min(c.before ?? 1e9, extra.before);
  };
  // HIDE-IGNORED
  for (const [e, rec] of recs) {
    if (!rec.on || rec.dyn) continue;              // visible at the last sample
    if (!rec.onscreen) continue;
    const L = tws(e);
    let best = null;
    for (const w of L) {
      if (w.to.o !== 0) continue;
      const wEnd = w.t0 + w.dur;
      if (L.some(u => u !== w && (u.to.o > 0 || u.to.d > 0) && u.t0 >= w.t0 - 1e-6)) continue;   // shown again on purpose
      if (!best || wEnd > best.wEnd) best = { w, wEnd };
    }
    if (!best) continue;
    // first sample >= hide end + .3 from which it is visible to the end
    let j0 = T.findIndex(t => t >= best.wEnd + .3);
    if (j0 < 0 || j0 >= lastJ) continue;
    let ok = true; for (let j = j0; j <= lastJ; j++) if (!visAt(e, j)) { ok = false; break; }
    if (!ok) continue;
    add('HIDE-IGNORED', e, T[j0], { before: Math.max(0, best.w.t0 - .1), why: `hide at ${best.w.t0.toFixed(2)}+${best.w.dur} ignored` });
  }
  // ORPHAN: a cohort (same parent, same shape and size, >= 4 members) where >= 75% were hidden by explicit hide tweens
  // and one or two never got a hide at all (forgotten in a loop), still visible 1.5 s after the last hide, not replacing a hidden sibling in place.
  const leavesOf = new Map();
  for (const e of recs.keys()) { const a = actorOf(e); if (!leavesOf.has(a)) leavesOf.set(a, []); leavesOf.get(a).push(e); }
  const aSize = a => {
    const v = actVis.get(a), j = v.findIndex(Boolean); if (j < 0) return '';
    const bb = leavesOf.get(a).map(e => recs.get(e).boxes[j]).filter(Boolean); if (!bb.length) return '';
    const x0 = Math.min(...bb.map(q => q.x)), y0 = Math.min(...bb.map(q => q.y)), x1 = Math.max(...bb.map(q => q.x + q.w)), y1 = Math.max(...bb.map(q => q.y + q.h));
    return Math.round((x1 - x0) / 12) + 'x' + Math.round((y1 - y0) / 12);
  };
  const cohorts = new Map();
  for (const a of actVis.keys()) {
    if (!oEls.has(a) || H.kept(a)) continue;
    const key = uid(a.parentNode || a) + '|' + leafSig(a) + '|' + aSize(a);
    if (!cohorts.has(key)) cohorts.set(key, []);
    cohorts.get(key).push(a);
  }
  const hideOf = a => { let best = null; for (const w of tws(a)) if (w.to.o === 0 && (!best || w.t0 + w.dur > best.t0 + best.dur)) best = w; return best; };
  for (const [key, M] of cohorts) {
    const ever = M.filter(a => actVis.get(a).some(Boolean));
    if (ever.length < 4) continue;
    const hid = ever.filter(a => hideOf(a)), nohide = ever.filter(a => !hideOf(a) && actVis.get(a)[lastJ]);
    if (!nohide.length || nohide.length > .25 * ever.length || hid.length < .75 * ever.length) continue;
    const ends = hid.map(a => { const w = hideOf(a); return w.t0 + w.dur; }).sort((x, y) => x - y);
    const Tq = ends[Math.ceil(.75 * ends.length) - 1];
    const j1 = T.findIndex(t => t >= Tq + 1.5);
    if (j1 < 0) continue;
    const ctr = a => { const v = actVis.get(a), j = v.lastIndexOf(true), bb = leavesOf.get(a).map(e => recs.get(e).boxes[j]).filter(Boolean);
      const x0 = Math.min(...bb.map(q => q.x)), y0 = Math.min(...bb.map(q => q.y)), x1 = Math.max(...bb.map(q => q.x + q.w)), y1 = Math.max(...bb.map(q => q.y + q.h));
      return [(x0 + x1) / 2, (y0 + y1) / 2, Math.max(x1 - x0, y1 - y0) / 2]; };
    for (const a of nohide) {
      const ca = ctr(a);
      if (hid.some(h => { const ch = ctr(h); return Math.hypot(ca[0] - ch[0], ca[1] - ch[1]) < Math.max(10, ca[2] * .6); })) continue;   // replaces a hidden sibling in place (a value that changed)
      const v = actVis.get(a); let ok = true; for (let j = j1; j <= lastJ; j++) if (!v[j]) { ok = false; break; }
      if (!ok) continue;
      const leaf = leavesOf.get(a).find(e => recs.get(e).onscreen); if (!leaf) continue;
      add('ORPHAN', leaf, T[j1], { before: Math.max(0, Tq - .6), why: `${hid.length} of ${ever.length} like it were hidden by ${Tq.toFixed(2)}, this one has no hide` });
    }
  }
  // REAPPEAR: a scheduled hide ended, and the element is back with no tween that shows it (a later, longer tween overwrote the hide)
  for (const [e, rec] of recs) {
    if (rec.dyn || rec.ivs.length < 2) continue;
    const L = tws(e);
    for (let i = 1; i < rec.ivs.length; i++) {
      const gs = rec.ivs[i - 1][1], gr = rec.ivs[i][0];
      if (gr - gs < .39) continue;
      const hw = L.find(w => w.to.o === 0 && w.t0 + w.dur >= gs - .6 && w.t0 + w.dur <= gr + .05);
      if (!hw) continue;
      if (L.some(w => (w.to.o > 0 || w.to.d > 0 || w.to.s > 0) && w.t0 > hw.t0 - 1e-6 && w.t0 <= gr + .05)) continue;
      add('REAPPEAR', e, gr, { before: gs - .2, why: `hidden ${gs.toFixed(2)}-${gr.toFixed(2)}, back with no show tween` });
      break;
    }
  }
  // STRAY
  for (const [e, rec] of recs) {
    if (!panels.length || rec.ivs[0][0] <= 0 || !rec.onscreen) continue;
    let layer = e; while (layer.parentNode && layer.parentNode !== scene) layer = layer.parentNode;
    if (e.closest('#ui')) continue;
    if (!allPanels.has(layer)) {
      const span = rec.ivs.reduce((s, v) => s + (v[1] - v[0]), 0);
      if (span >= 2) add('STRAY', e, rec.ivs[0][0] + 2, { before: rec.ivs[0][0] + .3, why: 'outside every panel() group' });
    } else if (lastPanel && layer !== lastPanel.el && panels.some(p => p.el === layer) && lastPanel.t0 >= .5) {
      const jj = T.findIndex(t => t >= lastPanel.t0 + 1.2);
      if (jj >= 0 && visAt(e, jj)) add('STRAY', e, T[jj], { before: lastPanel.t0 - .2, why: `inside a panel replaced at ${lastPanel.t0.toFixed(2)}` });
    }
  }
  // MOVING
  const moving = new Map();
  for (const [e, rec] of recs) {
    const m = new Array(NS).fill(false);
    for (let j = 1; j < NS; j++) {
      const a = rec.boxes[j], p = rec.boxes[j - 1];
      if (a && p && Math.hypot((a.x + a.w / 2) - (p.x + p.w / 2), (a.y + a.h / 2) - (p.y + p.h / 2)) > 3) m[j] = true;
    }
    moving.set(e, m);
  }
  const aMoving = new Map();
  for (const a of actVis.keys()) { const m = new Array(NS).fill(false); for (const [e, mm] of moving) if (actorOf(e) === a) for (let j = 0; j < NS; j++) if (mm[j]) m[j] = true; aMoving.set(a, m); }
  for (const [key, M] of cohorts) {
    const Mm = M.filter(a => aMoving.get(a).some(Boolean));
    if (Mm.length < 3) continue;
    let Tq = null, jq = -1;
    for (let j = 2; j < NS && Tq === null; j++) {
      const st = Mm.filter(a => { const mv = aMoving.get(a); return !mv[j] && !mv[j - 1] && mv.slice(0, j).some(Boolean); });
      if (st.length >= .7 * Mm.length) { Tq = T[j]; jq = j; }
    }
    if (Tq === null) continue;
    const j1 = T.findIndex(t => t >= Tq + 1.5);
    if (j1 < 0 || j1 + 1 > lastJ) continue;
    for (const a of Mm) {
      const mv = aMoving.get(a);
      if (!(mv[j1] && mv[j1 + 1] && actVis.get(a)[j1])) continue;
      let s0 = j1; while (s0 > 0 && mv[s0 - 1]) s0--;
      if (T[s0] > Tq) continue;
      const leaf = [...recs.keys()].find(e => actorOf(e) === a && moving.get(e)[j1]); if (!leaf) continue;
      add('MOVING', leaf, T[j1], { before: Math.max(0, Tq - .3), why: `cohort of ${Mm.length} stopped by ${Tq.toFixed(2)}` });
    }
  }
  // result
  const out = [];
  for (const c of clusters.values()) {
    const els = [...new Set(c.leaves)], j = Math.max(0, T.findIndex(t => t >= c.t - 1e-6));
    const sj = Math.min(lastJ, j);
    out.push({ kind: c.kind, t: +c.t.toFixed(2), before: +Math.max(0, c.before ?? c.t - 1).toFixed(2), why: c.why || '', leaves: els.length, actors: c.actors.size,
      texts: texts(els), kinds: kinds(els), box: boxAt(els, sj) || unionBox(els) });
  }
  const inv = [];
  const seen = new Set();
  for (const q of inversions) {
    const a = actorOf(q.e), key = uid(a.parentNode || a) + '|' + q.keys.join();
    if (seen.has(key)) { const r = inv.find(z => z.key === key); r.n++; continue; }
    seen.add(key);
    const r = { key, n: 1, keys: q.keys, uT0: +q.uT0.toFixed(2), uEnd: +q.uEnd.toFixed(2), wT0: +q.wT0.toFixed(2), wEnd: +q.wEnd.toFixed(2), uto: q.uto, wto: q.wto,
      texts: texts([...q.e.querySelectorAll ? [...q.e.querySelectorAll('text'), ...(q.e.tagName === 'text' ? [q.e] : [])] : []]), tag: q.e.tagName };
    const L = q.e.getBoundingClientRect(), sr = stage.getBoundingClientRect(), kk = 1600 / sr.width;
    r.box = [Math.round((L.left - sr.left) * kk), Math.round((L.top - sr.top) * kk), Math.round(L.width * kk), Math.round(L.height * kk)];
    inv.push(r);
  }
  return { k, id: b.id, dur: P.end, nSamples: NS, findings: out, inversions: inv };
}
"""

# Re-run beat k to time t on the same frame grid and draw boxes (red); then the caller takes a screenshot.
WITHIN_AT = r"""
([k, t, dt, boxes, color]) => {
  seeking = false; seek(k, false); setPlaying(false);
  P.t = 0; evalTo(0);
  for (let x = 0; x <= t + 1e-9; x += dt) { P.t = x; evalTo(x); }
  document.querySelectorAll('.__lfa').forEach(n => n.remove());
  document.querySelectorAll('.paused-mark').forEach(n => { n.style.display = 'none'; });
  const sr = document.getElementById('stage').getBoundingClientRect(), s = sr.width / 1600;
  boxes.forEach((bx, i) => {
    if (!bx) return;
    const [x, y, w, h] = bx, c = color;
    const d = document.createElement('div'); d.className = '__lfa';
    d.style.cssText = `position:fixed;pointer-events:none;z-index:99999;border:3px solid ${c};left:${sr.left + x * s - 3}px;top:${sr.top + y * s - 3}px;width:${w * s + 6}px;height:${h * s + 6}px;`;
    const l = document.createElement('div'); l.textContent = `${i + 1}`;
    l.style.cssText = `position:absolute;left:-3px;top:-24px;background:${c};color:#fff;font:700 16px sans-serif;padding:1px 7px;border-radius:3px`;
    d.appendChild(l); document.body.appendChild(d);
  });
}
"""


def rel(p):
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def server_ok(url):
    try:
        urllib.request.urlopen(url + "ch01/index.html", timeout=3)
        return True
    except Exception:
        return False


async def launch(p, browser):
    if browser == "firefox":
        return await p.firefox.launch(firefox_user_prefs={"media.volume_scale": "0.0"})
    return await p.chromium.launch(args=["--mute-audio"])


def load_answers(ch):
    """Question beat id -> key script, taken from the chapter's e2e test (tools/<book>/e2e_chNN.py)."""
    f = ROOT / "tools" / BOOK / f"e2e_{ch}.py"
    if not f.is_file():
        return {}
    tree = ast.parse(f.read_text())
    keep = [n for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id in ("R", "L", "ANSWERS", "PRACTICE") or
        isinstance(t, ast.Tuple) and any(isinstance(e, ast.Name) and e.id in ("R", "L") for e in t.elts) for t in n.targets)]
    env = {}
    try:
        exec(compile(ast.Module(body=keep, type_ignores=[]), str(f), "exec"), env)
    except Exception:
        return {}
    out = dict(env.get("ANSWERS", {}))
    if "final1" not in out and "PRACTICE" in env:
        out["final1"] = env["PRACTICE"]
    return out


async def answer(pg, steps):
    """Answer a question beat's cards with the e2e key scripts ('k:a,b', '=x,y', or a single key). True when all correct."""
    key = pg.keyboard.press
    for si, s in enumerate(steps):
        if s.startswith("w:"):     # a wrong try first: its feedback effects are part of the picture too
            ks = [x for x in s[2:].split("|")[0].split(",") if x]
            for kk in ks:
                await key(kk)
            await key("Enter")
            await pg.wait_for_timeout(300)
            for _ in ks:
                await key("Backspace")
            continue
        if s[:2] in ("e:", "x:"):   # wrong typed value(s) in the boxes
            for j, v in enumerate(s[2:].split("|")[0].split(",")):
                await pg.locator(".card input.box").nth(j).fill(v)
            await key("Enter")
            await pg.wait_for_timeout(300)
            continue
        if s.startswith("="):
            for j, v in enumerate(s[1:].split(",")):
                await pg.locator(".card input.box").nth(j).fill(v)
            await key("Enter")
        elif s.startswith("k:"):
            for kk in s[2:].split(","):
                await key(kk)
            await key("Enter")
        else:
            await key(s)
        await pg.wait_for_timeout(200)
        try:
            fb = await pg.inner_text(".card .fb", timeout=1500)
        except Exception:
            return False
        if "Correct" not in fb:
            return False
        if si < len(steps) - 1:
            await key("Enter")
            await pg.wait_for_timeout(250)
    return True


async def boundary(pg, k, bid, is_ask, answers, a):
    """Run the beat k -> k+1 probe; a question beat is answered first (its answer effects are part of its picture)."""
    if is_ask and bid in answers:
        await pg.evaluate(ASK_OPEN, k)
        await pg.wait_for_timeout(300)
        try:
            solved = await answer(pg, answers[bid])
        except Exception as e:
            solved = False
            print(f"   [{bid}] answer script failed ({str(e)[:70]}); checking the unanswered picture")
        if solved:
            await pg.evaluate(ASK_REMEMBER)
            await pg.keyboard.press("Enter")        # continue: the player starts beat k+1 from the picture it has
            await pg.wait_for_timeout(250)
            r = await pg.evaluate(POST, [k, a.times])
            r["answered"] = True
            return r
    await pg.evaluate(PRE_LESSON, k)
    return await pg.evaluate(POST, [k, a.times])


async def check_chapter(pg, ch, a):
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    await pg.goto(f"{a.url}{ch}/index.html?beat=0&t=0")
    await pg.wait_for_timeout(500)
    if errs or not await pg.evaluate("typeof BEATS !== 'undefined' && BEATS.length > 0 && typeof seek === 'function'"):
        return None, f"page not ready ({errs[:1] or 'no BEATS'})"
    try:
        ok = await pg.evaluate("BEATS.every(b => TIMINGS[b.id] && TIMINGS[b.id].dur > 0)")
    except Exception as e:
        return None, f"timings missing ({str(e)[:80]})"
    if not ok:
        return None, "timings incomplete (chapter still in build)"
    await pg.evaluate(INSTALL)
    await pg.evaluate(HELP)
    await pg.evaluate("hideCover()")
    n = await pg.evaluate("BEATS.length")
    out = Path(a.out_root) / ch / "leftovers"
    if a.shots:
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.png"):
            old.unlink()
    findings = []
    ids = await pg.evaluate("BEATS.map(b => b.id)")
    asks = await pg.evaluate("BEATS.map(b => !!b.ask)")
    answers = load_answers(ch)
    for k in range(n - 1):
        try:
            r = await boundary(pg, k, ids[k], asks[k], answers, a)
        except Exception as e:
            findings.append({"k": k, "error": str(e)[:200], "groups": []})
            continue
        if a.verbose:
            print(f"   [{ch}] {k:2d} {r['id']:>10} -> {r['next']:<10} checked={r['clears']} answered={r.get('answered', '-')}")
        if not r["groups"]:
            continue
        r["shot"] = None
        if a.shots:
            t = r["shotTimes"][-1]
            await pg.evaluate(ANNOT, [t, r["groups"]])
            f = out / f"b{k:02d}-{k + 1:02d}_{r['id']}__{r['next']}_t{t:.1f}.png"
            await pg.screenshot(path=str(f))
            await pg.evaluate("document.querySelectorAll('.__lfa').forEach(n => n.remove())")
            r["shot"] = rel(f)
        findings.append(r)
    return findings, None


def write_summary(summary, path):
    rows = ["# Leftovers summary (leftovers.py --all)", "",
            "A leftover = visible at the end of a beat, not inside the retired panel, not re-shown by the next beat, still visible 1 s / 3 s after a scene change (panel()). "
            "Question beats are answered with the e2e scripts (wrong try first when scripted) before the boundary is checked.", "",
            "| Chapter | Findings | Worst examples |", "| --- | ---: | --- |"]
    for ch, r in summary.items():
        if "skipped" in r:
            rows.append(f"| {ch} | skipped | {r['skipped']} |")
            continue
        ex = []
        for f in r["findings"]:
            for g in f.get("groups", []):
                txt = " / ".join(g["texts"]) or g["kinds"]
                ex.append(f"beat {f['k']} '{f['id']}' -> '{f['next']}': {g['leaves']}x {txt} at {g['box'][:2]}" + (" (moving)" if g["moving"] else "")
                          + (f" - `{f['shot']}`" if f.get("shot") else ""))
        rows.append(f"| {ch} | {r['count']} | {'<br>'.join(ex[:3]) or '-'} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n")


async def check_within(pg, ch, a):
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    await pg.goto(f"{a.url}{ch}/index.html?beat=0&t=0")
    await pg.wait_for_timeout(500)
    if errs or not await pg.evaluate("typeof BEATS !== 'undefined' && BEATS.length > 0 && typeof seek === 'function'"):
        return None, f"page not ready ({errs[:1] or 'no BEATS'})"
    try:
        ok = await pg.evaluate("BEATS.every(b => TIMINGS[b.id] && TIMINGS[b.id].dur > 0)")
    except Exception as e:
        return None, f"timings missing ({str(e)[:80]})"
    if not ok:
        return None, "timings incomplete (chapter still in build)"
    await pg.evaluate(INSTALL)
    await pg.evaluate(HELP)
    await pg.evaluate("hideCover()")
    n = await pg.evaluate("BEATS.length")
    out = Path(a.out_root) / ch / "leftovers-within"
    if a.shots:
        out.mkdir(parents=True, exist_ok=True)
        for old in list(out.glob("b*.png")):
            old.unlink()
    res = []
    for k in range(n):
        if a.beats and k not in a.beats:
            continue
        try:
            r = None
            for dt in a.dt:     # several frame grids: frame-boundary bugs show on some grids only
                q = await pg.evaluate(WITHIN, [k, dt, a.step])
                for f in q["findings"]:
                    f["dt"] = dt
                if r is None:
                    r = q
                    continue
                for f in q["findings"]:
                    for g in r["findings"]:
                        gx, gy, gw, gh = g["box"]; fx, fy, fw, fh = f["box"]
                        if g["kind"] == f["kind"] and fx < gx + gw + 30 and gx < fx + fw + 30 and fy < gy + gh + 30 and gy < fy + fh + 30:
                            x0, y0 = min(gx, fx), min(gy, fy)
                            g["box"] = [x0, y0, max(gx + gw, fx + fw) - x0, max(gy + gh, fy + fh) - y0]
                            g["leaves"] = max(g["leaves"], f["leaves"]); g["actors"] = max(g["actors"], f["actors"])
                            g["texts"] = sorted(set(g["texts"]) | set(f["texts"]))[:6]
                            break
                    else:
                        r["findings"].append(f)
            if r["findings"] and "dt" not in r["findings"][0]:
                for f in r["findings"]:
                    f.setdefault("dt", a.dt[0])
        except Exception as e:
            res.append({"k": k, "error": str(e)[:200], "findings": [], "inversions": []})
            continue
        if a.verbose:
            print(f"   [{ch}] {k:2d} {r['id']:<12} samples={r['nSamples']} findings={len(r['findings'])} inversions={len(r['inversions'])}")
        for i, f in enumerate(r["findings"][: a.max_shots]):
            f["shot"] = None
            if a.shots:
                base = out / f"b{k:02d}_{r['id']}_{f['kind'].lower()}{i + 1}"
                await pg.evaluate(WITHIN_AT, [k, f["before"], f["dt"], [f["box"]], "#2d9cff"])
                await pg.screenshot(path=f"{base}_before.png")
                await pg.evaluate(WITHIN_AT, [k, f["t"], f["dt"], [f["box"]], "#ff2d55"])
                await pg.screenshot(path=f"{base}_after.png")
                f["shot"] = rel(Path(f"{base}_after.png"))
        res.append(r)
    await pg.evaluate("document.querySelectorAll('.__lfa').forEach(n => n.remove())")
    return res, None


def fmt_f(f):
    tx = (" text: " + " | ".join(f["texts"])) if f["texts"] else ""
    return (f"{f['kind']:<13} t={f['t']}s {f['leaves']}x {f['kinds']} ({f['actors']} actor) box={f['box']} - {f['why']}{tx}"
            + (f"\n        shot: {f['shot']}" if f.get("shot") else ""))


def fmt_inv(q):
    tx = (" text: " + " | ".join(q["texts"])) if q["texts"] else ""
    return (f"TWEEN-INVERSION {q['n']}x <{q['tag']}> {','.join(q['keys'])}: tween {q['uT0']}->{q['uEnd']} (to {q['uto']}) outlasts later tween "
            f"{q['wT0']}->{q['wEnd']} (to {q['wto']}) box={q['box']}{tx}")


def write_within_summary(summary, path, a):
    rows = ["# Within-beat leftovers summary (leftovers.py --within --all)", "",
            f"Browser {a.browser}, frame steps {', '.join(f'{d * 1000:.1f} ms' for d in a.dt)}, sample step {a.step} s + every [[mark]]. Findings are per cluster (elements sharing a parent group).",
            "HIDE-IGNORED / TWEEN-INVERSION = a scheduled hide is overwritten by an earlier, longer tween on the same element; ORPHAN = cohort mostly faded, "
            "a few stay; REAPPEAR; STRAY (outside panel); MOVING (still moving after cohort).", "",
            "| Chapter | Findings | Inversions | By kind | Worst examples |", "| --- | ---: | ---: | --- | --- |"]
    for ch, r in summary.items():
        if "skipped" in r:
            rows.append(f"| {ch} | skipped | | | {r['skipped']} |")
            continue
        kinds = {}
        ex = []
        for b in r["beats"]:
            for f in b.get("findings", []):
                kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
                txt = " / ".join(f["texts"]) or f["kinds"]
                ex.append((f["leaves"], f"beat {b['k']} '{b['id']}' t={f['t']}: {f['kind']} {f['leaves']}x {txt}" + (f" - `{f['shot']}`" if f.get("shot") else "")))
        ex.sort(key=lambda z: -z[0])
        inv = sum(len(b.get("inversions", [])) for b in r["beats"])
        rows.append(f"| {ch} | {r['count']} | {inv} | {', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) or '-'} | {'<br>'.join(e for _, e in ex[:3]) or '-'} |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n")


async def main_within(a, chs):
    total, summary = 0, {}
    async with async_playwright() as p:
        browser = await launch(p, a.browser)
        for ch in chs:
            pg = await browser.new_page(viewport={"width": 1600, "height": 960})
            try:
                res, why = await check_within(pg, ch, a)
            finally:
                await pg.close()
            if res is None:
                print(f"== {ch}: SKIPPED - {why}")
                summary[ch] = {"skipped": why}
                continue
            for r in res:
                for q in r.get("inversions", []):
                    q["visibility"] = any(kk in ("o", "d") for kk in q["keys"])
            cnt = sum(len(r["findings"]) for r in res) + sum(1 for r in res for q in r.get("inversions", []) if q["visibility"])
            fcnt = sum(len(r["findings"]) for r in res)
            total += cnt
            ninv = sum(len(r.get("inversions", [])) for r in res)
            summary[ch] = {"count": fcnt, "inversions": ninv, "beats": res}
            print(f"== {ch}: {fcnt} within-beat finding cluster(s), {ninv} tween inversion(s) ({cnt - fcnt} on opacity/draw = counted)")
            for r in res:
                if "error" in r:
                    print(f"  beat {r['k']}: probe error {r['error']}")
                    continue
                if r["findings"] or r["inversions"]:
                    print(f"  beat {r['k']} '{r['id']}'")
                for f in r["findings"]:
                    print("    " + fmt_f(f))
                for q in r["inversions"]:
                    print("    " + fmt_inv(q))
        await browser.close()
    Path(a.json_within).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json_within).write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    if a.all:
        write_within_summary(summary, Path(a.summary_within), a)
    print(f"\nTOTAL: {total} within-beat finding(s) in {len(chs)} chapter(s)")
    return 1 if total else 0


async def main(a):
    chs = a.ch or sorted(d.name for d in SITE.glob("ch[0-9][0-9]") if (d / "index.html").is_file())
    if not server_ok(a.url):
        print(f"cannot reach {a.url} - start: python3 .claude/skills/papermorph/scripts/serve.py 8766 site", file=sys.stderr)
        return 2
    if a.within:
        return await main_within(a, chs)
    total, summary = 0, {}
    async with async_playwright() as p:
        browser = await launch(p, a.browser)
        for ch in chs:
            pg = await browser.new_page(viewport={"width": 1600, "height": 960})
            try:
                f, why = await check_chapter(pg, ch, a)
            finally:
                await pg.close()
            if f is None:
                print(f"== {ch}: SKIPPED - {why}")
                summary[ch] = {"skipped": why}
                continue
            cnt = sum(len(r["groups"]) for r in f)
            total += cnt
            summary[ch] = {"count": cnt, "boundaries": len(f), "findings": f}
            print(f"== {ch}: {cnt} leftover group(s) at {len(f)} scene change(s)")
            for r in f:
                if "error" in r:
                    print(f"  beat {r['k']}: probe error {r['error']}")
                    continue
                print(f"  beat {r['k']} '{r['id']}' -> {r['k'] + 1} '{r['next']}'   shot: {r['shot']}")
                for g in r["groups"]:
                    mv = f", MOVING {g['moving']} leaves up to {g['dist']}px" if g["moving"] else ""
                    tx = ("  text: " + " | ".join(g["texts"])) if g["texts"] else ""
                    print(f"    #{g['gi'] + 1} t={g['times']} {g['leaves']}x {g['kinds']} box(x,y,w,h)={g['box']} layer {g['layer']}"
                          f"{' [old panel]' if g['inOldPanel'] else ' [outside panel]'}{mv}{tx}")
        await browser.close()
    Path(a.json).parent.mkdir(parents=True, exist_ok=True)
    Path(a.json).write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    if a.all:
        write_summary(summary, Path(a.summary))
    print(f"\nTOTAL: {total} leftover group(s) in {len(chs)} chapter(s)")
    return 1 if total else 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ch", nargs="+", help="chapter folders, e.g. --ch ch01 ch02")
    ap.add_argument("--all", action="store_true", help="every chapter folder with a page")
    ap.add_argument("--book", default=BOOK, help="book slug (site/<book>)")
    ap.add_argument("--url", default=os.environ.get("BASE", f"http://localhost:8766/{BOOK}/"))
    ap.add_argument("--within", action="store_true", help="within-beat mode (orphans, hide-ignored, reappearing, stray, moving) instead of scene-change mode")
    ap.add_argument("--dt", type=float, nargs="+", default=[.0167, .0222, .0333], help="within: frame step(s) of the replayed beat clock, seconds (each beat is replayed once per value)")
    ap.add_argument("--step", type=float, default=.25, help="within: sampling interval, seconds (marks are always sampled)")
    ap.add_argument("--beats", nargs="+", type=int, help="within: only these beat indexes")
    ap.add_argument("--max-shots", type=int, default=6, help="within: screenshot pairs per beat")
    ap.add_argument("--summary-within", default=str(REVIEW / "leftovers-within-summary.md"))
    ap.add_argument("--json-within", default=str(REVIEW / "leftovers-within.json"))
    ap.add_argument("--browser", choices=["chromium", "firefox"], default="chromium")
    ap.add_argument("--times", nargs="+", type=float, default=[1.0, 3.0], help="seconds into the new beat to sample")
    ap.add_argument("-v", "--verbose", action="store_true", help="list every boundary and whether it was checked/answered")
    ap.add_argument("--no-shots", dest="shots", action="store_false")
    ap.add_argument("--out-root", default=str(REVIEW))
    ap.add_argument("--summary", default=str(REVIEW / "leftovers-summary.md"))
    ap.add_argument("--json", default=str(REVIEW / "leftovers.json"))
    a = ap.parse_args()
    if not a.ch and not a.all:
        ap.error("give --ch chNN [chMM ...] or --all")
    a.url = a.url if a.url.endswith("/") else a.url + "/"
    sys.exit(asyncio.run(main(a)))
