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
    if (this.isRunning) {
      await this.setSourceMode(mode, inputStream);
      return;
    }

    // Explicit user action context creation
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) {
      throw new Error('Web Audio API is not supported in this browser.');
    }

    this.ctx = new AudioContextClass({ latencyHint: 'interactive' });
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }

    // Load worklet from self-contained Blob URL
    const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
    const blobUrl = URL.createObjectURL(blob);
    try {
      await this.ctx.audioWorklet.addModule(blobUrl);
    } finally {
      URL.revokeObjectURL(blobUrl);
    }

    // Master gain for safety & instant mute
    this.masterGain = this.ctx.createGain();
    this.masterGain.gain.setValueAtTime(1.0, this.ctx.currentTime);
    this.masterGain.connect(this.ctx.destination);

    // Create Worklet Node with 1 input (stereo/mono) and 1 output (stereo)
    this.workletNode = new AudioWorkletNode(this.ctx, WORKLET_PROCESSOR_NAME, {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [2],
    });

    this.workletNode.connect(this.masterGain);

    this.workletNode.port.onmessage = (e) => {
      const msg = e.data;
      if (msg && msg.type === 'state' && this.onStateCallback) {
        this.onStateCallback(msg);
      }
    };

    this.isRunning = true;
    this.mode = mode;

    await this.setSourceMode(mode, inputStream);
  }

  public async setSourceMode(mode: 'synth' | 'input', stream?: MediaStream): Promise<void> {
    this.mode = mode;
    if (!this.workletNode) return;

    if (mode === 'input' && stream) {
      this.currentStream = stream;
      if (this.ctx) {
        if (this.mediaStreamSource) {
          this.mediaStreamSource.disconnect();
        }
        this.mediaStreamSource = this.ctx.createMediaStreamSource(stream);
        this.mediaStreamSource.connect(this.workletNode);
      }
      this.workletNode.port.postMessage({ type: 'set-source-mode', mode: 'input' });
    } else {
      if (this.mediaStreamSource) {
        this.mediaStreamSource.disconnect();
        this.mediaStreamSource = null;
      }
      this.workletNode.port.postMessage({ type: 'set-source-mode', mode: 'synth' });
    }
  }

  public setFilter(value: number): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-filter', value });
    }
  }

  public setReverb(value: number): void {
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
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-trim', db });
    }
  }

  public setInputChannel(channel: number): void {
    if (this.workletNode) {
      this.workletNode.port.postMessage({ type: 'set-input-channel', channel });
    }
  }

  public pluck(freqHz?: number, ampScale: number = 1.0): void {
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
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.masterGain) {
      this.masterGain.disconnect();
      this.masterGain = null;
    }
    if (this.ctx) {
      try {
        await this.ctx.close();
      } catch (e) {
        // ignore close error
      }
      this.ctx = null;
    }
  }
}
