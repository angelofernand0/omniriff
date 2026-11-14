// Riff: the coach character. Design only: this file draws and animates the avatar and
// exposes a small API. It contains no AI, opens no socket and sends nothing to the engine.
// COACH piece F will drive it later through OmniRiff.coach.set().
//
//   OmniRiff.coach.set({ state, target, cue })
//     state   asleep | idle | listening | thinking | speaking | pointing | pleased
//     target  an element or selector Riff travels to (null = home dock)
//     cue     one short line Riff says (shown in a bubble, or in the dock when home)
//
//   ?coach=off       hides Riff and the dock
//   ?coach=preview   scripted tour of the states, labelled PREVIEW on screen. Not AI.
//
// Rules (BRAND_SPEC.md section 7): Riff is the only round, smoothly moving thing on screen,
// and every move maps to something the coach is doing. No idle wandering.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const mode = params.get('coach') || 'on';
  const dock = document.getElementById('coachDock');
  const led = document.getElementById('led-coach');
  const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SIZE = 72;
  const STATES = ['asleep', 'idle', 'listening', 'thinking', 'speaking', 'pointing', 'pleased'];

  // ---------- drawing ----------
  // body: a disc with 8 soft ridges, like a knurled knob seen from above
  function bodyPath() {
    const pts = [];
    for (let i = 0; i < 128; i++) {
      const t = (i / 128) * Math.PI * 2;
      const r = 41 * (1 + 0.06 * Math.cos(8 * t));
      pts.push((r * Math.cos(t)).toFixed(2) + ',' + (r * Math.sin(t)).toFixed(2));
    }
    return 'M' + pts.join('L') + 'Z';
  }
  function ticks() {
    let out = '';
    for (let k = 0; k < 8; k++) {
      const t = ((2 * k + 1) * Math.PI) / 8;
      const c = Math.cos(t), s = Math.sin(t);
      out += `<line x1="${(36 * c).toFixed(2)}" y1="${(36 * s).toFixed(2)}" x2="${(30 * c).toFixed(2)}" y2="${(30 * s).toFixed(2)}"/>`;
    }
    return out;
  }
  const LID = 34;  // lid travel in viewBox units, open to shut
  const eye = (side) => {
    const cx = side * 15;
    return `<g class="riff-eye" transform="translate(${cx} -2)">
      <clipPath id="riffClip${side}"><ellipse rx="12.5" ry="16"/></clipPath>
      <g clip-path="url(#riffClip${side})">
        <ellipse class="riff-white" rx="12.5" ry="16"/>
        <g class="riff-pupil"><ellipse rx="7" ry="9.5"/><circle class="riff-glint" cx="2.6" cy="-4" r="3"/><circle class="riff-glint" cx="-2.6" cy="3.6" r="1.3"/></g>
        <rect class="riff-lid" x="-14" y="-50" width="28" height="${LID}"/>
      </g>
      <path class="riff-arc riff-arc-happy" d="M-10 4 Q0 -11 10 4"/>
      <path class="riff-arc riff-arc-sleep" d="M-10 -1 Q0 8 10 -1"/>
    </g>`;
  };

  const inner = (size) => `
    <div class="riff-sq">
      <svg viewBox="-50 -50 100 100" width="${size}" height="${size}" aria-hidden="true">
        <g class="riff-body"><path d="${bodyPath()}"/><g class="riff-ticks">${ticks()}</g></g>
        <g class="riff-face">${eye(-1)}${eye(1)}</g>
      </svg>
      <span class="riff-z" aria-hidden="true">z</span>
    </div>
    <div class="riff-cue" role="status"></div>`;

  // a still portrait of one state, for the brand sheet and docs. No behaviour.
  const POSE = { asleep: [1, 0, 0], idle: [0, 0, 0], listening: [0, -0.5, 0.5], thinking: [0.14, 0.6, -0.7], speaking: [0, 0, 0], pointing: [0, -0.8, 0.5], pleased: [1, 0, 0] };
  let clipSeq = 0;
  function portrait(state, size = 96) {
    const [lidv, lx, ly] = POSE[state] || POSE.idle;
    const d = document.createElement('div');
    d.className = 'riff riff-still';
    d.dataset.state = state;
    d.dataset.shut = String(lidv > 0.9);
    d.style.width = d.style.height = size + 'px';
    const n = ++clipSeq;
    d.innerHTML = inner(size).replace(/riffClip(-?1)/g, `riffClip${n}_$1`);
    d.querySelectorAll('.riff-lid').forEach((l) => l.setAttribute('transform', `translate(0 ${lidv * LID})`));
    d.querySelectorAll('.riff-pupil').forEach((p) => p.setAttribute('transform', `translate(${lx * 4.2} ${ly * 5.5})`));
    d.querySelector('.riff-face').setAttribute('transform', `translate(${lx * 2} ${ly * 2})`);
    return d;
  }
  window.OmniRiff = window.OmniRiff || {};
  window.OmniRiff.portrait = portrait;
  window.OmniRiff.states = STATES.slice();

  if (mode === 'off' || document.documentElement.dataset.riff === 'portraits') {
    if (mode === 'off') { if (dock) dock.hidden = true; if (led) led.hidden = true; }
    return;
  }

  const el = document.createElement('div');
  el.className = 'riff';
  el.dataset.state = 'asleep';
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', 'Riff, the coach');
  el.innerHTML = inner(SIZE);
  document.body.appendChild(el);
  const sq = el.querySelector('.riff-sq');
  const body = el.querySelector('.riff-body');
  const face = el.querySelector('.riff-face');
  const pupils = [...el.querySelectorAll('.riff-pupil')];
  const lids = [...el.querySelectorAll('.riff-lid')];
  const cueEl = el.querySelector('.riff-cue');
  const socket = dock ? dock.querySelector('.riff-socket') : null;
  const dockLine = document.getElementById('coachLine');
  const dockSub = document.getElementById('coachSub');

  // ---------- state ----------
  const st = { state: 'asleep', target: null, cue: '' };
  const pos = { x: 0, y: 0, vx: 0, vy: 0, placed: false };
  const look = { x: 0, y: 0, tx: 0, ty: 0 };
  let spin = 0, spinV = 0, twist = 0;      // body rotation: steady while thinking, a twist on arrival
  let impact = 0, impactV = 0;             // landing squash
  let lid = 1, lidT = 1;                   // 0 open .. 1 closed
  let blinkAt = performance.now() + 2500, glanceAt = 0, peekUntil = 0;
  let level = 0;                           // input level 0..1 from real engine frames
  let moving = false, docked = true, last = performance.now();

  let voice = 0, voiceAt = 0;              // Riff's own voice loudness 0..1 while it talks (coach.js)
  window.addEventListener('omniriff:voice', (e) => {
    const v = e.detail && e.detail.level;
    voice = typeof v === 'number' ? Math.max(0, Math.min(1, v)) : 0;
    voiceAt = performance.now();
  });
  setInterval(() => { if (performance.now() - voiceAt > 400) voice *= 0.5; }, 100);   // boundary pulses decay

  window.addEventListener('omniriff:frame', (e) => {
    const db = e.detail && e.detail.input_peak_dbfs;
    if (typeof db === 'number') level = Math.max(0, Math.min(1, (db + 48) / 48));
  });

  function resolve(t) {
    if (!t) return null;
    return typeof t === 'string' ? document.querySelector(t) : t;
  }
  function homePoint() {
    if (socket) { const r = socket.getBoundingClientRect(); if (r.width) return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
    return { x: window.innerWidth - 60, y: window.innerHeight - 60 };
  }
  // perch inside a corner of the thing being operated (data-perch="tr|tl|br|bl", default tr),
  // so the value stays readable and the label row above it stays clear
  function goalPoint() {
    const t = resolve(st.target);
    if (!t) return homePoint();
    const r = t.getBoundingClientRect();
    if (!r.width) return homePoint();
    const perch = t.dataset.perch || 'tr';
    const x = perch[1] === 'l' ? r.left + SIZE * 0.55 : r.right - SIZE * 0.55;
    const y = perch[0] === 'b' ? r.bottom - SIZE * 0.55 : r.top + SIZE * 0.55;
    return {
      x: Math.min(window.innerWidth - SIZE / 2 - 8, Math.max(SIZE / 2 + 8, x)),
      y: Math.min(window.innerHeight - SIZE / 2 - 8, Math.max(SIZE / 2 + 8, y)),
    };
  }

  function set(next) {
    const n = next || {};
    if (n.state && STATES.includes(n.state)) st.state = n.state;
    if ('target' in n) st.target = n.target || null;
    if ('cue' in n) st.cue = n.cue || '';
    if ('mood' in n) el.dataset.mood = n.mood || 'neutral';   // expression (R3b); feed field "mood"
    el.dataset.state = st.state;
    const away = !!resolve(st.target);
    if (away) docked = false;
    el.dataset.away = String(away);
    if (dock) dock.dataset.away = String(away);
    cueEl.textContent = st.cue;
    el.dataset.cue = String(!!st.cue && away);
    lidT = st.state === 'asleep' || st.state === 'pleased' ? 1 : 0;
    if (st.state === 'pointing') twist += 70;   // arrives and gives the control a turn
    renderDock();
  }

  const COPY = {
    asleep: ['COACH OFF', 'Not running. The rig plays without it.'],
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
    if (dockLine) dockLine.textContent = line;
    if (dockSub) dockSub.textContent = st.cue || sub;
    if (led) {
      const preview = mode === 'preview';
      led.classList.toggle('warn', preview);
      led.classList.toggle('on', false);
      led.querySelector('span').textContent = preview ? 'PREVIEW' : 'OFF';
    }
  }

  // ---------- frame loop ----------
  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const g = goalPoint();
    if (!pos.placed) { pos.x = g.x; pos.y = g.y; pos.placed = true; }

    // travel: a slightly underdamped spring, so arrivals overshoot and settle
    // docked: sit rigidly in the socket, so scrolling or resizing never makes Riff drift
    if (docked && !resolve(st.target)) { pos.x = g.x; pos.y = g.y; pos.vx = pos.vy = 0; }
    else if (motion) {
      const k = 150, c = 17;
      pos.vx += (k * (g.x - pos.x) - c * pos.vx) * dt;
      pos.vy += (k * (g.y - pos.y) - c * pos.vy) * dt;
      pos.x += pos.vx * dt; pos.y += pos.vy * dt;
    } else { pos.x = g.x; pos.y = g.y; pos.vx = pos.vy = 0; }
    const speed = Math.hypot(pos.vx, pos.vy);
    const dist = Math.hypot(g.x - pos.x, g.y - pos.y);
    if (speed > 260) moving = true;
    if (moving && dist < 10 && speed < 140) { moving = false; impactV = 9; }   // landed
    docked = !resolve(st.target) && !moving && dist < 1.5 && speed < 20;
    impactV += (-220 * impact - 16 * impactV) * dt; impact += impactV * dt;

    // squash and stretch: stretch along the direction of travel, squash on landing
    const stretch = Math.min(0.28, speed / 5200);
    const ang = Math.atan2(pos.vy, pos.vx) * 180 / Math.PI;
    let sx = 1 + stretch, sy = 1 - stretch;
    let extra = '';
    if (st.state === 'listening') { const b = 1 + level * 0.1; extra = ` scale(${(2 - b).toFixed(3)}, ${b.toFixed(3)})`; }
    else if (voice > 0.02) { const b = 1 + 0.09 * voice; extra = ` scale(${(2 - b).toFixed(3)}, ${b.toFixed(3)})`; }   // real voice loudness (coach.js)
    else if (st.state === 'speaking' || (st.state === 'pointing' && st.cue)) { const b = 1 + 0.035 * Math.sin(now / 70); extra = ` scale(${(2 - b).toFixed(3)}, ${b.toFixed(3)})`; }
    else if (st.state === 'asleep') { const b = 1 + 0.025 * Math.sin(now / 900); extra = ` scale(${(2 - b).toFixed(3)}, ${b.toFixed(3)})`; }
    else if (st.state === 'pleased') { const hop = Math.abs(Math.sin(now / 160)) * 6; extra = ` translate(0, ${(-hop).toFixed(1)}px)`; }
    const land = ` scale(${(1 + impact * 0.5).toFixed(3)}, ${(1 - impact * 0.5).toFixed(3)})`;
    el.style.transform = `translate(${(pos.x - SIZE / 2).toFixed(1)}px, ${(pos.y - SIZE / 2).toFixed(1)}px)`;
    sq.style.transform = motion
      ? `rotate(${ang.toFixed(1)}deg) scale(${sx.toFixed(3)}, ${sy.toFixed(3)}) rotate(${(-ang).toFixed(1)}deg)${land}${extra}`
      : '';

    // body: turns like a knob. Steady while thinking, one twist when it reaches a control.
    spinV += ((st.state === 'thinking' ? 90 : 0) - spinV) * Math.min(1, dt * 4);
    spin += spinV * dt;
    twist += (0 - twist) * Math.min(1, dt * 5);
    if (motion) body.setAttribute('transform', `rotate(${(spin - twist).toFixed(1)})`);

    // eyes
    if (st.state === 'pointing' || st.state === 'listening') {
      const t = resolve(st.target) || (st.state === 'listening' ? document.querySelector('.wave') : null);
      if (t) {
        const r = t.getBoundingClientRect();
        const dx = r.left + r.width / 2 - pos.x, dy = r.top + r.height / 2 - pos.y, d = Math.hypot(dx, dy) || 1;
        look.tx = dx / d; look.ty = dy / d;
      }
    } else if (st.state === 'thinking') { look.tx = 0.6; look.ty = -0.7; }
    else if (st.state === 'idle') {
      if (now > glanceAt) { const a = Math.random() * 6.28; const m = Math.random() < 0.4 ? 0 : 0.7; look.tx = Math.cos(a) * m; look.ty = Math.sin(a) * m; glanceAt = now + 1400 + Math.random() * 2600; }
    } else { look.tx = 0; look.ty = 0; }
    look.x += (look.tx - look.x) * Math.min(1, dt * 10);
    look.y += (look.ty - look.y) * Math.min(1, dt * 10);
    for (const p of pupils) p.setAttribute('transform', `translate(${(look.x * 4.2).toFixed(2)} ${(look.y * 5.5).toFixed(2)})`);
    face.setAttribute('transform', `translate(${(look.x * 2).toFixed(2)} ${(look.y * 2).toFixed(2)})`);

    // lids: blink when awake, half-open peek when poked asleep
    let want = lidT;
    if (st.state === 'asleep' && now < peekUntil) want = 0.45;
    if (lidT === 0) {
      if (now > blinkAt) { want = 1; if (now > blinkAt + 110) blinkAt = now + 2200 + Math.random() * 3800; }
      if (st.state === 'listening') want = Math.max(want, 0);   // wide open
      if (st.state === 'thinking') want = Math.max(want, 0.14);  // narrowed
    }
    lid += (want - lid) * Math.min(1, dt * 26);
    for (const l of lids) l.setAttribute('transform', `translate(0 ${(lid * LID).toFixed(2)})`);
    el.dataset.shut = String(lid > 0.9);
    el.dataset.side = pos.x > window.innerWidth / 2 ? 'left' : 'right';
  }

  // poke: Riff reacts to a click, then goes back to what it was doing
  el.addEventListener('click', () => {
    impactV = 7;
    peekUntil = performance.now() + 1100;
  });

  // ---------- preview: a scripted tour, never presented as AI ----------
  if (mode === 'preview') {
    if (dock) dock.dataset.preview = 'true';
    const tour = [
      [1600, { state: 'asleep', target: null, cue: '' }],
      [1800, { state: 'idle' }],
      [4200, { state: 'listening' }],
      [2600, { state: 'thinking' }],
      [4200, { state: 'pointing', target: '.wave', cue: 'Bar 2 is late. Looping it.' }],
      [3600, { state: 'pointing', target: '#card-filter', cue: 'Effects off. Hear it dry.' }],
      [3600, { state: 'pointing', target: '#handPanel', cue: 'Keep the hand swinging.' }],
      [3200, { state: 'pleased', target: null, cue: 'Change landed. 4 of 4.' }],
      [2000, { state: 'idle', cue: '' }],
    ];
    let i = 0;
    const next = () => { const [ms, s] = tour[i]; set(s); i = (i + 1) % tour.length; setTimeout(next, ms); };
    next();
  } else {
    set({ state: 'asleep' });
  }

  window.OmniRiff.coach = { set, states: STATES.slice(), get: () => ({ ...st }) };
  requestAnimationFrame(frame);
})();
