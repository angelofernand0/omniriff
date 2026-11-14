(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let state = null, ready = false, lastVolume = 0.35, commandCount = 0;
  let tail = Promise.resolve();
  const pending = new Map();
  const percent = value => `${Math.round(value * 100)}%`;
  const clock = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  function enabled(value) {
    ready = value;
    document.querySelectorAll('button,input').forEach(el => el.disabled = !value);
  }
  function command(action, value) {
    commandCount++;
    // Preserve action order even when two buttons are clicked quickly.
    tail = tail.then(async () => {
      const response = await fetch('/api/command', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action, value}), signal: AbortSignal.timeout(3000)
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Command failed');
      $('error').textContent = '';
    }).catch(error => { $('error').textContent = error.message; })
      .finally(() => { commandCount--; });
    return tail;
  }
  async function poll() {
    try {
      const response = await fetch('/api/state', {signal: AbortSignal.timeout(2000)});
      if (!response.ok) throw new Error('Demo unavailable');
      state = await response.json();
      const engine = state.engine;
      enabled(true);
      $('health').textContent = state.headless ? 'HEADLESS · NO SPEAKER OUTPUT' : 'LIVE · LAPTOP AUDIO';
      $('source').textContent = `${state.label} · repeating ${state.seconds.toFixed(1)}s phrase · real filter, reverb and looper`;
      $('playing').textContent = state.playing ? 'Pause guitar' : 'Resume guitar';
      $('loop').textContent = {idle: 'Record loop', recording: 'Play loop', playing: 'Clear loop'}[engine.loop.state];
      $('loop').classList.toggle('active', engine.loop.state !== 'idle');
      $('bypass').textContent = engine.bypass ? 'Enable FX' : 'Bypass FX';
      $('bypass').classList.toggle('active', engine.bypass);
      $('mute').textContent = state.volume > 0 ? 'Mute' : 'Unmute';
      $('position').textContent = `${clock(state.position)} / ${clock(state.seconds)}`;
      for (const name of ['volume', 'filter', 'reverb']) {
        const value = name === 'volume' ? state.volume : engine[name].target;
        if (document.activeElement !== $(name) && !pending.has(name) && !commandCount) {
          $(name).value = value;
          $(name + 'Value').textContent = percent(value);
        }
      }
      if (!$('dashboard').getAttribute('src')) {
        const url = `/dashboard/?ws=${encodeURIComponent(`ws://127.0.0.1:${state.ws_port}`)}`;
        $('dashboard').src = url;
        $('dashboardLink').href = url;
      }
    } catch (_) {
      enabled(false);
      $('health').textContent = 'OFFLINE · DEMO STOPPED';
      $('error').textContent = 'The local demo is unavailable. Check its terminal and restart the live launcher.';
    } finally { setTimeout(poll, 250); }
  }
  $('playing').onclick = () => command('playing', !state.playing);
  $('mute').onclick = () => {
    if (state.volume > 0) { lastVolume = state.volume; command('volume', 0); }
    else command('volume', lastVolume || 0.35);
  };
  $('loop').onclick = () => command('loop');
  $('bypass').onclick = () => command('bypass');
  document.querySelectorAll('[data-preset]').forEach(button => {
    button.onclick = () => command('preset', button.dataset.preset);
  });
  for (const name of ['volume', 'filter', 'reverb']) {
    $(name).oninput = () => {
      const value = Number($(name).value);
      $(name + 'Value').textContent = percent(value);
      pending.set(name, value);
    };
  }
  // Coalesce drag input; never queue every browser pointer event.
  setInterval(() => {
    if (!ready || commandCount) return;
    for (const [name, value] of pending) { pending.delete(name); command(name, value); }
  }, 60);
  document.addEventListener('keydown', event => {
    if (!ready || event.repeat || /INPUT|BUTTON|TEXTAREA|SELECT/.test(event.target.tagName)) return;
    const button = {' ': 'playing', l: 'loop', b: 'bypass'}[event.key.toLowerCase()];
    if (button) { event.preventDefault(); $(button).click(); }
  });
  poll();
})();
