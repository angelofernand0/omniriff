// OmniRiff dashboard: reads v1 state frames (protocol/state.schema.json) from the engine
// WebSocket and sends v1 control envelopes back on the same socket as source "dashboard".
// Optional by design: the instrument works with this page closed.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const WS_URL = params.get('ws') || 'ws://127.0.0.1:47801';
  // optional hand-view feed from vision/ (protocol/hand.schema.json); ?hand=off disables
  const HAND_URL = params.get('hand') === 'off' ? null : (params.get('hand') || 'ws://127.0.0.1:47802');
  const HAND_STALE_MS = 500;       // no hand frame for this long => clear the drawing
  const STALE_MS = 1000;           // no frame for this long => STALE
  const ENGAGED_MS = 350;          // vision accepted this recently => ENGAGED
  const ONLINE_MS = 3000;          // a source seen this recently => online
  const METER_FLOOR = -60;         // dBFS at the bottom of the meters
  const SEGS = 24, BLOCKS = 16, TOWER = 20;

  const $ = (id) => document.getElementById(id);
  const app = $('app');
  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();

  // ---------- build repeated elements ----------
  function fill(el, n, cls) {
    const out = [];
    for (let i = 0; i < n; i++) { const b = document.createElement('i'); if (cls) b.className = cls(i); b.style.setProperty('--i', i); el.appendChild(b); out.push(b); }
    return out;
  }
  const inSegs = fill($('inSegs'), SEGS);
  const outSegs = fill($('outSegs'), SEGS);
  const blocks = { filter: fill($('blocks-filter'), BLOCKS), reverb: fill($('blocks-reverb'), BLOCKS) };
  const tower = fill($('tower'), TOWER);

  // ---------- state ----------
  let ws = null, retry = 500, lastFrameAt = 0, state = null;
  let seq = 0;
  const meters = { in: { hold: METER_FLOOR, holdAt: 0 }, out: { hold: METER_FLOOR, holdAt: 0 } };
  let clipUntil = 0, lastClipped = null;
  const fx = { filter: { prev: null, liveUntil: 0, movedAt: 0 }, reverb: { prev: null, liveUntil: 0, movedAt: 0 } };
  const loop = { state: 'idle', samples: [], playStart: 0, seconds: 0, partial: false };

  // ---------- connection ----------
  function connect() {
    try { ws = new WebSocket(WS_URL); } catch (e) { schedule(); return; }
    ws.onopen = () => { retry = 500; };
    ws.onmessage = (msg) => {
      try { onFrame(JSON.parse(msg.data)); } catch (e) { /* ignore malformed frame */ }
    };
    ws.onclose = () => { ws = null; schedule(); };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function schedule() { setTimeout(connect, retry); retry = Math.min(4000, retry * 2); }

  // hand feed: aged by browser receive time, never by the frame's own timestamp
  const hand = { ws: null, retry: 1000, frame: null, at: 0 };
  function connectHand() {
    if (!HAND_URL) return;
    try { hand.ws = new WebSocket(HAND_URL); } catch (e) { scheduleHand(); return; }
    hand.ws.onopen = () => { hand.retry = 1000; };
    hand.ws.onmessage = (msg) => {
      try {
        const f = JSON.parse(msg.data);
        if (f && f.version === 1 && f.type === 'hand' && Array.isArray(f.landmarks)) { hand.frame = f; hand.at = performance.now(); }
      } catch (e) { /* ignore malformed frame */ }
    };
    hand.ws.onclose = () => { hand.ws = null; hand.frame = null; scheduleHand(); };
    hand.ws.onerror = () => { try { hand.ws.close(); } catch (e) {} };
  }
  function scheduleHand() { setTimeout(connectHand, hand.retry); hand.retry = Math.min(5000, hand.retry * 2); }

  function send(control, value) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const now = Date.now();
    seq = Math.max(seq + 1, now);  // strictly increasing, survives page reloads
    const ev = { version: 1, source: 'dashboard', seq, timestamp_ms: now, control };
    if (control === 'filter' || control === 'reverb') {
      ev.type = 'parameter'; ev.value = Math.min(1, Math.max(0, value)); ev.confidence = 1;
    } else {
      ev.type = 'action';
    }
    ws.send(JSON.stringify(ev));
    return true;
  }

  // ---------- frame handling ----------
  function onFrame(s) {
    if (!s || s.version !== 1) return;
    if (!state) delete app.dataset.boot;  // first frame: placeholders become values
    state = s;
    lastFrameAt = performance.now();
    window.dispatchEvent(new CustomEvent('omniriff:frame', { detail: s }));  // for juice.js
    const now = performance.now();

    // looper: build the waveform from input peaks while recording
    const ls = s.loop && s.loop.state;
    if (ls !== loop.state) {
      if (ls === 'recording') { loop.samples = []; loop.partial = false; }
      if (ls === 'playing') { loop.playStart = now; if (loop.state !== 'recording') loop.partial = true; }
      if (ls === 'idle') { loop.samples = []; loop.partial = false; }
      loop.state = ls;
    }
    if (ls === 'recording') loop.samples.push(waveLevel(s.input_peak_dbfs));
    loop.seconds = s.loop ? s.loop.seconds : 0;

    // fx movement => "injection" pulse
    for (const k of ['filter', 'reverb']) {
      const v = s[k] && s[k].value;
      if (typeof v !== 'number') continue;
      if (fx[k].prev !== null && Math.abs(v - fx[k].prev) > 0.004) { fx[k].liveUntil = now + 220; fx[k].movedAt = now; }
      fx[k].prev = v;
    }

    if (lastClipped !== null && s.clipped_samples > lastClipped) clipUntil = now + 2000;
    lastClipped = s.clipped_samples;
  }

  // waveform uses a tighter range than the meters so plucks read as shape, not a block
  const waveLevel = (db) => Math.pow(Math.max(0, Math.min(1, (db + 36) / 36)), 1.6);
  const level = (db) => Math.max(0, Math.min(1, (db - METER_FLOOR) / -METER_FLOOR));

  // ---------- render ----------
  function renderMeter(segs, m, db, now) {
    const lit = Math.round(level(db) * SEGS);
    if (db >= m.hold || now - m.holdAt > 1500) { m.hold = db; m.holdAt = now; }
    const holdIdx = Math.round(level(m.hold) * SEGS) - 1;
    for (let i = 0; i < SEGS; i++) {
      const segDb = METER_FLOOR + (i + 1) * (-METER_FLOOR / SEGS);
      const zone = segDb > -6 ? 'r' : segDb > -18 ? 'y' : 'g';
      segs[i].className = (i < lit ? zone : '') + (i === holdIdx && i >= lit ? ' ' + zone + ' hold' : '');
    }
  }

  function render() {
    const now = performance.now();
    const age = now - lastFrameAt;
    const conn = !state ? 'offline' : (ws && age < STALE_MS ? 'live' : (ws ? 'stale' : 'offline'));
    app.dataset.conn = conn;
    $('conn').textContent = conn === 'live' ? 'LIVE' : conn === 'stale' ? 'STALE' : 'OFFLINE';
    $('led-engine').classList.toggle('on', conn === 'live');
    $('led-engine').classList.toggle('warn', conn === 'stale');
    $('btnLoop').disabled = $('btnBypass').disabled = $('slFilter').disabled = $('slReverb').disabled = conn === 'offline';

    if (state) {
      const s = state;
      app.dataset.bypass = String(!!s.bypass);

      // replay: optional state.replay (PR #18). Keep the label up after it ends so
      // scripted controls are never mistaken for live sensors.
      const r = s.replay;
      app.dataset.replay = r ? 'true' : 'false';
      if (r) {
        $('replayChip').textContent = r.status === 'playing'
          ? `REPLAY ${r.position}/${r.total}`
          : `REPLAY · ${String(r.status).toUpperCase()}`;
      }

      // meters
      renderMeter(inSegs, meters.in, s.input_peak_dbfs, now);
      renderMeter(outSegs, meters.out, s.output_peak_dbfs, now);
      if (s.input_peak_dbfs >= -1) clipUntil = now + 2000;
      $('inClip').classList.toggle('on', now < clipUntil);
      $('inDb').textContent = s.input_peak_dbfs <= METER_FLOOR ? '-inf dB' : s.input_peak_dbfs.toFixed(1) + ' dB';

      // looper
      app.dataset.loop = loop.state;
      $('loopWord').textContent = { idle: 'READY', recording: 'REC', playing: 'PLAY' }[loop.state] || '—';
      $('loopLen').textContent = loop.state === 'idle' ? '--' : loop.seconds.toFixed(1) + ' s';
      $('loopHint').textContent = { idle: 'Press pedal to record', recording: 'Press again to close', playing: 'Press to clear' }[loop.state] || '';
      $('loopMeta').textContent = s.loop && s.loop.max_seconds ? Math.round(s.loop.max_seconds) + ' S MAX' : '';
      $('waveNote').textContent = loop.partial ? 'Recorded before this page opened. Shape not shown.' : '';

      // fx cards
      const vision = s.sources && s.sources.vision;
      const visionAccAge = vision && vision.last_accepted_ms != null ? s.timestamp_ms - vision.last_accepted_ms : Infinity;
      const visionSeenAge = vision && vision.last_seen_ms != null ? s.timestamp_ms - vision.last_seen_ms : Infinity;
      const target = fx.reverb.movedAt > fx.filter.movedAt ? 'reverb' : 'filter';
      const engaged = visionAccAge < ENGAGED_MS && conn === 'live';
      app.dataset.fx = engaged ? 'engaged' : 'idle';

      for (const k of ['filter', 'reverb']) {
        const v = s[k] ? s[k].value : 0;
        $('pct-' + k).textContent = Math.round(v * 100) + '%';
        const lit = Math.round(v * BLOCKS);
        blocks[k].forEach((b, i) => { b.className = i < lit ? 'on' : ''; });
        const card = $('card-' + k);
        card.classList.toggle('target', k === target && (fx[k].movedAt > 0));
        card.classList.toggle('live', now < fx[k].liveUntil);
      }
      $('sub-filter').textContent = s.filter ? (s.filter.value >= 0.995 ? 'Open' : 'Low-pass ' + Math.round(s.filter.cutoff_hz) + ' Hz') : '';
      $('sub-reverb').textContent = s.reverb ? (s.reverb.value <= 0.005 ? 'Dry' : 'Wet mix') : '';

      if (engaged) {
        const v = s[target].value;
        $('engName').textContent = target.toUpperCase();
        $('engPct').textContent = Math.round(v * 100) + '%';
        const lit = Math.round(v * TOWER);
        tower.forEach((b, i) => { b.className = i < lit - 1 ? 'on' : i === lit - 1 ? 'top' : ''; });
      }

      // sources
      status('st-vision', 'visionVal', vision, visionSeenAge, engaged ? 'PINCH' : 'ON', null, conn);
      const ard = s.sources && s.sources.arduino;
      const ardAge = ard && ard.last_seen_ms != null ? s.timestamp_ms - ard.last_seen_ms : Infinity;
      const serial = s.adapters && s.adapters.serial ? s.adapters.serial.status : 'disabled';
      status('st-arduino', 'pedalVal', ard, ardAge, 'ON', serial, conn);

      // diagnostics
      const c = s.controls || {};
      $('diag').textContent = `xruns ${s.xruns} · clipped ${s.clipped_samples} · events ${c.accepted ?? 0} ok · ${c.stale ?? 0} stale · ${c.duplicate ?? 0} dup · ${c.invalid ?? 0} invalid · ${c.low_confidence ?? 0} low-conf`;

      // sync manual sliders unless being dragged
      for (const k of ['filter', 'reverb']) {
        const el = $(k === 'filter' ? 'slFilter' : 'slReverb');
        if (document.activeElement !== el && s[k]) el.value = s[k].target;
        const pct = Math.round(parseFloat(el.value) * 100);
        el.style.setProperty('--v', pct + '%');
        $(k === 'filter' ? 'outFilter' : 'outReverb').textContent = pct + '%';
      }
    }

    drawWave(now);
    drawHand(now);
    requestAnimationFrame(render);
  }

  function status(boxId, valId, src, seenAge, onlineText, adapter, conn) {
    const box = $(boxId);
    const online = conn === 'live' && seenAge < ONLINE_MS;
    box.classList.toggle('online', online);
    box.classList.toggle('active', online && seenAge < ENGAGED_MS);
    let text;
    if (online) text = onlineText;
    else if (conn === 'stale') text = 'STALE';
    else if (conn === 'offline') text = 'OFF';
    else text = src ? 'IDLE' : 'OFF';
    if (conn === 'live' && adapter && adapter !== 'running' && !online) text = adapter === 'disabled' ? 'NO PORT' : String(adapter).toUpperCase();
    $(valId).textContent = text;
  }

  // ---------- waveform ----------
  const canvas = $('wave');
  const ctx = canvas.getContext('2d');
  function drawWave(now) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const pad = 12, bw = 6, gap = 2;
    const cols = Math.max(1, Math.floor((w - pad * 2) / (bw + gap)));
    const mid = h / 2, maxH = h / 2 - pad;
    const accent = color('--accent'), dim = color('--off'), rec = color('--rec'), unplayed = color('--dim');
    const smp = loop.samples;

    // grid: one tick per second of loop (or of max length while recording)
    let pos = 0;
    if (loop.state === 'playing' && loop.seconds > 0) pos = ((now - loop.playStart) / 1000 / loop.seconds) % 1;

    for (let c = 0; c < cols && loop.state !== 'idle'; c++) {  // idle: the empty state says it
      let v;
      if (smp.length === 0) v = loop.state === 'playing' ? 0.25 + 0.15 * Math.abs(Math.sin(c * 0.7)) : 0.02;
      else if (loop.state === 'recording') {
        // newest samples scroll in from the right
        const i = smp.length - cols + c;
        v = i >= 0 ? smp[i] : 0.02;
      } else {
        const i = Math.floor((c / cols) * smp.length);
        v = smp[Math.min(smp.length - 1, i)];
      }
      const bh = Math.max(2, Math.round(v * maxH));
      let fillc = dim;
      if (loop.state === 'recording') fillc = rec;
      else if (loop.state === 'playing') fillc = c / cols <= pos ? accent : unplayed;
      ctx.fillStyle = fillc;
      ctx.fillRect(pad + c * (bw + gap), Math.round(mid - bh), bw, bh * 2);
    }
    // ruler: one tick per second of loop, so the length reads without the number
    if (loop.state === 'playing' && loop.seconds > 0) {
      ctx.fillStyle = color('--line-2');
      const span = w - pad * 2;
      for (let t = 0; t <= loop.seconds + 1e-6; t += 1) ctx.fillRect(Math.round(pad + (t / loop.seconds) * span), h - 8, 2, 8);
      ctx.fillStyle = color('--text');
      ctx.fillRect(Math.round(pad + pos * span), 0, 4, h);
    }
  }

  // ---------- hand view ----------
  // MediaPipe hand topology: wrist 0, thumb 1-4, index 5-8, middle 9-12, ring 13-16, pinky 17-20
  const BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],
                 [9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
  const CAM_ASPECT = 4 / 3;  // landmarks are normalized per axis; undo that so the hand isn't stretched
  const view = { cx: 0.5, cy: 0.5, size: 0.4 };  // smoothed follow-zoom around the hand
  const handCanvas = $('handCanvas');
  const hctx = handCanvas.getContext('2d');
  function drawHand(now) {
    const fresh = hand.frame && now - hand.at < HAND_STALE_MS;
    if (!fresh) hand.frame = null;  // stale or disconnected: never keep an old hand on screen
    const f = hand.frame;
    let mode = 'off', label = HAND_URL ? 'NO CAMERA' : 'OFF';
    if (f && !f.present) { mode = 'none'; label = 'NO HAND'; }
    else if (f && f.engaged) {
      mode = 'engaged';
      const pct = typeof f.value === 'number' ? Math.round(f.value * 100) + '%' : '';
      label = (f.control ? f.control.toUpperCase() : 'MORPH') + ' ' + pct;
    } else if (f) { mode = 'seen'; label = 'SEEN'; }  // not "armed": may be waiting for an open-hand re-arm
    $('handPanel').dataset.hand = mode;
    $('handState').textContent = label;
    $('handEmptyWord').textContent = mode === 'none' ? 'NO HAND' : HAND_URL ? 'NO CAMERA' : 'HAND VIEW OFF';
    $('handEmptyHint').textContent = mode === 'none' ? 'Show one hand to the camera.' : HAND_URL ? 'Start vision to see your hand.' : 'Remove ?hand=off to turn it on.';

    const dpr = window.devicePixelRatio || 1;
    const w = handCanvas.clientWidth, h = handCanvas.clientHeight;
    if (handCanvas.width !== Math.round(w * dpr) || handCanvas.height !== Math.round(h * dpr)) {
      handCanvas.width = Math.round(w * dpr); handCanvas.height = Math.round(h * dpr);
    }
    hctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    hctx.clearRect(0, 0, w, h);
    const G = 12;
    hctx.fillStyle = color('--off');
    for (let gx = G / 2; gx < w; gx += G) for (let gy = G / 2; gy < h; gy += G) hctx.fillRect(Math.round(gx) - 1, Math.round(gy) - 1, 2, 2);

    const engaged = mode === 'engaged';
    if (engaged && typeof f.value === 'number') {  // value rail on the right edge
      const rh = Math.round(f.value * (h - 8));
      hctx.fillStyle = color('--accent-deep'); hctx.fillRect(w - 10, 4, 6, h - 8);
      hctx.fillStyle = color('--accent'); hctx.fillRect(w - 10, h - 4 - rh, 6, rh);
    }
    if (!f || !f.present || f.landmarks.length !== 21) return;

    // mirrored like a mirror, then follow-zoomed so the hand fills the panel; the rail shows the value
    const Q = f.landmarks.map(([x, y]) => [(1 - x) * CAM_ASPECT, y]);
    const xs = Q.map((q) => q[0]), ys = Q.map((q) => q[1]);
    const bx = (Math.min(...xs) + Math.max(...xs)) / 2, by = (Math.min(...ys) + Math.max(...ys)) / 2;
    const bs = Math.max(0.05, Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const k = 0.25;
    view.cx += (bx - view.cx) * k; view.cy += (by - view.cy) * k; view.size += (bs - view.size) * k;
    const sc = (0.72 * Math.min(w, h)) / view.size;
    const P = Q.map(([x, y]) => [(x - view.cx) * sc + w / 2, (y - view.cy) * sc + h / 2]);
    hctx.lineWidth = 3; hctx.lineCap = 'square';
    hctx.strokeStyle = engaged ? color('--accent') : color('--muted');
    hctx.beginPath();
    for (const [a, b] of BONES) { hctx.moveTo(P[a][0], P[a][1]); hctx.lineTo(P[b][0], P[b][1]); }
    hctx.stroke();
    hctx.fillStyle = color('--text');
    for (const [x, y] of P) hctx.fillRect(Math.round(x) - 3, Math.round(y) - 3, 6, 6);
    if (engaged) {  // the pinch: thumb tip + index tip
      hctx.strokeStyle = color('--accent'); hctx.lineWidth = 2;
      for (const i of [4, 8]) hctx.strokeRect(Math.round(P[i][0]) - 7, Math.round(P[i][1]) - 7, 14, 14);
    }
  }
  connectHand();

  // ---------- manual controls ----------
  // a key lights pink when the engine socket took the event, and nudges amber when it could not
  function press(btn, ok) {
    const cls = ok ? 'sent' : 'fail';
    btn.classList.remove('sent', 'fail');
    void btn.offsetWidth;
    btn.classList.add(cls);
    clearTimeout(btn._t);
    btn._t = setTimeout(() => btn.classList.remove(cls), 260);
  }
  $('btnLoop').addEventListener('click', (e) => press(e.currentTarget, send('loop')));
  $('btnBypass').addEventListener('click', (e) => press(e.currentTarget, send('bypass')));
  for (const [id, control, out] of [['slFilter', 'filter', 'outFilter'], ['slReverb', 'reverb', 'outReverb']]) {
    let last = 0;
    const show = (el) => { const pct = Math.round(parseFloat(el.value) * 100); el.style.setProperty('--v', pct + '%'); $(out).textContent = pct + '%'; };
    $(id).addEventListener('input', (e) => {
      show(e.target);
      const t = performance.now();
      if (t - last < 40) return;  // ~25 Hz
      last = t; send(control, parseFloat(e.target.value));
    });
    $(id).addEventListener('change', (e) => send(control, parseFloat(e.target.value)));
  }

  connect();
  requestAnimationFrame(render);
})();
