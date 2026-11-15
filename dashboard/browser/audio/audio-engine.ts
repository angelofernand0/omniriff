/**
 * Main-thread AudioEngine interface.
 * Coordinates AudioContext, AudioWorkletNode, media streams, and device routing.
 */

import { WORKLET_CODE, WORKLET_PROCESSOR_NAME } from './worklet-code';
import type { LoopState, FilterState, ReverbState } from '../protocol/types';

export interface WorkletTelemetryState {
  samplerate: number;
  bypass: boolean;
  loop: LoopState;
  filter: FilterState;
  reverb: ReverbState;
  input_peak_dbfs: number;
  output_peak_dbfs: number;
  clipped_samples: number;
  blocks: number;
}

export type StateCallback = (state: WorkletTelemetryState) => void;

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private masterGain: GainNode | null = null;
  private mediaStreamSource: MediaStreamAudioSourceNode | null = null;
  private currentStream: MediaStream | null = null;
  private onStateCallback: StateCallback | null = null;
  private starting: Promise<void> | null = null;
  private generation = 0;

  public isRunning: boolean = false;
  public isMuted: boolean = false;
  public mode: 'synth' | 'input' = 'synth';

  constructor() {}

  public get context(): AudioContext | null {
    return this.ctx;
  }

  public get sampleRate(): number {
    return this.ctx ? this.ctx.sampleRate : 48000;
  }

  public get baseLatency(): number {
    return this.ctx && 'baseLatency' in this.ctx ? (this.ctx as any).baseLatency : 0;
  }

  public get outputLatency(): number {
    return this.ctx && 'outputLatency' in this.ctx ? (this.ctx as any).outputLatency : 0;
  }

  public async start(mode: 'synth' | 'input' = 'synth', inputStream?: MediaStream): Promise<void> {
    this.requireInput(mode, inputStream);
    if (this.starting) await this.starting;
    if (this.isRunning) {
      await this.setSourceMode(mode, inputStream);
      return;
    }

    const task = this.initialize(mode, inputStream);
    this.starting = task;
    try {
      await task;
    } finally {
      if (this.starting === task) this.starting = null;
    }
  }

  private requireInput(mode: 'synth' | 'input', stream?: MediaStream): void {
    if (mode !== 'synth' && mode !== 'input') throw new Error('Unknown audio source mode.');
    if (mode === 'input' && (!stream || !stream.getAudioTracks().some((track) => track.readyState === 'live'))) {
      throw new Error('Live audio input requires an active audio stream.');
    }
  }

  private async initialize(mode: 'synth' | 'input', inputStream?: MediaStream): Promise<void> {
    // Explicit user action context creation
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    let ctx: AudioContext;
    try {
      if (!AudioContextClass) throw new Error('Web Audio API is not supported in this browser.');
      ctx = new AudioContextClass({ latencyHint: 'interactive' });
    } catch (error) {
      if (mode === 'input') inputStream?.getTracks().forEach((track) => track.stop());
      throw error;
    }
    const generation = ++this.generation;
    this.ctx = ctx;
    this.currentStream = mode === 'input' ? inputStream! : null;
    const checkCurrent = () => {
      if (this.ctx !== ctx || generation !== this.generation) throw new Error('Audio startup was stopped.');
    };
    try {
      if (!ctx.audioWorklet || typeof AudioWorkletNode !== 'function') {
        throw new Error('This browser cannot run AudioWorklet. Open the simulator in a current browser over HTTPS.');
      }
      if (ctx.state === 'suspended') await ctx.resume();
      checkCurrent();

      // Load worklet from self-contained Blob URL, including cleanup on failure.
      const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
      const blobUrl = URL.createObjectURL(blob);
      try {
        await ctx.audioWorklet.addModule(blobUrl);
      } finally {
        URL.revokeObjectURL(blobUrl);
      }
      checkCurrent();

      // Preserve the user's mute preference across mode restarts.
      this.masterGain = ctx.createGain();
      this.masterGain.gain.setValueAtTime(this.isMuted ? 0.0 : 1.0, ctx.currentTime);

      // Configure the source before the node can produce its first output block.
      this.workletNode = new AudioWorkletNode(ctx, WORKLET_PROCESSOR_NAME, {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [2],
        processorOptions: { sourceMode: mode },
      });

      this.workletNode.port.onmessage = (e) => {
        const msg = e.data;
        if (msg && msg.type === 'state' && this.onStateCallback) this.onStateCallback(msg);
      };

      await this.setSourceMode(mode, inputStream);
      checkCurrent();
      this.workletNode.connect(this.masterGain);
      this.masterGain.connect(ctx.destination);
      this.isRunning = true;
    } catch (error) {
      if (this.ctx === ctx) await this.stop();
      throw error;
    }
  }

  public async setSourceMode(mode: 'synth' | 'input', stream?: MediaStream): Promise<void> {
    this.requireInput(mode, stream);
    if (!this.workletNode) return;

    const nextSource = mode === 'input' ? this.ctx!.createMediaStreamSource(stream!) : null;
    try {
      nextSource?.connect(this.workletNode);
    } catch (error) {
      nextSource?.disconnect();
      throw error;
    }
    this.mediaStreamSource?.disconnect();
    const nextStream = mode === 'input' ? stream! : null;
    if (this.currentStream && this.currentStream !== nextStream) this.currentStream.getTracks().forEach((track) => track.stop());
    this.mediaStreamSource = nextSource;
    this.currentStream = nextStream;
    this.mode = mode;
    this.workletNode.port.postMessage({ type: 'set-source-mode', mode });
  }

  public setFilter(value: number): void {
    if (!Number.isFinite(value)) return;
    value = Math.max(0, Math.min(1, value));
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-filter', value });
    }
  }

  public setReverb(value: number): void {
    if (!Number.isFinite(value)) return;
    value = Math.max(0, Math.min(1, value));
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-reverb', value });
    }
  }

  public toggleBypass(): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'toggle-bypass' });
    }
  }

  public setBypass(value: boolean): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-bypass', value });
    }
  }

  public toggleLoop(): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'toggle-loop' });
    }
  }

  public clearLoop(): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'clear-loop' });
    }
  }

  public setInputTrim(db: number): void {
    if (!Number.isFinite(db)) return;
    db = Math.max(-60, Math.min(24, db));
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-trim', db });
    }
  }

  public setInputChannel(channel: number): void {
    if (!Number.isInteger(channel) || channel < 0 || channel >= 32) return;
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-input-channel', channel });
    }
  }

  public pluck(freqHz?: number, ampScale: number = 1.0): void {
    if (freqHz !== undefined && (!Number.isFinite(freqHz) || freqHz <= 0 || freqHz > this.sampleRate * 0.45)) return;
    if (!Number.isFinite(ampScale) || ampScale < 0) return;
    ampScale = Math.min(2, ampScale);
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'pluck', freqHz, ampScale });
    }
  }

  public setSynthAuto(auto: boolean): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-synth-auto', auto });
    }
  }

  public setSynthBpm(bpm: number): void {
    if (!Number.isFinite(bpm)) return;
    bpm = Math.max(40, Math.min(240, bpm));
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-synth-bpm', bpm });
    }
  }

  public toggleMute(): boolean {
    if (!this.masterGain || !this.ctx) return false;
    this.isMuted = !this.isMuted;
    this.masterGain.gain.setValueAtTime(this.isMuted ? 0.0 : 1.0, this.ctx.currentTime);
    return this.isMuted;
  }

  public onState(callback: StateCallback): void {
    this.onStateCallback = callback;
  }

  public async stop(): Promise<void> {
    this.generation++;
    this.isRunning = false;
    if (this.mediaStreamSource) {
      this.mediaStreamSource.disconnect();
      this.mediaStreamSource = null;
    }
    if (this.currentStream) {
      this.currentStream.getTracks().forEach((t) => t.stop());
      this.currentStream = null;
    }
    if (this.workletNode) {
      this.workletNode.port.onmessage = null;
      this.workletNode.port.close();
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.masterGain) {
      this.masterGain.disconnect();
      this.masterGain = null;
    }
    const closingContext = this.ctx;
    this.ctx = null;
    if (closingContext) {
      try {
        await closingContext.close();
      } catch (e) {
        // ignore close error
      }
    }
  }
}
