// The waveform IS the tape, and it comes off one big wheel that is half hidden under the record box.
// The wheel is centred on the record box's right edge, so only its right half shows, poking out across the
// gap into the waveform panel; the waveform leaves its rim. app.js paints the bars; this file paints the wheel
// on its own canvas, between the two boxes (the record box is above it, the waveform panel below). Every motion
// is caused by the real loop:
//   READY   a small empty core, nothing wound on it
//   REC     new audio enters at the right edge past a red record head, scrolls left as the waveform and winds
//           onto the wheel, which turns one way and grows with the recorded seconds (full at 12 s). Red, like
//           the bars.
//   close   the loop is spliced: the wheel turns pink and clunks once
//   PLAY    the wheel unwinds the other way in step with the playhead (a whole number of turns per loop, so it
//           lands on the same spot every wrap) and clunks on the downbeat; the played tape is pink
//   CLEAR   the wheel rewinds fast until it is an empty core again
// Pixel art in 5 px cells (4 on short panels), moving in 80 ms steps. With reduced motion it shows the state
// and does not turn.
//   OmniTape.layout()  -> { x0 }   where the bars start, in the waveform panel's own coordinates
//   OmniTape.paint(o)              o: { now, state, seconds, max, playStart }
'use strict';

(() => {
  const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const css = getComputedStyle(document.documentElement);
  const col = (v, d) => (css.getPropertyValue(v) || '').trim() || d;
  const C = {
    pink: col('--accent', '#FF5CCB'), pinkLow: col('--accent-low', '#B4318A'), pinkDim: col('--accent-dim', '#7A2A62'),
    rec: col('--rec', '#FF5340'), recLow: '#B33A2D', recDim: '#6E2A24',
    grey: col('--muted', '#A6A3B6'), greyMid: col('--dim', '#4A4858'), greyLow: col('--off', '#24232E'),
    line: col('--line-2', '#34323F'), text: col('--text', '#ECE9F5'), ink: col('--bg', '#0B0B10'),
  };
  const TAU = Math.PI * 2, TICK = 80, PAD = 12, REF = 12;
  const row = document.querySelector('.loop-row'), box = document.querySelector('.loop-state'), wave = document.querySelector('.wave');
  if (!row || !box || !wave) return;
  const cv = document.createElement('canvas');
  cv.className = 'wheel'; cv.setAttribute('aria-hidden', 'true');
  row.appendChild(cv);
  const ctx = cv.getContext('2d');

  const st = { mode: 'idle', r: 0, ang: 0, off: 0, clunk: 0, kick: 0, last: 0, lastPos: 0, beat: 0 };

  // sizes in cells: the flange fills the row's height; hub, empty core and full spool are fractions of it
  function geom() {
    const rr = row.getBoundingClientRect(), br = box.getBoundingClientRect(), wr = wave.getBoundingClientRect();
    const cell = rr.height >= 260 ? 5 : 4;
    const FL = Math.max(8, Math.floor((rr.height / 2 - 8) / cell));
    const R = FL * cell;
    const cx = br.right - rr.left, cy = rr.height / 2;                        // centred on the record box's right edge
    const x0 = cx + R + 10 - (wr.left - rr.left) - wave.clientLeft;           // bars start here, in the panel's coordinates
    return { rr, wr, cell, FL, R, cx, cy, x0, HUB: FL * 0.27, CORE: FL * 0.36, FULL: FL * 0.88 };
  }
  const ease = (a, b, k) => a + (b - a) * k;
  function targetR(o, g) {
    if (o.state === 'idle') return g.CORE;
    const f = Math.min(1, Math.max(0, (o.seconds || 0) / Math.min(o.max || 30, REF)));
    return g.CORE + (g.FULL - g.CORE) * Math.pow(f, 0.6);
  }

  function change(o) {
    const prev = st.mode;
    st.mode = o.state;
    if (o.state === 'playing') {
      st.off = st.ang;                                           // the playhead turns the wheel from where it is
      st.lastPos = 0;
      if (prev === 'recording') st.clunk = 3;                    // the splice
    } else if (o.state === 'recording') st.kick = 4;             // spin-up
  }

  function step(o, g, now) {
    st.r = ease(st.r, targetR(o, g), o.state === 'idle' ? 0.3 : 0.4);
    if (o.state === 'recording') {
      const up = st.kick > 0 ? 1 - st.kick-- / 5 : 1;
      st.ang -= (4.5 * up) / st.r;                               // winding on: one way (slower as the spool grows)
      st.beat += 1;
    } else if (o.state === 'playing') {
      const l = o.seconds || 1;
      const turns = Math.max(1, Math.round(l / 2.5));            // whole turns per loop: seamless at the wrap
      const pos = ((now - o.playStart) / 1000 / l) % 1;
      if (pos < st.lastPos) st.clunk = 3;                        // the downbeat
      st.lastPos = pos;
      st.ang = st.off + TAU * turns * pos;                       // unwinding: the other way
      st.beat = 0;
    } else if (st.r > g.CORE + 0.3) {
      st.ang += 0.5;                                             // clearing: rewinds, fast
    }
    if (st.clunk > 0) st.clunk -= 1;
  }

  function layout() { return { x0: geom().x0 }; }

  function paint(o) {
    const g = geom();
    if (!st.r) st.r = g.CORE;
    if (o.state !== st.mode) change(o);
    if (motion) {
      if (!st.last) st.last = o.now;
      let n = 0;
      while (o.now - st.last >= TICK && n++ < 6) { st.last += TICK; step(o, g, st.last); }
      if (n >= 6) st.last = o.now;
    } else st.r = targetR(o, g);

    const dpr = window.devicePixelRatio || 1, w = g.rr.width, h = g.rr.height;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const { cell, FL, cx, cy, HUB } = g;
    const rec = o.state === 'recording', play = o.state === 'playing', idle = o.state === 'idle';
    const tape = rec ? C.rec : play ? C.pink : C.grey;
    const tapeLow = rec ? C.recLow : play ? C.pinkLow : C.greyMid;
    const tapeDim = rec ? C.recDim : play ? C.pinkDim : C.greyLow;
    const hubC = st.clunk > 0 ? C.text : C.grey;
    const px = (x, y, c) => { ctx.fillStyle = c; ctx.fillRect(x, y, cell, cell); };

    // the wheel: only the right half shows (the left half is under the record box, so it is not drawn)
    for (let j = -FL; j < FL; j++) for (let i = 0; i < FL; i++) {
      const dx = i + 0.5, dy = j + 0.5, d = Math.hypot(dx, dy);
      if (d > FL) continue;
      const X = cx + i * cell, Y = cy + j * cell;
      if (d <= HUB) {                                           // hub, with three spokes that turn
        let spoke = false;
        if (d > 1.6) {
          const a = Math.atan2(dy, dx) - st.ang;
          for (let k = 0; k < 3; k++) {
            let q = ((a - (k * TAU) / 3) % TAU + TAU * 2) % TAU; if (q > Math.PI) q -= TAU;
            if (Math.abs(q) < 0.42) spoke = true;
          }
        }
        px(X, Y, spoke ? C.ink : hubC);
      } else if (d <= st.r) {                                    // wound tape: rings, the outer one brightest
        const ring = Math.floor((st.r - d) / 1.5);
        px(X, Y, ring === 0 ? tape : ring % 2 ? tapeDim : tapeLow);
      } else if (d > FL - 1.2) px(X, Y, C.greyMid);               // the flange
      else px(X, Y, C.ink);                                       // the empty part of the reel
    }

    // the tape leaving the rim for the bars, and the record head at the waveform's right edge
    if (!idle) {
      const rimX = cx + st.r * cell, x0abs = g.x0 + (g.wr.left - g.rr.left) + wave.clientLeft;
      ctx.fillStyle = tapeLow;
      ctx.fillRect(rimX - cell, cy - cell / 2, Math.max(0, x0abs - rimX + cell), cell);
    }
    if (rec) {
      ctx.fillStyle = st.beat % 10 < 5 ? C.rec : C.recDim;
      const hh = Math.round(g.wr.height / 2 - PAD);
      ctx.fillRect(g.wr.right - g.rr.left - wave.clientLeft - PAD + 2, cy - hh, 4, hh * 2);
    }
  }

  window.OmniTape = { layout, paint };
})();
