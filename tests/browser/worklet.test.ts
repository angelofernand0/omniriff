import { describe, it, expect } from 'vitest';
import { WORKLET_CODE, WORKLET_PROCESSOR_NAME } from '../../dashboard/browser/audio/worklet-code';

// Execute the exact Blob payload used by AudioEngine, with only the browser host
// APIs mocked. Testing dsp-math.ts alone does not exercise this deployed code.
function worklet(mode?: 'synth' | 'input', samplerate = 48000) {
  let Processor: any;
  class HostProcessor {
    port = { onmessage: null as any, postMessage: (_message: unknown) => {} };
  }
  const register = (name: string, constructor: any) => {
    expect(name).toBe(WORKLET_PROCESSOR_NAME);
    Processor = constructor;
  };
  new Function('AudioWorkletProcessor', 'registerProcessor', 'sampleRate', 'currentTime', WORKLET_CODE)(
    HostProcessor, register, samplerate, 0,
  );
  const processor = new Processor({ processorOptions: { sourceMode: mode } });
  const send = (message: object) => processor.port.onmessage({ data: message });
  const process = (channels: Float32Array[] = [], count = 128) => {
    const output = [new Float32Array(count), new Float32Array(count)];
    expect(processor.process([channels], [output], {})).toBe(true);
    expect(Array.from(output[0]).every(Number.isFinite)).toBe(true);
    expect(output[1]).toEqual(output[0]);
    return output[0];
  };
  return { processor, send, process };
}

const peak = (samples: Float32Array) => Math.max(...Array.from(samples, Math.abs));

describe('deployed AudioWorklet payload', () => {
  it('starts silently unless synth mode is explicitly configured', () => {
    expect(peak(worklet().process())).toBe(0);
    expect(peak(worklet('input').process())).toBe(0);
    expect(peak(worklet('synth').process())).toBeGreaterThan(0.01);
  });

  it('loses physical input without generating synthetic notes or selecting another channel', () => {
    const live = worklet('input');
    live.send({ type: 'set-bypass', value: true });
    const signal = new Float32Array(128).fill(0.15);
    for (let i = 0; i < 4; i++) live.process([signal]);
    expect(peak(live.process([signal]))).toBeGreaterThan(0.1);
    for (let i = 0; i < 20; i++) live.process(); // allow existing filter history to decay
    expect(peak(live.process())).toBe(0);
    live.send({ type: 'set-input-channel', channel: 1 });
    expect(peak(live.process([signal]))).toBe(0);
  });

  it('keeps a recorded loop playing after input disconnect, without adding a synth', () => {
    const live = worklet('input');
    live.send({ type: 'set-bypass', value: true });
    const signal = new Float32Array(128).fill(0.15);
    live.send({ type: 'toggle-loop' });
    for (let i = 0; i < 8; i++) live.process([signal]);
    live.send({ type: 'toggle-loop' });
    expect(live.processor.looper.state).toBe('playing');
    expect(peak(live.process())).toBeGreaterThan(0); // first block enters the recorded seam fade
    expect(peak(live.process())).toBeGreaterThan(0.1);
    expect(live.processor.synth.pos).toBe(0);
    live.send({ type: 'clear-loop' });
    expect(peak(live.process())).toBe(0);
  });

  it('changes the real synth BPM and bounds its eighth-note interval', () => {
    const sim = worklet('synth');
    sim.send({ type: 'set-synth-bpm', bpm: 120 });
    expect(sim.processor.synth.stepFrames).toBe(12000);
    sim.send({ type: 'set-synth-bpm', bpm: 10000 });
    expect(sim.processor.synth.bpm).toBe(240);
    sim.send({ type: 'set-synth-bpm', bpm: -100 });
    expect(sim.processor.synth.bpm).toBe(40);
    expect(peak(sim.process())).toBeGreaterThan(0.01);
  });

  it('rejects nonfinite and malformed numeric messages before recursive DSP is poisoned', () => {
    const sim = worklet('synth');
    for (const invalid of [NaN, Infinity, -Infinity, undefined, null, '0.5', {}]) {
      for (const type of ['set-filter', 'set-reverb']) sim.send({ type, value: invalid });
      sim.send({ type: 'set-trim', db: invalid });
      sim.send({ type: 'set-synth-bpm', bpm: invalid });
      sim.send({ type: 'set-input-channel', channel: invalid });
    }
    sim.send({ type: 'set-source-mode', mode: 'invalid' });
    expect(sim.processor.sourceMode).toBe('synth');
    expect(sim.processor.targetFilter).toBe(1);
    expect(sim.processor.targetReverb).toBe(0);
    expect(sim.processor.inputGain).toBe(1);
    expect(sim.processor.synth.bpm).toBe(92);
    expect(sim.processor.inputChannel).toBe(0);
    for (let i = 0; i < 20; i++) expect(peak(sim.process())).toBeLessThanOrEqual(sim.processor.ceiling);
    sim.send({ type: 'set-filter', value: 0.2 });
    sim.send({ type: 'set-reverb', value: 0.5 });
    expect(peak(sim.process())).toBeGreaterThan(0);
  });

  it('bounds finite control extremes and sanitizes invalid input samples', () => {
    const live = worklet('input');
    live.send({ type: 'set-filter', value: -100 });
    live.send({ type: 'set-reverb', value: 100 });
    live.send({ type: 'set-trim', db: 10000 });
    expect(live.processor.targetFilter).toBe(0);
    expect(live.processor.targetReverb).toBe(1);
    expect(live.processor.inputGain).toBeCloseTo(10 ** (24 / 20));
    const input = new Float32Array(128).fill(0.2);
    input[0] = NaN;
    input[1] = Infinity;
    input[2] = -Infinity;
    input[3] = 3e38;
    for (let i = 0; i < 40; i++) expect(peak(live.process([input]))).toBeLessThanOrEqual(live.processor.ceiling);
    live.send({ type: 'set-trim', db: -10000 });
    expect(live.processor.inputGain).toBeCloseTo(0.001);
  });

  it('rejects invalid plucks and preserves a zero-amplitude manual pluck', () => {
    const sim = worklet('synth');
    sim.send({ type: 'set-synth-auto', auto: false });
    for (const freqHz of [NaN, Infinity, -1, 0, 30000]) sim.send({ type: 'pluck', freqHz });
    for (const ampScale of [NaN, Infinity, -1]) sim.send({ type: 'pluck', freqHz: 110, ampScale });
    sim.send({ type: 'pluck', freqHz: 110, ampScale: 0 });
    expect(peak(sim.process())).toBe(0);
    sim.send({ type: 'pluck', freqHz: 110, ampScale: 100 });
    expect(peak(sim.process())).toBeGreaterThan(0.01);
  });

  it('supports live DSP at common browser sample rates and bounded quantum sizes', () => {
    for (const sr of [44100, 48000, 96000]) {
      const live = worklet('input', sr);
      live.send({ type: 'set-reverb', value: 1 });
      for (const count of [64, 128, 256, 512]) {
        expect(peak(live.process([new Float32Array(count).fill(0.25)], count))).toBeLessThanOrEqual(live.processor.ceiling);
      }
    }
  });
});
