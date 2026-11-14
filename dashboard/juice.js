// OmniRiff dashboard "juice": visual feedback layered on top of app.js. Display only.
// It reads the same v1 state frames (app.js re-dispatches each one as 'omniriff:frame')
// and the data-* attributes app.js sets on #app. It never invents state: every effect is
// triggered by a real change in an engine frame. The only inputs it adds are keyboard
// shortcuts that press the existing manual buttons.
//   ?juice=off            disables all of it
//   prefers-reduced-motion keeps the stamps and the effect graphs, drops particles/flash/shake
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  if (params.get('juice') === 'off') return;
  const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;

  const $ = (id) => document.getElementById(id);
  const app = $('app');
  const css = getComputedStyle(document.documentElement);
  const C = (n) => css.getPropertyValue(n).trim();
  const P = {
    accent: C('--accent'), rec: C('--rec'), warn: C('--warn'), ok: C('--ok'), text: C('--text'),
    muted: C('--muted'), off: C('--off'), deep: C('--accent-deep'), dim: '#4A4858',
  };
  const TICK_MS = 1000 / 30;  // particles move in 30 Hz steps for the pixel feel
  const GRID = 3;             // particles snap to a 3 px grid
  const MAX_PARTICLES = 500;

  // ---------- layers ----------
  const layer = document.createElement('canvas');
  layer.className = 'juice-layer';
  layer.setAttribute('aria-hidden', 'true');
  const flash = document.createElement('div');
  flash.className = 'juice-flash';
  flash.setAttribute('aria-hidden', 'true');
  document.body.append(flash, layer);
  const lctx = layer.getContext('2d');

  // effect graphs: one small canvas per card, one big faint one behind the engaged panel
  function addViz(parent, before, cls) {
    const c = document.createElement('canvas');
    c.className = cls;
    c.setAttribute('aria-hidden', 'true');
    parent.insertBefore(c, before);
    return c;
  }
  const viz = {
    filter: addViz($('card-filter'), $('blocks-filter'), 'juice-viz'),
    reverb: addViz($('card-reverb'), $('blocks-reverb'), 'juice-viz'),
  };
  const engagedBg = addViz($('engaged'), $('engaged').firstChild, 'juice-bg');

  // offline "attract" screen: honest about the engine being gone, but not a dead page
  const attract = document.createElement('div');
  attract.className = 'juice-attract';
  attract.setAttribute('role', 'status');
  attract.innerHTML =
    '<div class="ja-logo"><span class="ja-mark"></span>OMNIRIFF</div>' +
    '<div class="ja-bars" aria-hidden="true">' + '<i></i>'.repeat(24) + '</div>' +
    '<div class="ja-state" id="jaState">WAITING FOR ENGINE</div>' +
    '<div class="ja-hint" id="jaHint">python -m tools.sim run --demo</div>';
  attract.querySelectorAll('.ja-bars i').forEach((b, i) => {
    b.style.animationDelay = (-(i * 0.09) % 1.2).toFixed(2) + 's';
  });
  document.body.appendChild(attract);

  // ---------- helpers ----------
  const rect = (el) => el.getBoundingClientRect();
  const center = (el) => { const r = rect(el); return [r.left + r.width / 2, r.top + r.height / 2]; };
  const rnd = (a, b) => a + Math.random() * (b - a);
  const level = (db) => Math.max(0, Math.min(1, (db + 60) / 60));

  function restart(el, cls, ms) {
    el.classList.remove(cls);
    void el.offsetWidth;  // restart the CSS animation
    el.classList.add(cls);
    clearTimeout(el['_j' + cls]);
    el['_j' + cls] = setTimeout(() => el.classList.remove(cls), ms);
  }
  function doFlash(color) {
    if (!motion) return;
    flash.style.background = color;
    restart(flash, 'go', 300);
  }
  function shake(el) { if (motion) restart(el, 'juice-shake', 260); }
  function stamp(text, color) {
    const host = document.querySelector('.wave');
    host.querySelectorAll('.juice-stamp').forEach((n) => n.remove());
    const d = document.createElement('div');
    d.className = 'juice-stamp';
    d.textContent = text;
    d.style.color = color;
    host.appendChild(d);
    setTimeout(() => d.remove(), 1100);
  }

  // ---------- particles ----------
  const parts = [];
  // mode 'home': flies to (tx, ty) and "injects" into the target element on arrival
  // mode 'fall': sprays out and falls under gravity until its life runs out
  function emit(n, x, y, opt) {
    if (!motion) return;
    for (let i = 0; i < n && parts.length < MAX_PARTICLES; i++) {
      parts.push({
        x: x + rnd(-6, 6), y: y + rnd(-6, 6),
        vx: (opt.vx ?? 0) + rnd(-opt.spread, opt.spread), vy: (opt.vy ?? 0) + rnd(-opt.spread, opt.spread),
        tx: opt.tx, ty: opt.ty, hit: opt.hit, mode: opt.mode, color: opt.color,
        size: opt.size || (Math.random() < 0.3 ? 6 : 3), life: opt.life || 40, age: 0, px: x, py: y,
      });
    }
  }
  function step() {
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i];
      p.px = p.x; p.py = p.y; p.age++;
      if (p.mode === 'home') {
        const dx = p.tx - p.x, dy = p.ty - p.y, d = Math.hypot(dx, dy) || 1;
        const sp = Math.min(34, 6 + p.age * 1.6);
        p.vx = p.vx * 0.82 + (dx / d) * sp * 0.18;
        p.vy = p.vy * 0.82 + (dy / d) * sp * 0.18;
        p.x += p.vx; p.y += p.vy;
        if (d < 14 || p.age > 90) {
          if (p.hit && d < 14) restart(p.hit, 'juice-hit', 140);
          parts.splice(i, 1);
        }
      } else {
        p.vy += 0.7; p.vx *= 0.97;
        p.x += p.vx; p.y += p.vy;
        if (p.age > p.life) parts.splice(i, 1);
      }
    }
  }
  function drawParticles() {
    const dpr = window.devicePixelRatio || 1;
    const w = innerWidth, h = innerHeight;
    if (layer.width !== Math.round(w * dpr) || layer.height !== Math.round(h * dpr)) {
      layer.width = Math.round(w * dpr); layer.height = Math.round(h * dpr);
    }
    lctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    lctx.clearRect(0, 0, w, h);
    const g = (v) => Math.round(v / GRID) * GRID;
    for (const p of parts) {
      const fade = p.mode === 'fall' ? Math.max(0, 1 - p.age / p.life) : 1;
      lctx.globalAlpha = 0.35 * fade;  // one-step trail
      lctx.fillStyle = p.color;
      lctx.fillRect(g(p.px), g(p.py), p.size, p.size);
      lctx.globalAlpha = Math.ceil(fade * 3) / 3;  // stepped fade
      lctx.fillRect(g(p.x), g(p.y), p.size, p.size);
    }
    lctx.globalAlpha = 1;
  }

  // ---------- effect graphs ----------
  // filter: the low-pass magnitude response (2-pole approximation) on a log frequency axis
  // reverb: the dry hit followed by a decaying tail whose height follows the wet amount
  function sizeCanvas(c) {
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return null;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
    }
    const x = c.getContext('2d');
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    x.clearRect(0, 0, w, h);
    return [x, w, h];
  }
  const tailShape = Array.from({ length: 64 }, (_, i) => 0.7 + 0.3 * Math.abs(Math.sin(i * 12.9898) * 43758.5453 % 1));
  function drawGraph(c, kind, st, opts) {
    const got = sizeCanvas(c);
    if (!got || !st || !st[kind]) return;
    const [x, w, h] = got;
    const bw = opts.bw, gap = opts.gap, q = opts.q;
    const cols = Math.max(4, Math.floor((w + gap) / (bw + gap)));
    const on = opts.color, off = opts.offColor, mark = opts.mark || P.text;
    if (kind === 'filter') {
      const v = st.filter.value;
      const fc = v >= 0.995 ? 40000 : Math.max(20, st.filter.cutoff_hz || 20000);
      const lo = Math.log10(20), hi = Math.log10(20000);
      let cutCol = -1;
      for (let i = 0; i < cols; i++) {
        const f = Math.pow(10, lo + (hi - lo) * (i + 0.5) / cols);
        const fNext = Math.pow(10, lo + (hi - lo) * (i + 1.5) / cols);
        if (cutCol < 0 && fNext > fc) cutCol = i;
        const gain = 1 / Math.sqrt(1 + Math.pow(f / fc, 4));
        const bh = Math.max(q, Math.round((gain * h) / q) * q);
        x.fillStyle = i === cutCol ? mark : gain > 0.7 ? on : off;
        x.fillRect(i * (bw + gap), h - bh, bw, bh);
      }
    } else {
      const wet = st.reverb.value;
      for (let i = 0; i < cols; i++) {
        let a;
        if (i === 0) a = 1;  // the dry hit
        else a = wet * Math.exp(-(i - 1) / (cols * (0.15 + 0.3 * wet))) * tailShape[i % tailShape.length];
        const bh = Math.max(q, Math.round((a * h) / q) * q);
        x.fillStyle = i === 0 ? mark : a > 0.02 ? on : off;
        x.fillRect(i * (bw + gap), h - bh, bw, bh);
      }
    }
  }

  // ---------- frame-driven events ----------
  let s = null, lastLoop = null, playStart = 0, lastPos = 0;
  let lastBypass = null, lastClip = false, lastFx = 'idle', everLive = false, offlineSince = performance.now();
  const prev = { filter: null, reverb: null };

  window.addEventListener('omniriff:frame', (e) => {
    const f = e.detail;
    const now = performance.now();
    const first = s === null;
    s = f;
    const wave = document.querySelector('.wave');
    const wr = rect(wave);

    // loop transitions
    const ls = f.loop && f.loop.state;
    if (!first && ls !== lastLoop) {
      if (ls === 'recording') {
        stamp('REC', P.rec); doFlash(P.rec);
      } else if (ls === 'playing') {
        playStart = now; lastPos = 0;
        if (lastLoop === 'recording') {
          stamp('LOOP ' + (f.loop.seconds || 0).toFixed(1) + 'S', P.accent); doFlash(P.accent);
          emit(40, wr.left + wr.width / 2, wr.top + wr.height / 2, { mode: 'fall', color: P.accent, spread: 12, vy: -8, life: 34 });
        }
      } else if (ls === 'idle' && lastLoop) {
        stamp('CLEARED', P.muted);
        // the old loop crumbles off the waveform
        for (let i = 0; i < 70; i++) {
          emit(1, rnd(wr.left + 12, wr.right - 12), wr.top + wr.height / 2 + rnd(-wr.height / 4, wr.height / 4),
            { mode: 'fall', color: Math.random() < 0.5 ? P.dim : P.accent, spread: 3, vy: -3, life: rnd(20, 40) });
        }
      }
    }
    if (ls === 'playing' && first) playStart = now;
    lastLoop = ls;

    // recording: the input is sucked into the new end of the loop
    if (ls === 'recording' && level(f.input_peak_dbfs) > 0.45 && Math.random() < 0.6) {
      const [mx, my] = center($('inSegs'));
      emit(1, mx, my, { mode: 'home', tx: wr.right - 20, ty: wr.top + wr.height / 2 + rnd(-30, 30), color: P.rec, spread: 6, vy: 6, hit: wave });
    }

    // effect moves: inject particles from the control into the loop, at the playhead if it's playing
    for (const k of ['filter', 'reverb']) {
      const v = f[k] && f[k].value;
      if (typeof v !== 'number') continue;
      if (prev[k] !== null && !first) {
        const dv = Math.abs(v - prev[k]);
        if (dv > 0.004) {
          const engaged = app.dataset.fx === 'engaged';
          const src = engaged ? (document.querySelector('.tower i.top') || $('tower')) : $('card-' + k).querySelector('.juice-viz');
          const [sx, sy] = center(src);
          let tx = wr.left + wr.width * rnd(0.3, 0.9);
          if (ls === 'playing' && f.loop.seconds > 0) tx = wr.left + 12 + lastPos * (wr.width - 24);
          emit(Math.min(6, Math.ceil(dv * 80)), sx, sy, { mode: 'home', tx, ty: wr.top + wr.height / 2 + rnd(-24, 24), color: P.accent, spread: 10, vy: -6, hit: wave });
        }
      }
      prev[k] = v;
    }

    // bypass slam
    if (!first && lastBypass !== null && !!f.bypass !== lastBypass) {
      shake(document.querySelector('.fx-zone'));
      doFlash(f.bypass ? P.warn : P.ok);
      if (!f.bypass) stamp('FX ON', P.ok);
    }
    lastBypass = !!f.bypass;
  });

  // ---------- per-tick work ----------
  let lastTick = 0;
  const brand = document.querySelector('.brand-mark');
  function tick(now) {
    requestAnimationFrame(tick);
    if (now - lastTick < TICK_MS) return;
    lastTick = now;
    const conn = app.dataset.conn;

    // attract screen after 1.5 s offline
    if (conn !== 'offline') { everLive = everLive || conn === 'live'; offlineSince = now; }
    const showAttract = now - offlineSince > 1500;
    attract.classList.toggle('on', showAttract);
    if (showAttract) {
      $('jaState').textContent = everLive ? 'ENGINE OFFLINE · RECONNECTING' : 'WAITING FOR ENGINE';
      $('jaHint').style.visibility = everLive ? 'hidden' : 'visible';
    }

    if (s && conn === 'live') {
      // downbeat: the loop wraps around
      if (s.loop && s.loop.state === 'playing' && s.loop.seconds > 0) {
        const pos = ((now - playStart) / 1000 / s.loop.seconds) % 1;
        if (pos < lastPos) {
          restart(document.querySelector('.loop-state'), 'juice-beat', 180);
          const wr = rect(document.querySelector('.wave'));
          emit(10, wr.left + 14, wr.top + wr.height / 2, { mode: 'fall', color: P.text, spread: 5, vx: 4, vy: -7, life: 22 });
        }
        lastPos = pos;
      }
      // the brand mark breathes with the output level, in steps
      const lv = Math.round(level(s.output_peak_dbfs) * 4) / 4;
      brand.style.transform = 'scale(' + (1 + lv * 0.3).toFixed(2) + ')';
    } else {
      brand.style.transform = '';
    }

    // clip light came on
    const clip = $('inClip').classList.contains('on');
    if (clip && !lastClip) shake(document.querySelector('.bar .meter'));
    lastClip = clip;

    // hand takes over: burst from the hand view into the engaged panel
    const fxState = app.dataset.fx;
    if (fxState === 'engaged' && lastFx !== 'engaged') {
      const [hx, hy] = center($('handPanel'));
      const [ex, ey] = center($('engaged'));
      emit(18, hx, hy, { mode: 'home', tx: ex, ty: ey, color: P.accent, spread: 14, hit: $('engaged') });
    }
    lastFx = fxState;

    // effect graphs
    if (s) {
      for (const k of ['filter', 'reverb']) {
        const tgt = $('card-' + k).classList.contains('target');
        drawGraph(viz[k], k, s, { bw: 6, gap: 2, q: 4, color: tgt ? P.accent : P.text, offColor: P.off });
      }
      if (fxState === 'engaged') {
        const k = $('engName').textContent.toLowerCase();
        if (k === 'filter' || k === 'reverb') drawGraph(engagedBg, k, s, { bw: 14, gap: 4, q: 8, color: P.deep, offColor: '#1A1822', mark: '#5A2A75' });
      }
    }

    step();
    drawParticles();
  }
  requestAnimationFrame(tick);

  // ---------- keyboard ----------
  // F fullscreen, L loop, B bypass (the same as pressing the manual buttons)
  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    const k = e.key.toLowerCase();
    if (k === 'f') {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {});
    } else if (k === 'l') $('btnLoop').click();
    else if (k === 'b') $('btnBypass').click();
  });
})();
