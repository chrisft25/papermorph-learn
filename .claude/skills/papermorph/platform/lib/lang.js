// Interface language (not the lessons: narration, captions and chapter text stay as authored).
// Load FIRST in <head>/<body> of the cover and of every chapter page, before engine.js / contents.js:
//   <script src="../lib/lang.js"></script>
// It sets <html lang> from the saved choice; the engine and contents.js translate from that.
// Languages: the book's own language (the page's initial <html lang>), English, plus anything listed in window.UI_LANGS
// (define window.UI_LANGS / window.UI_STRINGS in a small script BEFORE this one; see references/i18n.md).
// UILang.t(spanish, english) picks by language (and window.UI_STRINGS[lang][spanish] when present);
// UILang.set('en') saves and reloads (a lesson reopens at the same moment); UILang.speech() gives the speech-API locale.
// The language pill (ES | EN ...) is added automatically.
(() => {
  'use strict';
  const KEY = 'ui-lang';
  const BOOK_LANG = (document.documentElement.lang || 'en').toLowerCase().split('-')[0];
  const LANGS = [...new Set([BOOK_LANG, 'en', ...(window.UI_LANGS || [])])];
  const HTML_LANG = { es: 'es-MX', pt: 'pt-BR', en: 'en' }, SPEECH = { es: 'es-MX', en: 'en-US', pt: 'pt-BR', fr: 'fr-FR', de: 'de-DE', it: 'it-IT', ca: 'ca-ES', nl: 'nl-NL', ja: 'ja-JP', zh: 'zh-CN' };
  const NAMES = { es: 'Español', en: 'English', pt: 'Português', fr: 'Français', de: 'Deutsch', it: 'Italiano', ca: 'Català', nl: 'Nederlands', ja: '日本語', zh: '中文' };
  let lang = BOOK_LANG;
  try { const v = localStorage.getItem(KEY); if (LANGS.includes(v)) lang = v; } catch {}
  const t = (es, en) => { const x = window.UI_STRINGS && window.UI_STRINGS[lang] && window.UI_STRINGS[lang][es]; return x !== undefined ? x : (lang === 'es' ? es : en); };
  document.documentElement.lang = HTML_LANG[lang] || lang;
  // ---- hosted mode (multi-user): the server owns each user's progress, notes, chats and preferences. ----
  // A non-httpOnly cookie 'tutor_hosted' (set at login) switches this on; locally it does nothing and costs no request.
  // Before anything else reads localStorage we pull the user's data from the server (one small synchronous request),
  // then mirror every later write to the synced keys back to the server. Engine/learn/tutor code is unchanged.
  const HOSTED = /(?:^|; )tutor_hosted=1/.test(document.cookie);
  const SYNC = k => (/^(learn:|learn-epoch:|flow:|tutor-notes:|animebook:progress:)/.test(k) || (/^tutor:/.test(k) && !/^tutor:(up|open)$/.test(k)) || k === 'ui-lang' || k === 'captions' || k === 'speed');
  let ME = null;
  if (HOSTED) try {
    const ls = localStorage, origSet = Storage.prototype.setItem, origRem = Storage.prototype.removeItem, setI = (k, v) => origSet.call(ls, k, v), remI = k => origRem.call(ls, k);
    const x = new XMLHttpRequest(); x.open('GET', '/api/kv', false); x.send();
    if (x.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); throw new Error('login required'); }
    ME = JSON.parse(x.responseText);
    // First login in this browser (no marker yet): ADOPT what is already here (notes, chats, progress from before accounts
    // existed) instead of discarding it: keys the server lacks are uploaded; for learning state the newer copy wins.
    // A marker for a DIFFERENT account means another person used this browser: clear their keys first.
    const prev = ls.getItem('sync-user'), adopt = {};
    if (prev !== null && prev !== ME.user) Object.keys(ls).filter(SYNC).forEach(k => remI(k));
    else if (prev === null) for (const k of Object.keys(ls).filter(SYNC)) {
      const lv = ls.getItem(k), sv = ME.items[k];
      if (sv === undefined) adopt[k] = lv;
      else if (k.startsWith('learn:')) { try { if (JSON.parse(lv).updated > JSON.parse(sv).updated) adopt[k] = lv; } catch {} }
      else if (k.startsWith('animebook:progress:')) {   // finished chapters: union of both copies, the browser's 'last' wins
        try { const x = JSON.parse(lv), y = JSON.parse(sv), m = { ...y, ...x, done: [...new Set([...(y.done || []), ...(x.done || [])])] }; if (x.last === undefined) m.last = y.last; adopt[k] = JSON.stringify(m); setI(k, adopt[k]); } catch {}
      } else if (k.startsWith('tutor-notes:')) {   // saved notes: keep the server's, add the browser's that it lacks
        try { const x = JSON.parse(lv), y = JSON.parse(sv), have = new Set(y.map(n => n.id)), m = [...y, ...x.filter(n => !have.has(n.id))]; if (m.length !== y.length) { adopt[k] = JSON.stringify(m); setI(k, adopt[k]); } } catch {}
      }
    }
    setI('sync-user', ME.user);
    Object.entries(ME.items).forEach(([k, v]) => { if (!(k in adopt)) setI(k, v); });
    setI('tutor:up', '1'); window.TUTOR_URL = location.origin; window.TUTOR_PERMS = ME.perms || [];
    let pend = {}, tm = 0;
    const flush = beacon => {
      clearTimeout(tm); tm = 0; if (!Object.keys(pend).length) return;
      const body = JSON.stringify({ items: pend }); pend = {};
      if (beacon && navigator.sendBeacon) navigator.sendBeacon('/api/kv', new Blob([body], { type: 'application/json' }));
      else fetch('/api/kv', { method: 'PUT', headers: { 'content-type': 'application/json' }, body, keepalive: body.length < 60000 }).catch(() => {});
    };
    const queue = (k, v) => { if (SYNC(k)) { pend[k] = v; if (!tm) tm = setTimeout(() => flush(false), 700); } };
    Storage.prototype.setItem = function (k, v) { origSet.call(this, k, v); if (this === ls) queue(k, String(v)); };
    Storage.prototype.removeItem = function (k) { origRem.call(this, k); if (this === ls) queue(k, null); };
    Object.entries(adopt).forEach(([k, v]) => queue(k, v));   // upload adopted local data
    addEventListener('pagehide', () => flush(true)); document.addEventListener('visibilitychange', () => { if (document.hidden) flush(true); });
    window.__syncLogout = async () => { flush(false); await fetch('/api/logout', { method: 'POST' }).catch(() => {}); Object.keys(ls).filter(SYNC).forEach(k => remI(k)); remI('sync-user'); location.href = '/login'; };
  } catch (e) { if (String(e.message) === 'login required') throw e; }

  // Learning-data epoch: bump it to reset progress everywhere. A browser whose marker differs wipes this book's learning
  // state (streak, XP, badges, cards, mastery, lab progress, reading progress) once, before anything reads it.
  // Saved notes ('tutor-notes:*'), tutor chat history and preferences are kept.
  const EPOCH = 'platform-1', bk = (location.pathname.match(/^\/([^/]+)\//) || [])[1];
  window.LEARN_EPOCH = EPOCH;
  if (bk) try {
    const mark = localStorage.getItem(`learn-epoch:${bk}`);
    if (mark !== EPOCH) {   // in login mode a missing marker means a NEW account: never wipe the progress the browser just adopted
      if (!(HOSTED && mark === null)) ['learn:' + bk, 'flow:' + bk, `animebook:progress:/${bk}/`].forEach(k => localStorage.removeItem(k));
      localStorage.setItem(`learn-epoch:${bk}`, EPOCH);
    }
  } catch {}
  // ---- user menu + settings (hosted) ----
  const T = t, esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const BTN = 'background:#1b2a25;color:#ece8dc;border:1px solid #34493f;border-radius:8px;padding:7px 12px;font:inherit;cursor:pointer';
  function menu(anchor) {
    document.getElementById('uMenu')?.remove();
    const m = document.createElement('div'); m.id = 'uMenu';
    m.style.cssText = 'position:fixed;top:48px;z-index:100;background:#121b18;border:1px solid #2a3b35;border-radius:10px;padding:6px;display:flex;flex-direction:column;gap:4px;font:13px "Avenir Next",Arial,sans-serif;min-width:150px;' + (anchor.closest('[data-uilang]').style.left ? 'left:14px' : 'right:14px');
    m.innerHTML = `<div style="padding:6px 8px;color:#9aa89f">${esc(ME.name || ME.user)}</div><button data-a="set" style="${BTN}">${T('Ajustes', 'Settings')}</button><button data-a="out" style="${BTN}">${T('Cerrar sesión', 'Log out')}</button>`;
    m.onclick = e => { const a = e.target.closest('button')?.dataset.a; if (a === 'out') window.__syncLogout(); if (a === 'set') { m.remove(); settings(); } };
    document.body.append(m); setTimeout(() => document.addEventListener('click', function f(e) { if (!m.contains(e.target)) { m.remove(); document.removeEventListener('click', f); } }), 0);
  }
  async function settings() {
    const S = await fetch('/api/settings').then(r => r.json()).catch(() => null); if (!S) return;
    const ov = document.createElement('div'); ov.style.cssText = 'position:fixed;inset:0;z-index:110;background:rgba(8,12,10,.78);display:grid;place-items:center;font:14px/1.5 "Avenir Next",Arial,sans-serif;color:#ece8dc';
    const inp = 'width:100%;box-sizing:border-box;margin:2px 0 10px;padding:8px 10px;background:#1b2a25;color:#ece8dc;border:1px solid #34493f;border-radius:8px;font:inherit';
    ov.innerHTML = `<div style="width:min(460px,94vw);max-height:90vh;overflow:auto;background:#0f1613;border:1px solid #2a3b35;border-radius:14px;padding:20px">
<h3 style="margin:0 0 4px">${T('Ajustes', 'Settings')} · ${esc(ME.name || ME.user)}</h3>
<div style="color:#9aa89f;font-size:12px;margin-bottom:12px">${T('Permisos', 'Permissions')}: ${S.perms.length ? esc(S.perms.join(', ')) : T('solo lectura y tutor', 'lessons and tutor only')}. ${T('Tus claves se guardan cifradas en el servidor y nunca vuelven al navegador.', 'Your keys are stored encrypted on the server and never sent back to the browser.')}</div>
<b>Claude API</b><div style="font-size:12px;color:#9aa89f">${T('URL base (vacío = ', 'Base URL (empty = ')}${esc(S.defaults.claude_url)})</div><input id="s_cu" style="${inp}" value="${esc(S.claude_url)}" placeholder="${esc(S.defaults.claude_url)}">
<div style="font-size:12px;color:#9aa89f">API key ${S.claude_key_set ? '· ✓ ' + T('guardada', 'saved') : '· ' + T('falta', 'missing')}</div><input id="s_ck" type="password" style="${inp}" autocomplete="off" placeholder="${S.claude_key_set ? T('(déjalo vacío para conservarla)', '(leave empty to keep it)') : 'sk-ant-…'}">
<details style="margin-bottom:10px"><summary style="cursor:pointer;color:#9aa89f">${T('Modelos (opcional)', 'Models (optional)')}</summary>
${['fast', 'normal', 'deep'].map(k => `<div style="font-size:12px;color:#9aa89f">${k}</div><input id="s_m_${k}" style="${inp}" value="${esc(S['model_' + k])}" placeholder="${esc(S.defaults['model_' + k])}">`).join('')}</details>
<div style="display:flex;gap:8px;justify-content:flex-end"><button id="s_x" style="${BTN}">${T('Cancelar', 'Cancel')}</button><button id="s_ok" style="${BTN};background:#f0b45a;color:#0f1613;font-weight:700">${T('Guardar', 'Save')}</button></div><div id="s_msg" style="font-size:12px;color:#8fd6b0;min-height:18px;margin-top:6px"></div></div>`;
    document.body.append(ov); ov.onclick = e => { if (e.target === ov || e.target.id === 's_x') ov.remove(); };
    ov.querySelector('#s_ok').onclick = async () => {
      const v = id => ov.querySelector('#' + id)?.value ?? '', body = { claude_url: v('s_cu'), claude_key: v('s_ck'), model_fast: v('s_m_fast'), model_normal: v('s_m_normal'), model_deep: v('s_m_deep') };
      const r = await fetch('/api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
      ov.querySelector('#s_msg').textContent = r.ok ? T('Guardado ✓', 'Saved ✓') : T('No se pudo guardar', 'Could not save'); if (r.ok) setTimeout(() => ov.remove(), 700);
    };
  }
  const UILang = {
    get: () => lang,
    t,
    langs: LANGS,
    speech: () => SPEECH[lang] || lang,
    set(l) {
      if (l === lang) return;
      try { localStorage.setItem(KEY, l); } catch {}
      let url = location.href;
      try { if (typeof P !== 'undefined' && P.started) { const u = new URL(location.href); u.searchParams.set('beat', P.i); u.searchParams.set('t', Math.round(P.t * 10) / 10); url = u.href; } } catch {}
      if (url === location.href) location.reload(); else location.href = url;
    },
    switcher() {
      const d = document.createElement('div');
      const lesson = /\/ch\d+[a-z]?\//.test(location.pathname);
      d.style.cssText = `position:fixed;top:12px;${lesson ? 'left' : 'right'}:14px;z-index:40;display:flex;gap:2px;background:#1b2a25;border:1px solid #3a5249;border-radius:16px;padding:2px;font:600 12px/1 "Avenir Next",Arial,sans-serif`;
      d.innerHTML = LANGS.map(l => `<button data-l="${l}" aria-label="${NAMES[l] || l}" style="border:0;border-radius:13px;padding:6px 10px;cursor:pointer;color:${l === lang ? '#0f1613' : '#ece8dc'};background:${l === lang ? '#f0b45a' : 'transparent'}">${l.toUpperCase()}</button>`).join('');
      if (ME) d.insertAdjacentHTML('beforeend', `<button data-user style="border:0;border-radius:13px;padding:6px 10px;cursor:pointer;color:#ece8dc;background:transparent;margin-left:4px;border-left:1px solid #3a5249">👤 ${String(ME.name || ME.user).replace(/[<&>]/g, '')}</button>`);
      d.onclick = e => { const b = e.target.closest('button'); if (!b) return; if (b.dataset.l) UILang.set(b.dataset.l); else if (b.dataset.user !== undefined) menu(b); };
      document.body.append(d);
    },
  };
  window.UILang = UILang;
  // Every page that loads this file gets the pill (top right on the cover, top left in lessons, clear of the tutor panel).
  const mount = () => { if (!document.querySelector('[data-uilang]')) { UILang.switcher(); document.body.lastChild.dataset.uilang = ''; } };
  if (document.body) mount(); else addEventListener('DOMContentLoaded', mount);
})();
