import { SourceManager, type OperatingMode } from './source-manager';
import type { StateFrame, HandFrame } from './protocol/types';
import './controls.css';

type BrowserSource = {
  onState(cb: (frame: StateFrame) => void): void;
  onHand(cb: (frame: HandFrame) => void): void;
  sendControl(control: string, value?: number): boolean;
  isConnected(): boolean;
};
declare global { interface Window { OmniBrowserSource?: BrowserSource; } }

const manager = new SourceManager();
let connected = false;
let coachLoaded = false;
let busy = false;
const app = document.getElementById('app')!;
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
      autoHand.checked = false;
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

const sourceButton = document.createElement('button');
sourceButton.type = 'button';
sourceButton.className = 'browser-source-button';
sourceButton.textContent = 'START SOUND';
sourceButton.setAttribute('aria-label', 'Sound and source settings');
document.querySelector('.bar')!.insertBefore(sourceButton, document.getElementById('drawerBtn'));

const dialog = document.createElement('dialog');
dialog.className = 'browser-settings';
dialog.setAttribute('aria-labelledby', 'browserTitle');
dialog.innerHTML = `
  <form method="dialog" class="browser-settings-heading"><h1 id="browserTitle">YOUR SIGNAL CHAIN</h1><button aria-label="Close sound settings">×</button></form>
  <p class="browser-intro">Play in your browser, or connect your local rig.</p>
  <label>Source<select id="browserMode"><option value="simulator">Browser simulator</option><option value="live">Live audio + camera</option><option value="python">Python bridge</option></select></label>
  <p id="browserDescription"></p>
  <fieldset id="browserLive"><legend>Live input</legend>
    <button type="button" id="browserRefresh">Refresh device list</button>
    <label>Audio input<select id="browserInput"><option value="">System default</option></select></label>
    <label>Input channel<select id="browserChannel"><option value="0">Channel 1 / mono</option><option value="1">Channel 2 / instrument</option></select></label>
    <label>Camera<select id="browserCamera"><option value="">System default</option></select></label>
    <p>Starting requests microphone and camera access. Camera failure leaves the audio and manual controls available.</p>
  </fieldset>
  <fieldset id="browserSim"><legend>Simulated guitar + hand</legend>
    <label class="browser-check"><input id="browserAutoHand" type="checkbox" checked>Automatic hand demo</label>
    <label class="browser-check"><input id="browserAutoGuitar" type="checkbox" checked>Play a riff</label>
    <label>Tempo <input id="browserBpm" type="number" min="40" max="240" step="1" value="92"></label>
    <button type="button" id="browserPluck">Pluck guitar</button>
  </fieldset>
  <fieldset id="browserGesture"><legend>Hand control</legend>
    <label>Pinch controls<select id="browserTarget"><option value="filter">Filter</option><option value="reverb">Reverb</option><option value="scene">Scene morph</option></select></label>
    <label id="browserSceneLabel">Scene<select id="browserScene"></select></label>
    <p>Open your hand to arm. Pinch and move up or down. Release to hold the sound. Open RIG to see the hand view and manual controls.</p>
  </fieldset>
  <p id="browserStatus" role="status" aria-live="polite">Ready. Sound starts when you press Start.</p>
  <div class="browser-actions"><button type="button" id="browserStart">Start simulator</button><button type="button" id="browserMute" disabled>Mute instrument</button><button type="button" id="browserStop" disabled>Stop</button></div>
  <p class="browser-footnote">Browser modes run filter, reverb and looping locally. Live coaching is available through the Python bridge.</p>`;
document.body.append(dialog);
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const mode = $<HTMLSelectElement>('browserMode');
const autoHand = $<HTMLInputElement>('browserAutoHand');
const autoGuitar = $<HTMLInputElement>('browserAutoGuitar');
const bpm = $<HTMLInputElement>('browserBpm');
const target = $<HTMLSelectElement>('browserTarget');
const scene = $<HTMLSelectElement>('browserScene');
const input = $<HTMLSelectElement>('browserInput');
const camera = $<HTMLSelectElement>('browserCamera');
const channel = $<HTMLSelectElement>('browserChannel');
const start = $<HTMLButtonElement>('browserStart');
const stop = $<HTMLButtonElement>('browserStop');
const mute = $<HTMLButtonElement>('browserMute');
const status = $('browserStatus');
mode.value = initialMode;
for (const [i, item] of manager.simulator.setlist.scenes.entries()) scene.add(new Option(item.name, String(i)));

