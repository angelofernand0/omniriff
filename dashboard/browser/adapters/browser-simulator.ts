/**
 * Browser Simulator Mode Adapter (Mode B).
 * Runs real Web Audio DSP with Karplus-Strong / harmonic guitar synth and synthetic hand choreography.
 * Publishes the shared v1 state/hand shapes; hardware xruns are not measured here.
 */

import { AudioEngine, type WorkletTelemetryState } from '../audio/audio-engine';
import { GestureController } from '../vision/gesture-controller';
import { Setlist } from '../vision/setlist';
import { SimulatedHandModel } from '../simulation/simulated-hand';
import { SimulatorChoreography } from '../simulation/choreography';
import type { StateFrame, HandFrame } from '../protocol/types';
import { absentHand, type ConnectionCallback } from './connection';
import { showSwapToast } from './browser-live';

export class BrowserSimulatorAdapter {
  public readonly modeId = 'simulator' as const;
  public readonly modeLabel = 'BROWSER SIM';

  public readonly audio: AudioEngine;
  public readonly controller: GestureController;
  public readonly setlist: Setlist;
  public readonly hand: SimulatedHandModel;
  public readonly choreography: SimulatorChoreography;

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
    this.setTarget(next);
  }

  public setTarget(next: 'filter' | 'reverb'): void {
    this.gestureTarget = next;
    showSwapToast(next);
    const select = typeof document !== 'undefined' ? document.getElementById('browserTarget') as HTMLSelectElement | null : null;
    if (select) {
      select.value = next;
      select.dispatchEvent(new Event('change'));
    }
  }

  private isGuitarAutoPlucking: boolean = true;
  private isGuitarPausedForLoop: boolean = false;
  private lastLoopState: 'idle' | 'recording' | 'playing' = 'idle';
  private onGuitarStateCb: ((playing: boolean) => void) | null = null;

  public onGuitarState(cb: (playing: boolean) => void): void {
    this.onGuitarStateCb = cb;
  }

  public get isGuitarPlaying(): boolean {
    return this.isGuitarAutoPlucking && !this.isGuitarPausedForLoop;
  }

  public toggleGuitar(): boolean {
    const next = !this.isGuitarPlaying;
    this.isGuitarAutoPlucking = next;
    this.isGuitarPausedForLoop = false; // manual override cancels auto-pause latch
    this.audio.setSynthAuto(next);
    this.onGuitarStateCb?.(next);
    return next;
  }

  public setGuitarPlaying(playing: boolean): void {
    this.isGuitarAutoPlucking = playing;
    this.isGuitarPausedForLoop = false;
    this.audio.setSynthAuto(playing);
    this.onGuitarStateCb?.(playing);
  }

  private animFrameId: number | null = null;
  private isRunning: boolean = false;
  private acceptedEvents: number = 0;
  private lastAcceptedMs: number | null = null;
  private lastStateEmitMs: number = 0;

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
    this.hand = new SimulatedHandModel();
    this.choreography = new SimulatorChoreography(this.hand, this.controller, this.setlist, (target) => {
      if (this.target !== target) {
        this.setTarget(target);
      }
    });

    this.audio.onState((ws) => {
      this.latestWorkletState = ws;
      if (ws.loop.state !== this.lastLoopState) {
        const prev = this.lastLoopState;
        this.lastLoopState = ws.loop.state;
        if (ws.loop.state === 'playing') {
          // Auto-pause guitar playback while listening to the loop
          if (this.isGuitarAutoPlucking && !this.isGuitarPausedForLoop) {
            this.isGuitarPausedForLoop = true;
            this.audio.setSynthAuto(false);
            this.onGuitarStateCb?.(false);
          }
        } else if (prev === 'playing') {
          // Loop stopped or cleared; auto-resume if it was paused for the loop
          if (this.isGuitarPausedForLoop) {
            this.isGuitarPausedForLoop = false;
            this.audio.setSynthAuto(true);
            this.onGuitarStateCb?.(true);
          }
        }
      }
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
    this.hand.present = false;
    this.isGuitarPausedForLoop = false;
    this.lastLoopState = 'idle';
    this.isGuitarAutoPlucking = true;
    this.onGuitarStateCb?.(true);
    try {
      await this.audio.start('synth');
      if (generation !== this.generation) { await this.audio.stop(); return; }
      this.choreography.reset();
      this.isRunning = true;
      this.onConnectionCb?.({ status: 'connected' });
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
    // 1. Advance choreography (or manual virtual controls)
    this.choreography.update(nowMs);

    // 2. Sample observation from simulated hand
    const obs = this.hand.getObservation(nowMs);

    // 3. Update deterministic gesture controller
    const nowSec = nowMs / 1000;
    const ev = this.controller.update(obs.y, obs.pinch, obs.confidence, nowSec, Date.now());

    // 4. Update hand engagement state
    this.hand.engaged = this.controller.active;
    this.hand.value = this.controller.value;
    this.hand.control = this.target === 'scene' ? null : this.controller.control;

    // 5. If controller emitted gesture event, route through Setlist and Audio
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

    // 6. Emit Hand Frame at 60 FPS for smooth rendering
    if (this.onHandCb) {
      this.onHandCb(this.hand.getHandFrame(Date.now()));
    }

    // 7. Emit State Frame throttled at ~25 Hz (every 40ms)
    if (nowMs - this.lastStateEmitMs >= 40) {
      this.lastStateEmitMs = nowMs;
      if (this.onStateCb) {
        this.onStateCb(this.buildStateFrame(Date.now()));
      }
    }
  }

  public buildStateFrame(nowMs: number): StateFrame {
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
          last_seen_ms: this.hand.present ? nowMs : null,
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
    this.isGuitarPausedForLoop = false;
    this.lastLoopState = 'idle';
    this.controller.rearm();
    this.onHandCb?.(absentHand());
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    await this.audio.stop();
    this.onConnectionCb?.({ status: 'stopped' });
  }
}
