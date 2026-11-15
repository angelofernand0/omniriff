// The loop as a tape machine, in the record box. Every motion is caused by the real loop:
//   READY      both reels still, a full spool of blank tape on the left, an empty hub on the right
//   REC        the left spool feeds the right one past the record head; the right spool grows with the
//              recorded seconds (of the loop's max), the tape that has passed the head turns pink
//   close      the tape is spliced into a ring: the top belt draws in, the spools balance, one clunk
//   PLAY       the ring circulates; the reels turn in step with the playhead (a whole number of turns
//              per loop, so they land on the same spot every wrap); the head clunks on the downbeat
//   CLEAR      the loop unspools backwards and the spools go home
// Pixel art on a 32x20 grid, scaled with hard edges. It moves in steps (one step per 80 ms), like the rest
// of the machine. No timers of its own while idle; with reduced motion it shows the state and does not move.
//   OmniTape.force(mode, seconds, pos)   a still for design review (mode: idle | recording | playing)
'use strict';

(() => {
  const cv = document.getElementById('tape');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const W = 32, H = 20, TICK = 80;
  const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const css = getComputedStyle(document.documentElement);
  const col = (v, d) => (css.getPropertyValue(v) || '').trim() || d;
  const C = {
    pink: col('--accent', '#FF5CCB'), pinkLow: col('--accent-low', '#B4318A'), pinkDim: col('--accent-dim', '#7A2A62'),
    grey: col('--muted', '#A6A3B6'), greyMid: col('--dim', '#4A4858'), greyLow: col('--off', '#24232E'),
    line: col('--line-2', '#34323F'), text: col('--text', '#ECE9F5'), ink: col('--bg', '#0B0B10'), rec: col('--rec', '#FF5340'),
  };
  const LC = { x: 7.5, y: 7.5 }, RC = { x: 24.5, y: 7.5 };      // reel centres
  const FLANGE = 7.5, HUB = 2.3, R0 = 6.8, R1 = 3.1;             // reel edge, hub radius, full spool, empty spool
  const AREA = R0 * R0 + R1 * R1;                                // tape area on the two spools stays constant
  const HEAD = { x0: 13, x1: 18, y0: 17, y1: 18 };               // head block
  const TAU = Math.PI * 2;

  const st = {
    mode: 'idle', seconds: 0, max: 30, playStart: 0, lastPos: 0,
    rL: R0, rR: R1, belt: 0, angL: 0, angR: 0, off: 0,
    speed: 0, flow: 0, clunk: 0, beat: 0, kick: 0, closing: 0, forced: null,
  };

  // ---------- the loop, from the engine's frames ----------
  window.addEventListener('omniriff:frame', (e) => {
    const l = e.detail && e.detail.loop;
    if (!l) return;
    st.seconds = l.seconds || 0;
    if (l.max_seconds) st.max = l.max_seconds;
    const now = performance.now();
    if (l.state !== st.mode) change(l.state, now);
  });

  function change(mode, now) {
    const prev = st.mode;
    st.mode = mode;
    if (mode === 'playing') {
      st.playStart = now; st.lastPos = 0;
      st.off = st.angL;                              // keep the spokes where they are; the playhead turns them from here
      if (prev === 'recording') { st.closing = 6; st.clunk = 3; }   // the splice: belt draws in, one clunk
    } else if (mode === 'recording') {
      st.kick = 4;                                    // the reels spin up over a few steps
    }
    if (!motion) settle();
    kickLoop();
  }

  // ---------- one step ----------
  const ease = (a, b, k) => a + (b - a) * k;
  function target() {
    if (st.mode === 'recording') {
      const f = Math.min(1, Math.max(0, st.seconds / st.max));
      const rR = R1 + 2.7 * Math.sqrt(f);
      return { rL: Math.sqrt(Math.max(R1 * R1, AREA - rR * rR)), rR, belt: 0 };
    }
    if (st.mode === 'playing') { const r = Math.sqrt(AREA / 2); return { rL: r, rR: r, belt: 1 }; }
    return { rL: R0, rR: R1, belt: 0 };
  }
  function settle() { const t = target(); st.rL = t.rL; st.rR = t.rR; st.belt = t.belt; }

  function step(now) {
    const t = target();
    st.rL = ease(st.rL, t.rL, 0.4); st.rR = ease(st.rR, t.rR, 0.4);
    st.belt = st.belt < t.belt ? Math.min(t.belt, st.belt + 1 / 6) : Math.max(t.belt, st.belt - 1 / 4);
    if (st.mode === 'recording') {
      const up = st.kick > 0 ? 1 - st.kick-- / 5 : 1;                 // spin-up
      st.angL += 0.9 * up / st.rL; st.angR += 0.9 * up / st.rR; st.flow += up;
      st.beat += 1;
    } else if (st.mode === 'playing') {
      const l = st.seconds || 1;
      const turns = Math.max(1, Math.round(l / 1.5));                  // whole turns per loop: seamless at the wrap
      const pos = ((now - st.playStart) / 1000 / l) % 1;
      if (pos < st.lastPos) st.clunk = 3;                              // the downbeat
      st.lastPos = pos;
      st.angL = st.off + TAU * turns * pos; st.angR = st.angL;
      st.flow = Math.floor(turns * pos * 15);
      st.beat = 0;
    } else if (st.belt > 0 || st.rL < R0 - 0.2) {                       // clearing: backwards, fast, until the spools are home
      st.angL -= 0.8; st.angR -= 0.8; st.flow -= 2;
    }
    if (st.clunk > 0) st.clunk -= 1;
    if (st.closing > 0) st.closing -= 1;
  }

  // ---------- drawing ----------
  function cell(x, y, c) {
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    ctx.fillStyle = c; ctx.fillRect(x, y, 1, 1);
  }
  function line(a, b, fn) {                                              // cells along a segment, with their index
    const n = Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y)) | 0 || 1;
    for (let i = 0; i <= n; i++) fn(Math.round(a.x + ((b.x - a.x) * i) / n - 0.5), Math.round(a.y + ((b.y - a.y) * i) / n - 0.5), i, n);
  }
  function reel(c, rPack, ang, pink) {
    const hubC = st.clunk > 0 ? C.text : C.grey;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const dx = x + 0.5 - c.x, dy = y + 0.5 - c.y, r = Math.hypot(dx, dy);
      if (r > FLANGE) continue;
      if (r <= HUB) {                                                    // the hub, with three spokes that turn
        let spoke = false;
        if (r > 0.9) {
          const a = Math.atan2(dy, dx) - ang;
          for (let k = 0; k < 3; k++) {
            let d = ((a - (k * TAU) / 3) % TAU + TAU * 2) % TAU; if (d > Math.PI) d -= TAU;
            if (Math.abs(d) < 0.5) spoke = true;
          }
        }
        cell(x, y, spoke ? C.ink : hubC);
      } else if (r <= rPack) {                                           // wound tape: rings, outer one brightest
        const ring = Math.floor(rPack - r);
        cell(x, y, ring === 0 ? (pink ? C.pink : C.grey) : ring % 2 ? (pink ? C.pinkDim : C.greyLow) : (pink ? C.pinkLow : C.greyMid));
      } else if (r > FLANGE - 0.9) cell(x, y, C.line);                    // the flange
    }
  }
  function tape(a, b, pink, dir) {                                       // a leg of tape: a solid run with marching dashes
    const base = pink ? C.pinkLow : C.greyMid, dash = pink ? C.pink : C.grey;
    line(a, b, (x, y, i, n) => {
      const j = dir > 0 ? i : n - i;
      cell(x, y, ((j - st.flow) % 5 + 5) % 5 < 3 ? dash : base);
    });
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    const rec = st.mode === 'recording', play = st.mode === 'playing';
    const pinkL = play || st.closing > 0;                                // left spool is blank tape until the loop is closed
    reel(LC, st.rL, st.angL, pinkL);
    reel(RC, st.rR, st.angR, rec || play);
    const Ls = { x: LC.x, y: LC.y + st.rL }, Rs = { x: RC.x, y: RC.y + st.rR };
    const Lh = { x: HEAD.x0 + 0.5, y: HEAD.y0 + 0.5 }, Rh = { x: HEAD.x1 + 0.5, y: HEAD.y0 + 0.5 };
    tape(Ls, Lh, play, 1);                                               // blank until the loop is closed
    tape(Rh, Rs, rec || play, 1);                                        // what has passed the head is recorded
    if (st.belt > 0) {                                                   // the splice: the top belt draws in left to right
      const a = { x: LC.x, y: LC.y - st.rL }, b = { x: RC.x, y: RC.y - st.rR };
      const full = { x: ease(a.x, b.x, st.belt), y: ease(a.y, b.y, st.belt) };
      tape(a, full, true, -1);
    }
    const on = st.clunk > 0;                                              // the head block
    const hc = rec ? (st.beat % 10 < 5 ? C.rec : C.pinkDim) : play ? (on ? C.text : C.pink) : C.line;
    for (let y = HEAD.y0; y <= HEAD.y1; y++) for (let x = HEAD.x0; x <= HEAD.x1; x++) cell(x, y, y === HEAD.y0 ? hc : C.greyMid);
  }

  // ---------- the clock: runs only while something is moving ----------
  let raf = 0, last = 0;
  function moving() {
    if (st.forced) return false;
    if (st.mode !== 'idle' || st.belt > 0 || st.closing > 0 || st.clunk > 0) return true;
    const t = target();
    return Math.abs(st.rL - t.rL) > 0.05 || Math.abs(st.rR - t.rR) > 0.05;
  }
  function loop(now) {
    raf = 0;
    if (now - last >= TICK) { last = now; step(now); draw(); }
    if (moving() && motion) raf = requestAnimationFrame(loop); else { settle(); draw(); }
  }
  function kickLoop() { if (!raf) raf = requestAnimationFrame(loop); }
  settle(); draw();

  // ---------- design review: a still of any state ----------
  window.OmniTape = {
    force(mode, seconds, pos) {
      st.forced = mode ? { mode, seconds, pos } : null;
      if (!mode) { change('idle', performance.now()); return; }
      st.mode = mode; st.seconds = seconds || 0; st.closing = 0; st.clunk = 0; st.belt = 0;
      settle(); st.rL = target().rL; st.rR = target().rR;
      const l = seconds || 4, turns = Math.max(1, Math.round(l / 1.5));
      st.angL = st.angR = mode === 'playing' ? TAU * turns * (pos || 0) : (pos || 0) * TAU;
      st.flow = mode === 'playing' ? Math.floor(turns * (pos || 0) * 15) : Math.floor((pos || 0) * 15); st.beat = 0;
      draw();
    },
  };
})();
