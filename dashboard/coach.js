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
    you: $('youLine'), youText: $('youText'), youInput: $('youInput'), talkBtn: $('talkBtn'),
    map: $('steps'), line: $('coachLine'), pedal: $('pedalNext'), pedalActs: document.querySelector('#pedalNext .acts'),
    goalRow: $('pGoalRow'), goal: $('pGoal'), nowRow: $('pNow'), drill: $('pDrill'), attempt: $('pAttempt'),
    gapRow: $('pMetric'), gapName: $('pMetricName'), gap: $('pMetricNow'), target: $('pTarget'), bar: $('pChart'),
    nextRow: $('pNextRow'), next: $('pNext'), last: $('pLast'),
    agent: $('agent'), agentPlan: $('agentPlan'), agentSteps: $('agentSteps'),
    mark: $('waveMark'),
  };
  const TARGET = { loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '#fxPower', input: '.loop-state', hand: '#handPanel' };
  const targetOf = (f) => (f.target === 'loop' && markOn ? '#waveMark' : f.target ? TARGET[f.target] || null : null);
  // what each tool is, said by Riff while it works (the raw names are in the coach's LangSmith trace)
  const DOING = [
    [/^get_take_report/, 'Listening back to your timing'], [/^get_hand_report/, 'Watching your strumming hand'],
    [/^open skill/, 'Picking a drill'], [/^write_drill_card/, 'Setting up the drill'], [/^compare_takes/, 'Comparing with your last take'],
    [/^read.*memories/, 'Checking your last session'], [/memories/, 'Remembering this for next time'], [/^rig_control/, 'Getting the rig ready'],
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
  function show(f, secs, quiet) {            // apply a frame to Riff and the bubble; its pop-ups land with it
    const target = targetOf(f);
    const hearingYou = ['listening', 'stopping', 'typing'].includes(talk.mode);   // Riff keeps listening to you
    if (!hearingYou) window.OmniRiff.coach.set({ state: f.state, target, cue: f.cue || '', mood: f.mood, stage: false });
    mark(target);
    renderRows(f); renderAgent(f); toasts(f, !!quiet); renderMap();
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
    const newLine = !!f.cue && f.cue !== prevCue;
    renderMark(f); renderMap();
    if (!newLine || joined) { renderRows(f); renderAgent(f); }   // a new line changes the rows and steps when it starts (show)
    if (joined) { joined = false; spoken = f.cue || ''; show(f, 0, true); return; }   // joined mid-line: no voice, no typing
    if (newLine && talk.mode === 'sent') { clearTimeout(talk.hide); talk.hide = setTimeout(hideYou, 6000); talk.mode = 'idle'; }
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
  let gapKey = null;
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
      const word = m.lower_is_better ? 'under' : 'over';
      ui.target.textContent = pass ? `\u2713 ${word} ${Math.round(m.target)}` : `target ${word} ${Math.round(m.target)}`;
      ui.target.dataset.pass = String(pass);
      const first = m.history[0], top = Math.max(first, last, m.target) * 1.15;
      const pc = (v) => `${Math.min(100, (v / top) * 100).toFixed(1)}%`;
      ui.bar.style.setProperty('--now', pc(last));
      ui.bar.style.setProperty('--goal', pc(m.target));
      ui.bar.style.setProperty('--was', pc(first));
      ui.bar.dataset.moved = String(m.history.length > 1);
      // a new take that lands in the zone: the row itself lights up (feedback on the thing that changed)
      const key = `${m.history.length}|${pass}`;
      if (pass && gapKey !== null && key !== gapKey) { ui.gapRow.dataset.flash = 'false'; void ui.gapRow.offsetWidth; ui.gapRow.dataset.flash = 'true'; }
      gapKey = key;
    } else gapKey = null;
    // DONE uses the same rows (SM: the rows were clearer than a card): DONE replaces NOW, the GAP
    // row keeps its bar with where you started, NEXT TIME replaces NEXT
    const summary = ses && ses.summary;
    const done = !!summary;
    ui.nowRow.querySelector('dt').textContent = done ? 'DONE' : 'NOW';
    if (done) {
      const drills = (ses.plan || []).filter((d) => d.status === 'done').length;
      const takes = m ? m.history.length : 0;
      ui.nowRow.hidden = !(drills || takes);
      ui.drill.textContent = `✓ ${drills} drill${drills === 1 ? '' : 's'}`;
      ui.attempt.textContent = takes ? `${takes} takes` : '';
      if (last !== null && m.history.length > 1) ui.target.textContent = `was ${Math.round(m.history[0])}`;
    }
    ui.nowRow.dataset.done = String(done);
    let next = ses && ses.next;
    if (done) { next = ses.next_time || null; if (!next) { const mm = /next(?: time)?:\s*(.+)$/i.exec(summary); next = mm ? mm[1] : null; } }
    ui.nextRow.querySelector('dt').textContent = done ? 'NEXT TIME' : 'NEXT';
    ui.nextRow.hidden = !next;
    if (next) ui.next.textContent = next.replace(/\.$/, '');
    // last time: only before the first drill, where it sets the scene
    ui.last.hidden = !(ses && ses.last_time) || done || !!(ses && ses.drill);
    if (ses && ses.last_time) ui.last.textContent = `Last time: ${ses.last_time}`;
  }

  // ---------- Riff at work: the deep agent's steps in plain words, while it works ----------
  // Only what the brain reports (todos = its plan, activity = its tool calls and its helpers Ears
  // and Eyes). Nothing invented. Shown while Riff is thinking; the moments worth saying out loud
  // (goal noted, drill card ready, saved to memory) also pop up beside Riff.
  const human = (slug) => slug.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase());
  function stepOf(a) {
    const w = a.what; let m;
    if (a.who === 'ears') return ['EARS', 'Listening back to your take'];
    if (a.who === 'eyes') return ['EYES', 'Watching your strumming hand'];
    if ((m = /^open skill (.+)/.exec(w))) return ['RIFF', `Picking a drill: ${human(m[1])}`];
    if (/^read/.test(w) && /memor/.test(w)) return ['RIFF', 'Checking what you played last time'];
    if (/memor/.test(w)) return ['RIFF', 'Remembering this for next time'];
    if (/^write_todos/.test(w)) return ['RIFF', 'Making a plan'];
    if (/^write_drill_card/.test(w)) return ['RIFF', 'Writing your drill card'];
    if (/goal/.test(w)) return ['RIFF', 'Noting what you’re working on'];
    if (/^compare_takes/.test(w)) return ['RIFF', 'Comparing with your last take'];
    if (/^rig_control/.test(w)) return ['RIFF', 'Getting your rig ready'];
    if (/^task\b/.test(w)) return ['RIFF', 'Asking a helper'];
    if (/^read/.test(w)) return ['RIFF', 'Checking its notes'];
    if (/^(write|edit)/.test(w)) return ['RIFF', 'Writing it down'];
    return ['RIFF', 'Working'];
  }
  let shownSteps = new Set();
  function renderAgent(f) {
    const acts = (f && f.activity) || [], todos = (f && f.todos) || [];
    const working = !!f && f.state === 'thinking' && !(f.session && f.session.mode === 'play');
    ui.agent.hidden = !working || (!acts.length && !todos.length);
    if (ui.agent.hidden) { shownSteps = new Set(); return; }
    // the plan as pixel dots: done, now, to do
    ui.agentPlan.replaceChildren(...todos.map((t) => { const i = document.createElement('i'); i.dataset.s = t.status; i.title = t.text; return i; }));
    const seen = new Set();
    ui.agentSteps.replaceChildren(...acts.slice(innerHeight < 700 ? -2 : -3).map((a) => {
      const [who, text] = stepOf(a);
      const li = document.createElement('li');
      li.dataset.s = a.status; li.dataset.who = who.toLowerCase();
      li.innerHTML = '<i></i><span></span><em></em>';
      li.children[0].textContent = who;
      li.children[1].textContent = text;
      li.children[2].textContent = a.status === 'done' ? '✓' : a.status === 'failed' ? '✗' : '';
      if (!shownSteps.has(text)) li.dataset.new = 'true';
      seen.add(text);
      return li;
    }));
    shownSteps = seen;
  }

  // pop-ups: a moment worth saying out loud, beside Riff, for three seconds
  const toastEl = document.createElement('div');
  toastEl.className = 'riff-toast'; toastEl.hidden = true; toastEl.setAttribute('role', 'status');
  toastEl.innerHTML = '<b></b><span></span>';
  document.body.appendChild(toastEl);
  let toastSeen = null, toastQ = [], toastBusy = false, drillsDone = null;
  function toasts(f, quiet) {
    const done = new Set(((f && f.activity) || []).filter((a) => a.status === 'done').map((a) => `${a.who}|${a.what}`));
    const fresh = toastSeen === null || quiet ? [] : [...done].filter((k) => !toastSeen.has(k));
    toastSeen = done;
    const ses = f && f.session, m = ses && ses.metric;
    // a drill you just passed: the win, in green, before anything else
    const plan = (ses && ses.plan) || [];
    const passed = plan.filter((d) => d.status === 'done').length;
    if (drillsDone !== null && !quiet && passed > drillsDone && plan.length) {
      const h = m ? m.history : [];
      const line = h.length > 1 ? `${human(m.name)} ${Math.round(h[h.length - 2])} \u2192 ${Math.round(h[h.length - 1])} ${m.unit}` : plan[passed - 1].title;
      toastQ.push([`DRILL ${passed} PASSED`, line, 'ok']);
    }
    drillsDone = ses ? passed : null;
    for (const k of fresh) {
      const what = k.split('|')[1];
      if (/memor/.test(what) && !/^read/.test(what)) {
        const line = m && m.history.length > 1 ? `${ses.goal || 'Today'}: ${Math.round(m.history[0])} → ${Math.round(m.history[m.history.length - 1])} ${m.unit}`
          : 'Riff will remember this next time';
        toastQ.push(['SAVED TO MEMORY', line, 'memory']);
      } else if (/^write_drill_card/.test(what) && f.drill_card) toastQ.push(['DRILL READY', f.drill_card.title]);
      else if (/goal/.test(what) && ses && ses.goal) toastQ.push(['GOAL NOTED', ses.goal]);
    }
    if (!toastBusy) nextToast();
  }
  function nextToast() {
    const t = toastQ.shift();
    if (!t) { toastBusy = false; return; }
    toastBusy = true;
    toastEl.children[0].textContent = t[0]; toastEl.children[1].textContent = t[1];
    toastEl.dataset.kind = t[2] || '';
    toastEl.hidden = false; toastEl.dataset.on = 'false'; toastEl.dataset.leaving = 'false';
    toastEl.style.width = Math.min(340, innerWidth - 32) + 'px';
    placeToast();
    requestAnimationFrame(() => { toastEl.dataset.on = 'true'; });
    if (window.OmniRiff.coach.nod) window.OmniRiff.coach.nod();
    const follow = () => { if (!toastEl.hidden && toastEl.dataset.leaving !== 'true') { placeToast(); requestAnimationFrame(follow); } };   // it travels with Riff
    requestAnimationFrame(follow);
    setTimeout(() => leave(t[2]), 3600);
  }
  // how a pop-up leaves: a memory is filed into Riff (it shrinks into Riff's head, Riff takes it with
  // a nod); anything else lifts away. Stepped like the pixel art, under half a second.
  function leave(kind) {
    toastEl.dataset.leaving = 'true';
    const done = () => { toastEl.hidden = true; toastEl.style.transform = ''; setTimeout(nextToast, 300); };
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !toastEl.animate) { done(); return; }
    let frames, ms;
    const r = document.querySelector('.riff:not(.riff-still)');
    if (kind === 'memory' && r) {
      const a = toastEl.getBoundingClientRect(), k = r.getBoundingClientRect();
      const dx = k.left + k.width / 2 - (a.left + a.width / 2), dy = k.top + k.height * 0.35 - (a.top + a.height / 2);
      frames = [{ transform: 'none', opacity: 1 }, { transform: 'translateY(-6px) scale(1.04)', opacity: 1, offset: 0.2 },
        { transform: `translate(${dx}px, ${dy}px) scale(0.06)`, opacity: 0.6 }];
      ms = 520;
    } else {
      frames = [{ transform: 'none', opacity: 1 }, { transform: 'translateY(-10px)', opacity: 0 }];
      ms = 260;
    }
    const anim = toastEl.animate(frames, { duration: ms, easing: `steps(${kind === 'memory' ? 8 : 3})`, fill: 'forwards' });
    anim.onfinish = () => {
      if (kind === 'memory' && window.OmniRiff.coach.nod) window.OmniRiff.coach.nod();   // Riff takes it in
      anim.cancel(); done();
    };
  }
  function placeToast() {                     // beside Riff's drawn body, never over it or the top bar
    const r = document.querySelector('.riff:not(.riff-still)');
    const k = r ? r.getBoundingClientRect() : { left: innerWidth - 300, top: 120, width: 80, height: 80 };
    const pad = k.height * 0.3;              // the pixel body overhangs its box when it stretches or hops
    const b = { left: k.left - pad, right: k.left + k.width + pad, top: k.top - pad, bottom: k.top + k.height + pad };
    const w = toastEl.offsetWidth, th = toastEl.offsetHeight;
    const bar = (document.querySelector('.bar') || document.body).getBoundingClientRect().bottom;
    let x, y;
    if (b.top - th - 8 >= bar + 8) { x = (b.left + b.right) / 2 - w / 2; y = b.top - th - 8; }   // above
    else if (b.left - w - 8 >= 16) { x = b.left - w - 8; y = (b.top + b.bottom) / 2 - th / 2; }  // left
    else { x = b.right + 8; y = (b.top + b.bottom) / 2 - th / 2; }                                 // right
    toastEl.style.left = `${Math.round(Math.max(16, Math.min(innerWidth - w - 16, x)))}px`;
    toastEl.style.top = `${Math.round(Math.max(bar + 8, Math.min(innerHeight - th - 16, y)))}px`;
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
    if (f === frame && !held && f.cue && lineShown === f.cue && f.target === 'loop' && !['listening', 'stopping', 'typing'].includes(talk.mode)) {
      window.OmniRiff.coach.set({ target: '#waveMark' }); mark('#waveMark');   // stand over the spot, now that it's there
    }
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
  let mapTimer = 0;
  function renderMap() {
    const f = frame, ses = f && f.session, loop = app ? app.dataset.loop : 'idle';
    const play = !f || f.state === 'asleep' || (ses && ses.mode === 'play');
    let step = 1;
    if (ses && ses.plan && ses.plan.length) { const i = ses.plan.findIndex((d) => d.status === 'now'); step = i >= 0 ? i + 2 : 4; }
    if (ui.map) {
      const was = Number(ui.map.dataset.step);
      if (!play && step > was && f) {         // you just finished step `was`: it fills in green
        ui.map.querySelectorAll('li').forEach((li) => { li.dataset.just = String(Number(li.dataset.n) === was); });
        clearTimeout(mapTimer); mapTimer = setTimeout(() => ui.map.querySelectorAll('li').forEach((li) => { li.dataset.just = 'false'; }), 1200);
      }
      ui.map.dataset.step = String(step); ui.map.dataset.mode = play ? 'play' : 'practice';
      ui.map.dataset.done = String(!!(ses && ses.summary));
    }
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
    else if (step === 1) acts = [['TAP', 'play what you\u2019re working on']];
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
    if (ui.talkBtn) {                          // talk: any time Riff is awake and you're not recording
      ui.talkBtn.hidden = !awake || loop === 'recording' || (f && f.state === 'thinking') || !ui.agent.hidden;
      const ask = !play && step === 1 && !(ses && ses.goal);
      ui.talkBtn.dataset.ask = String(ask);   // Riff is asking what you're working on: the button leads
    }
    if (ui.line) ui.line.dataset.empty = play ? (awake ? 'Free play. I\u2019ll stay quiet.' : 'Coach off. The rig plays without it.')
      : step === 1 ? 'Play me what you\u2019re working on.' : '';
  }
  if (app) new MutationObserver(() => {
    renderMap();
    if (app.dataset.loop !== 'recording' && lastMark) { lastMark = null; renderMark(frame); }   // the tag was measured while hidden
  }).observe(app, { attributes: true, attributeFilter: ['data-loop'] });

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

  // ---------- talk to Riff: hold V (or TALK), say it, let go. Between takes, never while recording ----------
  // Chrome's speech recognition turns it into text (it needs the internet); without it, or if the
  // mic is refused, the YOU line becomes a text box. The text goes to the coach as coach.say.
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const talk = { mode: 'idle', rec: null, heard: '', hide: 0, stop: 0 };
  function hideYou() { if (talk.mode === 'idle' && ui.you) { ui.you.hidden = true; ui.you.dataset.mode = 'idle'; } }
  function riffListens(on) {
    if (on) window.OmniRiff.coach.set({ state: 'listening', target: null, mood: 'curious', you: true });
    else {
      window.OmniRiff.coach.set({ you: false });
      if (frame) window.OmniRiff.coach.set({ state: frame.state, target: targetOf(frame), mood: frame.mood });
    }
  }
  function youMode(m, text) {
    talk.mode = m;
    ui.you.hidden = false; ui.you.dataset.mode = m;
    if (text !== undefined) ui.youText.textContent = text;
    ui.youInput.hidden = m !== 'typing';
    if (dock) dock.dataset.talk = m;
  }
  function startTalk() {
    if (talk.mode === 'listening' || talk.mode === 'typing' || !ui.you) return;
    if (!frame || frame.state === 'asleep') return;
    if (app && app.dataset.loop === 'recording') return;           // never while you play
    clearTimeout(talk.hide); clearTimeout(talk.stop);
    stopVoice(); held = null;
    talk.heard = '';
    riffListens(true);
    if (!SR) { openTyping(); return; }
    youMode('listening', '');
    try {
      const rec = new SR();
      talk.rec = rec;
      rec.lang = 'en-US'; rec.interimResults = true; rec.continuous = true;
      rec.onresult = (e) => {
        talk.heard = [...e.results].map((r) => r[0].transcript).join(' ').replace(/\s+/g, ' ').trim();
        ui.youText.textContent = talk.heard;
        if (window.OmniRiff.coach.nod) window.OmniRiff.coach.nod();   // Riff nods as your words come in
      };
      rec.onerror = (e) => {
        if (['not-allowed', 'service-not-allowed', 'network', 'audio-capture', 'language-not-supported'].includes(e.error)) {
          talk.rec = null; openTyping(e.error === 'network' ? 'No internet for speech. Type it:' : 'Mic unavailable. Type it:');
        }
      };
      rec.onend = () => {
        if (talk.rec !== rec) return;
        if (talk.mode === 'listening') { try { rec.start(); } catch (err) { /* ended for good */ } }   // still holding
        else if (talk.mode === 'stopping') finishTalk();
      };
      rec.start();
    } catch (e) { openTyping(); }
  }
  function stopTalk() {
    if (talk.mode !== 'listening') return;
    talk.mode = 'stopping';
    if (talk.rec) { try { talk.rec.stop(); } catch (e) { /* gone */ } talk.stop = setTimeout(finishTalk, 1200); }
    else finishTalk();
  }
  function finishTalk() {
    if (talk.mode !== 'stopping') return;
    clearTimeout(talk.stop);
    talk.rec = null;
    const text = talk.heard.trim();
    if (text) sendSay(text, 'voice');
    else { youMode('idle', 'Didn\u2019t catch that. Hold V and try again.'); riffListens(false); talk.hide = setTimeout(hideYou, 3000); }
  }
  function openTyping(why) {
    youMode('typing', why || '');
    ui.youInput.value = talk.heard || '';
    setTimeout(() => ui.youInput.focus(), 0);
  }
  function sendSay(text, via) {
    const msg = { version: 1, type: 'coach.say', timestamp_ms: Date.now(), text: text.slice(0, 240), via };
    if (!ws || ws.readyState !== 1) { youMode('idle', 'Riff isn\u2019t connected.'); riffListens(false); talk.hide = setTimeout(hideYou, 3000); return; }
    ws.send(JSON.stringify(msg));
    youMode('sent', msg.text);
    riffListens(false);
    talk.hide = setTimeout(() => { if (talk.mode === 'sent') { talk.mode = 'idle'; hideYou(); } }, 20000);
  }
  if (ui.youInput) ui.youInput.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter' && ui.youInput.value.trim()) { e.preventDefault(); ui.youInput.blur(); sendSay(ui.youInput.value.trim(), 'typed'); }
    else if (e.key === 'Escape') { talk.mode = 'idle'; ui.youInput.blur(); hideYou(); riffListens(false); }
  });
  if (ui.talkBtn) {
    ui.talkBtn.addEventListener('pointerdown', (e) => { e.preventDefault(); ui.talkBtn.setPointerCapture(e.pointerId); startTalk(); });
    ui.talkBtn.addEventListener('pointerup', stopTalk);
    ui.talkBtn.addEventListener('pointercancel', stopTalk);
  }
  window.addEventListener('keyup', (e) => { if (e.key.toLowerCase() === 'v') stopTalk(); });

  // ---------- keys (the simulator has no pedal) ----------
  window.addEventListener('keydown', (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === 'v' && !e.repeat && !e.metaKey && !e.ctrlKey) { e.preventDefault(); startTalk(); return; }
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

  window.OmniRiff.coachFeed = { get: () => frame, speaking: () => !!busy(), line: () => spoken,
    say: (text) => sendSay(text, 'typed'), talk: () => talk.mode };
  renderMap();
  connect();
})();
