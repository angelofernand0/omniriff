/** Serializes source transitions. Only the current, successfully started adapter can publish frames. */
import { BrowserSimulatorAdapter } from './adapters/browser-simulator';
import { BrowserLiveAdapter } from './adapters/browser-live';
import { PythonBridgeAdapter } from './adapters/python-bridge';
import { absentHand, type AdapterConnection } from './adapters/connection';
import { WebSerialPedalAdapter } from './adapters/web-serial';
import { PedalTaps, coachTalk } from './adapters/pedal-taps';
import type { StateFrame, HandFrame } from './protocol/types';

export type OperatingMode = 'simulator' | 'live' | 'python';
export interface SourceModeChangeInfo { mode: OperatingMode; label: string }
export interface SourceConnectionInfo extends AdapterConnection { mode: OperatingMode | null }

type Adapters = { simulator: BrowserSimulatorAdapter; live: BrowserLiveAdapter; python: PythonBridgeAdapter };
type Adapter = Adapters[OperatingMode];

export class SourceManager {
  public readonly simulator: BrowserSimulatorAdapter;
  public readonly live: BrowserLiveAdapter;
  public readonly python: PythonBridgeAdapter;
  public readonly pedal: WebSerialPedalAdapter;
  /** Pedal taps: single = loop, double = talk to Riff. */
  public readonly pedalTaps = new PedalTaps(() => { this.sendControl('loop'); }, coachTalk);
  public activeMode: OperatingMode | null = null;
  private activeAdapter: Adapter | null = null;
  private ready = false;
  private request = 0;
  private transition: Promise<void> = Promise.resolve();
  private connection: SourceConnectionInfo = { mode: null, status: 'stopped' };
  private onStateCallbacks: Array<(frame: StateFrame) => void> = [];
  private onHandCallbacks: Array<(frame: HandFrame) => void> = [];
  private onModeChangeCallbacks: Array<(info: SourceModeChangeInfo) => void> = [];
  private onConnectionCallbacks: Array<(info: SourceConnectionInfo) => void> = [];

  constructor(adapters: Partial<Adapters> = {}) {
    this.simulator = adapters.simulator ?? new BrowserSimulatorAdapter();
    this.live = adapters.live ?? new BrowserLiveAdapter();
    this.python = adapters.python ?? new PythonBridgeAdapter();
    this.pedal = new WebSerialPedalAdapter();
    this.live.pedal = this.pedal;
    this.simulator.pedal = this.pedal;
    this.pedal.onAction(action => {
      if (action === 'loop') this.pedalTaps.tap();
      else if (action === 'bypass') this.sendControl('bypass');
      else if (action === 'practice') {
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new KeyboardEvent('keydown', { key: 'y' }));
        }
      }
    });
    for (const mode of ['simulator', 'live', 'python'] as const) {
      const adapter = this[mode];
      adapter.onState(frame => {
        if (this.activeAdapter === adapter && this.ready) this.onStateCallbacks.forEach(cb => cb(frame));
      });
      adapter.onHand(frame => {
        if (this.activeAdapter === adapter && this.ready) this.onHandCallbacks.forEach(cb => cb(frame));
      });
      adapter.onConnection(info => {
        if (this.activeAdapter === adapter) this.publishConnection({ mode, ...info });
      });
    }
  }

  public get currentAdapter() { return this.activeAdapter; }

  /** Latest request wins; failed transitions do not poison subsequent retries. */
  public setMode(mode: OperatingMode): Promise<void> {
    if (!['simulator', 'live', 'python'].includes(mode)) return Promise.reject(new Error('Unknown source mode'));
    const request = ++this.request;
    const job = this.transition.then(async () => {
      if (request !== this.request) return;
      if (this.activeMode === mode && this.activeAdapter && this.ready) return;
      await this.releaseCurrent();
      if (request !== this.request) return;
      const adapter = this[mode];
      this.activeAdapter = adapter;
      this.activeMode = mode;
      this.publishConnection({ mode, status: 'starting' });
      try {
        await adapter.start();
        if (request !== this.request) {
          if (this.activeAdapter === adapter) await this.releaseCurrent();
          return;
        }
        this.ready = true;
        this.onModeChangeCallbacks.forEach(cb => cb({ mode, label: adapter.modeLabel }));
      } catch (error) {
        if (this.activeAdapter === adapter) await this.releaseCurrent();
        if (request !== this.request) return;
        this.publishConnection({ mode, status: 'error', message: String(error) });
        throw error;
      }
    });
    this.transition = job.catch(() => undefined);
    return job;
  }

  private async releaseCurrent(): Promise<void> {
    const adapter = this.activeAdapter;
    this.activeAdapter = null;
    this.activeMode = null;
    this.ready = false;
    this.onHandCallbacks.forEach(cb => cb(absentHand()));
    if (adapter) await adapter.stop();
  }

  /** Invalidate callbacks immediately, including while permission acquisition is pending. */
  public async stop(): Promise<void> {
    const request = ++this.request;
    const cleanup = this.releaseCurrent();
    // A browser permission prompt cannot be dismissed programmatically. Do not
    // let its old start promise block another source after Stop; adapters drop
    // late results using their own generation and stop any acquired tracks.
    this.transition = cleanup.catch(() => undefined);
    await cleanup;
    if (request === this.request) this.publishConnection({ mode: null, status: 'stopped' });
  }

  private publishConnection(info: SourceConnectionInfo): void {
    this.connection = info;
    this.onConnectionCallbacks.forEach(cb => cb({ ...info }));
  }
  /** Reports transport availability; the dashboard must still age received state frames. */
  public onConnection(cb: (info: SourceConnectionInfo) => void): void {
    this.onConnectionCallbacks.push(cb);
    cb({ ...this.connection });
  }
  public onState(cb: (frame: StateFrame) => void): void { this.onStateCallbacks.push(cb); }
  public onHand(cb: (frame: HandFrame) => void): void { this.onHandCallbacks.push(cb); }
  public onModeChange(cb: (info: SourceModeChangeInfo) => void): void { this.onModeChangeCallbacks.push(cb); }
  public sendControl(control: string, value?: number): boolean {
    return this.ready && this.activeAdapter ? this.activeAdapter.sendControl(control, value) : false;
  }
  public setFilter(v: number): void { this.sendControl('filter', v); }
  public setReverb(v: number): void { this.sendControl('reverb', v); }
  public toggleBypass(): void { this.sendControl('bypass'); }
  public toggleLoop(): void { this.sendControl('loop'); }
  public clearLoop(): void { if (this.ready) this.activeAdapter?.clearLoop(); }
}
