import { SourceManager, type OperatingMode } from './source-manager';
import type { StateFrame, HandFrame } from './protocol/types';
import './controls.css';
import { RemoteCoach, coachConfig, saveCoachConfig } from './coach/remote-coach';
import { DemoCoach, resetDemoMemory } from './coach/demo-coach';

type BrowserSource = {
  onState(cb: (frame: StateFrame) => void): void;
  onHand(cb: (frame: HandFrame) => void): void;
  sendControl(control: string, value?: number): boolean;
  isConnected(): boolean;
};
declare global { interface Window { OmniBrowserSource?: BrowserSource; OmniCoachSocket?: () => WebSocket; } }

const manager = new SourceManager();
let connected = false;
let coachLoaded = false;
let busy = false;
let startupRequest = 0;
let hasStarted = false;
const app = document.getElementById('app')!;
document.body.dataset.browser = 'true';
const params = new URLSearchParams(location.search);
const initial = params.get('source');
const initialMode: OperatingMode = initial === 'live' || initial === 'python' ? initial : 'simulator';

window.OmniBrowserSource = {
  onState: cb => manager.onState(cb),
  onHand: cb => manager.onHand(cb),
  isConnected: () => connected,
  sendControl(control, value) {
    if (!connected) return false;
    if ((control === 'filter' || control === 'reverb') && manager.activeMode === 'simulator') {
      manager.simulator.choreography.enabled = false;
      manager.simulator.controller.rearm();
    }
    return manager.sendControl(control, value);
  },
};

// Load existing classic layers in order; Python's original HTML stays untouched.
async function loadClassic(file: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = new URL(file, location.href).href;
    script.onload = () => resolve(); script.onerror = () => reject(new Error(`Could not load ${file}`));
    document.body.append(script);
  });
}
await loadClassic('brand.js');
(window as any).OmniBrand.mount();
// @ts-expect-error This existing classic script is loaded for its side effects.
await import('../app.js');
for (const file of ['juice.js', 'riff.js', 'stage.js', 'tape.js']) await loadClassic(file);

// Riff, the real AI coach, hosted (coach/server.py). The instrument stays in this browser.
// ?coach=demo: the pitch's scripted session in the browser (coach/demo-coach.ts), no server.
const demoCoach = params.get('coach') === 'demo' ? new DemoCoach(manager, params.get('fresh') === '1') : null;
if (params.get('fresh') === '1') {   // applied once; a later reload keeps whatever the demo remembers
  const clean = new URL(location.href); clean.searchParams.delete('fresh'); history.replaceState(null, '', clean);
}
const hosted = params.get('coach') === 'off' || demoCoach ? null : coachConfig(params);
const remoteCoach = hosted ? new RemoteCoach(hosted, manager) : null;
if (demoCoach) {
  window.OmniCoachSocket = demoCoach.socketFactory;
  // @ts-expect-error This existing classic script is loaded for its side effects.
  await import('../coach.js'); coachLoaded = true;
} else if (remoteCoach) {
  window.OmniCoachSocket = remoteCoach.socket;
  // @ts-expect-error This existing classic script is loaded for its side effects.
  await import('../coach.js'); coachLoaded = true;
}

const sourceButton = document.createElement('button');
sourceButton.type = 'button';
sourceButton.className = 'browser-source-button';
sourceButton.textContent = 'START SOUND';
sourceButton.setAttribute('aria-label', 'Sound and source settings');
document.getElementById('drawerBtn')!.before(sourceButton);

