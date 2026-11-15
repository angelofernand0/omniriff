/** Loopback Python transport. The Python engine remains authoritative for DSP. */
import type { StateFrame, HandFrame, ControlEnvelope } from '../protocol/types';
import { absentHand, isHandFrame, isStateFrame, type ConnectionCallback } from './connection';

export class PythonBridgeAdapter {
  public readonly modeId = 'python' as const;
  public readonly modeLabel = 'PYTHON BRIDGE';
  private wsUrl: string;
  private handUrl: string | null;
  private stateWs: WebSocket | null = null;
  private handWs: WebSocket | null = null;
  private isRunning = false;
  private generation = 0;
  private stateRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  private handRetryTimeout: ReturnType<typeof setTimeout> | null = null;
  private seq = 0;
  private lastStateTimestamp = -1;
  private lastHandTimestamp = -1;
  private loopState: StateFrame['loop']['state'] | null = null;
  private onStateCb: ((frame: StateFrame) => void) | null = null;
  private onHandCb: ((frame: HandFrame) => void) | null = null;
  private onConnectionCb: ConnectionCallback | null = null;

  constructor(customWsUrl?: string, customHandUrl?: string | null) {
    const params = new URLSearchParams(typeof window === 'undefined' ? '' : window.location.search);
    this.wsUrl = customWsUrl || params.get('ws') || 'ws://127.0.0.1:47801';
    this.handUrl = customHandUrl !== undefined ? customHandUrl : params.get('hand') === 'off' ? null :
      params.get('hand') || 'ws://127.0.0.1:47802';
  }

  public async start(): Promise<void> {
    if (this.isRunning) return;
    this.isRunning = true;
    ++this.generation;
    this.lastStateTimestamp = this.lastHandTimestamp = -1;
    this.loopState = null;
    this.onConnectionCb?.({ status: 'starting' });
    this.connectState();
    this.connectHand();
  }

  private connectState(): void {
    if (!this.isRunning) return;
    const generation = this.generation;
    let ws: WebSocket;
    try { ws = new WebSocket(this.wsUrl); }
    catch { this.onConnectionCb?.({ status: 'disconnected' }); this.scheduleStateRetry(); return; }
    this.stateWs = ws;
    const current = () => this.isRunning && generation === this.generation && this.stateWs === ws;
    ws.onmessage = msg => {
      if (!current() || typeof msg.data !== 'string' || msg.data.length > 131072) return;
      try {
        const frame: unknown = JSON.parse(msg.data);
        if (!isStateFrame(frame) || frame.timestamp_ms <= this.lastStateTimestamp) return;
        this.lastStateTimestamp = frame.timestamp_ms;
        this.loopState = frame.loop.state;
        this.onConnectionCb?.({ status: 'connected' });
        this.onStateCb?.(frame);
      } catch { /* invalid input never reaches the renderer */ }
    };
    ws.onclose = () => {
      if (!current()) return;
      this.stateWs = null;
      this.loopState = null;
      this.onConnectionCb?.({ status: 'disconnected' });
      this.scheduleStateRetry();
    };
    ws.onerror = () => { if (current()) { try { ws.close(); } catch { /* close is best effort */ } } };
  }

  private scheduleStateRetry(): void {
    if (!this.isRunning) return;
    if (this.stateRetryTimeout !== null) clearTimeout(this.stateRetryTimeout);
    const generation = this.generation;
    this.stateRetryTimeout = setTimeout(() => {
      this.stateRetryTimeout = null;
      if (this.isRunning && generation === this.generation) this.connectState();
    }, 2000);
  }

  private connectHand(): void {
    if (!this.isRunning || !this.handUrl) return;
    const generation = this.generation;
    let ws: WebSocket;
    try { ws = new WebSocket(this.handUrl); }
    catch { this.onHandCb?.(absentHand()); this.scheduleHandRetry(); return; }
    this.handWs = ws;
    const current = () => this.isRunning && generation === this.generation && this.handWs === ws;
    ws.onmessage = msg => {
      if (!current() || typeof msg.data !== 'string' || msg.data.length > 16384) return;
      try {
        const frame: unknown = JSON.parse(msg.data);
        if (!isHandFrame(frame) || frame.timestamp_ms <= this.lastHandTimestamp) return;
        this.lastHandTimestamp = frame.timestamp_ms;
        this.onHandCb?.(frame);
      } catch { /* invalid input never reaches the renderer */ }
    };
    ws.onclose = () => {
      if (!current()) return;
      this.handWs = null;
      this.onHandCb?.(absentHand());
      this.scheduleHandRetry();
    };
    ws.onerror = () => { if (current()) { try { ws.close(); } catch { /* close is best effort */ } } };
  }

  private scheduleHandRetry(): void {
    if (!this.isRunning || !this.handUrl) return;
    if (this.handRetryTimeout !== null) clearTimeout(this.handRetryTimeout);
    const generation = this.generation;
    this.handRetryTimeout = setTimeout(() => {
      this.handRetryTimeout = null;
      if (this.isRunning && generation === this.generation) this.connectHand();
    }, 2000);
  }

  public sendControl(control: string, value?: number): boolean {
    if (!this.isRunning || !this.stateWs || this.stateWs.readyState !== WebSocket.OPEN) return false;
    const now = Date.now();
    let event: ControlEnvelope;
    const seq = Math.max(this.seq + 1, now);
    if (control === 'filter' || control === 'reverb') {
      if (typeof value !== 'number' || !Number.isFinite(value)) return false;
      event = { version: 1, source: 'dashboard', seq, timestamp_ms: now, type: 'parameter',
        control, value: Math.min(1, Math.max(0, value)), confidence: 1 };
    } else if (control === 'loop' || control === 'bypass' || control === 'practice') {
      event = { version: 1, source: 'dashboard', seq, timestamp_ms: now, type: 'action', control };
    } else return false;
    try { this.stateWs.send(JSON.stringify(event)); this.seq = seq; return true; } catch { return false; }
  }
  public setFilter(v: number): void { this.sendControl('filter', v); }
  public setReverb(v: number): void { this.sendControl('reverb', v); }
  public toggleBypass(): void { this.sendControl('bypass'); }
  public toggleLoop(): void { this.sendControl('loop'); }
  /** Python has a cycle action rather than an unconditional clear; never start an idle loop here. */
  public clearLoop(): void { if (this.loopState === 'playing') this.sendControl('loop'); }
  public onState(cb: (frame: StateFrame) => void): void { this.onStateCb = cb; }
  public onHand(cb: (frame: HandFrame) => void): void { this.onHandCb = cb; }
  public onConnection(cb: ConnectionCallback): void { this.onConnectionCb = cb; }

  public async stop(): Promise<void> {
    this.isRunning = false;
    ++this.generation;
    if (this.stateRetryTimeout !== null) clearTimeout(this.stateRetryTimeout);
    if (this.handRetryTimeout !== null) clearTimeout(this.handRetryTimeout);
    this.stateRetryTimeout = this.handRetryTimeout = null;
    const sockets = [this.stateWs, this.handWs];
    this.stateWs = this.handWs = null;
    this.loopState = null;
    for (const ws of sockets) if (ws) {
      ws.onopen = ws.onmessage = ws.onclose = ws.onerror = null;
      try { ws.close(); } catch { /* closing an in-flight connection may fail */ }
    }
    this.onHandCb?.(absentHand());
    this.onConnectionCb?.({ status: 'stopped' });
  }
}
