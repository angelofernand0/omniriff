/**
 * Browser Live Rig Mode Adapter (Mode A).
 * Hardware Audio Input (Scarlett Solo / USB interface / mic) + MediaPipe webcam tracking.
 */

import { AudioEngine, type WorkletTelemetryState } from '../audio/audio-engine';
import { DeviceManager } from '../audio/devices';
import { LiveHandTracker } from '../vision/hand-tracker';
import { GestureController } from '../vision/gesture-controller';
import { Setlist } from '../vision/setlist';
import type { StateFrame, HandFrame } from '../protocol/types';

export class BrowserLiveAdapter {
  public readonly modeId = 'live' as const;
  public readonly modeLabel = 'LIVE RIG';

  public readonly audio: AudioEngine;
  public readonly devices: DeviceManager;
  public readonly tracker: LiveHandTracker;
  public readonly controller: GestureController;
  public readonly setlist: Setlist;

  private onStateCb: ((frame: StateFrame) => void) | null = null;
  private onHandCb: ((frame: HandFrame) => void) | null = null;

  private animFrameId: number | null = null;
  public isRunning: boolean = false;
  private acceptedEvents: number = 0;
  private lastAcceptedMs: number | null = null;
  private lastStateEmitMs: number = 0;

  private audioStream: MediaStream | null = null;
  private videoStream: MediaStream | null = null;

  private latestWorkletState: WorkletTelemetryState = {
    samplerate: 48000,
    bypass: false,
    loop: { state: 'idle', seconds: 0, max_seconds: 30 },
    filter: { target: 1.0, value: 1.0, cutoff_hz: 18000 },
    reverb: { target: 0.0, value: 0.0, dsp: true },
    input_peak_dbfs: -60,
    output_peak_dbfs: -60,
    clipped_samples: 0,
    blocks: 0,
  };

  constructor() {
    this.audio = new AudioEngine();
    this.devices = new DeviceManager();
    this.tracker = new LiveHandTracker();
    this.controller = new GestureController({
      low: 0.8,
      high: 0.2,
      rate: 20.0,
      confidence: 0.6,
      deadband: 0.015,
      tau: 0.12,
      control: 'filter',
    });
    this.setlist = new Setlist();

    this.audio.onState((ws) => {
      this.latestWorkletState = ws;
    });
  }

  public async start(): Promise<void> {
    if (this.isRunning) return;

    // 1. Enumerate and acquire audio stream upon explicit user gesture
    await this.devices.enumerate();
    this.audioStream = await this.devices.getAudioStream();

    // 2. Start audio engine with hardware input stream
    await this.audio.start('input', this.audioStream);
    this.audio.setInputChannel(this.devices.selectedChannel);

    // 3. Acquire webcam stream
    try {
      this.videoStream = await this.devices.getVideoStream();
      await this.tracker.start(this.videoStream);
    } catch (camErr) {
      console.warn('Webcam initialization failed or was declined; manual controls remain active:', camErr);
    }

    this.isRunning = true;

    const loop = (nowMs: number) => {
      if (!this.isRunning) return;
      this.step(nowMs);
      this.animFrameId = requestAnimationFrame(loop);
    };
    this.animFrameId = requestAnimationFrame(loop);
  }

  private step(nowMs: number): void {
    // 1. Update MediaPipe inference
    if (this.tracker.isRunning) {
      this.tracker.update(nowMs, this.controller.active, this.controller.control, this.controller.value);
    }

    // 2. Sample latest observation from tracker
    const obs = this.tracker.getObservation();

    // 3. Update gesture controller
    const nowSec = nowMs / 1000;
    const ev = this.controller.update(obs.y, obs.pinch, obs.confidence, nowSec, Math.floor(nowMs));

    // 4. Route events to Setlist and AudioWorklet
    if (ev) {
      this.acceptedEvents++;
      this.lastAcceptedMs = Math.floor(nowMs);

      const morphedEvents = this.setlist.current.events(ev);
      for (const mev of morphedEvents) {
        if (mev.control === 'filter') {
          this.audio.setFilter(mev.value);
        } else if (mev.control === 'reverb') {
          this.audio.setReverb(mev.value);
        }
      }
    }

    // 5. Emit Hand Frame
    if (this.onHandCb) {
      this.onHandCb(this.tracker.getHandFrame());
    }

    // 6. Emit State Frame throttled at ~25 Hz
    if (nowMs - this.lastStateEmitMs >= 40) {
      this.lastStateEmitMs = nowMs;
      if (this.onStateCb) {
        this.onStateCb(this.buildStateFrame(Math.floor(nowMs), obs.confidence));
      }
    }
  }

  public buildStateFrame(nowMs: number, handConfidence: number): StateFrame {
    const ws = this.latestWorkletState;
    return {
      version: 1,
      timestamp_ms: nowMs,
      samplerate: this.audio.sampleRate,
      bypass: ws.bypass,
      loop: { ...ws.loop },
      filter: { ...ws.filter },
      reverb: { ...ws.reverb },
      input_peak_dbfs: ws.input_peak_dbfs,
      output_peak_dbfs: ws.output_peak_dbfs,
      xruns: 0,
      clipped_samples: ws.clipped_samples,
      blocks: ws.blocks,
      events: {
        accepted: this.acceptedEvents,
        rejected: 0,
        low_confidence: 0,
      },
      controls: {
        accepted: this.acceptedEvents,
        invalid: 0,
        stale: 0,
        future: 0,
        duplicate: 0,
        low_confidence: 0,
        audio_rejected: 0,
      },
      sources: {
        vision: {
          last_seen_ms: this.tracker.isRunning && handConfidence > 0 ? nowMs : null,
          last_accepted_ms: this.lastAcceptedMs,
          accepted: this.acceptedEvents,
          dropped: 0,
          confidence: handConfidence > 0 ? handConfidence : null,
        },
      },
      adapters: {
        udp: { status: 'disabled', errors: 0, last_error: null },
        serial: { status: 'disabled', errors: 0, last_error: null },
        websocket: { status: 'disabled', errors: 0, last_error: null },
      },
    };
  }

  public onState(cb: (frame: StateFrame) => void): void {
    this.onStateCb = cb;
  }

  public onHand(cb: (frame: HandFrame) => void): void {
    this.onHandCb = cb;
  }

  public sendControl(control: string, value?: number): boolean {
    if (control === 'loop') {
      this.audio.toggleLoop();
      return true;
    }
    if (control === 'bypass') {
      this.audio.toggleBypass();
      return true;
    }
    if (control === 'filter' && typeof value === 'number') {
      this.audio.setFilter(value);
      return true;
    }
    if (control === 'reverb' && typeof value === 'number') {
      this.audio.setReverb(value);
      return true;
    }
    return false;
  }

  public setFilter(v: number): void {
    this.audio.setFilter(v);
  }

  public setReverb(v: number): void {
    this.audio.setReverb(v);
  }

  public toggleBypass(): void {
    this.audio.toggleBypass();
  }

  public toggleLoop(): void {
    this.audio.toggleLoop();
  }

  public clearLoop(): void {
    this.audio.clearLoop();
  }

  public async stop(): Promise<void> {
    this.isRunning = false;
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    this.tracker.stop();
    if (this.audioStream) {
      this.audioStream.getTracks().forEach((t) => t.stop());
      this.audioStream = null;
    }
    if (this.videoStream) {
      this.videoStream.getTracks().forEach((t) => t.stop());
      this.videoStream = null;
    }
    await this.audio.stop();
  }
}
