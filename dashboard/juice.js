// OmniRiff dashboard feedback layer, on top of app.js. Display only.
// It reads the same v1 state frames (app.js re-dispatches each one as 'omniriff:frame')
// and the data-* attributes app.js sets on #app. It never invents state: every effect is
// triggered by a real change in an engine frame, and it lands on the element that changed
// (BRAND_SPEC.md section 8). The only inputs it adds are keyboard shortcuts that press the
// existing manual keys.
//   ?juice=off            disables all of it
//   prefers-reduced-motion keeps the stamps and the effect graphs, drops hits and shakes
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
    accent: C('--accent'), rec: C('--rec'), ok: C('--ok'), text: C('--text'),
    muted: C('--muted'), off: C('--off'), deep: C('--accent-deep'), dim: C('--dim'), panel2: C('--panel-2'),
  };
  const TICK_MS = 1000 / 30;  // graphs redraw at 30 Hz

  // ---------- layers ----------
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

  // offline screen: says the engine is gone and how to start one. The LED row scans because
  // the page really is retrying the socket.
  const attract = document.createElement('div');
  attract.className = 'juice-attract';
  attract.setAttribute('role', 'status');
  attract.innerHTML =
    '<div class="logo x6"><span data-logo="lockup"></span></div>' +
    '<div class="ja-scan" aria-hidden="true">' + '<i></i>'.repeat(8) + '</div>' +
    '<div class="ja-state" id="jaState">NO ENGINE</div>' +
    '<dl class="ja-how" id="jaHint">' +
    '<dt>RIG</dt><dd>python -m engine.demo --open</dd>' +
    '<dt>SIM</dt><dd>python -m tools.sim run --demo</dd></dl>';
  attract.querySelectorAll('.ja-scan i').forEach((b, i) => { b.style.animationDelay = (i * 0.15 - 1.2).toFixed(2) + 's'; });
  document.body.appendChild(attract);
  if (window.OmniBrand) window.OmniBrand.mount(attract);

  // ---------- helpers ----------

  function restart(el, cls, ms) {
    el.classList.remove(cls);
    void el.offsetWidth;  // restart the CSS animation
    el.classList.add(cls);
    clearTimeout(el['_j' + cls]);
    el['_j' + cls] = setTimeout(() => el.classList.remove(cls), ms);
  }
  // a hit: the panel that changed flashes its border in the colour of the change
  function hit(el, color) {
    if (!motion) return;
    el.style.setProperty('--hit', color);
    restart(el, 'juice-hit', 260);
  }
  function shake(el) { if (motion) restart(el, 'juice-shake', 260); }
  function stamp(text, color) {
    const host = document.querySelector('.wave');
    host.querySelectorAll('.juice-stamp').forEach((n) => n.remove());
    const d = document.createElement('div');
    d.className = 'stamp juice-stamp';
    d.textContent = text;
    d.style.color = color;
    host.appendChild(d);
    setTimeout(() => d.remove(), 1100);
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

  const wavePanel = document.querySelector('.wave');
  function fxStamp(text, color) {
    const host = document.querySelector('.fx-zone');
    host.querySelectorAll('.juice-stamp').forEach((n) => n.remove());
    const d = document.createElement('div');
    d.className = 'stamp juice-stamp';
    d.textContent = text;
    d.style.color = color;
    host.appendChild(d);
    setTimeout(() => d.remove(), 1100);
  }

  // ---------- frame-driven events ----------
  let s = null, lastLoop = null, playStart = 0, lastPos = 0;
  let lastBypass = null, lastClip = false, everLive = false, offlineSince = performance.now();

  window.addEventListener('omniriff:frame', (e) => {
    const f = e.detail;
    const now = performance.now();
    const first = s === null;
    s = f;

    // loop transitions
    const ls = f.loop && f.loop.state;
    if (!first && ls !== lastLoop) {
      if (ls === 'recording') {
        stamp('REC', P.rec); hit(wavePanel, P.rec);
      } else if (ls === 'playing') {
        playStart = now; lastPos = 0;
        if (lastLoop === 'recording') {
          stamp('LOOP ' + (f.loop.seconds || 0).toFixed(1) + 'S', P.accent); hit(wavePanel, P.accent);
        }
      } else if (ls === 'idle' && lastLoop) {
        stamp('CLEARED', P.muted); hit(wavePanel, P.muted);
      }
    }
    if (ls === 'playing' && first) playStart = now;
    lastLoop = ls;

    // bypass slam
    if (!first && lastBypass !== null && !!f.bypass !== lastBypass) {
      shake(document.querySelector('.fx-zone'));
      if (!f.bypass) fxStamp('FX ON', P.ok);
    }
    lastBypass = !!f.bypass;
  });

  // ---------- per-tick work ----------
  let lastTick = 0;
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
      $('jaState').textContent = everLive ? 'ENGINE LOST · RETRYING' : 'NO ENGINE · START ONE';
      $('jaHint').style.visibility = everLive ? 'hidden' : 'visible';
    }

    if (s && conn === 'live') {
      // downbeat: the loop wraps around
      if (s.loop && s.loop.state === 'playing' && s.loop.seconds > 0) {
        const pos = ((now - playStart) / 1000 / s.loop.seconds) % 1;
        if (pos < lastPos) {
          restart(document.querySelector('.loop-state'), 'juice-beat', 180);
        }
        lastPos = pos;
      }
    }

    // clip light came on
    const clip = $('inClip').classList.contains('on');
    if (clip && !lastClip) shake(document.querySelector('.meters'));
    lastClip = clip;

    const fxState = app.dataset.fx;

    // effect graphs
    if (s) {
      for (const k of ['filter', 'reverb']) {
        const tgt = $('card-' + k).classList.contains('target');
        drawGraph(viz[k], k, s, { bw: 6, gap: 2, q: 4, color: tgt ? P.accent : P.dim, offColor: P.off });
      }
      if (fxState === 'engaged') {
        const k = $('engName').textContent.toLowerCase();
        if (k === 'filter' || k === 'reverb') drawGraph(engagedBg, k, s, { bw: 12, gap: 4, q: 8, color: P.deep, offColor: P.panel2, mark: C('--accent-dim') });
      }
    }

  }
  requestAnimationFrame(tick);

  // ---------- keyboard ----------
  // F fullscreen, L loop, B bypass (the same as pressing the manual keys; the key travels too)
  function tap(btn) {
    btn.classList.add('down');
    setTimeout(() => btn.classList.remove('down'), 100);
    btn.click();
  }
  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    const k = e.key.toLowerCase();
    if (k === 'f') {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {});
    } else if (k === 'l') tap($('btnLoop'));
    else if (k === 'b') tap($('btnBypass'));
  });
})();