const dialog = document.createElement('dialog');
dialog.className = 'browser-settings';
dialog.setAttribute('aria-labelledby', 'browserTitle');
dialog.innerHTML = `
  <form method="dialog" class="browser-settings-heading"><h1 id="browserTitle">PLAY OMNIRIFF</h1><button aria-label="Close sound settings">×</button></form>
  <p class="browser-intro">A guitar, effects, and hand control. Right in your browser.</p>
  <label>Source<select id="browserMode"><option value="simulator">Browser simulator</option><option value="live">Live audio + camera</option></select></label>
  <p id="browserDescription"></p>
  <p id="browserStatus" role="status" aria-live="polite">Ready. Sound starts when you press Start.</p>
  <div class="browser-actions"><button type="button" id="browserStart">Start simulator</button><button type="button" id="browserMute" disabled>Mute instrument</button><button type="button" id="browserStop" disabled>Stop</button></div>
  <fieldset id="browserLive"><legend>Live audio input</legend>
    <label>Audio input<select id="browserInput"><option value="">System default</option></select></label>
    <label>Input channel<select id="browserChannel"><option value="0">Channel 1 / mono</option><option value="1">Channel 2 / instrument</option></select></label>
    <label>Camera<select id="browserCamera"><option value="">System default</option></select></label>
    <button type="button" id="browserRefresh" style="margin-top: 10px;">Refresh device list</button>
    <p>Starting requests microphone and camera access. Camera failure leaves audio and manual controls available.</p>
  </fieldset>
  <details id="browserCoach" open><summary>Riff, the AI coach <span id="coachMode"></span></summary>
    <div class="browser-actions"><button type="button" id="demoStart">Start demo session</button><button type="button" id="demoReset">Reset for the pitch</button><button type="button" id="demoLeave">Leave demo</button></div>
    <p id="demoNote">The pitch session: tell Riff you can't get your timing right, record a loop, and follow Riff. Pick the Source above first (your guitar + camera, or the simulator).</p>
    <p>Riff listens to each loop you record (and watches your hand if the camera is on), then picks one thing to practice. Your sound stays in this browser; finished loops go to the coach server.</p>
    <label>Coach server<input id="coachServer" type="url" placeholder="wss://…/coach" autocomplete="off"></label>
    <label>Team passcode<input id="coachKey" type="password" autocomplete="off"></label>
    <div class="browser-actions"><button type="button" id="coachConnect">Connect Riff</button><button type="button" id="coachForget">Disconnect Riff</button></div>
    <p id="coachStatus" role="status" aria-live="polite"></p>
  </details>
  <p class="browser-footnote">Filter, reverb and looping run in your browser. Riff, the coach, runs on the coach server.</p>`;
document.body.append(dialog);
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const mode = $<HTMLSelectElement>('browserMode');
const input = $<HTMLSelectElement>('browserInput');
const camera = $<HTMLSelectElement>('browserCamera');
const channel = $<HTMLSelectElement>('browserChannel');
const start = $<HTMLButtonElement>('browserStart');
const stop = $<HTMLButtonElement>('browserStop');
const mute = $<HTMLButtonElement>('browserMute');
const status = $('browserStatus');
mode.value = initialMode === 'live' ? 'live' : 'simulator';

