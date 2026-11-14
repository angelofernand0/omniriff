// Coach column (piece F): the dashboard side of the coach feed (protocol/coach.schema.json).
//
//   ws://127.0.0.1:47803 (?coachws= overrides)   served by coach/ or by tools/sim's scripted session
//
// One column, one reading order: the session map, Riff with what it is saying (a speech bubble
// that types out in step with the voice), the deep agent at work (plan, subagents, skills, files,
// memory: only what the brain reports in todos/activity), then GOAL / NOW / GAP / NEXT (or the
// session result at DONE), then what the pedal does right now, as keycaps.
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
    map: $('steps'), line: $('coachLine'), pedal: $('pedalNext'), pedalActs: document.querySelector('#pedalNext .acts'),
    goalRow: $('pGoalRow'), goal: $('pGoal'), nowRow: $('pNow'), drill: $('pDrill'), attempt: $('pAttempt'),
    gapRow: $('pMetric'), gapName: $('pMetricName'), gap: $('pMetricNow'), target: $('pTarget'), bar: $('pChart'),
    nextRow: $('pNextRow'), next: $('pNext'), last: $('pLast'),
    agent: $('agent'), agentPlan: $('agentPlan'), agentSteps: $('agentSteps'),
    result: $('pResult'), rDrills: $('rDrills'), rName: $('rName'), rFrom: $('rFrom'), rTo: $('rTo'), rTarget: $('rTarget'),
    rSaved: $('rSaved'), rNext: $('rNext'), rNextRow: $('rNextRow'), mark: $('waveMark'),
  };
  const TARGET = { loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '#fxPower', input: '.loop-state', hand: '#handPanel' };
  const targetOf = (f) => (f.target === 'loop' && markOn ? '#waveMark' : f.target ? TARGET[f.target] || null : null);
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
    renderRows(null); renderAgent(null); renderMark(null); renderMap();
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
    const target = targetOf(f);
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
    renderMark(f); renderRows(f); renderAgent(f); renderMap();
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
    ui.nextRow.hidden = !(ses && ses.next) || !!summary;
    if (ses && ses.next) ui.next.textContent = ses.next;
    ui.last.hidden = !(ses && ses.last_time) || !!summary;
    if (ses && ses.last_time) ui.last.textContent = `Last time: ${ses.last_time}`;
    renderResult(f, !!summary);
  }

  // DONE: the session as a result, not a paragraph. Each drill, the number first → last against
  // its target, where the coach saved it, and what's next time.
  function renderResult(f, done) {
    ui.result.hidden = !done;
    if (!done) return;
    const ses = f.session, m = ses.metric;
    ui.gapRow.hidden = true; ui.nowRow.hidden = true;
    ui.rDrills.replaceChildren(...(ses.plan || []).map((d) => {
      const li = document.createElement('li');
      li.dataset.s = d.status;
      li.textContent = d.title;
      return li;
    }));
    const h = m && m.history.length ? m.history : null;
    ui.rName.parentElement.hidden = !h;
    if (h) {
      const first = h[0], last = h[h.length - 1];
      const pass = m.lower_is_better ? last <= m.target : last >= m.target;
      ui.rName.textContent = m.name === 'longest gap' ? 'GAP' : m.name.toUpperCase();
      ui.rFrom.textContent = `${Math.round(first)}`;
      ui.rTo.textContent = `${Math.round(last)} ${m.unit}`;
      ui.rTo.dataset.pass = String(pass);
      ui.rTarget.textContent = `${h.length} take${h.length === 1 ? '' : 's'} · target ${m.lower_is_better ? '<' : '>'}${Math.round(m.target)}`;
    }
    const mem = [...(f.activity || [])].reverse().find((a) => /memor/.test(a.what) && a.status === 'done');
    const path = mem && (mem.what.match(/\/\S+/) || [])[0];
    ui.rSaved.textContent = path ? `SAVED ${path}` : 'SAVED TO MEMORY';
    let next = ses.next_time || null;
    if (!next && ses.summary) { const mm = /next(?: time)?:\s*(.+)$/i.exec(ses.summary); next = mm ? mm[1] : ses.summary; }
    ui.rNextRow.hidden = !next;
    if (next) ui.rNext.textContent = next.replace(/\.$/, '');
  }

  // ---------- the deep agent at work: plan, subagents, skills, files, memory ----------
  // Only what the brain reports (todos = write_todos, activity = its tool calls). Nothing invented.
  function kindOf(a, f) {
    const w = a.what, strip = (s) => s.replace(/^(write|edit|read)(_file)?\s+/, '');
    let m;
    if (a.who !== 'coach') return ['SUBAGENT', `${a.who} · ${w}`];
    if ((m = /^open skill (.+)/.exec(w))) return ['SKILL', m[1]];
    if (/memor/.test(w)) return ['MEMORY', strip(w)];
    if (/^write_todos/.test(w)) return ['PLAN', 'write_todos'];
    if (/^write_drill_card/.test(w)) return ['FILE', (f.drill_card && f.drill_card.journal_path) || 'drill card'];
    if (/^task\b/.test(w)) return ['SUBAGENT', w];
    if (/^(write|edit|read)/.test(w) || w.includes('/')) return ['FILE', strip(w)];
    if ((m = /^rig_control\s*(.*)/.exec(w))) return ['RIG', m[1] || 'rig'];
    return ['TOOL', w];
  }
  const GLYPH = { running: '▸', done: '✓', failed: '✗', waiting: '…' };
  function renderAgent(f) {
    const acts = (f && f.activity) || [], todos = (f && f.todos) || [];
    const play = !f || f.state === 'asleep' || (f.session && f.session.mode === 'play');
    ui.agent.hidden = play || (!acts.length && !todos.length);
    if (ui.agent.hidden) return;
    const done = todos.filter((t) => t.status === 'completed').length;
    const now = todos.find((t) => t.status === 'in_progress');
    ui.agentPlan.textContent = todos.length ? `PLAN ${done}/${todos.length}${now ? ' · ' + now.text : ''}` : '';
    const max = innerHeight < 820 ? 3 : 4;
    ui.agentSteps.replaceChildren(...acts.slice(-max).map((a) => {
      const [k, text] = kindOf(a, f);
      const li = document.createElement('li');
      li.dataset.s = a.status;
      li.innerHTML = '<i></i><span></span><em></em>';
      li.children[0].textContent = k;
      li.children[1].textContent = text;
      li.children[2].textContent = a.status === 'waiting' ? 'you' : GLYPH[a.status] || '';
      return li;
    }));
  }

  // ---------- the spot in your loop the coach is talking about ----------
  let markOn = false, loopSecs = 0, lastMark = null;
  window.addEventListener('omniriff:frame', (e) => {
    const s = e.detail && e.detail.loop && e.detail.loop.seconds;
    if (typeof s === 'number' && Math.abs(s - loopSecs) > 0.01) { loopSecs = s; renderMark(frame); }
  });
  function renderMark(f) {
    const mk = f && f.mark;
    markOn = !!(mk && loopSecs > 0 && mk.start_s < loopSecs);
    if (!ui.mark) return;
    ui.mark.hidden = !markOn;
    if (!markOn) { lastMark = null; return; }
    const key = `${mk.start_s}|${mk.end_s}|${loopSecs}|${mk.label || ''}`;
    if (key === lastMark) return;
    lastMark = key;
    const a = Math.max(0, mk.start_s / loopSecs), b = Math.min(1, Math.max(mk.end_s, mk.start_s + 0.05) / loopSecs);
    ui.mark.style.left = `calc(12px + (100% - 24px) * ${a.toFixed(4)})`;
    ui.mark.style.width = `calc((100% - 24px) * ${(b - a).toFixed(4)})`;
    const tag = ui.mark.querySelector('span');
    tag.textContent = mk.label || `${Math.round((mk.end_s - mk.start_s) * 1000)} ms`;
    requestAnimationFrame(() => {            // the tag centres on the band but never leaves the waveform
      const w = ui.mark.parentElement.getBoundingClientRect(), b = ui.mark.getBoundingClientRect(), tw = tag.offsetWidth;
      const want = b.left + b.width / 2 - tw / 2;
      const left = Math.min(Math.max(want, w.left + 8), w.right - 8 - tw);
      tag.style.left = `${(left - b.left).toFixed(1)}px`;
    });
  }

  // ---------- the map and the pedal: where you are, and what one tap does now ----------
  function renderMap() {
    const f = frame, ses = f && f.session, loop = app ? app.dataset.loop : 'idle';
    const play = !f || f.state === 'asleep' || (ses && ses.mode === 'play');
    let step = 1;
    if (ses && ses.plan && ses.plan.length) { const i = ses.plan.findIndex((d) => d.status === 'now'); step = i >= 0 ? i + 2 : 4; }
    if (ui.map) { ui.map.dataset.step = String(step); ui.map.dataset.mode = play ? 'play' : 'practice'; }
    // what one press does right now, as keycaps: TAP / HOLD, or WAIT while Riff has the floor
    let acts;
    const awake = f && f.state !== 'asleep';
    if (play) {
      acts = [['TAP', loop === 'recording' ? 'close the loop' : loop === 'playing' ? 'clear the loop' : 'record a loop']];
      if (awake && loop !== 'recording') acts.push(['HOLD', 'practice with Riff', 'Y']);
    } else if (loop === 'recording') acts = [['TAP', 'stop, Riff listens']];
    else if (f && f.awaiting_approval) acts = [['TAP', 'yes, start the drill', 'Y'], ['', 'no', 'N']];
    else if (f && f.state === 'thinking') acts = [['WAIT', 'Riff is working on it']];
    else if (f && ['speaking', 'pointing'].includes(f.state)) acts = [['WAIT', 'Riff is talking']];
    else if (step === 4) acts = [['WAIT', 'Riff is wrapping up']];
    else if (step === 1) acts = [['TAP', 'record what you\u2019re working on']];
    else acts = [['TAP', 'record the drill take']];
    if (ui.pedal) {
      const key = JSON.stringify(acts);
      if (ui.pedal.dataset.acts !== key) {
        ui.pedal.dataset.acts = key;
        ui.pedal.dataset.wait = String(acts[0][0] === 'WAIT');
        ui.pedalActs.replaceChildren(...acts.map(([cap, does, kbd]) => {
          const s = document.createElement('span');
          s.className = 'act';
          s.innerHTML = '<span class="cap"></span><span class="does"></span><kbd></kbd>';
          s.children[0].textContent = cap; s.children[0].hidden = !cap;
          s.children[1].textContent = does;
          s.children[2].textContent = kbd || ''; s.children[2].hidden = !kbd;
          return s;
        }));
      }
    }
    if (ui.line) ui.line.dataset.empty = play ? (awake ? 'Free play. I\u2019ll stay quiet.' : 'Coach off. The rig plays without it.')
      : step === 1 ? 'Play me what you\u2019re working on.' : '';
  }
  if (app) new MutationObserver(renderMap).observe(app, { attributes: true, attributeFilter: ['data-loop'] });

  // ---------- voice: never cut off, never late ----------
  let actx = null, analyser = null, audioEl = null, spoken = '', hasCoachVoice = false, queued = null, locked = null, routed = false;
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
      routed = false;
      if (actx && analyser && actx.state === 'running') { try { actx.createMediaElementSource(a).connect(analyser); routed = true; } catch (e) { /* unanalysed */ } }
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
  // Riff's mouth and body follow its voice. With the real audio routed through an analyser, the
  // level is measured; otherwise (browser speech, audio started before the page was clicked) a
  // syllable rhythm is generated for as long as the voice is actually playing.
  function talking(on, browser) {
    cancelAnimationFrame(talkRaf);
    if (!on) { window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level: 0 } })); return; }
    const measured = !browser && analyser && routed;
    let t0 = performance.now(), quietFor = 0, sylAt = t0, sylLen = 190, amp = 0.8, n = 0;
    const tick = (now) => {
      let level;
      if (measured) {
        analyser.getByteTimeDomainData(buf);
        let peak = 0;
        for (let i = 0; i < buf.length; i++) peak = Math.max(peak, Math.abs(buf[i] - 128));
        level = Math.min(1, peak / 48);
      } else {
        if (now - sylAt > sylLen) {            // next syllable; a short breath every few words
          sylAt = now; n += 1;
          const breath = n % (5 + (n % 3)) === 0;
          sylLen = breath ? 260 : 150 + Math.random() * 110; amp = breath ? 0 : 0.55 + Math.random() * 0.45;
        }
        const ph = (now - sylAt) / sylLen;
        level = amp * Math.sin(Math.PI * Math.min(1, ph)) ** 0.7;
      }
      window.dispatchEvent(new CustomEvent('omniriff:voice', { detail: { level } }));
      if (!busy()) { quietFor += 1; if (quietFor > 3) { talking(false); return; } } else quietFor = 0;
      talkRaf = requestAnimationFrame(tick);
    };
    void t0;
    talkRaf = requestAnimationFrame(tick);
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
