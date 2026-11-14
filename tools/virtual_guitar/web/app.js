(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let state = null, ready = false, lastVolume = 0.35, commandCount = 0;
  let webcamStream = null, cameraOpening = false, sendingFrame = false;
  const canvas = document.createElement('canvas');
  canvas.width = 640; canvas.height = 480;
  let tail = Promise.resolve();
  const pending = new Map();
  const percent = value => `${Math.round(value * 100)}%`;
  const clock = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  const text = (id, value) => { if ($(id).textContent !== value) $(id).textContent = value; };
  function enabled(value) {
    if (ready === value) return;
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
      return true;
    }).catch(error => { $('error').textContent = error.message; return false; })
      .finally(() => { commandCount--; });
    return tail;
  }
  async function poll() {
    try {
      const response = await fetch('/api/state', {signal: AbortSignal.timeout(2000)});
      if (!response.ok) throw new Error('Demo unavailable');
      state = await response.json();
      const engine = state.engine;
      if (!ready) $('error').textContent = '';
      enabled(true);
      $('health').textContent = state.headless ? 'HEADLESS · NO SPEAKER OUTPUT' : 'LIVE · LAPTOP AUDIO';
      $('source').textContent = `${state.label} · repeating ${state.seconds.toFixed(1)}s phrase · real filter, reverb and looper`;
      text('playing', state.playing ? 'Pause guitar' : 'Resume guitar');
      text('loop', {idle: 'Record loop', recording: 'Play loop', playing: 'Clear loop'}[engine.loop.state]);
      $('loop').classList.toggle('active', engine.loop.state !== 'idle');
      text('bypass', engine.bypass ? 'Enable FX' : 'Bypass FX');
      $('bypass').classList.toggle('active', engine.bypass);
      text('mute', state.volume > 0 ? 'Mute' : 'Unmute');
      $('position').textContent = `${clock(state.position)} / ${clock(state.seconds)}`;
      const camera = state.camera;
      text('cameraHint', camera.control === 'scene' ? 'Advanced Scene Morph: open hand, then pinch and move vertically to blend filter and reverb. Release holds the sound. Light the hand from the front.' : 'Open hand, then pinch to grab the current filter. Drag up for brighter, down for darker; release holds. At 100%, move down first. Light the hand from the front.');
      text('cameraButton', webcamStream ? 'Stop webcam' : 'Start webcam');
      $('cameraButton').disabled = cameraOpening || !camera.model_ready || camera.status === 'stopping';
      text('cameraStatus', !camera.model_ready ? 'Hand model missing · see setup' : cameraOpening ? 'Waiting for webcam permission…' :
        camera.error ? camera.error : webcamStream ?
          `${camera.status === 'running' ? 'Tracking' : 'Waiting for hand'} · ${camera.frames} frames · ${camera.events} gesture controls` : 'Camera off');
      for (const name of ['volume', 'filter', 'reverb']) {
        const value = name === 'volume' ? state.volume : engine[name].target;
        if (document.activeElement !== $(name) && !pending.has(name) && !commandCount) {
          $(name).value = value;
          $(name + 'Value').textContent = percent(value);
        }
      }
      if (!$('dashboard').getAttribute('src')) {
        const url = `/dashboard/?ws=${encodeURIComponent(`ws://127.0.0.1:${state.ws_port}`)}&hand=${encodeURIComponent(`ws://127.0.0.1:${state.hand_port}`)}&sim=guitar`;
        $('dashboard').src = url;
        $('dashboardLink').href = url;
      }
    } catch (_) {
      enabled(false);
      pending.clear();
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
  function stopMedia() {
    if (webcamStream) webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
    $('webcam').srcObject = null;
    $('webcam').hidden = true;
  }
  async function sendFrame() {
    if (!webcamStream || sendingFrame) return;
    sendingFrame = true;
    try {
      if ($('webcam').readyState >= 2) {
        canvas.getContext('2d').drawImage($('webcam'), 0, 0, 640, 480);
        const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.65));
        if (blob) {
          const response = await fetch('/api/frame', {method: 'POST', headers: {'Content-Type':'image/jpeg'},
            body: blob, signal: AbortSignal.timeout(1500)});
          if (!response.ok) throw new Error((await response.json()).error || 'Camera frame rejected');
        }
      }
    } catch (error) { $('error').textContent = error.message; }
    finally { sendingFrame = false; if (webcamStream) setTimeout(sendFrame, 100); }
  }
  $('cameraButton').onclick = async () => {
    if (webcamStream) { stopMedia(); await command('camera_stop'); return; }
    if (cameraOpening) return;
    cameraOpening = true;
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser cannot open a webcam on localhost. Try Chrome.');
      const request = navigator.mediaDevices.getUserMedia({video:{width:640,height:480}, audio:false});
      let timedOut = false;
      request.then(stream => { if (timedOut) stream.getTracks().forEach(track => track.stop()); }, () => {});
      let timer;
      try {
        webcamStream = await Promise.race([request, new Promise((_, reject) => {
          timer = setTimeout(() => { timedOut = true; reject(new Error('Permission did not complete. Open this URL in Chrome and allow camera access.')); }, 12000);
        })]);
      } finally { clearTimeout(timer); }
      $('webcam').srcObject = webcamStream;
      $('webcam').hidden = false;
      await $('webcam').play();
      if (!await command('camera_start')) throw new Error('Tracker could not start');
      sendFrame();
    } catch (error) { stopMedia(); $('error').textContent = `Webcam: ${error.message}`; }
    finally { cameraOpening = false; }
  };
  addEventListener('pagehide', stopMedia);
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
