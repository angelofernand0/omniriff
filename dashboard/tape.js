// The waveform IS the tape, and it feeds into one wheel at the left end of the waveform panel.
// app.js paints the bars; this file paints the wheel and the tape that joins it to the bars. Every motion is
// caused by the real loop:
//   READY   a small empty core, nothing on it
//   REC     new audio enters at the right edge (a red record head), scrolls left as the waveform and winds
//           onto the wheel, which turns one way and grows with the recorded seconds (full at 12 s). Red,
//           like the bars.
//   close   the loop is spliced: the wheel turns pink and clunks once
//   PLAY    the wheel unwinds the other way in step with the playhead (a whole number of turns per loop, so it
//           lands on the same spot every wrap) and clunks on the downbeat; the played tape is pink
//   CLEAR   the wheel rewinds fast until it is an empty core again
// Pixel art in 5 px cells (4 or 3 on short panels), moving in 80 ms steps. With reduced motion it shows the state
// and does not turn.
//   OmniTape.layout(h)  -> { cell, r, x0 }   wheel radius and where the bars start, for a panel h px tall
//   OmniTape.paint(ctx, o)                   o: { w, h, now, state, seconds, max, playStart }
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
  const TAU = Math.PI * 2, TICK = 80;
  const FL = 11, HUB = 3.3, CORE = 4.6, FULL = 9.8;           // in cells: flange, hub, empty spool, full spool
  const PAD = 12, REF = 12;

  const st = { mode: 'idle', r: CORE, ang: 0, off: 0, clunk: 0, kick: 0, last: 0, lastPos: 0, beat: 0 };

  function layout(h) {
    const cell = h >= 260 ? 5 : h >= 130 ? 4 : 3;
    const r = FL * cell;
    return { cell, r, x0: PAD + 2 * r + 8 };
  }

  const ease = (a, b, k) => a + (b - a) * k;
  function targetR(o) {
    if (o.state === 'idle') return CORE;
    const f = Math.min(1, Math.max(0, (o.seconds || 0) / Math.min(o.max || 30, REF)));   // full at a long practice loop, not at the 30 s cap
    return CORE + (FULL - CORE) * Math.pow(f, 0.6);
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

  function step(o, now) {
    const t = targetR(o);
    st.r = ease(st.r, t, o.state === 'idle' ? 0.3 : 0.4);
    if (o.state === 'recording') {
      const up = st.kick > 0 ? 1 - st.kick-- / 5 : 1;
      st.ang -= (0.9 * up) / st.r;                               // winding on: one way
      st.beat += 1;
    } else if (o.state === 'playing') {
      const l = o.seconds || 1;
      const turns = Math.max(1, Math.round(l / 1.5));            // whole turns per loop: seamless at the wrap
      const pos = ((now - o.playStart) / 1000 / l) % 1;
      if (pos < st.lastPos) st.clunk = 3;                        // the downbeat
      st.lastPos = pos;
      st.ang = st.off + TAU * turns * pos;                       // unwinding: the other way
      st.beat = 0;
    } else if (st.r > CORE + 0.2) {
      st.ang += 0.9;                                             // clearing: rewinds, fast
    }
    if (st.clunk > 0) st.clunk -= 1;
  }

  function paint(ctx, o) {
    const { cell, r: R, x0 } = layout(o.h);
    if (o.state !== st.mode) change(o);
    if (motion) {
      if (!st.last) st.last = o.now;
      let n = 0;
      while (o.now - st.last >= TICK && n++ < 6) { st.last += TICK; step(o, st.last); }
      if (n >= 6) st.last = o.now;
    } else { st.r = targetR(o); }
    const cx = PAD + R, cy = Math.round(o.h / 2);
    const rec = o.state === 'recording', play = o.state === 'playing', idle = o.state === 'idle';
    const tape = rec ? C.rec : play ? C.pink : C.grey;
    const tapeLow = rec ? C.recLow : play ? C.pinkLow : C.greyMid;
    const tapeDim = rec ? C.recDim : play ? C.pinkDim : C.greyLow;
    const px = (x, y, c) => { ctx.fillStyle = c; ctx.fillRect(x, y, cell, cell); };
    const hubC = st.clunk > 0 ? C.text : C.grey;

    // the tape joining the wheel to the waveform, and the record head at the right edge
    if (!idle) {
      ctx.fillStyle = tapeLow;
      ctx.fillRect(cx + R - cell, cy - cell / 2, x0 - (cx + R) + cell, cell);
    }
    if (rec) {
      ctx.fillStyle = st.beat % 10 < 5 ? C.rec : C.recDim;
      const hh = Math.round(o.h / 2 - PAD);
      ctx.fillRect(o.w - PAD + 2, cy - hh, 4, hh * 2);
    }

    // the wheel
    for (let j = -FL; j < FL; j++) for (let i = -FL; i < FL; i++) {
      const dx = i + 0.5, dy = j + 0.5, d = Math.hypot(dx, dy);
      if (d > FL) continue;
      const X = cx - R + (i + FL) * cell, Y = cy - R + (j + FL) * cell;
      if (d <= HUB) {                                           // hub, with three spokes that turn
        let spoke = false;
        if (d > 1) {
          const a = Math.atan2(dy, dx) - st.ang;
          for (let k = 0; k < 3; k++) {
            let q = ((a - (k * TAU) / 3) % TAU + TAU * 2) % TAU; if (q > Math.PI) q -= TAU;
            if (Math.abs(q) < 0.5) spoke = true;
          }
        }
        px(X, Y, spoke ? C.ink : hubC);
      } else if (d <= st.r) {                                    // wound tape: rings, the outer one brightest
        const ring = Math.floor(st.r - d);
        px(X, Y, ring === 0 ? tape : ring % 2 ? tapeDim : tapeLow);
      } else if (d > FL - 1) px(X, Y, C.greyMid);                  // the flange
      else px(X, Y, C.ink);                                       // the empty part of the reel
    }
  }

  window.OmniTape = { layout, paint };
})();