function selectedMode(): OperatingMode { return mode.value as OperatingMode; }
function browserAdapter() { return manager.activeMode === 'live' ? manager.live : manager.simulator; }
function describe() {
  const selected = selectedMode();
  const liveEl = $('browserLive');
  if (liveEl) liveEl.hidden = selected !== 'live';
  $('browserDescription').textContent = {
    simulator: 'SIMULATED · A generated guitar and hand run entirely in your browser.',
    live: 'Your audio input, browser effects and webcam hand tracking. Choose the instrument channel for your interface.',
    python: 'Connect to your running local engine and coach. The Python engine owns the sound; this page is its dashboard.',
  }[selected] || '';
  start.textContent = connected && manager.activeMode === selected ? 'Keep playing' : { simulator: 'Start simulator', live: 'Start live input', python: 'Connect Python bridge' }[selected] || 'Start';
  start.disabled = busy;
  mode.disabled = busy; input.disabled = camera.disabled = channel.disabled = busy;
}
function label() {
  const active = manager.activeMode;
  if (active === 'simulator') {
    app.dataset.sim = 'browser';
    $('simChip').textContent = 'BROWSER SIM · SIMULATED';
    sourceButton.textContent = connected ? 'SIMULATED · SOUND' : 'SIMULATED · OFF';
  } else if (active === 'live') {
    delete app.dataset.sim;
    sourceButton.textContent = connected ? 'LIVE INPUT · SOUND' : 'LIVE INPUT · OFF';
  } else if (active === 'python') {
    if (params.get('sim')) {
      app.dataset.sim = params.get('sim')!;
      $('simChip').textContent = params.get('sim') === 'guitar' ? 'SIM GUITAR' : 'SIMULATED';
    } else delete app.dataset.sim;
    sourceButton.textContent = connected ? 'PYTHON · SOUND' : 'PYTHON · OFF';
  } else sourceButton.textContent = 'START SOUND';
  if (connected && active && active !== 'python' && browserAdapter().audio.isMuted) sourceButton.textContent = active === 'simulator' ? 'SIMULATED · MUTED' : 'LIVE INPUT · MUTED';
  $('pedalNext').hidden = active !== 'python' && !(remoteCoach || demoCoach);
  stop.disabled = !active && !busy;
  if (typeof loopControl !== 'undefined') loopControl.disabled = !connected;
  stop.textContent = active === 'python' ? 'Disconnect' : 'Stop';
  mute.disabled = !active || active === 'python' || !browserAdapter().audio.isRunning;
  mute.textContent = active && active !== 'python' && browserAdapter().audio.isMuted ? 'Unmute instrument' : 'Mute instrument';
}
let loopControl: HTMLButtonElement | undefined;
manager.onConnection(info => {
  connected = info.status === 'connected';
  status.dataset.kind = info.status;
  status.textContent = !hasStarted && info.status === 'stopped' ? 'Tap Start simulator to play.' : info.message || ({ starting: 'Starting…', connected: 'Connected.', disconnected: 'Disconnected. Waiting for the source.', stopped: 'Stopped. Microphone, camera and browser audio are released.', error: 'Could not start the source.' })[info.status];
  describe(); label();
});
manager.onModeChange(() => label());
loopControl = document.createElement('button');
loopControl.type = 'button'; loopControl.className = 'browser-loop-control'; loopControl.textContent = 'Record loop'; loopControl.disabled = true;
loopControl.addEventListener('click', () => window.OmniBrowserSource!.sendControl('loop'));
document.querySelector('.loop-state')!.append(loopControl);
manager.onState(frame => {
  loopControl!.disabled = !connected;
  loopControl!.textContent = { idle: 'Record loop', recording: 'Finish recording', playing: 'Clear loop' }[frame.loop.state];
  if (manager.activeMode !== 'python') {
    $('loopHint').textContent = { idle: 'Tap Record loop to begin', recording: 'Tap Finish to hear your loop', playing: 'Your loop is playing' }[frame.loop.state];
    const emptyHint = document.querySelector('#waveEmpty > span');
    if (emptyHint) emptyHint.textContent = 'Tap Record loop. Play. Tap Finish.';
  }
});

