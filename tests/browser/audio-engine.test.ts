import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AudioEngine } from '../../dashboard/browser/audio/audio-engine';

let contexts: FakeContext[];
let nodes: FakeWorklet[];
let loadModule: () => Promise<void>;
let resumeContext: () => Promise<void>;
let failNode: boolean;

class FakeGain {
  gain = { setValueAtTime: vi.fn() };
  connect = vi.fn();
  disconnect = vi.fn();
}

class FakeContext {
  state = 'suspended';
  currentTime = 1;
  sampleRate = 48000;
  destination = {};
  gains: FakeGain[] = [];
  sources: Array<{ connect: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }> = [];
  audioWorklet = { addModule: vi.fn(() => loadModule()) };
  resume = vi.fn(async () => { await resumeContext(); this.state = 'running'; });
  close = vi.fn(async () => { this.state = 'closed'; });
  setSinkId = vi.fn(async (_sinkId: string) => {});
  constructor() { contexts.push(this); }
  createGain() { const gain = new FakeGain(); this.gains.push(gain); return gain; }
  createMediaStreamSource(_stream: MediaStream) {
    const source = { connect: vi.fn(), disconnect: vi.fn() };
    this.sources.push(source);
    return source;
  }
}

class FakeWorklet {
  port = { postMessage: vi.fn(), close: vi.fn(), onmessage: null as any };
  connect = vi.fn();
  disconnect = vi.fn();
  constructor(_ctx: unknown, _name: string, public options: AudioWorkletNodeOptions) {
    if (failNode) throw new Error('node failed');
    nodes.push(this);
  }
}

function stream(readyState: 'live' | 'ended' = 'live') {
  const track = { readyState, stop: vi.fn() };
  return { track, media: { getAudioTracks: () => [track], getTracks: () => [track] } as unknown as MediaStream };
}

beforeEach(() => {
  contexts = [];
  nodes = [];
  failNode = false;
  loadModule = async () => {};
  resumeContext = async () => {};
  vi.stubGlobal('window', { AudioContext: FakeContext });
  vi.stubGlobal('AudioWorkletNode', FakeWorklet);
  vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:worklet'), revokeObjectURL: vi.fn() });
});

afterEach(() => vi.unstubAllGlobals());

