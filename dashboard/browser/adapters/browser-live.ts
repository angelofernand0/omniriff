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
import { absentHand, type ConnectionCallback } from './connection';

export function showSwapToast(control: 'filter' | 'reverb'): void {
  if (typeof document === 'undefined') return;
  const toast = document.getElementById('swapToast');
  const text = document.getElementById('swapToastText');
  if (toast && text) {
    text.textContent = `SWAPPED TO ${control.toUpperCase()}`;
    toast.hidden = false;
    toast.classList.remove('swap-toast-pop');
    void toast.offsetWidth; // re-flow to restart CSS animation
    toast.classList.add('swap-toast-pop');
    if ((toast as any)._timer) clearTimeout((toast as any)._timer);
    (toast as any)._timer = setTimeout(() => {
      toast.hidden = true;
      toast.classList.remove('swap-toast-pop');
      (toast as any)._timer = null;
    }, 1400);
  }
}

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

  private generation = 0;
  private starting: Promise<void> | null = null;
  private onConnectionCb: ConnectionCallback | null = null;
  private target: 'filter' | 'reverb' | 'scene' = 'filter';
  public get gestureTarget(): 'filter' | 'reverb' | 'scene' { return this.target; }
  public set gestureTarget(value: 'filter' | 'reverb' | 'scene') {
    if (!['filter', 'reverb', 'scene'].includes(value)) throw new Error('Unknown gesture target');
    if (this.target === value) return;
    this.target = value;
    this.controller.control = value === 'reverb' ? 'reverb' : 'filter';
    this.controller.rearm();
  }

  public swapTarget(): void {
    const next = this.target === 'filter' ? 'reverb' : 'filter';
    this.gestureTarget = next;
    const select = document.getElementById('browserTarget') as HTMLSelectElement | null;
    if (select) {
      select.value = next;
      select.dispatchEvent(new Event('change'));
    }
    showSwapToast(next);
  }

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
    this.tracker.onFistSwap = () => {
      this.swapTarget();
    };
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
    if (this.starting) {
      await this.starting;
      if (!this.isRunning) return this.start();
      return;
    }
    const pending = this.startRun(++this.generation);
    this.starting = pending;
    try { await pending; } finally { if (this.starting === pending) this.starting = null; }
  }

  private async startRun(generation: number): Promise<void> {
    this.onConnectionCb?.({ status: 'starting' });
    this.controller.rearm();
    this.acceptedEvents = 0;
    this.lastAcceptedMs = null;
    this.lastStateEmitMs = 0;
    try {
      await this.devices.enumerate();
      if (generation !== this.generation) return;
      const audioStream = await this.devices.getAudioStream();
      if (generation !== this.generation) { audioStream.getTracks().forEach(t => t.stop()); return; }
      this.audioStream = audioStream;
      await this.audio.start('input', audioStream);
      if (generation !== this.generation) { await this.audio.stop(); return; }
      this.audio.setInputChannel(this.devices.selectedChannel);
      let cameraWarning: string | undefined;
      try {
        const videoStream = await this.devices.getVideoStream();
        if (generation !== this.generation) { videoStream.getTracks().forEach(t => t.stop()); return; }
        this.videoStream = videoStream;
        await this.tracker.start(videoStream);
      } catch (error) {
        this.tracker.stop();
        this.videoStream?.getTracks().forEach(t => t.stop());
        this.videoStream = null;
        cameraWarning = 'Camera unavailable; manual audio controls remain available';
      }
      if (generation !== this.generation) return;
      this.isRunning = true;
      this.onConnectionCb?.({ status: 'connected', ...(cameraWarning ? { message: cameraWarning } : {}) });
      const loop = (nowMs: number) => {
        if (!this.isRunning || generation !== this.generation) return;
        this.step(nowMs);
        this.animFrameId = requestAnimationFrame(loop);
      };
      this.animFrameId = requestAnimationFrame(loop);
    } catch (error) {
      if (generation === this.generation) {
        await this.stop();
        this.onConnectionCb?.({ status: 'error', message: String(error) });
      }
      throw error;
    }
  }

  private step(nowMs: number): void {
    // 1. Update MediaPipe inference
    if (this.tracker.isRunning) {
      this.tracker.update(nowMs, this.controller.active, this.controller.control, this.controller.value);
    }

    // 2. Sample latest observation from tracker
    const observed = this.tracker.getObservation();
    const fresh = this.tracker.isRunning && nowMs - observed.timestamp_ms >= 0 && nowMs - observed.timestamp_ms <= 250;
    const obs = fresh ? observed : { y: null, pinch: null, confidence: 0 };

    // 3. Update gesture controller
    const nowSec = nowMs / 1000;
    const ev = this.controller.update(obs.y, obs.pinch, obs.confidence, nowSec, Date.now());

    // 4. Route events to Setlist and AudioWorklet
    if (ev) {
      this.acceptedEvents++;
      this.lastAcceptedMs = Date.now();

      const morphedEvents = this.target === 'scene' ? this.setlist.current.events(ev) : [ev];
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
      const hand = fresh ? this.tracker.getHandFrame() : absentHand();
      this.onHandCb({ ...hand, engaged: fresh && this.controller.active,
        control: this.target === 'scene' ? null : this.controller.control, value: this.controller.value });
    }

    // 6. Emit State Frame throttled at ~25 Hz
    if (nowMs - this.lastStateEmitMs >= 40) {
      this.lastStateEmitMs = nowMs;
      if (this.onStateCb) {
        this.onStateCb(this.buildStateFrame(Date.now(), obs.confidence));
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
          session: 0,
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
    if (!this.isRunning) return false;
    if (control === 'loop') {
      this.audio.toggleLoop();
      return true;
    }
    if (control === 'bypass') {
      this.audio.toggleBypass();
      return true;
    }
    if (control === 'filter' && typeof value === 'number' && Number.isFinite(value)) {
      this.audio.setFilter(Math.min(1, Math.max(0, value)));
      return true;
    }
    if (control === 'reverb' && typeof value === 'number' && Number.isFinite(value)) {
      this.audio.setReverb(Math.min(1, Math.max(0, value)));
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

  public onConnection(cb: ConnectionCallback): void { this.onConnectionCb = cb; }

  public async stop(): Promise<void> {
    ++this.generation;
    this.isRunning = false;
    this.controller.rearm();
    this.onHandCb?.(absentHand());
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
    this.onConnectionCb?.({ status: 'stopped' });
  }
}
