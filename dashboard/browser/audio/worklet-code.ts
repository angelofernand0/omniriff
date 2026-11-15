/**
 * Self-contained AudioWorklet processor code for OmniRiff real-time DSP.
 * Runs in AudioWorkletGlobalScope with zero external dependencies.
 * Zero-allocation in process() callback.
 */

export const WORKLET_PROCESSOR_NAME = 'omniriff-dsp-processor';

export const WORKLET_CODE = `
// OmniRiff Real-time DSP AudioWorkletProcessor
// Conforms to protocol/state.schema.json metrics

const COMB_44K = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617];
const ALLPASS_44K = [556, 441, 341, 225];
const INPUT_GAIN = 0.015;
const ALLPASS_FEEDBACK = 0.5;
const PENTATONIC_NOTES = [82.41, 98.00, 110.00, 123.47, 146.83, 164.81, 196.00, 220.00, 246.94];

function dbToGain(db) {
  return Math.pow(10.0, db / 20.0);
}

function gainToDb(gain) {
  return 20.0 * Math.log10(Math.max(gain, 1e-9));
}

function filterCutoffHz(value, minHz, maxHz, samplerate) {
  const v = Math.min(1.0, Math.max(0.0, value));
  const hz = minHz * Math.pow(maxHz / minHz, v);
  return Math.min(hz, 0.45 * samplerate);
}

class DelayLine {
  constructor(length) {
    this.length = Math.max(1, length);
    this.buf = new Float32Array(this.length);
    this.idx = 0;
  }
  clear() {
    this.buf.fill(0);
    this.idx = 0;
  }
}

class LowPass {
  constructor(samplerate, q) {
    this.samplerate = samplerate;
    this.q = q;
    this.cutoffHz = 0;
    this.b0 = 0; this.b1 = 0; this.b2 = 0;
    this.a1 = 0; this.a2 = 0;
    this.z1 = 0; this.z2 = 0;
  }
  setCutoff(cutoffHz) {
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
  process(x, out, offset, count) {
    let z1 = this.z1, z2 = this.z2;
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
  clear() {
    this.z1 = 0;
    this.z2 = 0;
  }
}

class Reverb {
  constructor(samplerate, maxBlock, room, damp) {
    const scale = samplerate / 44100.0;
    this.combs = COMB_44K.map((d) => new DelayLine(Math.floor(d * scale)));
    this.allpasses = ALLPASS_44K.map((d) => new DelayLine(Math.floor(d * scale)));
    this.feedback = room * 0.28 + 0.7;
    this.damp = damp * 0.4;
    this.combZi = new Float32Array(this.combs.length);
    this.scratchIn = new Float32Array(maxBlock);
    this.scratchAcc = new Float32Array(maxBlock);
  }
  process(x, out, offset, count) {
    const n = count;
    const inp = this.scratchIn;
    const acc = this.scratchAcc;
    const d = this.damp;
    const oneMinusD = 1.0 - d;
    const fb = this.feedback;

    for (let i = 0; i < n; i++) {
      inp[i] = x[offset + i] * INPUT_GAIN;
      acc[i] = 0.0;
    }

    for (let j = 0; j < this.combs.length; j++) {
      const comb = this.combs[j];
      const buf = comb.buf;
      const len = comb.length;
      let cIdx = comb.idx;
      let zi = this.combZi[j];

      for (let i = 0; i < n; i++) {
        const delayed = buf[cIdx];
        acc[i] += delayed;
        const damped = oneMinusD * delayed + d * zi;
        zi = damped;
        buf[cIdx] = inp[i] + fb * damped;
        cIdx = (cIdx + 1) % len;
      }
      comb.idx = cIdx;
      this.combZi[j] = zi;
    }

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
  clear() {
    for (const c of this.combs) c.clear();
    for (const a of this.allpasses) a.clear();
    this.combZi.fill(0);
    this.scratchIn.fill(0);
    this.scratchAcc.fill(0);
  }
}

class Looper {
  constructor(maxFrames, fadeFrames) {
    this.maxFrames = maxFrames;
    this.fadeFrames = fadeFrames;
    this.buf = new Float32Array(maxFrames);
    this.length = 0;
    this.pos = 0;
    this.state = 'idle';
  }
  toggle() {
    if (this.state === 'idle') {
      this.length = 0;
      this.pos = 0;
      this.state = 'recording';
    } else if (this.state === 'recording') {
      this.finishRecording();
    } else {
      this.length = 0;
      this.pos = 0;
      this.state = 'idle';
    }
  }
  clear() {
    this.length = 0;
    this.pos = 0;
    this.state = 'idle';
    this.buf.fill(0);
  }
  finishRecording() {
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
    this.state = 'playing';
  }
  process(dry, out, offset, count) {
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

class PeakLimiter {
  constructor(threshold, samplerate, stepFrames, releaseMs) {
    this.threshold = threshold;
    this.step = stepFrames;
    this.gain = 1.0;
    const tau = (Math.max(releaseMs, 1e-3) / 1000.0) * samplerate;
    this.releaseRate = 1.0 - Math.exp(-this.step / tau);
  }
  process(x, offset, count) {
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
        for (let i = 0; i < k; i++) x[base + i] *= target;
        this.gain = target;
      } else {
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

class Smoother {
  constructor(value, timeMs, samplerate, stepFrames) {
    this.value = value;
    const tauFrames = (Math.max(timeMs, 0.0) / 1000.0) * samplerate;
    this.coeff = tauFrames > 0 ? Math.exp(-stepFrames / tauFrames) : 0.0;
  }
  step(target) {
    this.value = target + (this.value - target) * this.coeff;
    if (Math.abs(this.value - target) < 1e-6) this.value = target;
    return this.value;
  }
}

class SyntheticGuitar {
  constructor(samplerate, bpm, seed, level) {
    this.samplerate = samplerate;
    this.bpm = bpm;
    this.level = level;
    this.stepFrames = Math.floor((samplerate * 60.0) / bpm / 2);
    this.rngState = seed;
    this.autoPluck = true;
    this.pos = 0;
    this.nextPluck = 0;
    this.beat = 0;
    this.voices = Array.from({ length: 8 }, () => ({
      freq: 110.0,
      phase: 0.0,
      amp: 0.0,
      decay: 0.999,
      active: false,
    }));
  }
  random() {
    this.rngState = (this.rngState * 1664525 + 1013904223) >>> 0;
    return this.rngState / 4294967296;
  }
  setBpm(bpm) {
    if (!Number.isFinite(bpm)) return;
    this.bpm = Math.max(40, Math.min(240, bpm));
    this.stepFrames = Math.floor((this.samplerate * 60.0) / this.bpm / 2);
  }
  pluck(freqHz, ampScale = 1.0) {
    const freq = freqHz || PENTATONIC_NOTES[Math.floor(this.random() * PENTATONIC_NOTES.length)];
    const amp = this.level * ampScale;
    const decay = Math.exp(-1.0 / (this.samplerate * (0.25 + this.random() * 0.35)));
    let bestIdx = 0, minAmp = Infinity;
    for (let i = 0; i < this.voices.length; i++) {
      if (!this.voices[i].active) { bestIdx = i; break; }
      if (this.voices[i].amp < minAmp) { minAmp = this.voices[i].amp; bestIdx = i; }
    }
    const v = this.voices[bestIdx];
    v.freq = freq;
    v.phase = 0.0;
    v.amp = amp;
    v.decay = decay;
    v.active = true;
  }
  process(out, offset, count) {
    for (let i = 0; i < count; i++) out[offset + i] = 0.0;
    let i = 0;
    while (i < count) {
      if (this.autoPluck && this.pos + i >= this.nextPluck) {
        const accent = this.beat % 8 === 0;
        const rest = this.beat % 8 === 5 || this.random() < 0.12;
        this.beat++;
        if (!rest) {
          const ampScale = accent ? 1.75 : 0.55 + this.random() * 0.45;
          this.pluck(null, ampScale);
        }
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
          const sample = (Math.sin(ph) + 0.45 * Math.sin(2.0 * ph) + 0.2 * Math.sin(3.0 * ph)) / 1.65;
          out[idx] += amp * sample;
          ph += w;
          if (ph > 2.0 * Math.PI) ph -= 2.0 * Math.PI;
          amp *= decay;
        }
        v.phase = ph;
        v.amp = amp;
        if (v.amp < 1e-4) v.active = false;
      }
      i = end;
    }
    this.pos += count;
    for (let j = 0; j < count; j++) {
      const idx = offset + j;
      if (out[idx] > 0.98) out[idx] = 0.98;
      else if (out[idx] < -0.98) out[idx] = -0.98;
    }
  }
}

class OmniRiffDSPProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const sr = sampleRate;
    this.sr = sr;
    // A live node must never emit a synth pluck before its first port message.
    this.sourceMode = options?.processorOptions?.sourceMode === 'synth' ? 'synth' : 'input';
    this.inputChannel = 0;
    this.inputGain = 1.0;
    this.ceiling = dbToGain(-1.0); // 0.89125
    this.targetFilter = 1.0;
    this.targetReverb = 0.0;
    this.bypass = false;
    this.bmix = 0.0;
    this.bstep = 1.0 / Math.max(1.0, (10.0 / 1000.0) * sr); // 10ms bypass fade
    this.blocks = 0;
    this.clipped = 0;
    this.inPeak = 0.0;
    this.outPeak = 0.0;
    this.lastTelemetryMs = 0;

    const maxQuantum = 512;
    this.dryBuf = new Float32Array(maxQuantum);
    this.loopBuf = new Float32Array(maxQuantum);
    this.mixBuf = new Float32Array(maxQuantum);
    this.wetBuf = new Float32Array(maxQuantum);
    this.rvScratch = new Float32Array(maxQuantum);
    this.monoBuf = new Float32Array(maxQuantum);

    this.filterSmoother = new Smoother(1.0, 40.0, sr, 32);
    this.reverbSmoother = new Smoother(0.0, 40.0, sr, 32);
    this.lowPass = new LowPass(sr, 0.9);
    this.lowPass.setCutoff(filterCutoffHz(1.0, 120.0, 18000.0, sr));
    this.reverb = new Reverb(sr, 32, 0.84, 0.5);
    this.looper = new Looper(Math.floor(30.0 * sr), Math.floor((5.0 / 1000.0) * sr));
    this.limiter = new PeakLimiter(this.ceiling * 0.999, sr, 32, 150.0);
    this.synth = new SyntheticGuitar(sr, 92.0, 7, 0.28);

    this.port.onmessage = (e) => {
      const msg = e.data;
      if (!msg) return;
      switch (msg.type) {
        case 'set-filter':
          if (Number.isFinite(msg.value)) this.targetFilter = Math.min(1.0, Math.max(0.0, msg.value));
          break;
        case 'set-reverb':
          if (Number.isFinite(msg.value)) this.targetReverb = Math.min(1.0, Math.max(0.0, msg.value));
          break;
        case 'toggle-bypass':
          this.bypass = !this.bypass;
          break;
        case 'set-bypass':
          this.bypass = !!msg.value;
          break;
        case 'toggle-loop':
          this.looper.toggle();
          break;
        case 'clear-loop':
          this.looper.clear();
          break;
        case 'set-trim':
          if (Number.isFinite(msg.db)) this.inputGain = dbToGain(Math.max(-60.0, Math.min(24.0, msg.db)));
          break;
        case 'set-source-mode':
          if (msg.mode === 'input' || msg.mode === 'synth') this.sourceMode = msg.mode;
          break;
        case 'set-input-channel':
          if (Number.isInteger(msg.channel) && msg.channel >= 0 && msg.channel < 32) this.inputChannel = msg.channel;
          break;
        case 'pluck':
          if (msg.freqHz != null && (!Number.isFinite(msg.freqHz) || msg.freqHz <= 0 || msg.freqHz > this.sr * 0.45)) break;
          if (msg.ampScale != null && (!Number.isFinite(msg.ampScale) || msg.ampScale < 0)) break;
          this.synth.pluck(msg.freqHz, Math.min(2.0, msg.ampScale ?? 1.0));
          break;
        case 'set-synth-auto':
          this.synth.autoPluck = !!msg.auto;
          break;
        case 'set-synth-bpm':
          this.synth.setBpm(msg.bpm);
          break;
      }
    };
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];
    if (!output || output.length === 0) return true;
    const count = output[0].length;
    const sr = this.sr;

    // 1. Gather dry signal
    let curInPeak = 0.0;
    if (this.sourceMode === 'input') {
      const inCh = inputs[0]?.[this.inputChannel];
      const g = this.inputGain;
      for (let i = 0; i < count; i++) {
        // Missing/disconnected input or an unavailable selected channel is silence.
        // Do not substitute another physical channel or the simulator.
        const raw = inCh ? inCh[i] * g : 0.0;
        const s = Number.isFinite(raw) ? Math.max(-32.0, Math.min(32.0, raw)) : 0.0;
        this.dryBuf[i] = s;
        const absS = Math.abs(s);
        if (absS > curInPeak) curInPeak = absS;
      }
    } else {
      this.synth.process(this.dryBuf, 0, count);
      for (let i = 0; i < count; i++) {
        const absS = Math.abs(this.dryBuf[i]);
        if (absS > curInPeak) curInPeak = absS;
      }
    }

    // 2. Looper processing
    this.looper.process(this.dryBuf, this.loopBuf, 0, count);

    // 3. Mix = dry + loop
    for (let i = 0; i < count; i++) {
      this.mixBuf[i] = this.dryBuf[i] + this.loopBuf[i];
    }

    // 4. Subblock DSP (32 frames per step)
    const st = 32;
    for (let s = 0; s < count; s += st) {
      const k = Math.min(st, count - s);
      const v = this.filterSmoother.step(this.targetFilter);
      this.lowPass.setCutoff(filterCutoffHz(v, 120.0, 18000.0, sr));
      this.lowPass.process(this.mixBuf, this.wetBuf, s, k);

      const rvAmount = this.reverbSmoother.step(this.targetReverb);
      this.reverb.process(this.wetBuf, this.rvScratch, s, k);
      if (rvAmount > 0.0) {
        const scale = rvAmount * 2.0;
        for (let j = 0; j < k; j++) {
          this.wetBuf[s + j] += this.rvScratch[s + j] * scale;
        }
      }
    }

    // 5. Bypass ramp
    const targetBypass = this.bypass ? 1.0 : 0.0;
    for (let i = 0; i < count; i++) {
      if (this.bmix < targetBypass) {
        this.bmix = Math.min(targetBypass, this.bmix + this.bstep);
      } else if (this.bmix > targetBypass) {
        this.bmix = Math.max(targetBypass, this.bmix - this.bstep);
      }
      const b = this.bmix;
      // mono = wet + (mix - wet) * b = mix * b + wet * (1 - b)
      this.monoBuf[i] = this.wetBuf[i] + (this.mixBuf[i] - this.wetBuf[i]) * b;
    }

    // 6. Limiter & Safety Clip
    this.limiter.process(this.monoBuf, 0, count);
    let curOutPeak = 0.0;
    const ceil = this.ceiling;

    for (let i = 0; i < count; i++) {
      let val = this.monoBuf[i];
      const absVal = Math.abs(val);
      if (absVal > ceil) {
        this.clipped++;
        val = val > 0 ? ceil : -ceil;
        this.monoBuf[i] = val;
      }
      if (absVal > curOutPeak) curOutPeak = absVal;
    }

    // 7. Route to outputs
    const ch0 = output[0];
    const ch1 = output.length > 1 ? output[1] : null;
    for (let i = 0; i < count; i++) {
      const s = this.monoBuf[i];
      ch0[i] = s;
      if (ch1) ch1[i] = s;
    }

    // 8. Meter decays
    const d = 0.9;
    this.inPeak = Math.max(curInPeak, this.inPeak * d);
    this.outPeak = Math.max(curOutPeak, this.outPeak * d);
    this.blocks++;

    // 9. Throttled telemetry to main thread (~20 Hz)
    const now = currentTime * 1000;
    if (now - this.lastTelemetryMs >= 48) {
      this.lastTelemetryMs = now;
      this.port.postMessage({
        type: 'state',
        samplerate: sr,
        bypass: this.bypass,
        loop: {
          state: this.looper.state,
          seconds: this.looper.length / sr,
          max_seconds: 30.0,
        },
        filter: {
          target: this.targetFilter,
          value: this.filterSmoother.value,
          cutoff_hz: this.lowPass.cutoffHz,
        },
        reverb: {
          target: this.targetReverb,
          value: this.reverbSmoother.value,
          dsp: true,
        },
        input_peak_dbfs: gainToDb(this.inPeak),
        output_peak_dbfs: gainToDb(this.outPeak),
        clipped_samples: this.clipped,
        blocks: this.blocks,
      });
    }

    return true;
  }
}

registerProcessor('omniriff-dsp-processor', OmniRiffDSPProcessor);
`;
