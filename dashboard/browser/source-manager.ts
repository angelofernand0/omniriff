/**
 * Unified Source Manager for OmniRiff.
 * Manages the three operating modes:
 *   Mode A: LIVE RIG (Browser Live)
 *   Mode B: BROWSER SIM (Browser Simulator - Default)
 *   Mode C: PYTHON BRIDGE (Local Python Engine)
 * Ensures strictly one active engine at a time.
 */

import { BrowserSimulatorAdapter } from './adapters/browser-simulator';
import { BrowserLiveAdapter } from './adapters/browser-live';
import { PythonBridgeAdapter } from './adapters/python-bridge';
import type { StateFrame, HandFrame } from './protocol/types';

export type OperatingMode = 'simulator' | 'live' | 'python';

export interface SourceModeChangeInfo {
  mode: OperatingMode;
  label: string;
}

export class SourceManager {
  private activeAdapter: BrowserSimulatorAdapter | BrowserLiveAdapter | PythonBridgeAdapter | null = null;
  public activeMode: OperatingMode | null = null;

  public readonly simulator = new BrowserSimulatorAdapter();
  public readonly live = new BrowserLiveAdapter();
  public readonly python = new PythonBridgeAdapter();

  private onStateCallbacks: Array<(frame: StateFrame) => void> = [];
  private onHandCallbacks: Array<(frame: HandFrame) => void> = [];
  private onModeChangeCallbacks: Array<(info: SourceModeChangeInfo) => void> = [];

  constructor() {
    // Wire adapters to dispatcher
    const handleState = (frame: StateFrame) => {
      for (const cb of this.onStateCallbacks) cb(frame);
    };
    const handleHand = (frame: HandFrame) => {
      for (const cb of this.onHandCallbacks) cb(frame);
    };

    this.simulator.onState(handleState);
    this.simulator.onHand(handleHand);

    this.live.onState(handleState);
    this.live.onHand(handleHand);

    this.python.onState(handleState);
    this.python.onHand(handleHand);
  }

  public get currentAdapter() {
    return this.activeAdapter;
  }

  public async setMode(mode: OperatingMode): Promise<void> {
    if (this.activeMode === mode && this.activeAdapter) return;

    // 1. Gracefully stop current active engine
    if (this.activeAdapter) {
      await this.activeAdapter.stop();
      this.activeAdapter = null;
    }

    this.activeMode = mode;

    // 2. Start newly selected mode
    if (mode === 'simulator') {
      this.activeAdapter = this.simulator;
      await this.simulator.start();
    } else if (mode === 'live') {
      this.activeAdapter = this.live;
      await this.live.start();
    } else if (mode === 'python') {
      this.activeAdapter = this.python;
      await this.python.start();
    }

    // 3. Notify listeners
    if (this.activeAdapter) {
      const info: SourceModeChangeInfo = {
        mode,
        label: this.activeAdapter.modeLabel,
      };
      for (const cb of this.onModeChangeCallbacks) cb(info);
    }
  }

  public async stop(): Promise<void> {
    if (this.activeAdapter) {
      await this.activeAdapter.stop();
      this.activeAdapter = null;
      this.activeMode = null;
    }
  }

  public onState(cb: (frame: StateFrame) => void): void {
    this.onStateCallbacks.push(cb);
  }

  public onHand(cb: (frame: HandFrame) => void): void {
    this.onHandCallbacks.push(cb);
  }

  public onModeChange(cb: (info: SourceModeChangeInfo) => void): void {
    this.onModeChangeCallbacks.push(cb);
  }

  // Delegated manual controls to active adapter
  public sendControl(control: string, value?: number): boolean {
    return this.activeAdapter ? this.activeAdapter.sendControl(control, value) : false;
  }

  public setFilter(v: number): void {
    this.activeAdapter?.setFilter(v);
  }

  public setReverb(v: number): void {
    this.activeAdapter?.setReverb(v);
  }

  public toggleBypass(): void {
    this.activeAdapter?.toggleBypass();
  }

  public toggleLoop(): void {
    this.activeAdapter?.toggleLoop();
  }

  public clearLoop(): void {
    this.activeAdapter?.clearLoop();
  }
}
