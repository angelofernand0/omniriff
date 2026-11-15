import { describe, it, expect } from 'vitest';
import {
  dbToGain,
  gainToDb,
  filterCutoffHz,
  Smoother,
  LowPass,
  Reverb,
  Looper,
  PeakLimiter,
} from '../../dashboard/browser/audio/dsp-math';

describe('DSP Math parity tests', () => {
  it('converts dB to gain and gain to dB accurately', () => {
    expect(dbToGain(0)).toBeCloseTo(1.0, 5);
    expect(dbToGain(-6.0205999)).toBeCloseTo(0.5, 4);
    expect(dbToGain(-20)).toBeCloseTo(0.1, 5);

    expect(gainToDb(1.0)).toBeCloseTo(0.0, 5);
    expect(gainToDb(0.5)).toBeCloseTo(-6.0206, 3);
    expect(gainToDb(0.1)).toBeCloseTo(-20.0, 5);
  });

  it('maps filter cutoff exponentially and clamps to Nyquist 0.45*sr', () => {
    const sr = 48000;
    const minHz = 120.0;
    const maxHz = 18000.0;

    // Endpoint 0.0 -> minHz
    expect(filterCutoffHz(0.0, minHz, maxHz, sr)).toBeCloseTo(120.0, 4);
    // Endpoint 1.0 -> maxHz clamped to 0.45 * sr = 21600 (maxHz 18000 < 21600)
    expect(filterCutoffHz(1.0, minHz, maxHz, sr)).toBeCloseTo(18000.0, 4);

    // Midpoint 0.5: exponential sqrt(minHz * maxHz) = sqrt(120 * 18000) = 1469.69 Hz
    const expectedMid = Math.sqrt(minHz * maxHz);
    expect(filterCutoffHz(0.5, minHz, maxHz, sr)).toBeCloseTo(expectedMid, 1);

    // Clamping at low samplerate: sr = 24000 -> 0.45 * 24000 = 10800 Hz
    expect(filterCutoffHz(1.0, minHz, maxHz, 24000)).toBeCloseTo(10800.0, 4);
  });

  it('smooths parameter changes over time', () => {
    const sr = 48000;
    const stepFrames = 32;
    const timeMs = 40.0;
    const smoother = new Smoother(1.0, timeMs, sr, stepFrames);

    expect(smoother.value).toBe(1.0);
    // Step towards 0.0
    const v1 = smoother.step(0.0);
    expect(v1).toBeLessThan(1.0);
    expect(v1).toBeGreaterThan(0.0);

    // After sufficient steps (~850 steps = ~550ms), reaches exact target
    for (let i = 0; i < 900; i++) {
      smoother.step(0.0);
    }
    expect(smoother.value).toBe(0.0);
  });

  it('filters high frequencies with LowPass RBJ biquad', () => {
    const sr = 48000;
    const lp = new LowPass(sr, 0.9);
    lp.setCutoff(500); // 500 Hz cutoff

    const n = 512;
    const inputHigh = new Float32Array(n);
    const outputHigh = new Float32Array(n);

    // Generate high-frequency tone at 10 kHz
    for (let i = 0; i < n; i++) {
      inputHigh[i] = Math.sin((2 * Math.PI * 10000 * i) / sr);
    }

    lp.process(inputHigh, outputHigh, 0, n);

    // Measure steady-state amplitude of filtered high-frequency tone
    let highAmp = 0;
    for (let i = 256; i < n; i++) {
      const val = Math.abs(outputHigh[i]);
      if (val > highAmp) highAmp = val;
    }
    // High frequency should be heavily attenuated (well below 0.1)
    expect(highAmp).toBeLessThan(0.05);

    // Now test low-frequency tone at 100 Hz (well below 500 Hz cutoff)
    lp.clear();
    const inputLow = new Float32Array(n);
    const outputLow = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      inputLow[i] = Math.sin((2 * Math.PI * 100 * i) / sr);
    }

    lp.process(inputLow, outputLow, 0, n);
    let lowAmp = 0;
    for (let i = 256; i < n; i++) {
      const val = Math.abs(outputLow[i]);
      if (val > lowAmp) lowAmp = val;
    }
    // Low frequency should pass through with minimal attenuation
    expect(lowAmp).toBeGreaterThan(0.8);
  });

  it('runs Freeverb reverb with continuous tail and no NaN', () => {
    const sr = 48000;
    const maxBlock = 128;
    const reverb = new Reverb(sr, maxBlock, 0.84, 0.5);

    const impulse = new Float32Array(maxBlock);
    impulse[0] = 1.0;
    const out1 = new Float32Array(maxBlock);
    const out2 = new Float32Array(maxBlock);

    reverb.process(impulse, out1, 0, maxBlock);

    // Zero out input for subsequent blocks until comb delays emerge (>1214 samples)
    impulse[0] = 0.0;
    let maxVal = 0;
    for (let b = 0; b < 20; b++) {
      reverb.process(impulse, out2, 0, maxBlock);
      for (let i = 0; i < maxBlock; i++) {
        expect(Number.isFinite(out2[i])).toBe(true);
        if (Math.abs(out2[i]) > maxVal) maxVal = Math.abs(out2[i]);
      }
    }
    expect(maxVal).toBeGreaterThan(0.0);
  });

  it('cycles looper through idle -> recording -> playing -> idle states with fades', () => {
    const sr = 48000;
    const maxFrames = 48000; // 1 second
    const fadeFrames = 240; // 5ms
    const looper = new Looper(maxFrames, fadeFrames);

    expect(looper.state).toBe('idle');
    looper.toggle();
    expect(looper.state).toBe('recording');

    // Feed audio while recording
    const block = new Float32Array(256);
    block.fill(0.5);
    const out = new Float32Array(256);

    looper.process(block, out, 0, 256);
    expect(looper.length).toBe(256);
    expect(out[0]).toBe(0.0); // Output muted while recording

    looper.toggle();
    expect(looper.state).toBe('playing');

    // Check that edges were faded
    expect(looper.buf[0]).toBeCloseTo(0.0, 4);

    // Feed dry audio while playing
    looper.process(block, out, 0, 256);
    expect(out[100]).toBeCloseTo(0.5, 2);

    looper.toggle();
    expect(looper.state).toBe('idle');
    expect(looper.length).toBe(0);
  });

  it('limits signal peaks to threshold without clipping', () => {
    const sr = 48000;
    const step = 32;
    const threshold = dbToGain(-1.0); // ~0.89125
    const limiter = new PeakLimiter(threshold, sr, step, 150.0);

    const n = 256;
    const audio = new Float32Array(n);
    // Massive blast of 4.0 (+12 dBFS)
    audio.fill(4.0);

    limiter.process(audio, 0, n);

    for (let i = 0; i < n; i++) {
      expect(audio[i]).toBeLessThanOrEqual(threshold + 1e-4);
      expect(Number.isFinite(audio[i])).toBe(true);
    }
  });
});
