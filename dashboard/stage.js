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
    const on = d.bypass !== 'true';
    fx.setAttribute('aria-pressed', String(on));
    fx.dataset.on = String(on);
    fx.querySelector('.fx-word').textContent = on ? 'ON' : 'OFF';
    fx.disabled = d.conn === 'offline';
  }
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