async function refreshDevices() {
  await manager.live.devices.enumerate();
  for (const [select, devices] of [[input, manager.live.devices.audioInputs], [camera, manager.live.devices.videoInputs]] as const) {
    const previous = select.value;
    select.replaceChildren(new Option('System default', ''));
    for (const device of devices) select.add(new Option(device.label, device.deviceId));
    if (Array.from(select.options).some(option => option.value === previous)) select.value = previous;
  }
}
$('browserRefresh').addEventListener('click', () => { void refreshDevices().catch(error => { status.textContent = String(error); }); });
mode.addEventListener('change', () => { describe(); });
function openSettings() {
  if (!document.getElementById('drawer')!.hidden) document.getElementById('drawerClose')!.click();
  describe(); dialog.showModal();
}
sourceButton.addEventListener('click', openSettings);
const rigSettings = document.createElement('button');
rigSettings.type = 'button'; rigSettings.className = 'browser-source-button'; rigSettings.textContent = 'SOUND & SOURCE';
rigSettings.setAttribute('aria-label', 'Sound and source settings in rig');
rigSettings.addEventListener('click', openSettings);
document.querySelector('#drawer h2')!.after(rigSettings);
start.addEventListener('click', async () => {
  if (busy) return;
  const request = ++startupRequest;
  hasStarted = true;
  busy = true; describe(); label();
  const requested = selectedMode();
  try {
    if (coachLoaded && !(remoteCoach || demoCoach) && requested !== 'python') {
      await manager.stop();
      if (request !== startupRequest) return;
      const url = new URL(location.href); url.searchParams.set('source', requested);
      url.searchParams.delete('sim');
      location.assign(url);
      return;
    }
    manager.live.devices.selectedAudioInputId = input.value || null;
    manager.live.devices.selectedVideoInputId = camera.value || null;
    manager.live.devices.selectedChannel = Number(channel.value);
    manager.simulator.gestureTarget = manager.live.gestureTarget = 'filter';
    if (requested === 'python' && remoteCoach) throw new Error('Disconnect Riff (the hosted coach) before using the Python bridge.');
    if (requested === 'python' && !coachLoaded) {
      // @ts-expect-error This existing classic script is loaded for its side effects.
      await import('../coach.js'); coachLoaded = true;
      if (request !== startupRequest) return;
    }
    if (requested === 'live' && manager.activeMode === 'live') await manager.stop();
    if (request !== startupRequest) return;
    await manager.setMode(requested);
    if (request !== startupRequest) return;
    const address = new URL(location.href); address.searchParams.set('source', requested); history.replaceState(null, '', address);
    if (requested !== 'python') {
      const adapter = browserAdapter();
      adapter.controller.rearm();
      adapter.audio.setInputChannel(Number(channel.value));
      if (requested === 'simulator') {
        manager.simulator.choreography.enabled = true;
        adapter.audio.setSynthAuto(true);
        adapter.audio.setSynthBpm(92);
      }
      if (!remoteCoach && !demoCoach) $('coachLine').textContent = 'Play freely. Open settings to connect Riff, the coach.';
    }
    dialog.close();
  } catch (error) {
    if (request !== startupRequest) return;
    status.dataset.kind = 'error';
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally { if (request === startupRequest) { busy = false; describe(); label(); } }
});
stop.addEventListener('click', async () => {
  const python = manager.activeMode === 'python' || (coachLoaded && !(remoteCoach || demoCoach)) || (busy && selectedMode() === 'python');
  ++startupRequest; busy = false; describe();
  await manager.stop(); connected = false; label();
  if (python) location.reload(); // unload the coach socket too; the Python instrument keeps playing
});
mute.addEventListener('click', () => { if (manager.activeMode !== 'python') browserAdapter().audio.toggleMute(); label(); });
const pendingControls = setInterval(() => { if (busy) label(); }, 200);
window.addEventListener('pagehide', () => { clearInterval(pendingControls); ++startupRequest; busy = false; void manager.stop(); });
const coachServer = $<HTMLInputElement>('coachServer');
const coachKey = $<HTMLInputElement>('coachKey');
coachServer.value = hosted?.url ?? '';
coachKey.value = hosted?.key ?? '';
const coachStatus = $('coachStatus');
coachStatus.textContent = demoCoach ? 'Demo coach: the pitch session, scripted in this browser.' : remoteCoach ? 'Connecting to Riff…' : 'Not connected. Ask your team for the server address and passcode.';
if (remoteCoach) remoteCoach.status = text => { coachStatus.textContent = text; };
function reloadWithCoach(url: string, key: string) {
  saveCoachConfig(url, key);
  const next = new URL(location.href);
  next.searchParams.delete('coachserver'); next.searchParams.delete('coachkey'); next.searchParams.delete('coach');
  if (manager.activeMode && manager.activeMode !== 'python') next.searchParams.set('source', manager.activeMode);
  location.assign(next);
}
$('coachConnect').addEventListener('click', () => {
  if (!/^wss?:\/\//.test(coachServer.value.trim())) { coachStatus.textContent = 'The server address starts with wss:// (or ws:// on this computer).'; return; }
  reloadWithCoach(coachServer.value, coachKey.value);
});
$('coachForget').addEventListener('click', () => reloadWithCoach('', ''));

// Demo session buttons: the same as ?coach=demo (&fresh=1), keeping the chosen source.
function reloadDemo(demo: boolean, fresh = false) {
  const next = new URL(location.href);
  for (const key of ['coach', 'fresh', 'coachserver', 'coachkey']) next.searchParams.delete(key);
  if (demo) next.searchParams.set('coach', 'demo');
  if (fresh) next.searchParams.set('fresh', '1');
  next.searchParams.set('source', selectedMode() === 'live' ? 'live' : 'simulator');
  location.assign(next);
}
$('demoStart').addEventListener('click', () => reloadDemo(true));
$('demoReset').addEventListener('click', () => { resetDemoMemory(); reloadDemo(true); });   // the pitch opening
$('demoLeave').addEventListener('click', () => reloadDemo(false));
$('demoStart').hidden = !!demoCoach;
$('demoReset').hidden = $('demoLeave').hidden = !demoCoach;
$('coachMode').textContent = demoCoach ? '· DEMO' : remoteCoach ? '· LIVE' : '';
for (const id of ['coachServer', 'coachKey', 'coachConnect', 'coachForget']) {
  const el = document.getElementById(id);
  const row = el?.closest('label') ?? el;
  if (row && demoCoach) (row as HTMLElement).hidden = true;   // the demo needs no server
}
describe();
dialog.showModal();
