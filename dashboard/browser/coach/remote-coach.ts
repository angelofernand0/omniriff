/**
 * Hosted coach client: the website's own instrument (your guitar + webcam, or the simulator)
 * coached by the real Riff running on coach/server.py.
 *
 * One WebSocket carries everything. coach.js uses it exactly as it uses the local feed
 * (coach.frame / coach.audio in, coach.say / coach.approve out); this module adds the
 * instrument side: looper state, finished takes with the webcam wrist track, Y to start
 * practice, and approved rig changes coming back from the coach.
 */
import type { SourceManager } from '../source-manager';
import type { StateFrame, HandFrame } from '../protocol/types';

export interface CoachServerConfig { url: string; key: string; }

const SERVER_KEY = 'omniriff.coachServer';
const PASS_KEY = 'omniriff.coachKey';
const PLAYER_KEY = 'omniriff.player';
const TAKE_RATE = 16000;            // Ears listens to the pick attack; 16 kHz keeps a 30 s take ~1 MB
const HAND_KEEP_MS = 40_000;

function storage(key: string, value?: string): string {
  try {
    if (value === undefined) return localStorage.getItem(key) || '';
    if (value) localStorage.setItem(key, value); else localStorage.removeItem(key);
  } catch { /* private window: the page still works, it just won't remember */ }
  return value || '';
}

/** Server from ?coachserver=, then this browser's saved choice, then the build default. */
export function coachConfig(params: URLSearchParams): CoachServerConfig | null {
  const fromUrl = params.get('coachserver');
  if (fromUrl !== null) storage(SERVER_KEY, fromUrl);
  if (params.get('coachkey') !== null) storage(PASS_KEY, params.get('coachkey')!);
  const url = fromUrl ?? (storage(SERVER_KEY) || (import.meta.env.VITE_COACH_SERVER as string | undefined) || '');
  return url ? { url, key: storage(PASS_KEY) } : null;
}

export function saveCoachConfig(url: string, key: string): void { storage(SERVER_KEY, url.trim()); storage(PASS_KEY, key.trim()); }

function playerId(): string {
  let id = storage(PLAYER_KEY);
  if (!/^[a-z0-9][a-z0-9-]{7,63}$/.test(id)) {
    id = 'p-' + Array.from(crypto.getRandomValues(new Uint8Array(10)), b => b.toString(16).padStart(2, '0')).join('');
    storage(PLAYER_KEY, id);
  }
  return id;
}

function resample(samples: Float32Array, from: number, to: number): Int16Array {
  const ratio = from / to;
  const n = Math.floor(samples.length / ratio);
  const out = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    // box filter over the source span: enough anti-aliasing for an onset detector
    const start = Math.floor(i * ratio), end = Math.max(start + 1, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end && j < samples.length; j++) sum += samples[j];
    const v = Math.max(-1, Math.min(1, sum / (end - start)));
    out[i] = Math.round(v * 32767);
  }
  return out;
}

function base64(bytes: Uint8Array): string {
  let text = '';
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}

interface WristSample { timestamp_ms: number; wrist: [number, number]; confidence: number; handedness: 'Right'; }

export class RemoteCoach {
  private ws: WebSocket | null = null;
  private state: StateFrame | null = null;
  private hands: WristSample[] = [];
  private pump: number | undefined;
  private lastStatus = '';
  private statusCb: (text: string) => void = () => {};
  /** The settings panel subscribes after the socket may already have opened: replay the latest line. */
  public set status(cb: (text: string) => void) { this.statusCb = cb; if (this.lastStatus) cb(this.lastStatus); }
  public get status(): (text: string) => void { return (text: string) => { this.lastStatus = text; this.statusCb(text); }; }

  constructor(private readonly config: CoachServerConfig, private readonly manager: SourceManager) {
    manager.onState(frame => { this.state = frame; });
    manager.onHand(frame => this.hand(frame));
    for (const adapter of [manager.simulator, manager.live]) {
      adapter.audio.onTake((samples, rate) => this.take(samples, rate));
    }
    window.addEventListener('keydown', event => {
      if (event.key.toLowerCase() !== 'y' || event.repeat) return;
      if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
      const frame = (window as any).OmniRiff?.coachFeed?.get?.();
      if (!frame?.awaiting_approval) this.practice();   // with an approval pending, coach.js sends coach.approve
    });
  }

  /** coach.js calls this instead of `new WebSocket(...)`, on every (re)connect. */
  public socket = (): WebSocket => {
    const url = new URL(this.config.url);
    if (this.config.key) url.searchParams.set('key', this.config.key);
    url.searchParams.set('player', playerId());
    const ws = new WebSocket(url);
    this.ws = ws;
    ws.addEventListener('open', () => {
      this.status('Riff is connected.');
      window.clearInterval(this.pump);
      this.pump = window.setInterval(() => this.sendState(), 250);
    });
    ws.addEventListener('close', event => {
      if (this.ws === ws) { this.ws = null; window.clearInterval(this.pump); }
      this.status(event.code === 1006 ? 'Cannot reach the coach server (wrong address or passcode, or it is busy).' : 'Coach disconnected.');
    });
    ws.addEventListener('message', event => {
      let message: any;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message?.type === 'omniriff.control' && ['bypass', 'filter', 'reverb', 'loop'].includes(message.control)) {
        this.manager.sendControl(message.control, typeof message.value === 'number' ? message.value : undefined);
      } else if (message?.type === 'omniriff.take_ack' && message.result !== 'ok') {
        this.status(`The coach could not use that take: ${message.result}.`);
      }
    });
    return ws;
  };

  private send(message: object): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(message));
    return true;
  }

  private sendState(): void {
    if (!this.state) return;
    const s = this.state;
    this.send({ type: 'omniriff.state', loop: { state: s.loop.state }, bypass: s.bypass,
      filter: { value: s.filter.value }, reverb: { value: s.reverb.value } });
  }

  public practice(): void { this.send({ type: 'omniriff.practice' }); }

  private hand(frame: HandFrame): void {
    const now = Date.now();
    if (frame.present && frame.landmarks.length) {
      const [x, y] = frame.landmarks[0];
      if (Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 1 && y >= 0 && y <= 1) {
        this.hands.push({ timestamp_ms: now, wrist: [x, y], confidence: Math.min(1, Math.max(0, frame.confidence || 0.9)), handedness: 'Right' });
      }
    }
    while (this.hands.length && now - this.hands[0].timestamp_ms > HAND_KEEP_MS) this.hands.shift();
  }

  private take(samples: Float32Array, rate: number): void {
    const ended = Date.now();
    const started = Math.round(ended - (1000 * samples.length) / rate);
    const pcm = resample(samples, rate, TAKE_RATE);
    const hands = this.hands.filter(h => h.timestamp_ms >= started - 200 && h.timestamp_ms <= ended + 200);
    const sent = this.send({ type: 'omniriff.take', samplerate: TAKE_RATE, started_unix_ms: started,
      pcm16_b64: base64(new Uint8Array(pcm.buffer)), hands });
    this.status(sent ? `Sent your ${(samples.length / rate).toFixed(1)} s take to Riff${hands.length ? ' with your hand track' : ''}.` : 'Riff is not connected; the take stays local.');
  }
}
