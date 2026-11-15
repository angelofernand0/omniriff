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
    line: $('coachLine'), pedal: $('pedalNext'), pedalActs: document.querySelector('#pedalNext .acts'),
    list: $('sessionList'),
    mark: $('waveMark'),
  };
  const TARGET = { loop: '.wave', filter: '#card-filter', reverb: '#card-reverb', bypass: '#fxPower', input: '.loop-state', hand: '#handPanel' };
  const targetOf = (f) => (f.target === 'loop' && markOn ? '#waveMark' : f.target ? TARGET[f.target] || null : null);
  let ws = null, retry = 0, frame = null, joined = false, muted = false;
  try { muted = localStorage.getItem('omniriff.voiceMuted') === '1'; } catch (e) { /* storage blocked */ }

  // ---------- socket ----------
  const REPLAY_URL = params.get('replay');   // ?replay=<file.jsonl>: play a recorded coach session (replay.js), no socket
  function dispatch(m) {
    if (m && m.version === 1 && m.type === 'coach.frame') onFrame(m);
    else if (m && m.version === 1 && m.type === 'coach.audio') onAudio(m);
  }
  function startReplay() {
    const s = document.createElement('script');
    s.src = new URL('replay.js', document.currentScript ? document.currentScript.src : location.href).href;
    s.onload = () => { joined = true; window.OmniReplay.play(REPLAY_URL, dispatch, { loop: params.get('replayloop') !== 'off' }); };
    s.onerror = () => console.warn('replay.js could not be loaded');
    document.body.append(s);
  }
  function connect() {
    if (REPLAY_URL) { startReplay(); return; }
    // On the website, OmniCoachSocket opens the hosted coach (browser/coach/remote-coach.ts).
    try { ws = window.OmniCoachSocket ? window.OmniCoachSocket() : new WebSocket(URL_); } catch (e) { later(); return; }
    ws.onopen = () => { retry = 0; joined = true; };
    ws.onmessage = (ev) => {
      let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      dispatch(m);
    };
    ws.onclose = () => { offline(); later(); };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* closed */ } };
  }
  function later() { setTimeout(connect, Math.min(4000, 500 * 2 ** retry++)); }
  function send(type) {
    if (!frame || isReplay(frame) || isShowcase(frame) || !frame.awaiting_approval || !ws || ws.readyState !== 1) return false;  // display modes are read-only
    ws.send(JSON.stringify({ version: 1, type, timestamp_ms: Date.now(), approval_id: frame.awaiting_approval.id }));
    return true;
  }

  function offline() {
    frame = null; held = null; clearTimeout(waitTimer);
    if (showcaseTag) showcaseTag.hidden = true;
    window.OmniRiff.coach.set({ state: 'asleep', target: null, cue: '', mood: 'sleepy', stage: false });
    mark(null); type('', 0); setLed('off', 'OFF');
    if (dock) dock.dataset.state = 'asleep';
    renderList(null); renderMark(null); renderMap();
  }
  function setLed(kind, word) {
    if (led) { led.classList.toggle('online', kind === 'live'); led.classList.toggle('warn', kind === 'scripted' || kind === 'replay'); led.querySelector('span').textContent = word; }
    if (app) app.dataset.coach = kind;
  }
  // A recorded session played back by coach/replay.py: scripted=true and a replay- session id (agreed on the board,
  // no schema change). It must say REPLAY the whole time, and nothing the player does can reach it.
  const isReplay = (f) => !!f && f.scripted === true && typeof f.session_id === 'string' && f.session_id.startsWith('replay-');
  const isShowcase = (f) => !!f && f.scripted === true && typeof f.session_id === 'string' && f.session_id.startsWith('showcase-');
  const replayTag = document.createElement('div');
  replayTag.className = 'replay-tag'; replayTag.hidden = true; replayTag.setAttribute('role', 'status');
  replayTag.textContent = 'REPLAY · a recorded session, not live';
  const coachCol = document.querySelector('.coach-col');
  if (coachCol) coachCol.prepend(replayTag);
  const showcaseTag = document.createElement('div');
  showcaseTag.className = 'replay-tag'; showcaseTag.hidden = true; showcaseTag.setAttribute('role', 'status');
  showcaseTag.textContent = 'SIMULATED · SCRIPTED EXAMPLE · NUMBERS ILLUSTRATIVE';
  if (coachCol) coachCol.prepend(showcaseTag);

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
    renderList(f); toasts(f, !!quiet); renderMap();
    if (dock) dock.dataset.state = f.state;
    if (f.cue && f.cue !== lineShown) { lineShown = f.cue; type(f.cue, secs); }
    else if (!f.cue) thinkingText(f);
  }
  function thinkingText(f) {                 // no line: Riff is not saying anything; the checklist shows what it is doing
    if (f.state === 'thinking') { lineShown = ''; type('\u2026', 0, true); }
    else if (f.state === 'listening') { lineShown = ''; type('Listening\u2026', 0, true); }
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
    const replay = isReplay(f);
    replayTag.hidden = !replay;
    showcaseTag.hidden = !isShowcase(f);
    setLed(replay ? 'replay' : f.scripted ? 'scripted' : 'live',
      f.state === 'asleep' ? 'OFF' : replay ? 'REPLAY' : f.scripted ? 'SCRIPTED' : 'LIVE');
    if (isShowcase(f)) {
      clearTimeout(waitTimer);
      held = null;
      show(f, 0, true); // silent, visual-only: no browser speech or voice clip
      renderMark(f);
      return;
    }
    const newLine = !!f.cue && f.cue !== prevCue;
    renderMark(f); renderMap();
    if (!newLine || joined) renderList(f);   // a new line changes the rows and steps when it starts (show)
    if (joined) { joined = false; spoken = f.cue || ''; show(f, 0, true); return; }   // joined mid-line: no voice, no typing
    if (newLine && talk.mode === 'sent') { clearTimeout(talk.hide); talk.hide = setTimeout(hideYou, 6000); talk.mode = 'idle'; }
    if (newLine) {
      held = f;                               // Riff waits for this line's voice, then everything starts at once
      const ready = pendingAudio.get(f.cue);
      if (ready && !muted) { pendingAudio.delete(f.cue); enqueue(ready); return; }
      clearTimeout(waitTimer);
      const isDemo = f && typeof f.session_id === 'string' && f.session_id.startsWith('demo-');
      const delay = (hasCoachVoice && !f.scripted && !isDemo) ? 1200 : 150;
      waitTimer = setTimeout(() => {          // no audio in time: say it with the browser (or just type it)
        if (frame !== f || spoken === f.cue) return;
        // the Dev demo has Riff's recorded voice for every line: never a robot voice there, just the text
        if (!muted && !isDemo && 'speechSynthesis' in window) enqueue({ text: f.cue, browser: true });
        else if (!busy()) { held = null; show(f, f.cue.split(' ').length / 2.6); }
      }, muted ? 0 : delay);
      return;
    }
    if (busy()) held = f; else show(f, 0);   // never move mid-sentence
  }
  function release(textStarting, secs) {
    const f = held; held = null;
    if (f) show(f, f.cue === textStarting ? secs : 0);
  }

  // ---------- the checklist: one list, one row structure ----------
  // Every row is  mark | LABEL | what | result.  Done rows say what happened, the row you are on says how far
  // along you are and opens to show detail (your number against its target, or what Riff is doing right now),
  // rows ahead sit back, darker. Same thing, same place, same kind of words, for every step Riff can plan.
  // Built only from the feed: session (goal, plan of drills, metric, summary, next_time, last_time) and the
  // agent's activity and todos. No session yet = the road ahead, nothing measured.
  const human = (slug) => slug.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase());
  function stepOf(a) {                          // one agent tool call, in plain words
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
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  let seenRows = new Set(), seenSteps = new Set(), doneKeys = new Set(), justUntil = new Map(), gapKey = null;

  function listModel(f) {
    let ses = f && f.session;
    const rows = [];
    const play = !!ses && ses.mode === 'play';
    let carry = null;                              // a session that is over: it becomes LAST TIME, and the next one starts fresh
    if (play) {                                    // free play: nothing is planned, so no road ahead; only what happened last time
      carry = ses.summary || ses.last_time || null;
      return carry ? [{ k: 'last', s: 'ctx', label: 'LAST TIME', text: carry }] : [];
    }
    const working = !!f && f.state === 'thinking' && !play;
    const plan = ses && ses.plan && ses.plan.length ? ses.plan : ses && ses.drill ? [{ title: ses.drill.title, status: 'now' }] : [];
    const m = ses && ses.metric, hist = m && m.history ? m.history : [];
    const summary = !!(ses && ses.summary);
    const goal = ses && ses.goal;
    const nowIdx = plan.findIndex((d) => d.status === 'now');
    const last = carry || (ses && !summary && !plan.length ? ses.last_time : null);
    if (last) rows.push({ k: 'last', s: 'ctx', label: 'LAST TIME', text: last });
    rows.push(goal ? { k: 'goal', s: 'done', label: 'GOAL', text: goal }
      : working || plan.length ? { k: 'goal', s: 'ctx', label: 'GOAL', text: 'Not set' }
      : { k: 'goal', s: 'now', label: 'GOAL', text: 'Tell Riff what you’re working on' });
    if (!plan.length) {
      rows.push(working ? { k: 'read', s: 'now', label: 'RIFF', text: 'Reading your take', work: true }
        : { k: 'drills', s: 'next', label: 'DRILLS', text: 'Riff picks these after your first take' });
    }
    plan.forEach((d, i) => {
      const now = d.status === 'now';
      const at = ses && ses.attempt;
      rows.push({
        k: `drill${i}`, s: d.status === 'done' ? 'done' : now ? 'now' : d.status === 'skipped' ? 'skip' : 'next',
        label: `DRILL ${i + 1}`, text: d.title,
        value: now && at ? `take ${Math.max(at.n, 1)} of ${at.of}` : '',
        work: now && working, metric: now && hist.length ? m : null,
      });
    });
    const wrapNow = working && plan.length && nowIdx < 0 && !summary;
    const drillsDone = plan.filter((d) => d.status === 'done').length;
    rows.push(summary
      ? { k: 'end', s: 'done', label: 'DONE', text: `${drillsDone || 1} drill${drillsDone === 1 ? '' : 's'}${hist.length ? ` · ${hist.length} take${hist.length === 1 ? '' : 's'}` : ''}`,
          value: m && hist.length > 1 ? `${Math.round(hist[0])} → ${Math.round(hist[hist.length - 1])} ${m.unit}` : '' }
      : { k: 'end', s: wrapNow ? 'now' : 'next', label: 'DONE', text: 'Result and what\u2019s next', work: wrapNow });
    if (summary) {
      let nt = ses.next_time;
      if (!nt) { const mm = /next(?: time)?:\s*(.+)$/i.exec(ses.summary); nt = mm ? mm[1] : null; }
      if (nt) rows.push({ k: 'nexttime', s: 'ctx', label: 'NEXT TIME', text: nt.replace(/\.$/, '') });
    }
    return rows;
  }

  function workNode(f) {                         // what Riff is doing right now, from the feed's activity and plan
    const acts = (f.activity || []).slice(-(innerHeight < 700 ? 3 : 4)), todos = f.todos || [];
    const box = el('div', 'work');
    const head = el('div', 'work-head');
    head.append(el('b', null, 'RIFF’S CHECKS'));
    if (todos.length) {
      const dots = el('span', 'plan-dots');
      todos.forEach((t) => { const i = document.createElement('i'); i.dataset.s = t.status; i.title = t.text; dots.append(i); });
      head.append(dots, el('small', null, `${todos.filter((t) => t.status === 'completed').length} of ${todos.length}`));
    }
    box.append(head);
    const ol = el('ol');
    const seen = new Set();
    acts.forEach((a) => {
      const [who, text] = stepOf(a);
      const li = el('li'); li.dataset.s = a.status; li.dataset.who = who.toLowerCase();
      li.append(el('i', null, who), el('span', null, text), el('em', null, a.status === 'done' ? '✓' : a.status === 'failed' ? '✗' : ''));
      if (!seenSteps.has(text)) li.dataset.new = 'true';
      seen.add(text); ol.append(li);
    });
    seenSteps = seen;
    box.append(ol);
    return box;
  }

  function metricNode(m) {                       // your number against its target, with where you started
    const hist = m.history, last = hist[hist.length - 1];
    const pass = m.lower_is_better ? last <= m.target : last >= m.target;
    const word = m.lower_is_better ? 'under' : 'over';
    const box = el('div', 'metric'); box.dataset.pass = String(pass);
    const head = el('div', 'metric-head');
    head.append(el('em', null, cap(m.name)), el('b', null, `${Math.round(last)} ${m.unit}`),
      el('small', null, pass ? `✓ ${word} ${Math.round(m.target)}` : `target ${word} ${Math.round(m.target)}`));
    const bar = el('span', 'gap-bar');
    ['zone', 'trail', 'was', 'now'].forEach((c) => bar.append(el('i', c)));
    const first = hist[0], top = Math.max(first, last, m.target) * 1.15;
    const pc = (v) => `${Math.min(100, (v / top) * 100).toFixed(1)}%`;
    bar.style.setProperty('--now', pc(last)); bar.style.setProperty('--goal', pc(m.target)); bar.style.setProperty('--was', pc(first));
    bar.dataset.moved = String(hist.length > 1);
    const key = `${hist.length}|${pass}`;          // a new take that lands in the zone: the block lights up
    if (pass && gapKey !== null && key !== gapKey) box.dataset.flash = 'true';
    gapKey = key;
    box.append(head, bar);
    return box;
  }

  function renderList(f) {
    const L = ui.list;
    if (!L) return;
    const show = !!f && f.state !== 'asleep';
    const rows = show ? listModel(f) : [];
    L.hidden = !rows.length;
    if (!rows.length) { seenRows = new Set(); seenSteps = new Set(); doneKeys = new Set(); gapKey = null; return; }
    const now = performance.now(), keys = new Set(), done = new Set();
    if (!rows.some((r) => r.metric)) gapKey = null;
    L.replaceChildren(...rows.map((r) => {
      keys.add(r.k); if (r.s === 'done') done.add(r.k);
      if (r.s === 'done' && doneKeys.size && !doneKeys.has(r.k) && seenRows.has(r.k)) justUntil.set(r.k, now + 1200);   // you just finished this step
      const li = el('li', 'step'); li.dataset.s = r.s; li.dataset.k = r.k;
      if (!seenRows.has(r.k) && seenRows.size) li.dataset.new = 'true';
      if ((justUntil.get(r.k) || 0) > now) li.dataset.just = 'true';
      const body = el('div', 'body');
      body.append(el('span', 'what', r.text), el('em', 'val', r.value || ''));
      li.append(el('i', 'mark'), el('b', 'lab', r.label), body);
      if (r.work || r.metric) {
        const d = el('div', 'detail');
        if (r.work) d.append(workNode(f));
        if (r.metric) d.append(metricNode(r.metric));
        li.append(d);
      }
      return li;
    }));
    seenRows = keys; doneKeys = done;
    const cur = L.querySelector('.step[data-s="now"]');   // keep the row you are on in view when the list is long
    if (cur) {
      const top = cur.offsetTop - L.offsetTop, h = cur.offsetHeight;
      if (top < L.scrollTop) L.scrollTop = top; else if (top + h > L.scrollTop + L.clientHeight) L.scrollTop = top + h - L.clientHeight;
    } else L.scrollTop = 0;
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
    ui.mark.style.left = `calc(var(--wave-left, 12px) + (100% - var(--wave-left, 12px) - 12px) * ${a.toFixed(4)})`;
    ui.mark.style.width = `calc((100% - var(--wave-left, 12px) - 12px) * ${(b - a).toFixed(4)})`;
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
    // what one press does right now, as keycaps: TAP / HOLD, or WAIT while Riff has the floor
    let acts;
    const awake = f && f.state !== 'asleep';
    if (isShowcase(f)) acts = [['AUTO', 'scripted practice loop']];
    else if (play) {
      acts = [['TAP', loop === 'recording' ? 'close the loop' : loop === 'playing' ? 'clear the loop' : 'record a loop']];
      if (awake && loop !== 'recording') acts.push(['HOLD', 'practice with Riff', 'Y']);
    } else if (loop === 'recording') acts = [['TAP', 'stop, Riff listens']];
    else if (f && f.awaiting_approval) acts = [['HOLD', 'approve the drill', window.OmniCoachSocket ? 'Y \u00b7 THUMB UP' : 'Y'], ['', 'no', 'N']];   // website: a held thumbs-up approves too
    else if (f && f.state === 'thinking') acts = [['WAIT', 'Riff is working on it']];
    else if (f && (busy() || (held && held === f && held.cue))) acts = [['WAIT', 'Riff is talking']];   // the real voice, not the frame's state: when Riff is done, you can tap
    else if (step === 4) acts = [['WAIT', 'Riff is wrapping up']];
    else if (step === 1) acts = [['TAP', 'play what you\u2019re working on']];
    else acts = [['TAP', loop === 'playing' ? 'clear, then record a fresh take' : 'record a fresh drill take']];
    // a plugged-in pedal talks with a double tap (browser/adapters/pedal-taps.ts)
    if (awake && loop !== 'recording' && !(f && f.state === 'thinking') && window.OmniRiff.pedal && window.OmniRiff.pedal.connected()) acts.push(['TAP\u00d72', 'talk to Riff', 'V']);
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
      ui.talkBtn.hidden = isShowcase(f) || !awake || loop === 'recording' || (f && f.state === 'thinking');
      const ask = !play && step === 1 && !(ses && ses.goal);
      ui.talkBtn.dataset.ask = String(ask);   // Riff is asking what you're working on: the button leads
      const key = $('talkKey'), pedalOn = !!(window.OmniRiff.pedal && window.OmniRiff.pedal.connected());
      if (key) key.textContent = pedalOn ? 'TAP\u00d72' : 'HOLD V';
      ui.talkBtn.title = pedalOn ? 'Double-tap the pedal (or hold V) to talk to Riff' : 'Hold to talk to Riff (V)';
    }
    if (ui.line) ui.line.dataset.empty = play ? (awake ? 'Free play. I\u2019ll stay quiet.' : 'Riff is asleep. You can still play.')
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
    renderMap();                              // the pedal hint follows the voice: WAIT while talking, TAP when done
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
  // Hands-free (the pedal: double tap) has no key to let go of, so it sends after a pause in
  // your speech, or when you tap again. The words come from the voice mic (the laptop's own mic
  // by default, never the guitar input); see browser/audio/voice-mic.ts.
  const talk = { mode: 'idle', rec: null, heard: '', hide: 0, stop: 0, handsFree: false, quiet: 0, track: null, id: 0 };
  const HANDS_FREE_PAUSE_MS = 1600, HANDS_FREE_FIRST_WORD_MS = 7000, HANDS_FREE_MAX_MS = 20000;
  function releaseTrack() { if (talk.track) { try { talk.track.stop(); } catch (e) { /* gone */ } talk.track = null; } }
  function armQuiet(ms) {
    clearTimeout(talk.quiet);
    if (talk.handsFree) talk.quiet = setTimeout(stopTalk, ms);
  }
  function canTalk() {
    return !!ui.you && !!frame && !isShowcase(frame) && frame.state !== 'asleep' && !(app && app.dataset.loop === 'recording')
      && talk.mode !== 'listening' && talk.mode !== 'typing';
  }
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
  function startTalk(handsFree) {
    if (talk.mode === 'listening' || talk.mode === 'typing' || !ui.you) return;
    if (!frame || frame.state === 'asleep') return;
    if (app && app.dataset.loop === 'recording') return;           // never while you play
    clearTimeout(talk.hide); clearTimeout(talk.stop); clearTimeout(talk.quiet);
    talk.handsFree = !!handsFree;
    const id = ++talk.id;
    stopVoice(); held = null;
    talk.heard = '';
    riffListens(true);
    if (!SR) { openTyping(); return; }
    youMode('listening', talk.handsFree ? 'Listening\u2026 pause or tap the pedal to send.' : '');
    if (talk.handsFree) armQuiet(HANDS_FREE_FIRST_WORD_MS);
    const mic = window.OmniRiff.voiceMic;
    if (mic && mic.track) {
      mic.track().then((track) => {
        if (id !== talk.id || talk.mode !== 'listening') { if (track) track.stop(); return; }
        talk.track = track; listen(id);
      }, () => { if (id === talk.id && talk.mode === 'listening') listen(id); });
    } else listen(id);
  }
  function listen(id) {
    if (id !== talk.id) return;
    try {
      const rec = new SR();
      talk.rec = rec;
      rec.lang = 'en-US'; rec.interimResults = true; rec.continuous = true;
      rec.onresult = (e) => {
        talk.heard = [...e.results].map((r) => r[0].transcript).join(' ').replace(/\s+/g, ' ').trim();
        ui.youText.textContent = talk.heard;
        if (window.OmniRiff.coach.nod) window.OmniRiff.coach.nod();   // Riff nods as your words come in
        if (talk.heard) armQuiet(HANDS_FREE_PAUSE_MS);
      };
      rec.onerror = (e) => {
        if (['not-allowed', 'service-not-allowed', 'network', 'audio-capture', 'language-not-supported'].includes(e.error)) {
          talk.rec = null; clearTimeout(talk.quiet); releaseTrack(); openTyping(e.error === 'network' ? 'No internet for speech. Type it:' : 'Mic unavailable. Type it:');
        }
      };
      rec.onend = () => {
        if (talk.rec !== rec) return;
        if (talk.mode === 'listening') { try { startRec(rec); } catch (err) { /* ended for good */ } }   // still holding
        else if (talk.mode === 'stopping') finishTalk();
      };
      startRec(rec);
    } catch (e) { releaseTrack(); openTyping(); }
  }
  // Chrome 135+ takes the mic track; older browsers ignore the argument and use the default mic.
  function startRec(rec) {
    if (talk.track && talk.track.readyState === 'live') rec.start(talk.track); else rec.start();
  }
  function stopTalk() {
    if (talk.mode !== 'listening') return;
    clearTimeout(talk.quiet);
    talk.mode = 'stopping';
    if (talk.rec) { try { talk.rec.stop(); } catch (e) { /* gone */ } talk.stop = setTimeout(finishTalk, 1200); }
    else finishTalk();
  }
  function finishTalk() {
    if (talk.mode !== 'stopping') return;
    clearTimeout(talk.stop);
    talk.rec = null;
    releaseTrack();
    const text = talk.heard.trim();
    if (text) sendSay(text, 'voice');
    else { youMode('idle', talk.handsFree ? 'Didn\u2019t catch that. Double-tap the pedal and try again.' : 'Didn\u2019t catch that. Hold V and try again.'); riffListens(false); talk.hide = setTimeout(hideYou, 3000); }
  }
  function openTyping(why) {
    youMode('typing', why || '');
    ui.youInput.value = talk.heard || '';
    setTimeout(() => ui.youInput.focus(), 0);
  }
  function sendSay(text, via) {
    const msg = { version: 1, type: 'coach.say', timestamp_ms: Date.now(), text: text.slice(0, 240), via };
    if (isReplay(frame) || isShowcase(frame)) { youMode('idle', 'This is a scripted display. Riff can\u2019t hear you.'); riffListens(false); talk.hide = setTimeout(hideYou, 3000); return; }
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
    ui.talkBtn.addEventListener('pointerdown', (e) => { e.preventDefault(); ui.talkBtn.setPointerCapture(e.pointerId); startTalk(false); });
    ui.talkBtn.addEventListener('pointerup', stopTalk);
    ui.talkBtn.addEventListener('pointercancel', stopTalk);
  }
  window.addEventListener('keyup', (e) => { if (e.key.toLowerCase() === 'v') stopTalk(); });

  // ---------- keys (the simulator has no pedal) ----------
  window.addEventListener('keydown', (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === 'v' && !e.repeat && !e.metaKey && !e.ctrlKey) { e.preventDefault(); startTalk(false); return; }
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
    say: (text) => sendSay(text, 'typed'), talk: () => talk.mode,
    // the pedal (browser/adapters/pedal-taps.ts): double tap listens, a tap while listening sends
    canTalk, listen: () => startTalk(true), sendNow: stopTalk };
  renderMap();
  connect();
})();
