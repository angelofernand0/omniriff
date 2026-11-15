/**
 * OmniRiff Real-time DSP building blocks in TypeScript.
 * Direct mathematical parity with audio/dsp.py, audio/reverb.py, audio/looper.py.
 * Zero-allocation during sample processing.
 */

export function dbToGain(db: number): number {
  return Math.pow(10.0, db / 20.0);
}

export function gainToDb(gain: number): number {
  return 20.0 * Math.log10(Math.max(gain, 1e-9));
}

export function filterCutoffHz(value: number, minHz: number, maxHz: number, samplerate: number): number {
  const v = Math.min(1.0, Math.max(0.0, value));
  const hz = minHz * Math.pow(maxHz / minHz, v);
  return Math.min(hz, 0.45 * samplerate);
}

export class Smoother {
  public value: number;
  private readonly coeff: number;

  constructor(value: number, timeMs: number, samplerate: number, stepFrames: number) {
    this.value = value;
    const tauFrames = (Math.max(timeMs, 0.0) / 1000.0) * samplerate;
    this.coeff = tauFrames > 0 ? Math.exp(-stepFrames / tauFrames) : 0.0;
  }

  public step(target: number): number {
    this.value = target + (this.value - target) * this.coeff;
    if (Math.abs(this.value - target) < 1e-6) {
      this.value = target;
    }
    return this.value;
  }
}

export class LowPass {
  public readonly samplerate: number;
  public readonly q: number;
  public cutoffHz: number = 0;

  // Biquad coefficients: b0, b1, b2, a1, a2 (a0 normalized to 1)
  private b0: number = 0;
  private b1: number = 0;
  private b2: number = 0;
  private a1: number = 0;
  private a2: number = 0;

  // Direct Form II Transposed state registers (zi in scipy)
  private z1: number = 0;
  private z2: number = 0;

  constructor(samplerate: number, q: number) {
    this.samplerate = samplerate;
    this.q = q;
  }

  public setCutoff(cutoffHz: number): void {
    if (cutoffHz === this.cutoffHz) return;
    this.cutoffHz = cutoffHz;
    const w0 = (2.0 * Math.PI * cutoffHz) / this.samplerate;
    const cosw = Math.cos(w0);
    const sinw = Math.sin(w0);
    const alpha = sinw / (2.0 * this.q);
    const a0 = 1.0 + alpha;

    this.b0 = (1.0 - cosw) / 2.0 / a0;
    this.b1 = (1.0 - cosw) / a0;
    this.b2 = this.b0;
    this.a1 = (-2.0 * cosw) / a0;
    this.a2 = (1.0 - alpha) / a0;
  }

  public process(x: Float32Array, out: Float32Array, offset: number, count: number): void {
    let z1 = this.z1;
    let z2 = this.z2;
    const b0 = this.b0, b1 = this.b1, b2 = this.b2;
    const a1 = this.a1, a2 = this.a2;

    for (let i = 0; i < count; i++) {
      const idx = offset + i;
      const inVal = x[idx];
      const y = b0 * inVal + z1;
      z1 = b1 * inVal - a1 * y + z2;
      z2 = b2 * inVal - a2 * y;
      out[idx] = y;
    }

    this.z1 = z1;
    this.z2 = z2;
  }

  public clear(): void {
    this.z1 = 0;
    this.z2 = 0;
  }
}

export const COMB_44K = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617] as const;
export const ALLPASS_44K = [556, 441, 341, 225] as const;
export const INPUT_GAIN = 0.015;
export const ALLPASS_FEEDBACK = 0.5;

class DelayLine {
  public readonly buf: Float32Array;
  public readonly length: number;
  public idx: number = 0;

  constructor(length: number) {
    this.length = Math.max(1, length);
    this.buf = new Float32Array(this.length);
  }

  public clear(): void {
    this.buf.fill(0);
    this.idx = 0;
  }
}

