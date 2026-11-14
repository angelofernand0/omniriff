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
  const app = $('app'), dock = $('coachDock'), led = $('led-coach');
  const els = {
    tag: dock && dock.querySelector('.preview-tag'), cue: $('coachLine'), acts: $('coachActsLine'),
    ask: $('coachAsk'), askText: $('coachAskText'), plan: $('coachPlan'), ba: $('coachBA'),
    goal: $('pGoal'), now: $('pNow'), step: $('pStep'), drill: $('pDrill'), attempt: $('pAttempt'),
    metric: $('pMetric'), mName: $('pMetricName'), mNow: $('pMetricNow'), target: $('pTarget'), chart: $('pChart'),
    nextRow: $('pNextRow'), next: $('pNext'), last: $('pLast'),
  };

  // logical targets (schema) → what Riff walks to. Buttons get reached with the finger.
  const TARGET = {
    loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '#fxPower',
    input: '.loop-state', hand: '#handPanel', coach: null, player: null,
  };

  let ws = null, retry = 0, frame = null, live = false, joined = false;
  let muted = false;
  try { muted = localStorage.getItem('omniriff.voiceMuted') === '1'; } catch (e) { /* storage blocked */ }

  // ---------- socket ----------
  function connect() {
    try { ws = new WebSocket(URL_); } catch (e) { later(); return; }
    ws.onopen = () => { retry = 0; joined = true; };
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
  const WHO = { coach: 'RIFF', ears: 'EARS', eyes: 'EYES' };
  // what each tool means, said like a person (the raw tool names are in the coach's LangSmith trace)
  const SAYS = [
    [/^get_take_report/, 'reading your timing'], [/^get_hand_report/, 'watching your strumming hand'],
    [/^open skill (.+)/, (m) => `opening the ${m[1].replace(/-/g, ' ')} drill`], [/^write_drill_card/, 'writing the drill'],
    [/^rig_control (\w+)/, (m) => m[1] === 'bypass' ? 'asking to switch effects off' : `asking to change ${m[1]}`],
    [/^compare_takes/, 'comparing your takes'], [/memories/, 'remembering this for next time'],
    [/^get_rig_state/, 'checking the rig'], [/^say/, 'talking'],
  ];
  const human = (what) => { for (const [re, out] of SAYS) { const m = what.match(re); if (m) return typeof out === 'function' ? out(m) : out; } return what.replace(/_/g, ' '); };

  function offline() {
    live = false; frame = null; held = null;
    window.OmniRiff.coach.set({ state: 'asleep', target: null, cue: '', mood: 'sleepy', stage: false });
    mark(null);
    if (dock) { delete dock.dataset.scripted; dock.dataset.ask = 'false'; dock.dataset.state = 'asleep'; }
    if (els.cue) els.cue.textContent = '';
    if (els.acts) els.acts.textContent = '';
    setLed('off', 'OFF');
  }

  function setLed(kind, word) {
    if (!led) return;
    led.classList.toggle('online', kind === 'live');
    led.classList.toggle('warn', kind === 'scripted');
    led.querySelector('span').textContent = word;
    if (app) app.dataset.coach = kind;
  }

  // the control Riff is operating gets an outline; nothing else on the instrument changes
  let marked = null;
  function mark(sel) {
    if (marked) marked.classList.remove('spot-target');
    marked = sel ? document.querySelector(sel) : null;
    if (marked) marked.classList.add('spot-target');
  }

  // Riff's body follows its voice. While a line is playing, a frame that brings no new line updates
  // the panels at once but Riff (pose, place, caption) waits until the line is finished.
  let held = null, shown = null;
  function riff(f) {
    shown = f;
    const target = f.target ? TARGET[f.target] : null;
    window.OmniRiff.coach.set({ state: f.state, target, cue: f.cue || '', mood: f.mood, stage: false });
    mark(target);
    if (dock) dock.dataset.state = f.state;
    if (els.cue) els.cue.textContent = f.cue || '';
  }
  function releaseHeld() { if (held) { const f = held; held = null; riff(f); } }

  function apply(f) {
    const prevCue = frame && frame.cue;
    frame = f; live = true;
    const newLine = !!f.cue && f.cue !== prevCue;
    if (busy() && !newLine) held = f;      // finish the sentence first
    else if (!busy() || joined) riff(f);
    else held = f;                          // a new line is queued: Riff moves when it starts
    setLed(f.scripted ? 'scripted' : 'live', f.state === 'asleep' ? 'OFF' : f.scripted ? 'SCRIPTED' : 'LIVE');
    if (dock) {
      if (f.scripted) dock.dataset.scripted = 'true'; else delete dock.dataset.scripted;
      dock.dataset.ask = String(!!f.awaiting_approval);
    }
    render(f);
    if (joined) { joined = false; spoken = f.cue || ''; }   // joined mid-line: don't start talking halfway
    else if (newLine) cueChanged(f.cue);
  }

  function render(f) {
    const a = f.awaiting_approval;
    if (els.ask) { els.ask.hidden = !a; if (a) els.askText.textContent = a.summary; }

    // the plan for this take (deepagents todos)
    if (els.plan) els.plan.innerHTML = (f.todos || []).slice(0, 6).map((t) => `<li data-s="${t.status}">${esc(t.text)}</li>`).join('');

    // what the harness is doing right now, said like a person
    if (els.acts) {
      const now = [...(f.activity || [])].reverse().find((x) => x.status === 'running' || x.status === 'waiting');
      els.acts.textContent = now && f.state !== 'idle' ? `${WHO[now.who]} · ${human(now.what)}${now.status === 'running' ? '…' : ''}` : '';
    }

    // a result: big before/after numbers
    const b = f.before_after;
    if (els.ba) {
      els.ba.hidden = !b;
      if (b) {
        const pct = (v) => Math.round(v * 100);
        els.ba.dataset.improved = String(b.improved);
        els.ba.innerHTML =
          `<div><span>LONGEST GAP</span><b>${Math.round(b.worst_gap_ms[0])}<i>→</i>${Math.round(b.worst_gap_ms[1])}<small>ms</small></b></div>`
          + `<div><span>HESITATIONS</span><b>${b.hesitations[0]}<i>→</i>${b.hesitations[1]}</b></div>`
          + `<div><span>STEADY</span><b>${pct(b.tempo_stability[0])}<i>→</i>${pct(b.tempo_stability[1])}<small>%</small></b></div>`;
      }
    }
    practice(f);
  }

  // PRACTICE: the session the coach is running. From `session` when the coach sends it; otherwise
  // the best the frame allows (the drill card), and never an invented number.
  function practice(f) {
    const ses = f.session || null, card = f.drill_card;
    const goal = (ses && ses.goal) || (card && card.passage) || null;
    if (els.goal) els.goal.textContent = goal || (f.state === 'asleep' ? 'Coach off' : 'Play a take to start');
    const drill = (ses && ses.drill) || (card ? { title: card.title, step: 1, of: 1 } : null);
    els.now.hidden = !drill;
    if (drill) {
      els.step.textContent = drill.of > 1 ? `DRILL ${drill.step}/${drill.of}` : 'DRILL';
      els.drill.textContent = drill.title;
      const at = ses && ses.attempt;
      els.attempt.textContent = at ? `TAKE ${Math.max(at.n, 1)}/${at.of}` : (card ? `${card.reps}×` : '');
    }
    const m = ses && ses.metric;
    els.metric.hidden = !m;
    if (m) {
      const last = m.history.length ? m.history[m.history.length - 1] : null;
      const pass = (v) => (m.lower_is_better ? v <= m.target : v >= m.target);
      els.mName.textContent = m.name.toUpperCase();
      els.mNow.textContent = last === null ? '--' : `${Math.round(last)} ${m.unit}`;
      els.mNow.dataset.pass = String(last !== null && pass(last));
      els.target.textContent = `goal ${m.lower_is_better ? 'under' : 'over'} ${Math.round(m.target)} ${m.unit}`;
      const top = Math.max(m.target * 1.6, ...m.history, 1);
      els.chart.innerHTML = m.history.map((v, i) =>
        `<i class="${pass(v) ? 'pass' : ''}${i === m.history.length - 1 ? ' last' : ''}" style="height:${Math.max(4, (v / top) * 100).toFixed(1)}%" title="${Math.round(v)} ${esc(m.unit)}"></i>`).join('')
        + `<span class="goal" style="bottom:${((m.target / top) * 100).toFixed(1)}%" data-label="${Math.round(m.target)} ${esc(m.unit)}"></span>`;
    }
    const next = ses && ses.next;
    els.nextRow.hidden = !next;
    if (next) els.next.textContent = next;
    const lt = ses && ses.last_time;
    els.last.hidden = !lt;
    if (lt) els.last.textContent = `Last time: ${lt}`;
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
    if (dock) delete dock.dataset.voice;
    const m = locked; locked = null;
    if (m && frame && frame.cue === m.text && !muted) enqueue(m);
  }
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);

  // Pacing: Riff never cuts itself off. A new line waits for the current one to end (the newest
  // waiting line wins). The coach paces its lines too; this is the safety net.
  // Voice source: the coach's ElevenLabs audio. The browser voice is used only when the coach has
  // no voice at all (no coach.audio seen within 2.5 s of a line), never as a warm-up.
  let hasCoachVoice = false, queued = null, locked = null;
  const busy = () => (audioEl && !audioEl.paused && !audioEl.ended) || ('speechSynthesis' in window && speechSynthesis.speaking);

  function cueChanged(text) {
    clearTimeout(fallbackTimer);
    if (muted) return;
    const ready = pendingAudio.get(text);
    if (ready) { pendingAudio.delete(text); enqueue(ready); return; }
    if (!hasCoachVoice) {
      fallbackTimer = setTimeout(() => {
        if (!hasCoachVoice && frame && frame.cue === text && spoken !== text) enqueue({ text, browser: true });
      }, 2500);
    }
  }

  function onAudio(m) {
    hasCoachVoice = true;
    clearTimeout(fallbackTimer);
    if (muted) return;
    if (!frame || frame.cue !== m.text) {          // early: keep it for when the cue lands
      pendingAudio.set(m.text, m);
      if (pendingAudio.size > 6) pendingAudio.delete(pendingAudio.keys().next().value);
      return;
    }
    if (spoken === m.text) return;
    enqueue(m);
  }

  function enqueue(item) {
    if (busy()) { queued = item; return; }
    start(item);
  }
  function start(item) {
    if (held && held.cue === item.text) releaseHeld();   // the line starts: Riff moves with it
    else if (els.cue) els.cue.textContent = item.text;
    if (item.browser) speakBrowser(item.text); else playAudio(item);
  }
  function finished() {
    talking(false);
    if (!queued) releaseHeld();                           // done talking: catch up
    const q = queued; queued = null;
    if (q && frame && frame.cue === q.text) setTimeout(() => { if (!busy()) start(q); else queued = q; }, 250);
  }

  function playAudio(m) {
    spoken = m.text;
    try {
      const bytes = Uint8Array.from(atob(m.audio_b64), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bytes], { type: m.mime }));
      const a = new Audio(url);
      audioEl = a;
      if (actx && analyser) {
        try { actx.createMediaElementSource(a).connect(analyser); } catch (e) { /* plays unanalysed */ }
      }
      a.onended = () => { URL.revokeObjectURL(url); if (audioEl === a) audioEl = null; finished(); };
      a.play().then(() => talking(true)).catch(() => {
        // the browser wants a click first: keep the line, say so, play it on the first click
        audioEl = null; spoken = ''; locked = m;
        if (dock) dock.dataset.voice = 'locked';
      });
    } catch (e) { audioEl = null; finished(); }
  }

  function speakBrowser(text) {
    if (!('speechSynthesis' in window)) return;
    spoken = text;
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02; u.pitch = 1.15;
    u.onstart = () => talking(true, true);
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

  window.OmniRiff.coachFeed = { get: () => frame, live: () => live, speaking: () => !!busy(), line: () => spoken };
  connect();
})();
