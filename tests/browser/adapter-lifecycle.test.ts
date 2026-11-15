import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';

vi.mock('../../dashboard/browser/audio/audio-engine', () => ({ AudioEngine: class {
  sampleRate = 48000; start = vi.fn(async () => {}); stop = vi.fn(async () => {});
  onState = vi.fn(); setFilter = vi.fn(); setReverb = vi.fn(); setInputChannel = vi.fn();
  toggleLoop = vi.fn(); toggleBypass = vi.fn(); clearLoop = vi.fn();
} }));
vi.mock('../../dashboard/browser/audio/devices', () => ({ DeviceManager: class {
  selectedChannel = 0; enumerate = vi.fn(async () => {});
  getAudioStream = vi.fn(async () => ({ getTracks: () => [] } as unknown as MediaStream));
  getVideoStream = vi.fn(async () => ({ getTracks: () => [] } as unknown as MediaStream));
} }));
vi.mock('../../dashboard/browser/vision/hand-tracker', () => ({ LiveHandTracker: class {
  isRunning = false;
  observation = { present: false, y: null, pinch: null, confidence: 0, timestamp_ms: 0 };
  start = vi.fn(async () => { this.isRunning = true; });
  stop = vi.fn(() => { this.isRunning = false; });
  update = vi.fn(); getObservation = () => this.observation;
  getHandFrame = () => ({ version: 1, type: 'hand', timestamp_ms: Date.now(), present: true, engaged: false,
    confidence: .95, control: 'filter', value: .5, landmarks: Array.from({ length: 21 }, () => [.5, .5]) });
} }));
import { BrowserLiveAdapter } from '../../dashboard/browser/adapters/browser-live';
import { BrowserSimulatorAdapter } from '../../dashboard/browser/adapters/browser-simulator';
import { PythonBridgeAdapter } from '../../dashboard/browser/adapters/python-bridge';

