// Manual test mode (?manual=1): nothing runs by itself, so every change on screen is one you caused.
// Needs the simulator's own web server (python -m tools.sim run ...), which serves /sim/... .
//   - stops the scripted demo (pedal presses, pinch sweeps, hand in and out)
//   - a thin strip in the page's bottom margin (it covers nothing): AUTO, GUITAR, HAND, and a PINCH pad you drag
//   - keys that already exist: L loop pedal, B FX, Y / N answer Riff, V hold to talk
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('manual') !== '1') return;
  document.documentElement.dataset.manual = 'true';
  const api = async (path, q) => {
    try { return await (await fetch(path + (q ? '?' + new URLSearchParams(q) : ''), { cache: 'no-store' })).json(); } catch (e) { return null; }
  };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  const strip = el('div', 'manual-strip'); strip.setAttribute('role', 'group'); strip.setAttribute('aria-label', 'Manual test controls');
  const tag = el('b', 'm-tag', 'MANUAL TEST');
  const btn = (label) => { const b = el('button', 'm-btn', label); b.type = 'button'; return b; };
  const bAuto = btn('AUTO'), bGuitar = btn('GUITAR'), bHand = btn('HAND');
  const sel = { control: 'filter' };
  const bF = btn('FILTER'), bR = btn('REVERB');
  const pad = el('div', 'm-pad'); const knob = el('i'); pad.append(knob);
  const keys = el('span', 'm-keys', 'L loop · B FX · Y N Riff · V talk');
  const sepPinch = el('span', 'm-sep', 'PINCH');
  strip.append(tag, bAuto, bGuitar, bHand, sepPinch, bF, bR, pad, keys);
  document.body.append(strip);

  const st = { auto: false, guitar: true, hand: false };
  const paint = () => {
    bAuto.textContent = `AUTO ${st.auto ? 'ON' : 'OFF'}`; bAuto.dataset.on = String(st.auto);
    bGuitar.textContent = `GUITAR ${st.guitar ? 'ON' : 'OFF'}`; bGuitar.dataset.on = String(st.guitar);
    bHand.textContent = `HAND ${st.hand ? 'IN' : 'OUT'}`; bHand.dataset.on = String(st.hand);
    bF.dataset.on = String(sel.control === 'filter'); bR.dataset.on = String(sel.control === 'reverb');
  };
  const apply = (s) => {
    if (!s || s.error) return;
    st.auto = !!s.auto; st.guitar = !!s.guitar; st.hand = !!(s.hand && s.hand.present);
    if (s.hand === null) {                       // the simulator's hand is off: vision (your camera) drives the hand and the pinch
      [bHand, bF, bR, pad, sepPinch].forEach((e) => { e.hidden = true; });
      keys.textContent = 'HAND: real camera (python -m vision) · L loop · B FX · Y N Riff · V talk';
    }
    paint();
  };
  paint();

  api('/sim/auto', { on: '0' }).then((s) => {            // stop whatever the simulator was doing by itself
    if (!s) { tag.textContent = 'MANUAL TEST: NO SIM SERVER'; tag.dataset.bad = 'true'; strip.dataset.bad = 'true'; return; }
    apply(s);
  });
  bAuto.onclick = async () => apply(await api('/sim/auto', { on: st.auto ? '0' : '1' }));
  bGuitar.onclick = async () => apply(await api('/sim/guitar', { on: st.guitar ? '0' : '1' }));
  bHand.onclick = async () => apply(await api('/sim/hand', { present: st.hand ? '0' : '1', engaged: '0' }));
  bF.onclick = () => { sel.control = 'filter'; paint(); };
  bR.onclick = () => { sel.control = 'reverb'; paint(); };

  // the pinch pad: press and drag. Left is 0, right is 1. Letting go lifts the pinch; the hand stays in frame.
  let down = false, lastSent = 0;
  const valueAt = (e) => { const r = pad.getBoundingClientRect(); return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); };
  const send = (e, engaged) => {
    const v = valueAt(e);
    knob.style.left = `${(v * 100).toFixed(1)}%`;
    return api('/sim/hand', { present: '1', engaged: engaged ? '1' : '0', control: sel.control, value: v.toFixed(3) });
  };
  pad.addEventListener('pointerdown', (e) => { down = true; pad.setPointerCapture(e.pointerId); pad.dataset.down = 'true'; st.hand = true; paint(); send(e, true); });
  pad.addEventListener('pointermove', (e) => {
    if (!down) return;
    const now = performance.now();
    if (now - lastSent < 33) return;        // 30 Hz, like the vision feed
    lastSent = now; send(e, true);
  });
  const up = (e) => { if (!down) return; down = false; pad.dataset.down = 'false'; send(e, false); };
  pad.addEventListener('pointerup', up); pad.addEventListener('pointercancel', up);
})();
