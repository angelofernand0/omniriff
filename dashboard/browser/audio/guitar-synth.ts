/**
 * Synthetic guitar synthesizer for Browser Simulator mode.
 * Parity with tools/sim/synth.py: plucked decaying harmonics on an eighth-note grid.
 * Zero allocation during synthesis callback.
 */

export const PENTATONIC_NOTES = [82.41, 98.00, 110.00, 123.47, 146.83, 164.81, 196.00, 220.00, 246.94] as const;

interface Voice {
  freq: number;
  phase: number;
  amp: number;
  decay: number;
  active: boolean;
}

export class SyntheticGuitar {
  public readonly samplerate: number;
  public bpm: number;
  public level: number;
  private autoPluckEnabled: boolean = true;

  public get autoPluck(): boolean { return this.autoPluckEnabled; }
  public set autoPluck(enabled: boolean) {
    if (enabled && !this.autoPluckEnabled) {
      // Resume from the current audio clock, never replay paused note slots.
      this.nextPluck = Math.max(this.nextPluck, this.pos);
    }
    this.autoPluckEnabled = enabled;
  }

  private stepFrames: number;
  private pos: number = 0;
  private nextPluck: number = 0;
  private beat: number = 0;

  // Preallocated voice pool (max 8 voices, zero allocations)
  private readonly voices: Voice[];
  private rngState: number;

  constructor(samplerate: number = 48000, bpm: number = 92.0, seed: number = 7, level: number = 0.28) {
    this.samplerate = samplerate;
    this.bpm = bpm;
    this.level = level;
    this.stepFrames = Math.floor((samplerate * 60.0) / bpm / 2); // eighth notes
    this.rngState = seed;

    this.voices = Array.from({ length: 8 }, () => ({
      freq: 110.0,
      phase: 0.0,
      amp: 0.0,
      decay: 0.999,
      active: false,
    }));
  }

  // Simple, deterministic pseudo-random number generator
  private random(): number {
    this.rngState = (this.rngState * 1664525 + 1013904223) >>> 0;
    return this.rngState / 4294967296;
  }

  private randomRange(min: number, max: number): number {
    return min + this.random() * (max - min);
  }

  public pluck(freqHz?: number, ampScale: number = 1.0): void {
    const freq = freqHz ?? PENTATONIC_NOTES[Math.floor(this.random() * PENTATONIC_NOTES.length)];
    const amp = this.level * ampScale;
    const decay = Math.exp(-1.0 / (this.samplerate * this.randomRange(0.25, 0.6)));

    // Find inactive or oldest/quietest voice
    let bestIdx = 0;
    let minAmp = Infinity;
    for (let i = 0; i < this.voices.length; i++) {
      if (!this.voices[i].active) {
        bestIdx = i;
        break;
      }
      if (this.voices[i].amp < minAmp) {
        minAmp = this.voices[i].amp;
        bestIdx = i;
      }
    }

    const v = this.voices[bestIdx];
    v.freq = freq;
    v.phase = 0.0;
    v.amp = amp;
    v.decay = decay;
    v.active = true;
  }

  private autoStep(): void {
    const accent = this.beat % 8 === 0;
    const rest = this.beat % 8 === 5 || this.random() < 0.12;
    this.beat++;
    if (rest) return;

    const ampScale = accent ? 1.75 : this.randomRange(0.55, 1.0);
    this.pluck(undefined, ampScale);
  }

  public setBpm(bpm: number): void {
    this.bpm = Math.max(40, Math.min(240, bpm));
    this.stepFrames = Math.floor((this.samplerate * 60.0) / this.bpm / 2);
  }

  public process(out: Float32Array, offset: number, count: number): void {
    for (let i = 0; i < count; i++) {
      out[offset + i] = 0.0;
    }

    let i = 0;
    while (i < count) {
      if (this.autoPluck && this.pos + i >= this.nextPluck) {
        this.autoStep();
        this.nextPluck += this.stepFrames;
      }
      let end = this.autoPluck ? Math.min(count, this.nextPluck - this.pos) : count;
      if (end <= i) end = i + 1;
      const m = end - i;

      for (const v of this.voices) {
        if (!v.active) continue;

        let ph = v.phase;
        let amp = v.amp;
        const decay = v.decay;
        const w = (2.0 * Math.PI * v.freq) / this.samplerate;

        for (let j = 0; j < m; j++) {
          const idx = offset + i + j;
          // Plucked guitar harmonic spectrum: fundamental + 0.45 * 2nd + 0.2 * 3rd
          const sample = (Math.sin(ph) + 0.45 * Math.sin(2.0 * ph) + 0.2 * Math.sin(3.0 * ph)) / 1.65;
          out[idx] += amp * sample;

          ph += w;
          if (ph > 2.0 * Math.PI) ph -= 2.0 * Math.PI;
          amp *= decay;
        }

        v.phase = ph;
        v.amp = amp;
        if (v.amp < 1e-4) {
          v.active = false;
        }
      }

      i = end;
    }

    this.pos += count;

    // Hard safety clamp to [-0.98, 0.98]
    for (let j = 0; j < count; j++) {
      const idx = offset + j;
      const val = out[idx];
      if (val > 0.98) out[idx] = 0.98;
      else if (val < -0.98) out[idx] = -0.98;
    }
  }

  public clear(): void {
    for (const v of this.voices) {
      v.active = false;
      v.amp = 0.0;
    }
    this.pos = 0;
    this.nextPluck = 0;
    this.beat = 0;
  }
}
