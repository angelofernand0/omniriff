/**
 * Local Python Engine Bridge Adapter (Mode C).
 * Connects to ws://127.0.0.1:47801 (engine state/control) and ws://127.0.0.1:47802 (hand feed).
 * Leaves Python engine 100% authoritative for DSP and state.
 */

import type { StateFrame, HandFrame, ControlEnvelope } from '../protocol/types';

export class PythonBridgeAdapter {
  public readonly modeId = 'python' as const;
  public readonly modeLabel = 'PYTHON BRIDGE';

  private wsUrl: string;
  private handUrl: string | null;

  private stateWs: WebSocket | null = null;
  private handWs: WebSocket | null = null;

  private isRunning: boolean = false;
  private stateRetryTimeout: any = null;
  private handRetryTimeout: any = null;
  private seq: number = 0;

  private onStateCb: ((frame: StateFrame) => void) | null = null;
  private onHandCb: ((frame: HandFrame) => void) | null = null;

  constructor(customWsUrl?: string, customHandUrl?: string) {
    const params = new URLSearchParams(window.location.search);
    this.wsUrl = customWsUrl || params.get('ws') || 'ws://127.0.0.1:47801';
    this.handUrl =
      customHandUrl !== undefined
        ? customHandUrl
        : params.get('hand') === 'off'
        ? null
        : params.get('hand') || 'ws://127.0.0.1:47802';
  }

  public async start(): Promise<void> {
    if (this.isRunning) return;
    this.isRunning = true;
    this.connectState();
    this.connectHand();
  }

  private connectState(): void {
    if (!this.isRunning) return;
    try {
      this.stateWs = new WebSocket(this.wsUrl);
    } catch (e) {
      this.scheduleStateRetry();
      return;
    }

    this.stateWs.onmessage = (msg) => {
      try {
        const frame = JSON.parse(msg.data);
        if (frame && frame.version === 1 && this.onStateCb) {
          this.onStateCb(frame);
        }
      } catch (e) {
        // ignore malformed frame
      }
    };

    this.stateWs.onclose = () => {
      this.stateWs = null;
      this.scheduleStateRetry();
    };

    this.stateWs.onerror = () => {
      try {
        this.stateWs?.close();
      } catch (e) {}
    };
  }

  private scheduleStateRetry(): void {
    if (!this.isRunning) return;
    clearTimeout(this.stateRetryTimeout);
    this.stateRetryTimeout = setTimeout(() => {
      this.connectState();
    }, 2000);
  }

  private connectHand(): void {
    if (!this.isRunning || !this.handUrl) return;
    try {
      this.handWs = new WebSocket(this.handUrl);
    } catch (e) {
      this.scheduleHandRetry();
      return;
    }

    this.handWs.onmessage = (msg) => {
      try {
        const frame = JSON.parse(msg.data);
        if (frame && frame.version === 1 && frame.type === 'hand' && this.onHandCb) {
          this.onHandCb(frame);
        }
      } catch (e) {
        // ignore malformed frame
      }
    };

    this.handWs.onclose = () => {
      this.handWs = null;
      this.scheduleHandRetry();
    };

    this.handWs.onerror = () => {
      try {
        this.handWs?.close();
      } catch (e) {}
    };
  }

  private scheduleHandRetry(): void {
    if (!this.isRunning || !this.handUrl) return;
    clearTimeout(this.handRetryTimeout);
    this.handRetryTimeout = setTimeout(() => {
      this.connectHand();
    }, 2000);
  }

  public sendControl(control: string, value?: number): boolean {
    if (!this.stateWs || this.stateWs.readyState !== WebSocket.OPEN) return false;
    const now = Date.now();
    this.seq = Math.max(this.seq + 1, now);

    let ev: ControlEnvelope;
    if (control === 'filter' || control === 'reverb') {
      if (typeof value !== 'number') return false;
      ev = {
        version: 1,
        source: 'dashboard',
        seq: this.seq,
        timestamp_ms: now,
        type: 'parameter',
        control,
        value,
        confidence: 1.0,
      };
    } else if (control === 'loop' || control === 'bypass') {
      ev = {
        version: 1,
        source: 'dashboard',
        seq: this.seq,
        timestamp_ms: now,
        type: 'action',
        control,
      };
    } else {
      return false;
    }

    try {
      this.stateWs.send(JSON.stringify(ev));
      return true;
    } catch (e) {
      return false;
    }
  }

  public setFilter(v: number): void {
    this.sendControl('filter', v);
  }

  public setReverb(v: number): void {
    this.sendControl('reverb', v);
  }

  public toggleBypass(): void {
    this.sendControl('bypass');
  }

  public toggleLoop(): void {
    this.sendControl('loop');
  }

  public clearLoop(): void {
    // Single-track toggle
    this.sendControl('loop');
  }

  public onState(cb: (frame: StateFrame) => void): void {
    this.onStateCb = cb;
  }

  public onHand(cb: (frame: HandFrame) => void): void {
    this.onHandCb = cb;
  }

  public async stop(): Promise<void> {
    this.isRunning = false;
    clearTimeout(this.stateRetryTimeout);
    clearTimeout(this.handRetryTimeout);
    if (this.stateWs) {
      try {
        this.stateWs.close();
      } catch (e) {}
      this.stateWs = null;
    }
    if (this.handWs) {
      try {
        this.handWs.close();
      } catch (e) {}
      this.handWs = null;
    }
  }
}