describe('AudioEngine resource and source lifecycle', () => {
  it('rejects missing or ended live input before constructing an audio graph', async () => {
    const audio = new AudioEngine();
    await expect(audio.start('input')).rejects.toThrow('active audio stream');
    await expect(audio.start('input', stream('ended').media)).rejects.toThrow('active audio stream');
    expect(contexts).toHaveLength(0);
    expect(nodes).toHaveLength(0);
    expect(audio.isRunning).toBe(false);
  });

  it('configures input mode before connecting the worklet to the destination', async () => {
    const audio = new AudioEngine();
    await audio.start('input', stream().media);
    expect(nodes[0].options.processorOptions).toEqual({ sourceMode: 'input' });
    expect(nodes[0].port.postMessage).toHaveBeenCalledWith({ type: 'set-source-mode', mode: 'input' });
    expect(nodes[0].port.postMessage.mock.invocationCallOrder[0]).toBeLessThan(nodes[0].connect.mock.invocationCallOrder[0]);
    expect(audio.isRunning).toBe(true);
    await audio.stop();
  });

  it('cleans up a failed worklet module and permits a fresh start', async () => {
    const audio = new AudioEngine();
    const input = stream();
    loadModule = async () => { throw new Error('module failed'); };
    await expect(audio.start('input', input.media)).rejects.toThrow('module failed');
    expect(input.track.stop).toHaveBeenCalledOnce();
    expect(contexts[0].close).toHaveBeenCalledOnce();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:worklet');
    expect(audio.context).toBeNull();
    expect(audio.isRunning).toBe(false);
    loadModule = async () => {};
    await audio.start('synth');
    expect(audio.isRunning).toBe(true);
    expect(contexts).toHaveLength(2);
    await audio.stop();
  });

  it('cleans up failures in resume and worklet construction', async () => {
    for (const failure of ['resume', 'node']) {
      const audio = new AudioEngine();
      const input = stream();
      resumeContext = failure === 'resume' ? async () => { throw new Error('resume failed'); } : async () => {};
      failNode = failure === 'node';
      await expect(audio.start('input', input.media)).rejects.toThrow(`${failure} failed`);
      expect(input.track.stop).toHaveBeenCalledOnce();
      expect(contexts.at(-1)!.close).toHaveBeenCalledOnce();
      expect(audio.context).toBeNull();
      expect(audio.isRunning).toBe(false);
    }
  });

  it('releases acquired input when AudioContext construction fails', async () => {
    vi.stubGlobal('window', { AudioContext: class { constructor() { throw new Error('context failed'); } } });
    const audio = new AudioEngine();
    const input = stream();
    await expect(audio.start('input', input.media)).rejects.toThrow('context failed');
    expect(input.track.stop).toHaveBeenCalledOnce();
    expect(audio.context).toBeNull();
  });

  it('does not resurrect an engine stopped while its module is loading', async () => {
    let finish!: () => void;
    loadModule = () => new Promise<void>((resolve) => { finish = resolve; });
    const audio = new AudioEngine();
    const input = stream();
    const starting = audio.start('input', input.media);
    const rejected = expect(starting).rejects.toThrow('startup was stopped');
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
    await audio.stop();
    finish();
    await rejected;
    expect(nodes).toHaveLength(0);
    expect(input.track.stop).toHaveBeenCalledOnce();
    expect(audio.context).toBeNull();
    expect(audio.isRunning).toBe(false);
  });

  it('preserves mute preference and muted gain after stopping and restarting', async () => {
    const audio = new AudioEngine();
    await audio.start('synth');
    expect(audio.toggleMute()).toBe(true);
    await audio.stop();
    await audio.start('synth');
    expect(audio.isMuted).toBe(true);
    expect(contexts[1].gains[0].gain.setValueAtTime).toHaveBeenCalledWith(0, 1);
    expect(audio.toggleMute()).toBe(false);
    expect(contexts[1].gains[0].gain.setValueAtTime).toHaveBeenLastCalledWith(1, 1);
    await audio.stop();
  });

  it('does not clear a new context when the previous context finishes closing', async () => {
    const audio = new AudioEngine();
    await audio.start('synth');
    let finish!: () => void;
    contexts[0].close.mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    const stopping = audio.stop();
    await audio.start('synth');
    const currentContext = audio.context;
    finish();
    await stopping;
    expect(audio.context).toBe(currentContext);
    expect(audio.context).not.toBeNull();
    expect(audio.isRunning).toBe(true);
    await audio.stop();
  });

  it('keeps existing input after an invalid switch and stops replaced tracks', async () => {
    const audio = new AudioEngine();
    const first = stream();
    await audio.start('input', first.media);
    await expect(audio.setSourceMode('input')).rejects.toThrow('active audio stream');
    expect(audio.mode).toBe('input');
    expect(first.track.stop).not.toHaveBeenCalled();
    const second = stream();
    await audio.setSourceMode('input', second.media);
    expect(first.track.stop).toHaveBeenCalledOnce();
    expect(contexts[0].sources[0].disconnect).toHaveBeenCalledOnce();
    await audio.setSourceMode('synth');
    expect(second.track.stop).toHaveBeenCalledOnce();
    expect(audio.mode).toBe('synth');
    await audio.stop();
  });

  it('rejects invalid numerical controls and clamps finite values before posting', async () => {
    const audio = new AudioEngine();
    await audio.start('synth');
    const post = nodes[0].port.postMessage;
    post.mockClear();
    for (const value of [NaN, Infinity, -Infinity]) {
      audio.setFilter(value);
      audio.setReverb(value);
      audio.setInputTrim(value);
      audio.setInputChannel(value);
      audio.setSynthBpm(value);
      audio.pluck(value);
      audio.pluck(110, value);
    }
    audio.setInputChannel(1.5);
    audio.setInputChannel(32);
    expect(post).not.toHaveBeenCalled();
    audio.setFilter(-1);
    audio.setReverb(2);
    audio.setInputTrim(10000);
    audio.setSynthBpm(10000);
    audio.pluck(110, 0);
    expect(post.mock.calls.map(([message]) => message)).toEqual([
      { type: 'set-filter', value: 0 },
      { type: 'set-reverb', value: 1 },
      { type: 'set-trim', db: 24 },
      { type: 'set-synth-bpm', bpm: 240 },
      { type: 'pluck', freqHz: 110, ampScale: 0 },
    ]);
    await audio.stop();
  });

  it('updates audio output device sink ID', async () => {
    const audio = new AudioEngine();
    await audio.start('synth');
    const result = await audio.setAudioOutput('headphones-device-id');
    expect(result).toBe(true);
    expect(contexts[0].setSinkId).toHaveBeenCalledWith('headphones-device-id');
    expect(audio.outputDeviceId).toBe('headphones-device-id');
    await audio.stop();
  });
});
