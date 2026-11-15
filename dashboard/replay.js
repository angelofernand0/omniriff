// Browser player for a recorded coach session (coach/replay.py's JSONL: a header line, then
// {at_ms, message} lines of coach.frame and coach.audio). Used by coach.js when the page has
// ?replay=<file>. It sends nothing anywhere and cannot be talked to.
//
// Honesty rules (same contract as coach/replay.py, agreed on the board):
//  - every frame is forced to scripted=true and a "replay-" session id, so the dashboard shows REPLAY
//    for the whole playback, whatever the recording said;
//  - the file is size- and shape-checked before anything is shown; a bad file shows nothing.
'use strict';

window.OmniReplay = (() => {
  const FORMAT = 'omniriff.coach.replay';
  const MAX_EVENTS = 20000, MAX_BYTES = 64 * 1024 * 1024, PAUSE_BEFORE_LOOP_MS = 8000;

  function parse(text) {
    if (typeof text !== 'string' || text.length > MAX_BYTES) throw new Error('replay file too large');
    const lines = text.split('\n').filter((l) => l.trim());
    if (lines.length < 2 || lines.length > MAX_EVENTS + 1) throw new Error('replay file has no events or too many');
    const head = JSON.parse(lines[0]);
    if (!head || head.format !== FORMAT || head.version !== 1) throw new Error('not an omniriff coach replay');
    const events = [];
    let last = 0;
    for (const line of lines.slice(1)) {
      const e = JSON.parse(line);
      const m = e && e.message;
      if (!e || typeof e.at_ms !== 'number' || !isFinite(e.at_ms) || e.at_ms < last) throw new Error('bad event timing');
      if (!m || m.version !== 1 || (m.type !== 'coach.frame' && m.type !== 'coach.audio')) throw new Error('bad message');
      last = e.at_ms;
      events.push({ at: e.at_ms, m });
    }
    return events;
  }

  function relabel(m) {
    if (m.type !== 'coach.frame') return m;
    const id = String(m.session_id || 'session').replace(/^replay-/, '');
    return { ...m, scripted: true, session_id: ('replay-' + id).slice(0, 64), awaiting_approval: null };
  }

  function play(url, emit, opts = {}) {
    let timers = [], stopped = false;
    const clear = () => { timers.forEach(clearTimeout); timers = []; };
    fetch(url, { credentials: 'omit' })
      .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
      .then((text) => {
        const events = parse(text);
        const run = () => {
          if (stopped) return;
          clear();
          const t0 = events[0].at;
          for (const ev of events) timers.push(setTimeout(() => emit(relabel(ev.m)), ev.at - t0));
          const end = events[events.length - 1].at - t0;
          if (opts.loop !== false) timers.push(setTimeout(run, end + PAUSE_BEFORE_LOOP_MS));
        };
        run();
      })
      .catch((err) => console.warn('replay not shown:', err.message));
    return () => { stopped = true; clear(); };
  }

  return { play, parse, relabel };
})();
