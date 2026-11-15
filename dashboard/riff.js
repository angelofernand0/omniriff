// Riff: the coach character. This file draws and animates the avatar and exposes a small API.
// It contains no AI, opens no socket and sends nothing to the engine; coach.js drives it from
// the coach feed.
//
//   OmniRiff.coach.set({ state, target, cue, mood })
//     state   asleep | idle | listening | thinking | speaking | pointing | pleased
//     target  an element or selector Riff travels to (null = home dock)
//     cue     one short line Riff says (shown in a bubble, or in the dock when home)
//     mood    neutral | curious | concentrating | aha | concerned | encouraging | proud | sleepy
//   OmniRiff.portrait(state, size, mood)   a still, for the brand sheet
//
//   ?coach=off       hides Riff and the dock
//   ?coach=preview   scripted tour of states and moods, labelled PREVIEW on screen. Not AI.
//
// Drawing: real pixel art. Riff is rasterised every frame on a 36x36 grid (the logo mark's
// language: knurled pink body, tall ink eyes with one paper glint, no whites, no mouth) and
// scaled 3x with hard pixel edges. Squash and stretch happen inside the grid, so Riff stays
// pixel art while it deforms.
//
// Motion: springs, not keyframes. Travel has anticipation (eyes lead, a wind-up squash), a
// volume-preserving stretch along the velocity, and an underdamped landing squash that wobbles
// out. Talking (real voice loudness), listening (real input level), hops and leans all feed the
// same deformation springs, so they blend instead of snapping.
//
// Rules (BRAND_SPEC.md section 7): Riff is the only round, smoothly moving thing on screen.
// Small signs of life (blinks, glances) are allowed; anything larger follows a real event.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const mode = params.get('coach') || 'on';
  const dock = document.getElementById('coachDock');
  const led = document.getElementById('led-coach');
  const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SIZE = 72;           // the box Riff occupies (24 grid cells at 3px)
  const G = 36, PX = 3;      // render grid and pixel size; the grid overhangs the 24-cell box for stretch
  const STATES = ['asleep', 'idle', 'listening', 'thinking', 'speaking', 'pointing', 'pleased'];
  const MOODS = ['neutral', 'curious', 'concentrating', 'aha', 'concerned', 'encouraging', 'proud', 'sleepy'];
  // what each state looks like when the feed doesn't say (preview, older coaches)
  const STATE_MOOD = { asleep: 'sleepy', idle: 'neutral', listening: 'concentrating', thinking: 'curious',
    speaking: 'neutral', pointing: 'encouraging', pleased: 'proud' };

  // ---------- palette (brand tokens) ----------
  const css = getComputedStyle(document.documentElement);
  const hex = (v, d) => {
    const s = (css.getPropertyValue(v) || '').trim() || d;
    const n = parseInt(s.replace('#', ''), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const PAL = {
    awake: { body: hex('--accent', '#FF5CCB'), light: [255, 168, 228], shade: hex('--accent-shade', '#D63FA6'), rim: hex('--accent-low', '#B4318A') },
    asleep: { body: hex('--accent-shade', '#D63FA6'), light: hex('--accent', '#FF5CCB'), shade: hex('--accent-low', '#B4318A'), rim: hex('--accent-dim', '#7A2A62') },
    ink: hex('--bg', '#0B0B10'), paper: [255, 255, 255],
  };

  // ---------- face presets: lids cut the ink eyes ----------
  //   top/bot: lid closure from above/below (0..1); tilt: inner corners down (+) / up (-);
  //   l/r: eye scale; arc: draw happy arcs instead of eyes
  const FACE = {
    neutral:       { top: 0,    bot: 0,    tilt: 0,     l: 1,    r: 1 },
    curious:       { top: 0,    bot: 0,    tilt: 0,     l: 1.15, r: 0.85, head: 0.13 },
    concentrating: { top: 0.42, bot: 0.12, tilt: 0,     l: 1,    r: 1 },
    aha:           { top: 0,    bot: 0,    tilt: 0,     l: 1.22, r: 1.22 },
    concerned:     { top: 0.2,  bot: 0,    tilt: 0.38,  l: 1,    r: 1, head: -0.05 },
    encouraging:   { top: 0,    bot: 0.34, tilt: -0.2,  l: 1,    r: 1 },
    proud:         { top: 0,    bot: 0,    tilt: 0,     l: 1,    r: 1, arc: 1 },
    sleepy:        { top: 0.62, bot: 0,    tilt: 0,     l: 1,    r: 1 },
  };

  // ---------- the rasteriser ----------
  // p: { spin, d, a, v, tilt, hop, lookX, lookY, lidL, lidR, face, asleep, glint }
  function render(ctx, img, p) {
    const data = img.data;
    const pal = p.asleep ? PAL.asleep : PAL.awake;
    const cx = G / 2, cy = G / 2 + 0.5 - p.hop;
    const r0 = 10.4;
    const ca = Math.cos(p.a), sa = Math.sin(p.a);
    const ct = Math.cos(-p.tilt), st_ = Math.sin(-p.tilt);
    const sd = 1 + p.d, sv = 1 + p.v;
    const f = p.face;
    const eyes = [
      { side: -1, x: -4.1 + p.lookX * 1.7, y: -1.2 + p.lookY * 1.5, s: f.l, lid: p.lidL },
      { side: 1, x: 4.1 + p.lookX * 1.7, y: -1.2 + p.lookY * 1.5, s: f.r, lid: p.lidR },
    ];
    for (let y = 0; y < G; y++) {
      for (let x = 0; x < G; x++) {
        // undo the deformation to find this pixel in body space
        let qx = x + 0.5 - cx, qy = y + 0.5 - cy;
        let tx = qx * ct - qy * st_, ty = qx * st_ + qy * ct;             // head tilt
        ty /= sv; tx *= sv;                                                 // vertical squash (volume kept)
        let ux = tx * ca + ty * sa, uy = -tx * sa + ty * ca;                // into the travel frame
        ux /= sd; uy *= sd;                                                 // stretch along travel
        qx = ux * ca - uy * sa; qy = ux * sa + uy * ca;
        const r = Math.hypot(qx, qy), th = Math.atan2(qy, qx);
        // knurled edge: 8 even ridges that turn with the knob
        const k = Math.cos(8 * (th - p.spin));
        const R = r0 + 0.62 * k;
        const i = (y * G + x) * 4;
        if (r > R) { data[i + 3] = 0; continue; }
        // shading, kept to two thin arcs so the silhouette stays clean: light top-left, rim bottom-right
        const nx = qx / (r || 1), ny = qy / (r || 1);
        const edge = R - r;
        const lit = -(nx * 0.62 + ny * 0.78);
        let c = pal.body;
        if (edge < 1.25 && lit < -0.5) c = pal.shade;
        else if (edge < 1.25 && lit > 0.72) c = pal.light;
        // eyes
        for (const e of eyes) {
          const ink = eyePixel(qx - e.x, qy - e.y, e, f, p);
          if (ink) { c = ink === 2 ? PAL.paper : PAL.ink; break; }
        }
        // mouth: only while Riff talks; it opens with the loudness of its own voice
        if (p.mouth > 0.05 && !p.asleep) {
          const mx = qx - p.lookX * 1.2, my = qy - (4.9 + p.lookY * 0.8);
          const mw = 1.5 + 1.1 * p.mouth, mh = 0.45 + 1.9 * p.mouth;
          if ((mx / mw) ** 2 + (my / mh) ** 2 <= 1) c = PAL.ink;
        }
        data[i] = c[0]; data[i + 1] = c[1]; data[i + 2] = c[2]; data[i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  // 0 = body, 1 = ink, 2 = paper (glint)
  function eyePixel(dx, dy, e, f, p) {
    const w = 3.6 * e.s, h = 6.8 * e.s;
    if (p.asleep || e.lid > 0.88) {                 // closed: a resting curve
      const yy = dy - (p.asleep ? 0.2 : 0.6);
      return Math.abs(dx) < w * 0.75 && Math.abs(yy - 0.18 * dx * dx) < 0.62 ? 1 : 0;
    }
    if (f.arc) {                                     // proud: happy arcs (upside-down U)
      const rr = Math.hypot(dx, dy - 1.6);
      return dy < 1.8 && rr > 1.45 && rr < 2.75 ? 1 : 0;
    }
    if (Math.abs(dx) > w / 2 || Math.abs(dy) > h / 2) return 0;
    if (Math.abs(dx) > w / 2 - 0.7 && Math.abs(dy) > h / 2 - 0.7) return 0;   // pill corners
    // lids: blink/wink closes from the top; the mood shapes top and bottom; tilt drops the inner corner
    const inner = -e.side * dx;                                                // + toward the nose
    const top = -h / 2 + h * Math.max(e.lid, f.top) + f.tilt * inner * 0.9;
    const bot = h / 2 - h * f.bot;
    if (dy < top || dy > bot) return 0;
    // glint: one paper pixel high on the outside. It always shows while the eye is open (SM): a lid
    // pushes it down instead of hiding it, and the hit box is wide enough that a pixel always lands
    const gx = w / 2 - 1.15 + p.glint * 0.3, gy = Math.min(Math.max(-h / 2 + 1.35, top + 1.1), bot - 1.1);
    const gr = 0.78 + p.glint * 0.25;
    if (bot - top > 1.6 && Math.abs(dx - gx) < gr && Math.abs(dy - gy) < gr) return 2;
    return 1;
  }

  function makeCanvas(cssSize) {
    const c = document.createElement('canvas');
    c.width = c.height = G;
    c.className = 'riff-px';
    c.style.width = c.style.height = cssSize + 'px';
    return c;
  }

  function stillParams(state, mood) {
    const m = mood || STATE_MOOD[state] || 'neutral';
    const face = { ...FACE[m] };
    if (state === 'pleased') Object.assign(face, FACE.proud);
    const look = { thinking: [0.6, -0.7], listening: [-0.4, 0.5], pointing: [-0.8, 0.4] }[state] || [0, 0];
    return { spin: 0, d: 0, a: 0, v: 0, tilt: face.head || 0, hop: 0, lookX: look[0], lookY: look[1],
      lidL: 0, lidR: 0, face, asleep: state === 'asleep', glint: m === 'aha' ? 1 : 0, mouth: state === 'speaking' ? 0.5 : 0 };
  }

  // a still portrait of one state (and mood), for the brand sheet and docs. No behaviour.
  function portrait(state, size = 96, mood) {
    const d = document.createElement('div');
    d.className = 'riff riff-still';
    d.dataset.state = state;
    d.style.width = d.style.height = size + 'px';
    const c = makeCanvas(size * G / 24);
    d.appendChild(c);
    const ctx = c.getContext('2d');
    render(ctx, ctx.createImageData(G, G), stillParams(state, mood));
    if (state === 'asleep') d.insertAdjacentHTML('beforeend', '<span class="riff-z" aria-hidden="true">z</span>');
    return d;
  }
  window.OmniRiff = window.OmniRiff || {};
  window.OmniRiff.portrait = portrait;
  window.OmniRiff.states = STATES.slice();
  window.OmniRiff.moods = MOODS.slice();

  if (mode === 'off' || document.documentElement.dataset.riff === 'portraits') {
    if (mode === 'off') { if (dock) dock.hidden = true; if (led) led.hidden = true; }
    return;
  }

  // ---------- the live character ----------
  const el = document.createElement('div');
  el.className = 'riff';
  el.dataset.state = 'asleep';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', 'Riff, the coach');
  el.innerHTML = '<div class="riff-sq"><span class="riff-z" aria-hidden="true">z</span></div><div class="riff-cue" role="status"></div>';
  const canvas = makeCanvas(G * PX);
  const PX_HOME = 4, PX_CONTROL = 4.5, PX_STAGE = 8;   // CSS px per grid cell in each place
  let cssPx = PX_HOME, cssPxV = 0;
  const box = () => 24 * cssPx;                          // the square Riff occupies
  // the pointing hand: a pixel glove with one finger out (ink outline, paper fill)
  const FINGER = ['.....#######.', '....#+++++++#', '.####+#######', '#+++#+#......', '#++++++#.....', '#++++++#.....', '.######......'];
  const finger = document.createElement('canvas');
  finger.width = FINGER[0].length; finger.height = FINGER.length;
  finger.className = 'riff-finger';
  { const fx = finger.getContext('2d');
    FINGER.forEach((row, y) => [...row].forEach((ch, x) => {
      if (ch === '.') return;
      fx.fillStyle = ch === '#' ? `rgb(${PAL.ink})` : `rgb(${PAL.paper})`;
      fx.fillRect(x, y, 1, 1);
    })); }
  let pressAt = -1e9, contactDone = true, lastBypass = null;
  const PRESS = { back: 170, hit: 250, end: 640 };   // ms: wind-up until back, lunge until hit, recoil until end
  // a press that happened while Riff was still on its way: it keeps that target, arrives, then presses
  let lockEl = null, lockUntil = 0, pendingPress = false;
  const curTarget = () => (performance.now() < lockUntil && lockEl ? lockEl : resolve(st.target));
  el.querySelector('.riff-sq').prepend(canvas);
  el.appendChild(finger);
  document.body.appendChild(el);
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(G, G);
  const cueEl = el.querySelector('.riff-cue');
  const socket = document.querySelector('.riff-socket');
  const stageEl = document.querySelector('.riff-stage');
  const dockLine = document.getElementById('coachLine');
  // while Riff is out, its home keeps a dotted outline, so the bubble still points at someone
  let ghost = null;
  if (socket) {
    ghost = document.createElement('div');
    ghost.className = 'riff-ghost';
    ghost.setAttribute('aria-hidden', 'true');
    const gc = makeCanvas(0);
    gc.className = 'riff-px riff-ghost-px';
    const gx = gc.getContext('2d'), gi = gx.createImageData(G, G);
    const inside = (x, y) => { const qx = x + 0.5 - G / 2, qy = y + 0.5 - G / 2 - 0.5, r = Math.hypot(qx, qy);
      return r <= 10.4 + 0.62 * Math.cos(8 * Math.atan2(qy, qx)); };
    const col = hex('--muted', '#8A8A9A');
    for (let y = 0; y < G; y++) for (let x = 0; x < G; x++) {
      const edge = inside(x, y) && (!inside(x - 1, y) || !inside(x + 1, y) || !inside(x, y - 1) || !inside(x, y + 1));
      const i = (y * G + x) * 4;
      if (edge && (x + y) % 2 === 0) { gi.data[i] = col[0]; gi.data[i + 1] = col[1]; gi.data[i + 2] = col[2]; gi.data[i + 3] = 255; }
    }
    gx.putImageData(gi, 0, 0);
    ghost.append(gc);
    socket.appendChild(ghost);
  }
  const dockSub = document.getElementById('coachSub');

  const st = { state: 'asleep', target: null, cue: '', mood: 'sleepy', moodSet: false };
  const pos = { x: 0, y: 0, vx: 0, vy: 0, placed: false };
  const look = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0 };
  const def = { d: 0, dv: 0, a: 0, v: 0, vv: 0, tilt: 0, tv: 0, hop: 0 };
  const face = { ...FACE.sleepy };
  let spin = 0, spinV = 0, twist = 0;
  let moving = false, docked = true, last = performance.now();
  let windupUntil = 0, lastGoal = null;
  let blinkStart = -1e9, blinkAt = performance.now() + 2500, doubleBlink = false;
  let winkStart = -1e9, winkSide = 1, ahaUntil = 0, peekUntil = 0;
  let level = 0, voice = 0, voiceAt = 0, hopPhase = 0, mouth = 0, syl = false;
  let lastLoop = null, lastStrum = null;

  // real signals: the guitar's level, Riff's own voice, loop record, strums (G live layer)
  window.addEventListener('omniriff:frame', (e) => {
    const f = e.detail || {};
    if (typeof f.input_peak_dbfs === 'number') level = Math.max(0, Math.min(1, (f.input_peak_dbfs + 48) / 48));
    const loop = f.loop && f.loop.state;
    if (loop === 'recording' && lastLoop && lastLoop !== 'recording' && st.state !== 'asleep') pop(0.9);   // eyes widen: it's listening now
    lastLoop = loop || lastLoop;
    if (typeof f.bypass === 'boolean') {
      const t = resolve(st.target);
      if (lastBypass !== null && f.bypass !== lastBypass && t && t.id === 'fxPower') {
        lockEl = t; lockUntil = performance.now() + 1500; pendingPress = true;
      }
      lastBypass = f.bypass;
    }
    const strum = f.live && f.live.last_strum_ms;
    if (strum && strum !== lastStrum && lastStrum !== null && st.state === 'listening') pop(0.35);          // a tiny pop per real strum
    lastStrum = strum || lastStrum;
  });
  window.addEventListener('omniriff:voice', (e) => {
    const v = e.detail && e.detail.level;
    voice = typeof v === 'number' ? Math.max(0, Math.min(1, v)) : 0;
    voiceAt = performance.now();
  });
  function press() {                      // Riff winds up, lunges and pushes the control it is standing at
    pressAt = performance.now(); contactDone = false;
    def.vv += 1.4;                         // gathers itself
  }
  function contact() {                   // the finger lands: the control moves now, not before
    const t = curTarget();
    if (t) {
      t.classList.add('pressed'); setTimeout(() => t.classList.remove('pressed'), 220);
      window.dispatchEvent(new CustomEvent('omniriff:riffpress', { detail: { el: t } }));
    }
    def.dv -= 4.5; def.vv -= 1.2;          // squash on impact, wobble out
  }
  function pop(strength) { def.vv += 3.2 * strength; ahaUntil = performance.now() + 260 * strength; }

  function resolve(t) {
    if (!t) return null;
    return typeof t === 'string' ? document.querySelector(t) : t;
  }
  function stagePoint() {
    if (!st.stage || !stageEl) return null;
    const r = stageEl.getBoundingClientRect();
    return r.width ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
  }
  function homePoint() {
    const sp = stagePoint();
    if (sp) return sp;
    if (socket) { const r = socket.getBoundingClientRect(); if (r.width) return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
    return { x: window.innerWidth - 60, y: window.innerHeight - 60 };
  }
  // perch inside a corner of the thing being operated (data-perch="tr|tl|br|bl", default tr)
  function goalPoint() {
    const t = curTarget();
    if (!t) return homePoint();
    const r = t.getBoundingClientRect();
    if (!r.width) return homePoint();
    const perch = t.dataset.perch || 'tr';
    // a control (a button): stand beside it and reach over with the finger; a panel: perch in a corner
    if (t.dataset.reach === 'down') {     // perch on the panel's top edge over the spot, point down into it
      // (SM review 4: standing inside the waveform crowded it; on the edge, the bars stay readable)
      const bar = document.querySelector('.bar');
      const floor = (bar ? bar.getBoundingClientRect().bottom : 0) + box() * 0.5 + 4;
      return { x: Math.min(window.innerWidth - box() / 2 - 8, Math.max(box() / 2 + 8, r.left + r.width / 2)), y: Math.max(floor, r.top - box() * 0.05) };
    }
    if (t.dataset.reach) {
      const left = t.dataset.reach === 'left';
      return { x: left ? r.left - box() * 0.85 : r.right + box() * 0.85, y: r.top + r.height / 2 };
    }
    const x = perch[1] === 'l' ? r.left + box() * 0.55 : r.right - box() * 0.55;
    const y = perch[0] === 'b' ? r.bottom - box() * 0.55 : r.top + box() * 0.55;
    return {
      x: Math.min(window.innerWidth - box() / 2 - 8, Math.max(box() / 2 + 8, x)),
      y: Math.min(window.innerHeight - box() / 2 - 8, Math.max(box() / 2 + 8, y)),
    };
  }

  function set(next) {
    const n = next || {};
    const prevState = st.state, prevMood = st.mood;
    if (n.state && STATES.includes(n.state)) st.state = n.state;
    if ('target' in n) st.target = n.target || null;
    if ('cue' in n) st.cue = n.cue || '';
    if ('stage' in n) st.stage = !!n.stage;
    if ('you' in n) { st.you = !!n.you; if (st.you) pop(0.6); }   // the player is talking: turn to them
    if (n.mood && MOODS.includes(n.mood)) { st.mood = n.mood; st.moodSet = true; }
    else if (!st.moodSet || 'state' in n && !('mood' in n)) st.mood = STATE_MOOD[st.state];
    el.dataset.state = st.state;
    el.dataset.mood = st.mood;
    const away = !!resolve(st.target) || !!st.stage;
    if (away) docked = false;
    el.dataset.away = String(away);
    if (dock) dock.dataset.away = String(away);
    cueEl.textContent = st.cue;
    el.dataset.cue = String(!!st.cue && away);
    if (st.state === 'pointing' && prevState !== 'pointing') twist += 1.2;           // gives the control a turn
    if (st.mood === 'aha' && prevMood !== 'aha') pop(1);
    if (st.mood === 'encouraging' && prevMood !== 'encouraging') wink();
    if (st.state === 'asleep' && prevState !== 'asleep') def.vv -= 2;               // settles down
    if (prevState === 'asleep' && st.state !== 'asleep') { def.vv += 3; blink(); }   // wakes with a stretch
    renderDock();
  }

  function blink() { blinkStart = performance.now(); }
  function wink() { winkStart = performance.now() + 180; winkSide = Math.random() < 0.5 ? -1 : 1; }

  const COPY = {
    asleep: ['COACH OFF', 'Riff is asleep. You can still play.'],
    idle: ['COACH READY', 'Play a take.'],
    listening: ['LISTENING', 'Keep playing.'],
    thinking: ['READING TAKE', 'One moment.'],
    speaking: ['COACH', ''],
    pointing: ['COACH', ''],
    pleased: ['PASSED', ''],
  };
  function renderDock() {
    if (!dock) return;
    const [line, sub] = COPY[st.state];
    dock.dataset.state = st.state;
    if (dockLine && mode === 'preview') dockLine.textContent = st.cue;   // live: coach.js types it in step with the voice
    void line; void sub;
    if (led && mode === 'preview') {
      led.classList.add('warn');
      led.querySelector('span').textContent = 'PREVIEW';
    }
  }

  // 0..1..0 over `ms`, eased: a lid closing and opening
  const lidCurve = (t, ms) => (t < 0 || t > ms ? 0 : Math.sin(Math.PI * (t / ms)) ** 0.7);
  const spring = (x, v, target, k, c, dt) => { v += (k * (target - x) - c * v) * dt; return [x + v * dt, v]; };

  // ---------- frame loop ----------
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.033, (now - last) / 1000);
    last = now;
    const g = goalPoint();
    if (!pos.placed) { pos.x = g.x; pos.y = g.y; pos.placed = true; }
    const away = !!curTarget() || !!stagePoint();

    // anticipation: a new far goal → the eyes go first and the body winds up, then launches
    const far = Math.hypot(g.x - pos.x, g.y - pos.y);
    if (motion && far > 60 && (!lastGoal || Math.hypot(g.x - lastGoal.x, g.y - lastGoal.y) > 60) && !moving) {
      windupUntil = now + 120;
      def.a = Math.atan2(g.y - pos.y, g.x - pos.x);
      blink();
    }
    lastGoal = g;
    const winding = now < windupUntil;

    // travel
    if (!motion || (docked && !away)) { pos.x = g.x; pos.y = g.y; pos.vx = pos.vy = 0; }
    else if (!winding) {
      [pos.x, pos.vx] = spring(pos.x, pos.vx, g.x, 120, 15, dt);
      [pos.y, pos.vy] = spring(pos.y, pos.vy, g.y, 120, 15, dt);
    }
    const speed = Math.hypot(pos.vx, pos.vy);
    const dist = Math.hypot(g.x - pos.x, g.y - pos.y);
    if (speed > 220) moving = true;
    if (moving && dist < 12 && speed < 160) { moving = false; def.dv -= 5.5; }   // landing: squash along travel, wobble out
    docked = !away && !moving && dist < 1.5 && speed < 20;

    // deformation springs. d: stretch along a (volume kept); v: vertical; tilt: head + lean
    if (speed > 40) {
      const va = Math.atan2(pos.vy, pos.vx);
      let da = va - def.a;
      da = Math.atan2(Math.sin(da), Math.cos(da));
      def.a += da * Math.min(1, dt * 14);
    }
    let dTarget = winding ? -0.2 : Math.min(0.34, speed / 1500);
    if (!motion) dTarget = 0;
    [def.d, def.dv] = spring(def.d, def.dv, dTarget, 260, 12, dt);

    if (now - voiceAt > 300) voice *= Math.pow(0.02, dt);                       // boundary pulses decay
    let vTarget = 0;
    if (st.state === 'listening') vTarget += level * 0.07;
    // talking: the mouth follows the voice (fast open, slower close), each syllable bobs the body
    // and nods the head, so it reads as speech and not as the idle breathing
    mouth += (voice - mouth) * Math.min(1, dt * (voice > mouth ? 40 : 16));
    if (!syl && voice > 0.42) { syl = true; if (motion) { def.vv += 1.5; def.tv += (Math.random() - 0.5) * 0.9; } }
    else if (syl && voice < 0.22) syl = false;
    if (voice > 0.02) vTarget += voice * 0.2;                                    // talks with its body
    if (st.state !== 'asleep' && !moving) vTarget += 0.012 * Math.sin(now / 650); // breathing
    if (st.state === 'asleep') vTarget -= 0.05 + 0.02 * Math.sin(now / 1100);
    // pleased: hop. Squash at contact, stretch in the air, all through the spring
    if (st.state === 'pleased' && motion) {
      hopPhase = (hopPhase + dt / 0.62) % 1;
      const airborne = hopPhase < 0.7;
      const t = airborne ? hopPhase / 0.7 : 0;
      def.hop = airborne ? 3.2 * Math.sin(Math.PI * t) : 0;
      vTarget += airborne ? 0.1 * Math.sin(Math.PI * t) : -0.11;
    } else { def.hop += (0 - def.hop) * Math.min(1, dt * 12); hopPhase = 0; }
    if (!motion) vTarget = 0;
    [def.v, def.vv] = spring(def.v, def.vv, vTarget, 340, 14, dt);

    const lean = motion ? Math.max(-0.22, Math.min(0.22, pos.vx / 2600)) : 0;
    const want = FACE[st.state === 'pleased' ? 'proud' : st.mood] || FACE.neutral;
    [def.tilt, def.tv] = spring(def.tilt, def.tv, (want.head || 0) + lean, 120, 11, dt);

    // knob: turns while thinking, one twist on arriving at a control
    spinV += ((st.state === 'thinking' ? 1.6 : 0) - spinV) * Math.min(1, dt * 4);
    spin += spinV * dt;
    twist += (0 - twist) * Math.min(1, dt * 5);

    // face: ease toward the mood's lids
    for (const key of ['top', 'bot', 'tilt', 'l', 'r']) face[key] += ((want[key] || 0) - (face[key] || 0)) * Math.min(1, dt * 14);
    face.arc = want.arc;
    face.head = want.head;
    const ahaK = now < ahaUntil ? 1 : 0;

    // gaze: saccades (fast spring with a little overshoot); eyes lead travel
    const gazeAt = (t) => {
      const r = t.getBoundingClientRect();
      const dx = r.left + r.width / 2 - pos.x, dy = r.top + r.height / 2 - pos.y, d = Math.hypot(dx, dy) || 1;
      return [dx / d, dy / d];
    };
    let tx = look.tx, ty = look.ty;
    if (winding || moving) [tx, ty] = [Math.cos(def.a), Math.sin(def.a)];
    else if (st.you) [tx, ty] = [0, 0.3];                                       // listening to you: eyes on you
    else if (st.state === 'pointing' || st.state === 'listening') {
      const t = resolve(st.target) || (st.state === 'listening' ? document.querySelector('.wave') : null);
      [tx, ty] = t ? gazeAt(t) : [0, 0.2];
    } else if (st.state === 'thinking') [tx, ty] = [0.65, -0.75];
    else if (st.state === 'idle') {
      if (now > look.nextGlance || !look.nextGlance) {
        const a = Math.random() * 6.28, m = Math.random() < 0.45 ? 0 : 0.75;
        [tx, ty] = [Math.cos(a) * m, Math.sin(a) * m];
        look.nextGlance = now + 1200 + Math.random() * 2800;
      }
    } else [tx, ty] = [0, 0.1];                                                  // speaking, pleased: at the player
    if (Math.hypot(tx - look.tx, ty - look.ty) > 0.95 && now - blinkStart > 400) blink();  // blink on a big glance
    look.tx = tx; look.ty = ty;
    [look.x, look.vx] = spring(look.x, look.vx, look.tx, 520, 26, dt);
    [look.y, look.vy] = spring(look.y, look.vy, look.ty, 520, 26, dt);

    // blinks: every 2-6 s, sometimes double
    if (st.state !== 'asleep' && now > blinkAt) {
      blink();
      doubleBlink = Math.random() < 0.18;
      blinkAt = now + 2000 + Math.random() * 4000;
    }
    if (doubleBlink && now - blinkStart > 260) { blink(); doubleBlink = false; }
    const bl = lidCurve(now - blinkStart, 150);
    const wk = lidCurve(now - winkStart, 320);
    let lidL = bl + (winkSide < 0 ? wk : 0), lidR = bl + (winkSide > 0 ? wk : 0);
    if (st.state === 'asleep') lidL = lidR = now < peekUntil ? 0.45 : 1;

    // position the box; draw the pixels
    // size: grows into the spotlight and shrinks back to the perch on a spring (a little overshoot)
    // at home Riff fills its booth (the coach column sizes it); at a control it is a little smaller
    const homePx = socket && socket.getBoundingClientRect().width ? socket.getBoundingClientRect().width / 24 : PX_HOME;
    const pxGoal = curTarget() ? PX_CONTROL : stagePoint() ? homePx * 1.12 : homePx;
    if (motion) [cssPx, cssPxV] = spring(cssPx, cssPxV, pxGoal, 90, 13, dt); else cssPx = pxGoal;
    if (Math.abs(cssPxV) > 4 && Math.abs(pxGoal - cssPx) > 0.5 && def.vv * cssPxV >= 0) def.vv += 0.02 * cssPxV;  // grows with a stretch
    const B = box();
    el.style.width = el.style.height = B + 'px';
    canvas.style.width = canvas.style.height = G * cssPx + 'px';

    // the finger: out while Riff is at a control or a spot. A press is wind-up, lunge, contact, recoil
    const tgt = curTarget();
    const locked = now < lockUntil && lockEl;
    const arrived = tgt && !moving && dist < 14 && (st.state === 'pointing' || locked);
    if (pendingPress && arrived) { pendingPress = false; press(); lockUntil = now + PRESS.end + 200; }   // press, a beat, then go
    const tr = tgt && tgt.getBoundingClientRect();
    const down = !!tgt && tgt.dataset.reach === 'down';
    const reachLeft = !down && !!tgt && (tr.left + tr.width / 2) < pos.x;
    const dir = down ? [0, 1] : reachLeft ? [-1, 0] : [1, 0];
    const tp = now - pressAt;
    let lunge = 0;
    if (tp >= 0 && tp < PRESS.end && motion) {
      if (tp < PRESS.back) lunge = -0.4 * Math.sin((tp / PRESS.back) * Math.PI / 2);
      else if (tp < PRESS.hit) lunge = -0.4 + 1.4 * ((tp - PRESS.back) / (PRESS.hit - PRESS.back));
      else lunge = (1 - (tp - PRESS.hit) / (PRESS.end - PRESS.hit)) ** 2;
      if (tp > PRESS.back && tp < PRESS.hit) { def.a = Math.atan2(dir[1], dir[0]); def.d += (0.3 - def.d) * Math.min(1, dt * 30); }
    }
    if (!contactDone && tp >= PRESS.hit) { contactDone = true; contact(); }
    const off = lunge * B * 0.3;
    el.style.transform = `translate(${(pos.x - B / 2 + dir[0] * off).toFixed(1)}px, ${(pos.y - B / 2 + dir[1] * off).toFixed(1)}px)`;
    const push = Math.max(0, lunge) * 2.5;
    const fs = cssPx * 0.9, fw = finger.width * fs, fh = finger.height * fs;
    finger.style.width = fw + 'px';
    finger.style.height = fh + 'px';
    finger.dataset.on = String(!!arrived || (tp >= 0 && tp < PRESS.end));
    finger.style.transform = down
      ? `translate(${(-fw / 2).toFixed(1)}px, ${(B * 0.3 + fw / 2 - fh / 2 + push * fs).toFixed(1)}px) rotate(90deg)`
      : `translate(${reachLeft ? -(fw + B * 0.32) - push * fs : B * 0.32 + push * fs}px, ${(-fh / 2).toFixed(1)}px) scaleX(${reachLeft ? -1 : 1})`;

    // home: while Riff is out, a dotted outline stays
    if (ghost) {
      const hp = homePoint();
      const out = Math.hypot(pos.x - hp.x, pos.y - hp.y) > B * 0.6;   // really left, not just told to
      if (dock && dock.dataset.home !== String(!out)) dock.dataset.home = String(!out);
      if (out) {
        const sr = socket.getBoundingClientRect();
        const gcv = ghost.firstChild;
        const gpx = (sr.width / 24) * G;
        if (gcv.style.width !== gpx + 'px') gcv.style.width = gcv.style.height = gpx + 'px';
      }
    }
    const scale = 1 + 0.12 * ahaK;
    render(ctx, img, {
      spin: spin - twist, d: Math.max(-0.3, Math.min(0.4, def.d)), a: def.a, v: Math.max(-0.25, Math.min(0.25, def.v)), tilt: def.tilt, hop: def.hop,
      lookX: look.x, lookY: look.y, lidL, lidR, asleep: st.state === 'asleep' && !(now < peekUntil),
      face: { ...face, l: face.l * scale, r: face.r * scale }, glint: ahaK || st.mood === 'aha' ? 1 : 0,
      mouth: Math.min(1, mouth * 1.25),
    });
    el.dataset.shut = String(st.state === 'asleep');
    el.dataset.side = pos.x > window.innerWidth / 2 ? 'left' : 'right';
  }

  // poke: Riff reacts to a click, then goes back to what it was doing
  el.addEventListener('click', () => {
    def.vv -= 4;
    if (st.state === 'asleep') peekUntil = performance.now() + 1100; else wink();
  });

  // ---------- preview: a scripted tour, never presented as AI ----------
  if (mode === 'preview') {
    if (dock) dock.dataset.preview = 'true';
    const tour = [
      [1600, { state: 'asleep', target: null, cue: '', mood: 'sleepy' }],
      [1800, { state: 'idle', mood: 'neutral' }],
      [3600, { state: 'listening', mood: 'concentrating' }],
      [2400, { state: 'thinking', mood: 'curious' }],
      [1400, { state: 'thinking', mood: 'aha' }],
      [4200, { state: 'speaking', target: null, stage: true, cue: 'Ooh, close. Your strumming hand stops right at the change.', mood: 'concerned' }],
      [3600, { state: 'pointing', target: '#fxPower', stage: false, cue: 'Okay, effects off so you can hear the timing.', mood: 'encouraging' }],
      [1400, { press: true }],
      [3200, { state: 'listening', target: null, cue: '', mood: 'concentrating' }],
      [3800, { state: 'pleased', target: null, stage: true, cue: "Nice. That gap's down to about a tenth of a second.", mood: 'proud' }],
      [2000, { state: 'idle', stage: false, cue: '', mood: 'neutral' }],
    ];
    let i = 0;
    const app = document.getElementById('app');
    const next = () => {
      const [ms, s] = tour[i];
      if (s.press) press(); else set(s);
      if (app) app.dataset.spot = st.stage || (st.state === 'pointing' && st.cue) ? 'on' : 'off';
      document.querySelectorAll('.spot-target').forEach((e) => e.classList.remove('spot-target'));
      const t = resolve(st.target);
      if (t && app && app.dataset.spot === 'on') t.classList.add('spot-target');
      i = (i + 1) % tour.length; setTimeout(next, ms);
    };
    next();
  } else {
    set({ state: 'asleep' });
  }

  const nod = () => { def.vv -= 1.6; def.tv += (Math.random() - 0.5) * 0.5; };   // a small nod as you talk
  window.OmniRiff.coach = { set, press, nod, states: STATES.slice(), moods: MOODS.slice(), get: () => ({ ...st }) };
  requestAnimationFrame(frame);
})();
