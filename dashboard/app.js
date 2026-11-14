// OmniRiff dashboard: reads v1 state frames (protocol/state.schema.json) from the engine
// WebSocket and sends v1 control envelopes back on the same socket as source "dashboard".
// Optional by design: the instrument works with this page closed.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const WS_URL = params.get('ws') || 'ws://127.0.0.1:47801';
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
    for (let i = 0; i < n; i++) { const b = document.createElement('i'); if (cls) b.className = cls(i); el.appendChild(b); out.push(b); }
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
    state = s;
    lastFrameAt = performance.now();
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
      $('inDb').textContent = s.input_peak_dbfs <= METER_FLOOR ? '–∞ dB' : s.input_peak_dbfs.toFixed(1) + ' dB';

      // looper
      app.dataset.loop = loop.state;
      $('loopWord').textContent = { idle: 'READY', recording: 'REC', playing: 'PLAY' }[loop.state] || '—';
      $('loopLen').textContent = loop.state === 'idle' ? 'no loop' : loop.seconds.toFixed(1) + ' s';
      $('loopHint').textContent = { idle: 'tap pedal to record', recording: 'tap to close loop', playing: 'tap to clear' }[loop.state] || '';
      $('waveNote').textContent = loop.partial ? 'loop recorded before this page opened' : '';

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
      $('sub-filter').textContent = s.filter ? (s.filter.value >= 0.995 ? 'open' : Math.round(s.filter.cutoff_hz) + ' Hz low-pass') : '';
      $('sub-reverb').textContent = s.reverb ? (s.reverb.value <= 0.005 ? 'dry' : 'wet ' + Math.round(s.reverb.value * 100) + '%') : '';

      if (engaged) {
        const v = s[target].value;
        $('engName').textContent = target.toUpperCase();
        $('engPct').textContent = Math.round(v * 100) + '%';
        const lit = Math.round(v * TOWER);
        tower.forEach((b, i) => { b.className = i < lit - 1 ? 'on' : i === lit - 1 ? 'top' : ''; });
      }

      // sources
      status('st-vision', 'visionVal', vision, visionSeenAge, engaged ? 'pinch held' : 'watching', null, conn);
      const ard = s.sources && s.sources.arduino;
      const ardAge = ard && ard.last_seen_ms != null ? s.timestamp_ms - ard.last_seen_ms : Infinity;
      const serial = s.adapters && s.adapters.serial ? s.adapters.serial.status : 'disabled';
      status('st-arduino', 'pedalVal', ard, ardAge, 'connected', serial, conn);

      // diagnostics
      const c = s.controls || {};
      $('diag').textContent = `xruns ${s.xruns} · clipped ${s.clipped_samples} · events ok ${c.accepted ?? 0} · stale ${c.stale ?? 0} · dup ${c.duplicate ?? 0} · invalid ${c.invalid ?? 0} · low-conf ${c.low_confidence ?? 0}`;

      // sync manual sliders unless being dragged
      for (const k of ['filter', 'reverb']) {
        const el = $(k === 'filter' ? 'slFilter' : 'slReverb');
        if (document.activeElement !== el && s[k]) el.value = s[k].target;
      }
    }

    drawWave(now);
    requestAnimationFrame(render);
  }

  function status(boxId, valId, src, seenAge, onlineText, adapter, conn) {
    const box = $(boxId);
    const online = conn === 'live' && seenAge < ONLINE_MS;
    box.classList.toggle('online', online);
    box.classList.toggle('active', online && seenAge < ENGAGED_MS);
    let text;
    if (online) text = onlineText;
    else if (conn === 'stale') text = 'stale';
    else if (conn === 'offline') text = 'offline';
    else text = src ? 'quiet' : 'offline';
    if (conn === 'live' && adapter && adapter !== 'running' && !online) text = 'serial ' + adapter;
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
    const accent = color('--accent'), dim = color('--off'), rec = color('--rec');
    const smp = loop.samples;

    // grid: one tick per second of loop (or of max length while recording)
    let pos = 0;
    if (loop.state === 'playing' && loop.seconds > 0) pos = ((now - loop.playStart) / 1000 / loop.seconds) % 1;

    for (let c = 0; c < cols; c++) {
      let v;
      if (loop.state === 'idle') v = 0.02;
      else if (smp.length === 0) v = loop.state === 'playing' ? 0.25 + 0.15 * Math.abs(Math.sin(c * 0.7)) : 0.02;
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
      else if (loop.state === 'playing') fillc = c / cols <= pos ? accent : '#4A4858';
      ctx.fillStyle = fillc;
      ctx.fillRect(pad + c * (bw + gap), Math.round(mid - bh), bw, bh * 2);
    }
    if (loop.state === 'playing') {
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(Math.round(pad + pos * (w - pad * 2)), 0, 3, h);
    }
  }

  // ---------- manual controls ----------
  $('btnLoop').addEventListener('click', () => send('loop'));
  $('btnBypass').addEventListener('click', () => send('bypass'));
  for (const [id, control] of [['slFilter', 'filter'], ['slReverb', 'reverb']]) {
    let last = 0;
    $(id).addEventListener('input', (e) => {
      const t = performance.now();
      if (t - last < 40) return;  // ~25 Hz
      last = t; send(control, parseFloat(e.target.value));
    });
    $(id).addEventListener('change', (e) => send(control, parseFloat(e.target.value)));
  }

  connect();
  requestAnimationFrame(render);
})();