export class Reverb {
  private readonly combs: DelayLine[];
  private readonly allpasses: DelayLine[];
  public readonly minDelay: number;
  private readonly feedback: number;
  private readonly damp: number;
  private readonly combZi: Float32Array; // 1-pole low-pass state for each comb

  // Scratch memory preallocated for subblock processing
  private readonly scratchIn: Float32Array;
  private readonly scratchAcc: Float32Array;
  private readonly scratchTmp: Float32Array;

  constructor(samplerate: number, maxBlock: number, room: number = 0.84, damp: number = 0.5) {
    const scale = samplerate / 44100.0;
    this.combs = COMB_44K.map((d) => new DelayLine(Math.floor(d * scale)));
    this.allpasses = ALLPASS_44K.map((d) => new DelayLine(Math.floor(d * scale)));

    let minD = Infinity;
    for (const c of this.combs) if (c.length < minD) minD = c.length;
    for (const a of this.allpasses) if (a.length < minD) minD = a.length;
    this.minDelay = minD;

    this.feedback = room * 0.28 + 0.7;
    this.damp = damp * 0.4;
    this.combZi = new Float32Array(this.combs.length);

    this.scratchIn = new Float32Array(maxBlock);
    this.scratchAcc = new Float32Array(maxBlock);
    this.scratchTmp = new Float32Array(maxBlock);
  }

  public process(x: Float32Array, out: Float32Array, offset: number, count: number): void {
    const n = count;
    const inp = this.scratchIn;
    const acc = this.scratchAcc;
    const tmp = this.scratchTmp;
    const d = this.damp;
    const oneMinusD = 1.0 - d;
    const fb = this.feedback;

    // Scale input by INPUT_GAIN
    for (let i = 0; i < n; i++) {
      inp[i] = x[offset + i] * INPUT_GAIN;
      acc[i] = 0.0;
    }

    // Process parallel combs
    for (let j = 0; j < this.combs.length; j++) {
      const comb = this.combs[j];
      const buf = comb.buf;
      const len = comb.length;
      let cIdx = comb.idx;
      let zi = this.combZi[j];

      for (let i = 0; i < n; i++) {
        const delayed = buf[cIdx];
        acc[i] += delayed;

        // Damping 1-pole filter: damped[i] = (1 - d) * delayed + d * zi
        const damped = oneMinusD * delayed + d * zi;
        zi = damped;

        // Feedback + input
        buf[cIdx] = inp[i] + fb * damped;
        cIdx = (cIdx + 1) % len;
      }
      comb.idx = cIdx;
      this.combZi[j] = zi;
    }

    // Process series allpasses
    for (let j = 0; j < this.allpasses.length; j++) {
      const ap = this.allpasses[j];
      const buf = ap.buf;
      const len = ap.length;
      let apIdx = ap.idx;

      for (let i = 0; i < n; i++) {
        const delayed = buf[apIdx];
        const inputSample = acc[i];
        const newAcc = delayed - inputSample;
        buf[apIdx] = inputSample + delayed * ALLPASS_FEEDBACK;
        acc[i] = newAcc;
        apIdx = (apIdx + 1) % len;
      }
      ap.idx = apIdx;
    }

    for (let i = 0; i < n; i++) {
      out[offset + i] = acc[i];
    }
  }

  public clear(): void {
    for (const c of this.combs) c.clear();
    for (const a of this.allpasses) a.clear();
    this.combZi.fill(0);
    this.scratchIn.fill(0);
    this.scratchAcc.fill(0);
    this.scratchTmp.fill(0);
  }
}

export type LooperState = 'idle' | 'recording' | 'playing';

export class Looper {
  public readonly buf: Float32Array;
  public readonly maxFrames: number;
  public readonly fadeFrames: number;
  public length: number = 0;
  public pos: number = 0;
  public state: LooperState = 'idle';

