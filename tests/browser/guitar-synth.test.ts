import { describe, it, expect, vi } from 'vitest';
import { SyntheticGuitar, PENTATONIC_NOTES } from '../../dashboard/browser/audio/guitar-synth';

describe('SyntheticGuitar tests', () => {
  it('resumes after a long pause without replaying missed notes', () => {
    const synth = new SyntheticGuitar();
    const block = new Float32Array(128);
    synth.autoPluck = false;
    for (let i = 0; i < 11250; i++) synth.process(block, 0, block.length);
    const pluck = vi.spyOn(synth, 'pluck');
    synth.autoPluck = true;
    synth.process(block, 0, block.length);
    expect(pluck).toHaveBeenCalledOnce();
    expect(block.some(sample => sample !== 0)).toBe(true);
  });

  it('generates audible, finite guitar samples within [-0.98, 0.98]', () => {
    const sr = 48000;
    const synth = new SyntheticGuitar(sr, 92.0, 42, 0.3);
    const n = 1024;
    const buf = new Float32Array(n);

    // Initial pluck
    synth.pluck(NOTES_E2);
    synth.process(buf, 0, n);

    let peak = 0;
    for (let i = 0; i < n; i++) {
      expect(Number.isFinite(buf[i])).toBe(true);
      expect(buf[i]).toBeGreaterThanOrEqual(-0.98);
      expect(buf[i]).toBeLessThanOrEqual(0.98);
      if (Math.abs(buf[i]) > peak) peak = Math.abs(buf[i]);
    }

    expect(peak).toBeGreaterThan(0.01);
  });

  it('supports manual note plucks on pentatonic frequencies', () => {
    const sr = 48000;
    const synth = new SyntheticGuitar(sr, 92.0, 10, 0.3);
    synth.autoPluck = false; // manual plucks only

    const buf = new Float32Array(512);
    synth.process(buf, 0, 512);
    // Silent before pluck
    expect(buf[0]).toBe(0.0);

    synth.pluck(PENTATONIC_NOTES[0]); // Low E
    synth.process(buf, 0, 512);
    expect(Math.abs(buf[10])).toBeGreaterThan(0.01);
  });
});

const NOTES_E2 = 82.41;
