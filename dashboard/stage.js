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
    if (document.body.dataset.browser === 'true') {
      fx.disabled = false;
    } else {
      fx.disabled = d.conn === 'offline';
    }
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

  new MutationObserver(status).observe(app, { attributes: true, attributeFilter: ['data-conn', 'data-replay', 'data-sim', 'data-bypass', 'data-coach'] });
  status();

  // ---------- FX power: the same control as BYPASS ----------
  fx.addEventListener('click', () => {
    $('btnBypass').click();
    if (document.body.dataset.browser === 'true') {
      const nowOn = fx.dataset.on === 'true';
      show(!nowOn, true);
      app.dataset.bypass = String(nowOn);
    }
  });
})();