function selectedMode(): OperatingMode { return mode.value as OperatingMode; }
function browserAdapter() { return manager.activeMode === 'live' ? manager.live : manager.simulator; }
function describe() {
  const selected = selectedMode();
  $('browserLive').hidden = selected !== 'live';
  $('browserSim').hidden = selected !== 'simulator';
  $('browserGesture').hidden = selected === 'python';
  $('browserSceneLabel').hidden = target.value !== 'scene';
  $('browserDescription').textContent = {
    simulator: 'SIMULATED · Synthetic guitar and a generated hand, through real browser effects. No microphone, camera or AI calls.',
    live: 'Your audio input, browser effects and webcam hand tracking. Choose the instrument channel for your interface.',
    python: 'Connect to your running local engine and coach. The Python engine owns the sound; this page is its dashboard.',
  }[selected];
  start.textContent = { simulator: 'Start simulator', live: 'Start live input', python: 'Connect Python bridge' }[selected];
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
    if (params.get('sim')) app.dataset.sim = params.get('sim')!; else delete app.dataset.sim;
    sourceButton.textContent = connected ? 'PYTHON · SOUND' : 'PYTHON · OFF';
  } else sourceButton.textContent = 'START SOUND';
  stop.disabled = !active || busy;
  stop.textContent = active === 'python' ? 'Disconnect' : 'Stop';
  mute.disabled = !active || active === 'python' || busy;
  mute.textContent = active && active !== 'python' && browserAdapter().audio.isMuted ? 'Unmute instrument' : 'Mute instrument';
}
manager.onConnection(info => {
  connected = info.status === 'connected';
  status.textContent = info.message || ({ starting: 'Starting…', connected: 'Connected.', disconnected: 'Disconnected. Waiting for the source.', stopped: 'Stopped. Microphone, camera and browser audio are released.', error: 'Could not start the source.' })[info.status];
  label();
});
manager.onModeChange(() => label());

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
mode.addEventListener('change', describe);
sourceButton.addEventListener('click', () => { describe(); dialog.showModal(); });
start.addEventListener('click', async () => {
  if (busy) return;
  busy = true; describe(); label();
  const requested = selectedMode();
  try {
    if (coachLoaded && requested !== 'python') {
      await manager.stop();
      const url = new URL(location.href); url.searchParams.set('source', requested);
      url.searchParams.delete('sim');
      location.assign(url);
      return;
    }
    manager.live.devices.selectedAudioInputId = input.value || null;
    manager.live.devices.selectedVideoInputId = camera.value || null;
    manager.live.devices.selectedChannel = Number(channel.value);
    manager.simulator.gestureTarget = manager.live.gestureTarget = target.value as 'filter' | 'reverb' | 'scene';
    if (requested === 'python' && !coachLoaded) {
      // @ts-expect-error This existing classic script is loaded for its side effects.
      await import('../coach.js'); coachLoaded = true;
    }
    if (requested === 'live' && manager.activeMode === 'live') await manager.stop();
    await manager.setMode(requested);
    if (requested !== 'python') {
      const adapter = browserAdapter();
      adapter.setlist.select(Number(scene.value)); adapter.controller.rearm();
      adapter.audio.setInputChannel(Number(channel.value));
      if (requested === 'simulator') {
        manager.simulator.choreography.enabled = autoHand.checked;
        if (!autoHand.checked) manager.simulator.hand.present = false;
        adapter.audio.setSynthAuto(autoGuitar.checked);
        adapter.audio.setSynthBpm(Number(bpm.value));
      }
      $('coachLine').textContent = 'Play freely. Connect the Python bridge for live coaching.';
    }
    dialog.close();
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : String(error);
  } finally { busy = false; describe(); label(); }
});
stop.addEventListener('click', async () => {
  const python = manager.activeMode === 'python';
  await manager.stop(); connected = false; label();
  if (python) location.reload(); // unload the coach socket too; the Python instrument keeps playing
});
mute.addEventListener('click', () => { if (manager.activeMode !== 'python') browserAdapter().audio.toggleMute(); label(); });
autoHand.addEventListener('change', () => {
  manager.simulator.choreography.enabled = autoHand.checked;
  manager.simulator.controller.rearm();
  if (autoHand.checked) manager.simulator.choreography.reset(); else manager.simulator.hand.present = false;
});
autoGuitar.addEventListener('change', () => manager.simulator.audio.setSynthAuto(autoGuitar.checked));
bpm.addEventListener('change', () => { const value = Math.min(240, Math.max(40, Number(bpm.value) || 92)); bpm.value = String(value); manager.simulator.audio.setSynthBpm(value); });
$('browserPluck').addEventListener('click', () => manager.simulator.audio.pluck());
target.addEventListener('change', () => {
  for (const adapter of [manager.simulator, manager.live]) { adapter.gestureTarget = target.value as 'filter' | 'reverb' | 'scene'; adapter.controller.rearm(); }
  describe();
});
scene.addEventListener('change', () => {
  for (const adapter of [manager.simulator, manager.live]) { adapter.setlist.select(Number(scene.value)); adapter.controller.rearm(); }
});
window.addEventListener('pagehide', () => { void manager.stop(); });
describe();
dialog.showModal();
