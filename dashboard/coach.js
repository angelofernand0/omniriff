// Coach column (piece F): the dashboard side of the coach feed (protocol/coach.schema.json).
//
//   ws://127.0.0.1:47803 (?coachws= overrides)   served by coach/ or by tools/sim's scripted session
//
// One column, one reading order: the session map, Riff with what it is saying (a speech bubble
// that types out in step with the voice), then GOAL / NOW / GAP / NEXT, then what the pedal does.
// Riff, the bubble and the voice start together: a new line waits (up to 2.5 s) for its audio,
// and Riff never moves or starts a new line while the current one is still being said.
// Keys exist only because the simulator has no pedal: Y / N answer Riff, M mutes.
'use strict';

(() => {
  const params = new URLSearchParams(location.search);
  const mode = params.get('coach') || 'on';
  if (mode === 'off' || mode === 'preview' || !window.OmniRiff || !window.OmniRiff.coach) return;
  const URL_ = params.get('coachws') || 'ws://127.0.0.1:47803';
  const $ = (id) => document.getElementById(id);
  const app = $('app'), dock = $('coachDock'), led = $('led-coach');
  const ui = {
    map: $('steps'), line: $('coachLine'), pedal: $('pedalNext'),
    goalRow: $('pGoalRow'), goal: $('pGoal'), nowRow: $('pNow'), drill: $('pDrill'), attempt: $('pAttempt'),
    gapRow: $('pMetric'), gapName: $('pMetricName'), gap: $('pMetricNow'), target: $('pTarget'), bar: $('pChart'),
    nextRow: $('pNextRow'), next: $('pNext'), doneRow: $('pSummary'), done: $('pSummaryText'), last: $('pLast'),
  };
  const TARGET = { loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '#fxPower', input: '.loop-state', hand: '#handPanel' };
  // what each tool is, said by Riff while it works (the raw names are in the coach's LangSmith trace)
  const DOING = [
    [/^get_take_report/, 'Listening back to your timing'], [/^get_hand_report/, 'Watching your strumming hand'],
    [/^open skill/, 'Picking a drill'], [/^write_drill_card/, 'Setting up the drill'], [/^compare_takes/, 'Comparing with your last take'],
    [/memories/, 'Remembering this for next time'], [/^rig_control/, 'Getting the rig ready'],
  ];
  const doing = (w) => { for (const [re, s] of DOING) if (re.test(w)) return s; return 'Thinking'; };

  let ws = null, retry = 0, frame = null, joined = false, muted = false;
  try { muted = localStorage.getItem('omniriff.voiceMuted') === '1'; } catch (e) { /* storage blocked */ }

  // ---------- socket ----------
  function connect() {
    try { ws = new WebSocket(URL_); } catch (e) { later(); return; }
    ws.onopen = () => { retry = 0; joined = true; };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m && m.version === 1 && m.type === 'coach.frame') onFrame(m);
      else if (m && m.version === 1 && m.type === 'coach.audio') onAudio(m);
    };
    ws.onclose = () => { offline(); later(); };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* closed */ } };
  }
  function later() { setTimeout(connect, Math.min(4000, 500 * 2 ** retry++)); }
  function send(type) {
    if (!frame || !frame.awaiting_approval || !ws || ws.readyState !== 1) return false;
    ws.send(JSON.stringify({ version: 1, type, timestamp_ms: Date.now(), approval_id: frame.awaiting_approval.id }));
    return true;
  }

  function offline() {
    frame = null; held = null; clearTimeout(waitTimer);
    window.OmniRiff.coach.set({ state: 'asleep', target: null, cue: '', mood: 'sleepy', stage: false });
    mark(null); type('', 0); setLed('off', 'OFF');
    if (dock) dock.dataset.state = 'asleep';
    renderRows(null); renderMap();
  }
  function setLed(kind, word) {
    if (led) { led.classList.toggle('online', kind === 'live'); led.classList.toggle('warn', kind === 'scripted'); led.querySelector('span').textContent = word; }
    if (app) app.dataset.coach = kind;
  }

  // ---------- Riff: pose, place and bubble, always together with the voice ----------
  let marked = null;
  function mark(sel) {
    if (marked) marked.classList.remove('spot-target');
    marked = sel ? document.querySelector(sel) : null;
    if (marked) marked.classList.add('spot-target');
  }
  let held = null, waitTimer = 0, lineShown = '';
  function show(f, secs) {                   // apply a frame to Riff and the bubble
    const target = f.target ? TARGET[f.target] || null : null;
    window.OmniRiff.coach.set({ state: f.state, target, cue: f.cue || '', mood: f.mood, stage: false });
    mark(target);
    if (dock) dock.dataset.state = f.state;
    if (f.cue && f.cue !== lineShown) { lineShown = f.cue; type(f.cue, secs); }
    else if (!f.cue) thinkingText(f);
  }
  function thinkingText(f) {                 // no line: the bubble says what Riff is doing, quietly
    const now = [...(f.activity || [])].reverse().find((x) => x.status === 'running');
    if (f.state === 'thinking') { lineShown = ''; type(`${now ? doing(now.what) : 'Thinking'}…`, 0, true); }
    else if (f.state === 'listening') { lineShown = ''; type('Listening…', 0, true); }
  }

  // typewriter: reveal the line over the time it takes to say it
  let typeTimer = 0;
  function type(text, secs, quiet) {
    clearInterval(typeTimer);
    if (!ui.line) return;
    ui.line.dataset.quiet = String(!!quiet);
    if (!text || quiet || !(secs > 0)) { ui.line.textContent = text; return; }
    const step = Math.max(12, Math.min(60, (secs * 1000 * 0.92) / text.length));
    let i = 0;
    ui.line.textContent = '';
    typeTimer = setInterval(() => { i += 1; ui.line.textContent = text.slice(0, i); if (i >= text.length) clearInterval(typeTimer); }, step);
  }

  function onFrame(f) {
    const prevCue = frame && frame.cue;
    frame = f;
    setLed(f.scripted ? 'scripted' : 'live', f.state === 'asleep' ? 'OFF' : f.scripted ? 'SCRIPTED' : 'LIVE');
    renderRows(f); renderMap();
    if (joined) { joined = false; spoken = f.cue || ''; show(f, 0); return; }   // joined mid-line: no voice, no typing
    const newLine = !!f.cue && f.cue !== prevCue;
    if (newLine) {
      held = f;                               // Riff waits for this line's voice, then everything starts at once
      const ready = pendingAudio.get(f.cue);
      if (ready && !muted) { pendingAudio.delete(f.cue); enqueue(ready); return; }
      clearTimeout(waitTimer);
      waitTimer = setTimeout(() => {          // no audio in time: say it with the browser (or just type it)
        if (frame !== f || spoken === f.cue) return;
        if (!muted && !hasCoachVoice && 'speechSynthesis' in window) enqueue({ text: f.cue, browser: true });
        else if (!busy()) { held = null; show(f, f.cue.split(' ').length / 2.6); }
      }, muted ? 0 : 2500);
      return;
    }
    if (busy()) held = f; else show(f, 0);   // never move mid-sentence
  }
  function release(textStarting, secs) {
    const f = held; held = null;
    if (f) show(f, f.cue === textStarting ? secs : 0);
  }

  // ---------- the rows: GOAL / NOW / GAP / NEXT (or DONE) ----------
  function renderRows(f) {
    const ses = f && f.session, card = f && f.drill_card;
    const goal = (ses && ses.goal) || (card && card.passage) || null;
    ui.goalRow.hidden = !goal;
    if (goal) ui.goal.textContent = goal;
    const drill = ses ? ses.drill : card ? { title: card.title } : null;
    ui.nowRow.hidden = !drill;
    if (drill) {
      ui.drill.textContent = drill.title;
      const at = ses && ses.attempt;
      ui.attempt.textContent = at ? `take ${Math.max(at.n, 1)} of ${at.of}` : '';
    }
    const m = ses && ses.metric, last = m && m.history.length ? m.history[m.history.length - 1] : null;
    ui.gapRow.hidden = last === null;
    if (last !== null) {
      const pass = m.lower_is_better ? last <= m.target : last >= m.target;
      ui.gapName.textContent = m.name === 'longest gap' ? 'GAP' : m.name.toUpperCase();
      ui.gap.textContent = `${Math.round(last)} ${m.unit}`;
      ui.gapRow.dataset.pass = String(pass);
      ui.target.textContent = `target ${m.lower_is_better ? 'under' : 'over'} ${Math.round(m.target)}`;
      const top = Math.max(m.target * 3, ...m.history);
      ui.bar.style.setProperty('--now', `${Math.min(100, (last / top) * 100).toFixed(1)}%`);
      ui.bar.style.setProperty('--goal', `${((m.target / top) * 100).toFixed(1)}%`);
    }
    const summary = ses && ses.summary;
    ui.doneRow.hidden = !summary;
    if (summary) ui.done.textContent = summary;
    ui.nextRow.hidden = !(ses && ses.next) || !!summary;
    if (ses && ses.next) ui.next.textContent = ses.next;
    ui.last.hidden = !(ses && ses.last_time) || !!summary;
    if (ses && ses.last_time) ui.last.textContent = `Last time: ${ses.last_time}`;
  }

  // ---------- the map and the pedal: where you are, and what one tap does now ----------
  function renderMap() {
    const f = frame, ses = f && f.session, loop = app ? app.dataset.loop : 'idle';
    const play = !f || f.state === 'asleep' || (ses && ses.mode === 'play');
    let step = 1;
    if (ses && ses.plan && ses.plan.length) { const i = ses.plan.findIndex((d) => d.status === 'now'); step = i >= 0 ? i + 2 : 4; }
    if (ui.map) { ui.map.dataset.step = String(step); ui.map.dataset.mode = play ? 'play' : 'practice'; }
    let say;
    if (play) say = loop === 'recording' ? 'tap to close the loop' : 'free play · hold for another round (Y)';
    else if (loop === 'recording') say = 'tap to stop';
    else if (f && f.awaiting_approval) say = 'tap to start the drill';
    else if (f && ['thinking', 'speaking', 'pointing'].includes(f.state)) say = 'wait for Riff';
    else if (step === 1) say = 'tap, play it, tap again';
    else if (step === 4) say = 'wait for Riff';
    else say = 'tap to play the drill';
    if (ui.pedal) ui.pedal.querySelector('span').textContent = say;
  }
  if (app) new MutationObserver(renderMap).observe(app, { attributes: true, attributeFilter: ['data-loop'] });

  // ---------- voice: never cut off, never late ----------
  let actx = null, analyser = null, audioEl = null, spoken = '', hasCoachVoice = false, queued = null, locked = null;
  const pendingAudio = new Map();
  const busy = () => (audioEl && !audioEl.paused && !audioEl.ended) || ('speechSynthesis' in window && speechSynthesis.speaking);
  function unlock() {
    if (!actx) {
      try { actx = new (window.AudioContext || window.webkitAudioContext)(); analyser = actx.createAnalyser(); analyser.fftSize = 512; analyser.connect(actx.destination); }
      catch (e) { actx = null; }
    }
    if (actx && actx.state === 'suspended') actx.resume();
    if (dock) delete dock.dataset.voice;
    const m = locked; locked = null;
    if (m && frame && frame.cue === m.text && !muted) enqueue(m);
  }
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);

  function onAudio(m) {
    hasCoachVoice = true;
    if (muted) return;
    if (!frame || frame.cue !== m.text) {    // early: keep it for when its line lands
      pendingAudio.set(m.text, m);
      if (pendingAudio.size > 6) pendingAudio.delete(pendingAudio.keys().next().value);
      return;
    }
    if (spoken === m.text) return;
    clearTimeout(waitTimer);
    enqueue(m);
  }
  function enqueue(item) { if (busy()) queued = item; else start(item); }
  function start(item) { if (item.browser) speakBrowser(item.text); else playAudio(item); }
  function finished() {
    talking(false);
    const q = queued; queued = null;
    if (q && frame && frame.cue === q.text) { setTimeout(() => (busy() ? (queued = q) : start(q)), 250); return; }
    if (held && held.cue === spoken) held = null;
    if (held) release('', 0);                 // the line is done: Riff catches up
  }
  function playAudio(m) {
    spoken = m.text;
    try {
      const bytes = Uint8Array.from(atob(m.audio_b64), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: m.mime }));
      const a = new Audio(url);
      audioEl = a;
      if (actx && analyser) { try { actx.createMediaElementSource(a).connect(analyser); } catch (e) { /* unanalysed */ } }
      a.onended = () => { URL.revokeObjectURL(url); if (audioEl === a) audioEl = null; finished(); };
      a.play().then(() => {
        talking(true);
        const secs = Number.isFinite(a.duration) ? a.duration : m.text.split(' ').length / 2.6;
        release(m.text, secs);               // Riff moves, the bubble types, the voice plays: together
      }).catch(() => { audioEl = null; spoken = ''; locked = m; if (dock) dock.dataset.voice = 'locked'; release(m.text, 0); });
    } catch (e) { audioEl = null; finished(); }
  }
  function speakBrowser(text) {
    spoken = text;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02; u.pitch = 1.15;
    u.onstart = () => { talking(true, true); release(text, text.split(' ').length / 2.6); };
    u.onend = finished;
    u.onboundary = () => window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: 0.8 } }));
    speechSynthesis.speak(u);
  }
  function stopVoice() {
    queued = null;
    if (audioEl) { try { audioEl.pause(); } catch (e) { /* gone */ } audioEl = null; }
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    talking(false);
  }
  let talkRaf = 0;
  const buf = new Uint8Array(256);
  function talking(on, browser) {
    cancelAnimationFrame(talkRaf);
    if (!on) { window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: 0 } })); return; }
    if (browser || !analyser) return;
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i] - 128));
      window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: Math.min(1, peak / 64) } }));
      talkRaf = requestAnimationFrame(tick);
    };
    tick();
  }

  // ---------- keys (the simulator has no pedal) ----------
  window.addEventListener('keydown', (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === 'y' && send('coach.approve')) e.preventDefault();
    else if (k === 'n' && send('coach.reject')) e.preventDefault();
    else if (k === 'm') {
      muted = !muted;
      try { localStorage.setItem('omniriff.voiceMuted', muted ? '1' : '0'); } catch (err) { /* blocked */ }
      if (muted) stopVoice();
      if (dock) dock.dataset.muted = String(muted);
    }
  });
  if (dock) dock.dataset.muted = String(muted);

  window.OmniRiff.coachFeed = { get: () => frame, speaking: () => !!busy(), line: () => spoken };
  renderMap();
  connect();
})();
