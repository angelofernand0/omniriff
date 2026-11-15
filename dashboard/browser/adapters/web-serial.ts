import type { StateSources, AdapterStatus } from '../protocol/types';

export type PedalAction = 'loop' | 'bypass' | 'practice';

export interface WebSerialPedalTelemetry {
  accepted: number;
  dropped: number;
  session: number;
  lastSeenMs: number | null;
  lastAcceptedMs: number | null;
  practiceCount: number;
  lastPracticeMs: number | null;
  status: AdapterStatus['status'];
  errors: number;
  lastError: string | null;
}

export class WebSerialPedalAdapter {
  private port: any = null;
  private reader: any = null;
  private running = false;
  private buffer = '';
  private lastSeq: number | null = null;

  public accepted = 0;
  public dropped = 0;
  public session = 0;
  public lastSeenMs: number | null = null;
  public lastAcceptedMs: number | null = null;
  public practiceCount = 0;
  public lastPracticeMs: number | null = null;
  public status: AdapterStatus['status'] = 'disabled';
  public errors = 0;
  public lastError: string | null = null;

  private actionCallbacks: Array<(action: PedalAction) => void> = [];
  private statusCallbacks: Array<(status: AdapterStatus['status'], err?: string | null) => void> = [];

  public isSupported(): boolean {
    return typeof navigator !== 'undefined' && 'serial' in navigator;
  }

  public get isConnected(): boolean {
    return this.status === 'running' && this.port !== null;
  }

  public onAction(cb: (action: PedalAction) => void): () => void {
    this.actionCallbacks.push(cb);
    return () => {
      this.actionCallbacks = this.actionCallbacks.filter(c => c !== cb);
    };
  }

  public onStatus(cb: (status: AdapterStatus['status'], err?: string | null) => void): () => void {
    this.statusCallbacks.push(cb);
    return () => {
      this.statusCallbacks = this.statusCallbacks.filter(c => c !== cb);
    };
  }

  private notifyStatus(): void {
    for (const cb of this.statusCallbacks) cb(this.status, this.lastError);
  }

  public async requestAndConnect(): Promise<boolean> {
    if (!this.isSupported()) {
      throw new Error('Web Serial is not supported in this browser. Please use Chrome, Edge, or Opera.');
    }
    try {
      this.status = 'starting';
      this.notifyStatus();
      const port = await (navigator as any).serial.requestPort();
      await this.connect(port);
      return true;
    } catch (err: any) {
      if (err.name === 'NotFoundError') {
        // User cancelled the port selection dialog
        this.status = this.port ? 'running' : 'disabled';
        this.notifyStatus();
        return false;
      }
      this.status = 'error';
      this.errors++;
      this.lastError = err instanceof Error ? err.message : String(err);
      this.notifyStatus();
      throw err;
    }
  }

  public async connect(port: any): Promise<void> {
    if (this.port) await this.disconnect();
    this.port = port;
    this.buffer = '';
    this.lastSeq = null;
    await port.open({ baudRate: 115200 });
    this.running = true;
    this.status = 'running';
    this.notifyStatus();
    void this.readLoop();
  }

  public feedLine(raw: string): void {
    const trimmed = raw.trim();
    if (!trimmed) return;
    const now = Date.now();
    this.lastSeenMs = now;

    try {
      const event = JSON.parse(trimmed);
      if (
        !event ||
        typeof event !== 'object' ||
        event.type !== 'action' ||
        typeof event.seq !== 'number' ||
        event.seq < 0 ||
        !Number.isInteger(event.seq)
      ) {
        this.dropped++;
        return;
      }

      const control = event.control;
      if (control !== 'loop' && control !== 'bypass' && control !== 'practice') {
        this.dropped++;
        return;
      }

      if (this.lastSeq !== null) {
        if (event.seq === 0 && this.lastSeq > 0) {
          // Board reset starts a new session
          this.session++;
          this.lastSeq = 0;
        } else if (event.seq <= this.lastSeq) {
          // Duplicate or stale sequence
          this.dropped++;
          return;
        } else {
          this.lastSeq = event.seq;
        }
      } else {
        this.lastSeq = event.seq;
      }

      this.accepted++;
      this.lastAcceptedMs = now;

      if (control === 'practice') {
        this.practiceCount++;
        this.lastPracticeMs = now;
      }

      for (const cb of this.actionCallbacks) cb(control);
    } catch {
      this.dropped++;
    }
  }

  public feedChunk(data: Uint8Array | string): void {
    const text = typeof data === 'string' ? data : new TextDecoder().decode(data);
    this.buffer += text;
    if (this.buffer.length > 2048) {
      // Exceeded max line buffer; discard to prevent memory growth
      this.buffer = '';
      this.dropped++;
      return;
    }
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() || '';
    for (const line of lines) {
      this.feedLine(line);
    }
  }

  private async readLoop(): Promise<void> {
    if (!this.port?.readable) return;
    try {
      const reader = this.port.readable.getReader();
      this.reader = reader;
      while (this.running) {
        const { value, done } = await reader.read();
        if (done) break;
        if (value) this.feedChunk(value);
      }
    } catch (err: any) {
      if (this.running) {
        this.errors++;
        this.lastError = err instanceof Error ? err.message : String(err);
        this.status = 'error';
        this.notifyStatus();
      }
    } finally {
      try { this.reader?.releaseLock(); } catch { /* ignore */ }
      this.reader = null;
    }
    if (this.running) {
      this.running = false;
      this.status = 'stopped';
      this.notifyStatus();
    }
  }

  public async disconnect(): Promise<void> {
    this.running = false;
    if (this.reader) {
      try { await this.reader.cancel(); } catch { /* ignore */ }
      try { this.reader.releaseLock(); } catch { /* ignore */ }
      this.reader = null;
    }
    if (this.port) {
      try { await this.port.close(); } catch { /* ignore */ }
      this.port = null;
    }
    this.status = 'stopped';
    this.notifyStatus();
  }

  public get sourcesArduino(): StateSources['arduino'] | undefined {
    if (this.status === 'disabled' && this.lastSeenMs === null) return undefined;
    return {
      last_seen_ms: this.lastSeenMs,
      last_accepted_ms: this.lastAcceptedMs,
      accepted: this.accepted,
      dropped: this.dropped,
      session: this.session,
    };
  }

  public get adapterStatus(): AdapterStatus {
    return {
      status: this.status,
      errors: this.errors,
      last_error: this.lastError,
    };
  }

  public get pedalTelemetry(): { practice_count: number; last_practice_ms: number } | undefined {
    if (this.practiceCount === 0 || this.lastPracticeMs === null) return undefined;
    return {
      practice_count: this.practiceCount,
      last_practice_ms: this.lastPracticeMs,
    };
  }
}
