// Spotlight layout glue: the rig drawer, the one status pill, the FX power button and the hand
// inset. Reads only what app.js already writes on #app; sends nothing new (FX power clicks the
// same BYPASS control the drawer has, so every safety rule of the engine still applies).
'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const app = $('app'), drawer = $('drawer'), btn = $('drawerBtn'), pill = $('statusPill'), fx = $('fxPower');
  if (!app) return;

  // ---------- rig drawer: everything an engineer needs, out of the player's way ----------
  function toggle(open) {
    drawer.hidden = !(open === undefined ? drawer.hidden : open);
    btn.setAttribute('aria-expanded', String(!drawer.hidden));
  }
  btn.addEventListener('click', () => toggle());
  $('drawerClose').addEventListener('click', () => toggle(false));
  window.addEventListener('keydown', (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key.toLowerCase() === 'd' && !e.metaKey && !e.ctrlKey) toggle();
    else if (e.key === 'Escape') toggle(false);
  });

  // ---------- one status word for the player; the details are in the drawer ----------
  function status() {
    const d = app.dataset;
    let word = 'LIVE', kind = 'ok';
    if (d.conn === 'offline') [word, kind] = ['NO ENGINE', 'warn'];
    else if (d.conn === 'stale') [word, kind] = ['STALE', 'warn'];
    else if (d.replay === 'true') [word, kind] = ['REPLAY', 'warn'];
    else if (d.sim) [word, kind] = [d.sim === 'guitar' ? 'SIM GUITAR' : 'SIMULATED', 'warn'];
    if (d.coach === 'scripted') { word += ' · SCRIPTED COACH'; kind = 'warn'; }
    pill.textContent = word;
    pill.dataset.kind = kind;
    fx.disabled = d.conn === 'offline';
    flip(d.bypass !== 'true');
  }

  // ---------- FX power: a real toggle. It snaps when it changes; if Riff is the one pressing it,
  // the lever moves at the instant Riff's finger lands (riff.js 'omniriff:riffpress'), not before ----------
  let shown = null, waiting = 0;
  function flip(on) {
    if (shown === null) { show(on, false); return; }
    if (on === shown) return;
    const riffAtIt = fx.classList.contains('spot-target');
    clearTimeout(waiting);
    if (riffAtIt) waiting = setTimeout(() => show(on, true), 1400);   // Riff never arrives: flip anyway
    else show(on, true);
  }
  function show(on, snap) {
    clearTimeout(waiting);
    shown = on;
    fx.setAttribute('aria-pressed', String(on));
    fx.dataset.on = String(on);
    fx.querySelector('.fx-word').textContent = on ? 'ON' : 'OFF';
    if (snap) { fx.classList.remove('snap'); void fx.offsetWidth; fx.classList.add('snap'); }
  }
  fx.addEventListener('animationend', () => fx.classList.remove('snap'));
  window.addEventListener('omniriff:riffpress', (e) => {
    if (e.detail && e.detail.el === fx && app.dataset.bypass !== String(!shown)) show(app.dataset.bypass !== 'true', true);
  });

  // ---------- knobs: the analog face of FILTER and REVERB. Stepped, like the rest of the machine ----------
  const KG = 18;
  const css = getComputedStyle(document.documentElement);
  const tok = (v, d) => (css.getPropertyValue(v) || '').trim() || d;
  const knobs = ['filter', 'reverb'].map((k) => {
    const c = $('knob-' + k);
    if (!c) return null;
    c.width = c.height = KG;
    return { k, c, ctx: c.getContext('2d'), v: -1 };
  }).filter(Boolean);
  function drawKnob(kn, v, lit) {
    const q = Math.round(v * 20) / 20;                 // 21 detents
    if (q === kn.v && lit === kn.lit) return;
    kn.v = q; kn.lit = lit;
    const x = kn.ctx, mid = KG / 2;
    x.clearRect(0, 0, KG, KG);
    const ang = (t) => (-135 + 270 * t) * Math.PI / 180 - Math.PI / 2;
    for (let i = 0; i <= 10; i++) {                    // the scale printed around it
      const a = ang(i / 10);
      x.fillStyle = i / 10 <= q + 1e-6 ? (lit ? tok('--accent', '#FF5CCB') : tok('--text', '#EDEDF2')) : tok('--line-2', '#3A3A48');
      x.fillRect(Math.round(mid - 0.5 + Math.cos(a) * 8.2), Math.round(mid - 0.5 + Math.sin(a) * 8.2), 1, 1);
    }
    for (let y = 0; y < KG; y++) for (let xx = 0; xx < KG; xx++) {   // the cap: a chunky pixel circle, lit top-left
      const dx = xx + 0.5 - mid, dy = y + 0.5 - mid, r = Math.hypot(dx, dy);
      if (r > 6.4) continue;
      const rim = r > 5.4, lightSide = dx + dy < -2;
      x.fillStyle = rim ? (lightSide ? tok('--muted', '#8A8A9A') : tok('--line-2', '#3A3A48')) : tok('--dim', '#4A4A5A');
      x.fillRect(xx, y, 1, 1);
    }
    const a = ang(q);                                   // the pointer: centre to edge
    x.fillStyle = lit ? tok('--accent', '#FF5CCB') : tok('--text', '#EDEDF2');
    for (let r = 0.5; r <= 6; r += 0.25) x.fillRect(Math.floor(mid + Math.cos(a) * r), Math.floor(mid + Math.sin(a) * r), 1, 1);
  }
  window.addEventListener('omniriff:frame', (e) => {
    const f = e.detail || {};
    for (const kn of knobs) {
      const s = f[kn.k];
      if (s && typeof s.value === 'number') drawKnob(kn, Math.max(0, Math.min(1, s.value)), $('card-' + kn.k).classList.contains('target'));
    }
  });
  knobs.forEach((kn) => drawKnob(kn, 0, false));
  new MutationObserver(status).observe(app, { attributes: true, attributeFilter: ['data-conn', 'data-replay', 'data-sim', 'data-bypass', 'data-coach'] });
  status();

  // ---------- FX power: the same control as BYPASS ----------
  fx.addEventListener('click', () => $('btnBypass').click());

  // ---------- hand inset: only while the camera sees a hand ----------
  const hp = $('handPanel'), inset = document.querySelector('.hand-inset');
  const hand = () => { inset.dataset.show = String(!['off', 'none'].includes(hp.dataset.hand)); };
  new MutationObserver(hand).observe(hp, { attributes: true, attributeFilter: ['data-hand'] });
  hand();
})();