let callbacks: Map<number, FrameRequestCallback>; let nextId: number;
function tick(time: number) { const scheduled = [...callbacks.values()]; callbacks.clear(); scheduled.forEach(cb => cb(time)); }
class FakeSocket {
  static OPEN = 1; static instances: FakeSocket[] = [];
  readyState = 1; onopen: any = null; onmessage: any = null; onclose: any = null; onerror: any = null;
  send = vi.fn(); close = vi.fn(); constructor(public url: string) { FakeSocket.instances.push(this); }
  frame(frame: unknown) { this.onmessage?.({ data: JSON.stringify(frame) }); }
}
function state(timestamp_ms = 1000) {
  return { version: 1, timestamp_ms, samplerate: 48000, bypass: false,
    loop: { state: 'idle', seconds: 0, max_seconds: 30 },
    filter: { target: 1, value: 1, cutoff_hz: 18000 }, reverb: { target: 0, value: 0, dsp: true },
    input_peak_dbfs: -60, output_peak_dbfs: -60, xruns: 0, clipped_samples: 0, blocks: 1,
    events: { accepted: 0, rejected: 0, low_confidence: 0 },
    controls: { accepted: 0, invalid: 0, stale: 0, future: 0, duplicate: 0, low_confidence: 0, audio_rejected: 0 },
    sources: {}, adapters: Object.fromEntries(['udp','serial','websocket'].map(k => [k,{ status: 'disabled', errors: 0, last_error: null }])) };
}
beforeEach(() => {
  callbacks = new Map(); nextId = 0; FakeSocket.instances = [];
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => { callbacks.set(++nextId, cb); return nextId; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => callbacks.delete(id));
  vi.stubGlobal('WebSocket', FakeSocket); vi.spyOn(Date, 'now').mockReturnValue(1700000000000);
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Browser adapter lifecycle', () => {
  it('sim start failure cleans up and can retry; stopped callbacks cannot publish', async () => {
    const adapter = new BrowserSimulatorAdapter(); const received = vi.fn(); adapter.onState(received);
    vi.mocked(adapter.audio.start).mockRejectedValueOnce(new Error('worklet failed'));
    await expect(adapter.start()).rejects.toThrow('worklet failed'); expect(adapter.audio.stop).toHaveBeenCalled();
    await adapter.start(); const late = [...callbacks.values()][0]; tick(1000);
    expect(received).toHaveBeenCalled(); await adapter.stop(); const count = received.mock.calls.length;
    late(2000); expect(received).toHaveBeenCalledTimes(count); expect(adapter.sendControl('loop')).toBe(false);
  });
  it('sim defaults to direct filter, uses Unix protocol time and morphs only when requested', async () => {
    const adapter = new BrowserSimulatorAdapter(); adapter.choreography.enabled = false;
    const states: any[] = [], hands: any[] = []; adapter.onState(f => states.push(f)); adapter.onHand(f => hands.push(f));
    await adapter.start(); adapter.hand.present = true; adapter.hand.pinchAmount = 0; tick(1000);
    adapter.hand.pinchAmount = 1; tick(1100);
    expect(adapter.audio.setFilter).toHaveBeenCalled(); expect(adapter.audio.setReverb).not.toHaveBeenCalled();
    expect(states.at(-1).timestamp_ms).toBe(1700000000000); expect(hands.at(-1).timestamp_ms).toBe(1700000000000);
    expect(hands.at(-1).control).toBe('filter');
    adapter.gestureTarget = 'reverb'; adapter.hand.pinchAmount = 0; tick(1200); adapter.hand.pinchAmount = 1; tick(1300);
    expect(adapter.audio.setReverb).toHaveBeenCalled(); expect(hands.at(-1).control).toBe('reverb');
    adapter.gestureTarget = 'scene'; adapter.hand.pinchAmount = 0; tick(1400); adapter.hand.pinchAmount = 1; tick(1500);
    expect(hands.at(-1).control).toBeNull(); await adapter.stop();
  });
  it('stops a late acquired audio stream after cancellation without starting audio', async () => {
    const adapter = new BrowserLiveAdapter(); const track = { stop: vi.fn() }; let acquired!: (stream: MediaStream) => void;
    vi.mocked(adapter.devices.getAudioStream).mockImplementation(() => new Promise(resolve => { acquired = resolve; }));
    const pending = adapter.start(); await Promise.resolve(); await Promise.resolve(); await adapter.stop();
    acquired({ getTracks: () => [track] } as unknown as MediaStream); await pending;
    expect(track.stop).toHaveBeenCalledOnce(); expect(adapter.audio.start).not.toHaveBeenCalled(); expect(adapter.isRunning).toBe(false);
  });
  it('keeps manual audio available after camera denial and expires old hand observations', async () => {
    const denied = new BrowserLiveAdapter(); vi.mocked(denied.devices.getVideoStream).mockRejectedValueOnce(new Error('denied'));
    await denied.start(); expect(denied.isRunning).toBe(true); expect(denied.sendControl('bypass')).toBe(true); await denied.stop();
    const adapter = new BrowserLiveAdapter(); const hand = vi.fn(); adapter.onHand(hand); await adapter.start();
    const tracker: any = adapter.tracker;
    tracker.observation = { present: true, y: .5, pinch: .6, confidence: .95, timestamp_ms: 1000 }; tick(1000);
    tracker.observation = { ...tracker.observation, pinch: .1, timestamp_ms: 1100 }; tick(1100);
    expect(adapter.controller.active).toBe(true); const sent = vi.mocked(adapter.audio.setFilter).mock.calls.length;
    tick(1500); expect(adapter.controller.active).toBe(false); expect(hand.mock.calls.at(-1)?.[0].present).toBe(false);
    expect(adapter.audio.setFilter).toHaveBeenCalledTimes(sent); await adapter.stop();
  });
});

describe('Python bridge callbacks and input contract', () => {
  it('drops malformed/duplicate frames and callbacks from a stopped socket after restart', async () => {
    const adapter = new PythonBridgeAdapter('ws://127.0.0.1:1', null); const received = vi.fn(), connection = vi.fn();
    adapter.onState(received); adapter.onConnection(connection); await adapter.start();
    const old = FakeSocket.instances[0], late = old.onmessage;
    old.frame({ version: 1 }); expect(received).not.toHaveBeenCalled(); old.frame(state()); old.frame(state());
    expect(received).toHaveBeenCalledOnce(); expect(connection.mock.calls.at(-1)?.[0].status).toBe('connected');
    await adapter.stop(); await adapter.start(); late({ data: JSON.stringify(state(2000)) });
    expect(received).toHaveBeenCalledOnce(); FakeSocket.instances[1].frame(state(3000)); expect(received).toHaveBeenCalledTimes(2);
    expect(adapter.sendControl('filter', Number.NaN)).toBe(false); expect(adapter.sendControl('filter', 4)).toBe(true);
    expect(JSON.parse(FakeSocket.instances[1].send.mock.calls[0][0]).value).toBe(1); await adapter.stop();
  });
  it('cancels retries on stop and clears a disconnected hand without stopping the engine', async () => {
    vi.useFakeTimers(); const adapter = new PythonBridgeAdapter('ws://127.0.0.1:1', 'ws://127.0.0.1:2');
    const hand = vi.fn(); adapter.onHand(hand); await adapter.start();
    FakeSocket.instances[1].onclose(); expect(hand.mock.calls.at(-1)?.[0].present).toBe(false);
    await adapter.stop(); await vi.advanceTimersByTimeAsync(5000); expect(FakeSocket.instances).toHaveLength(2);
  });
});
