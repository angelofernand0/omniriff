// Coach layer (roadmap R3, piece F): the dashboard side of the coach feed.
//
//   ws://127.0.0.1:47803   protocol/coach.schema.json, served by the coach (coach/) or by the
//                          SCRIPTED session (python -m tools.sim coach / run --coach-sim)
//   ?coachws=ws://...      override the feed URL      ?coach=off | preview  (riff.js handles those)
//
// It drives Riff (OmniRiff.coach.set), fills the 04 COACH dock (plan, drill card, before/after,
// activity strip, approval prompt), sends coach.approve / coach.reject (Y / N), and plays Riff's
// voice: coach.audio from the coach when it arrives, the browser's voice as a fallback. M mutes.
// A scripted session is always labelled SCRIPTED. With no feed, the dock reads COACH OFF and the
// rig plays exactly as before.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const mode = params.get('coach') || 'on';
  if (mode === 'off' || mode === 'preview' || !window.OmniRiff || !window.OmniRiff.coach) return;
  const URL_ = params.get('coachws') || 'ws://127.0.0.1:47803';
  const $ = (id) => document.getElementById(id);
  const dock = $('coachDock'), led = $('led-coach'), detail = $('coachDetail');
  const els = {
    tag: dock && dock.querySelector('.preview-tag'),
    ask: $('coachAsk'), askText: $('coachAskText'),
    plan: $('coachPlan'), drill: $('coachDrill'), ba: $('coachBA'), acts: $('coachActs'),
  };

  // logical targets (schema) → the element Riff perches on
  const TARGET = {
    loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '.fx-zone',
    input: '.meters', hand: '#handPanel', coach: null, player: null,
  };

  let ws = null, retry = 0, frame = null, live = false;
  let muted = false;
  try { muted = localStorage.getItem('omniriff.voiceMuted') === '1'; } catch (e) { /* storage blocked */ }

  // ---------- socket ----------
  function connect() {
    try { ws = new WebSocket(URL_); } catch (e) { later(); return; }
    ws.onopen = () => { retry = 0; };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m && m.version === 1 && m.type === 'coach.frame') apply(m);
      else if (m && m.version === 1 && m.type === 'coach.audio') onAudio(m);
    };
    ws.onclose = () => { offline(); later(); };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* already closed */ } };
  }
  function later() { setTimeout(connect, Math.min(4000, 500 * 2 ** retry++)); }
  function send(type) {
    if (!frame || !frame.awaiting_approval || !ws || ws.readyState !== 1) return false;
    ws.send(JSON.stringify({ version: 1, type, timestamp_ms: Date.now(), approval_id: frame.awaiting_approval.id }));
    return true;
  }

  // ---------- render ----------
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MARK = { completed: '✓', in_progress: '▸', pending: '·', done: '✓', running: '…', waiting: '?', failed: '✕' };

  function offline() {
    live = false; frame = null;
    window.OmniRiff.coach.set({ state: 'asleep', target: null, cue: '', mood: 'sleepy' });
    if (detail) detail.hidden = true;
    if (dock) { delete dock.dataset.scripted; dock.dataset.ask = 'false'; }
    setLed('off', 'OFF');
  }

  function setLed(kind, word) {
    if (!led) return;
    led.classList.toggle('online', kind === 'live');
    led.classList.toggle('warn', kind === 'scripted');
    led.querySelector('span').textContent = word;
  }

  function apply(f) {
    const prevCue = frame && frame.cue;
    frame = f; live = true;
    const target = f.target ? TARGET[f.target] : null;
    window.OmniRiff.coach.set({ state: f.state, target, cue: f.cue || '', mood: f.mood, gaze: f.target === 'player' ? 'player' : null });
    // riff.js renders the LED for its own preview; the feed owns it from here
    setLed(f.scripted ? 'scripted' : 'live', f.state === 'asleep' ? 'OFF' : f.scripted ? 'SCRIPTED' : 'LIVE');
    if (dock) {
      if (f.scripted) dock.dataset.scripted = 'true'; else delete dock.dataset.scripted;
      dock.dataset.ask = String(!!f.awaiting_approval);
    }
    if (els.tag) els.tag.textContent = f.scripted ? 'SCRIPTED · NOT AI' : 'SCRIPTED PREVIEW';
    render(f);
    if (f.cue && f.cue !== prevCue) cueChanged(f.cue);
  }

  function render(f) {
    if (!detail) return;
    const a = f.awaiting_approval;
    els.ask.hidden = !a;
    if (a) els.askText.textContent = a.summary;

    const d = f.drill_card;
    els.drill.hidden = !d;
    if (d) {
      els.drill.innerHTML = `<header><b>DRILL</b><span>${esc(d.title)}</span></header>`
        + `<p>${esc(d.passage)} · ${d.reps}×</p><p class="pass">PASS: ${esc(d.pass_rule)}</p>`
        + (d.journal_path ? `<p class="path">${esc(d.journal_path)}</p>` : '');
    }

    // the plan only while there's no drill card or result competing for the space
    const todos = f.todos || [];
    els.plan.hidden = !todos.length || !!d || !!f.before_after;
    els.plan.innerHTML = '<header><b>PLAN</b></header>' + todos.slice(0, 5).map((t) =>
      `<li data-s="${t.status}"><i>${MARK[t.status]}</i>${esc(t.text)}</li>`).join('');

    const b = f.before_after;
    els.ba.hidden = !b;
    if (b) {
      const pct = (v) => Math.round(v * 100);
      els.ba.dataset.improved = String(b.improved);
      els.ba.innerHTML = '<header><b>BEFORE → AFTER</b></header>'
        + `<div><span>WORST GAP</span><b>${Math.round(b.worst_gap_ms[0])} → ${Math.round(b.worst_gap_ms[1])} ms</b></div>`
        + `<div><span>HESITATIONS</span><b>${b.hesitations[0]} → ${b.hesitations[1]}</b></div>`
        + `<div><span>STEADY</span><b>${pct(b.tempo_stability[0])} → ${pct(b.tempo_stability[1])}%</b></div>`;
    }

    const acts = (f.activity || []).slice(-3);
    els.acts.hidden = !acts.length;
    els.acts.innerHTML = acts.map((x) =>
      `<li data-s="${x.status}"><b>${x.who.toUpperCase()}</b><span>${esc(x.what)}</span><i>${MARK[x.status]}</i></li>`).join('');

    detail.hidden = els.ask.hidden && els.drill.hidden && els.plan.hidden && els.ba.hidden && els.acts.hidden;
  }

  // ---------- voice ----------
  // coach.audio (ElevenLabs, rendered in the coach process) is preferred. If it hasn't arrived
  // 1.5 s after a new cue, the browser speaks instead. Riff's talking squash follows the real
  // loudness of whatever is playing (omniriff:voice events), not a canned loop.
  let actx = null, analyser = null, audioEl = null, fallbackTimer = 0, spoken = '';
  const pendingAudio = new Map();   // text → audio message that arrived before its frame

  function unlock() {           // browsers allow audio only after a click or key press
    if (!actx) {
      try {
        actx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = actx.createAnalyser(); analyser.fftSize = 512; analyser.connect(actx.destination);
      } catch (e) { actx = null; }
    }
    if (actx && actx.state === 'suspended') actx.resume();
  }
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);

  function cueChanged(text) {
    stopVoice();
    clearTimeout(fallbackTimer);
    if (muted) return;
    const ready = pendingAudio.get(text);
    if (ready) { pendingAudio.delete(text); playAudio(ready); return; }
    fallbackTimer = setTimeout(() => { if (frame && frame.cue === text && spoken !== text) speakBrowser(text); }, 1500);
  }

  function onAudio(m) {
    if (muted) return;
    if (!frame || frame.cue !== m.text) {          // early: keep it for when the cue lands
      pendingAudio.set(m.text, m);
      if (pendingAudio.size > 6) pendingAudio.delete(pendingAudio.keys().next().value);
      return;
    }
    if (spoken === m.text) return;
    clearTimeout(fallbackTimer);
    playAudio(m);
  }

  function playAudio(m) {
    stopVoice();
    spoken = m.text;
    try {
      const bytes = Uint8Array.from(atob(m.audio_b64), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: m.mime }));
      audioEl = new Audio(url);
      if (actx && analyser) {
        try { actx.createMediaElementSource(audioEl).connect(analyser); } catch (e) { /* plays unanalysed */ }
      }
      audioEl.onended = () => { URL.revokeObjectURL(url); talking(false); };
      audioEl.play().then(() => talking(true)).catch(() => { spoken = ''; speakBrowser(m.text); });
    } catch (e) { speakBrowser(m.text); }
  }

  function speakBrowser(text) {
    if (!('speechSynthesis' in window)) return;
    spoken = text;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02; u.pitch = 1.15;
    u.onstart = () => talking(true, true);
    u.onend = () => talking(false);
    u.onboundary = () => window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: 0.8 } }));
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }

  function stopVoice() {
    if (audioEl) { try { audioEl.pause(); } catch (e) { /* gone */ } audioEl = null; }
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    talking(false);
  }

  let talkRaf = 0;
  const buf = new Uint8Array(256);
  function talking(on, browser) {
    cancelAnimationFrame(talkRaf);
    if (!on) { window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: 0 } })); return; }
    if (browser || !analyser) return;   // browser voice: boundary events drive the pulse
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i] - 128));
      window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: Math.min(1, peak / 64) } }));
      talkRaf = requestAnimationFrame(tick);
    };
    tick();
  }

  // ---------- keys: Y / N answer Riff, M mutes ----------
  window.addEventListener('keydown', (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === 'y' && send('coach.approve')) e.preventDefault();
    else if (k === 'n' && send('coach.reject')) e.preventDefault();
    else if (k === 'm') {
      muted = !muted;
      try { localStorage.setItem('omniriff.voiceMuted', muted ? '1' : '0'); } catch (err) { /* storage blocked */ }
      if (muted) stopVoice();
      if (dock) dock.dataset.muted = String(muted);
    }
  });
  if (dock) dock.dataset.muted = String(muted);
  const yes = $('coachYes'), no = $('coachNo');
  if (yes) yes.addEventListener('click', () => send('coach.approve'));
  if (no) no.addEventListener('click', () => send('coach.reject'));

  window.OmniRiff.coachFeed = { get: () => frame, live: () => live };
  connect();
})();