  public takesFinished: number = 0;
  public recordingsStarted: number = 0;
  public takeStartedMs: number = 0;
  public takeEndedMs: number = 0;
  public takeLength: number = 0;

  constructor(maxFrames: number, fadeFrames: number) {
    this.maxFrames = maxFrames;
    this.fadeFrames = fadeFrames;
    this.buf = new Float32Array(maxFrames);
  }

  public toggle(): void {
    if (this.state === 'idle') {
      this.length = 0;
      this.pos = 0;
      this.state = 'recording';
      this.recordingsStarted++;
      this.takeStartedMs = Date.now();
    } else if (this.state === 'recording') {
      this.finishRecording();
    } else {
      this.length = 0;
      this.pos = 0;
      this.state = 'idle';
    }
  }

  public clear(): void {
    this.length = 0;
    this.pos = 0;
    this.state = 'idle';
    this.buf.fill(0);
  }

  private finishRecording(): void {
    if (this.length === 0) {
      this.state = 'idle';
      return;
    }
    const fade = Math.min(this.fadeFrames, Math.floor(this.length / 4));
    if (fade > 0) {
      for (let i = 0; i < fade; i++) {
        const ramp = i / fade;
        this.buf[i] *= ramp;
        this.buf[this.length - 1 - i] *= ramp;
      }
    }
    this.pos = 0;
    this.takeEndedMs = Date.now();
    this.takeLength = this.length;
    this.state = 'playing';
    this.takesFinished++;
  }

  public process(dry: Float32Array, out: Float32Array, offset: number, count: number): void {
    if (this.state === 'recording') {
      const k = Math.min(count, this.maxFrames - this.length);
      for (let i = 0; i < k; i++) {
        this.buf[this.length + i] = dry[offset + i];
      }
      this.length += k;
      for (let i = 0; i < count; i++) {
        out[offset + i] = 0.0;
      }
      if (this.length >= this.maxFrames) {
        this.finishRecording();
      }
    } else if (this.state === 'playing') {
      let i = 0;
      while (i < count) {
        const k = Math.min(count - i, this.length - this.pos);
        for (let j = 0; j < k; j++) {
          out[offset + i + j] = this.buf[this.pos + j];
        }
        i += k;
        this.pos += k;
        if (this.pos >= this.length) {
          this.pos = 0;
        }
      }
    } else {
      for (let i = 0; i < count; i++) {
        out[offset + i] = 0.0;
      }
    }
  }
}

export class PeakLimiter {
  public readonly threshold: number;
  public readonly step: number;
  public gain: number = 1.0;
  private readonly releaseRate: number;

  constructor(threshold: number, samplerate: number, stepFrames: number, releaseMs: number) {
    this.threshold = threshold;
    this.step = stepFrames;
    const tau = (Math.max(releaseMs, 1e-3) / 1000.0) * samplerate;
    this.releaseRate = 1.0 - Math.exp(-this.step / tau);
  }

  public process(x: Float32Array, offset: number, count: number): void {
    const st = this.step;
    for (let s = 0; s < count; s += st) {
      const k = Math.min(st, count - s);
      let peak = 0.0;
      const base = offset + s;
      for (let i = 0; i < k; i++) {
        const val = Math.abs(x[base + i]);
        if (val > peak) peak = val;
      }

      const target = peak > this.threshold ? this.threshold / peak : 1.0;
      const g = this.gain;

      if (target < g) {
        // Fast attack: jump to target gain immediately
        for (let i = 0; i < k; i++) {
          x[base + i] *= target;
        }
        this.gain = target;
      } else {
        // Smooth release ramp toward target
        const newGain = Math.min(target, g + (1.0 - g) * this.releaseRate);
        if (newGain !== g || g !== 1.0) {
          for (let i = 0; i < k; i++) {
            const rampGain = g + ((i + 1) / k) * (newGain - g);
            x[base + i] *= rampGain;
          }
          this.gain = newGain;
        }
      }
    }
  }
}
