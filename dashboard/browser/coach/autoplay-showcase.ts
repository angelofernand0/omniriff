/** Unattended, visual-only browser showcase. All coaching text and metrics are scripted. */
import type { SourceManager } from '../source-manager';
import type { StateFrame } from '../protocol/types';

type Message = Record<string, unknown>;

class ShowcaseSocket {
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(private readonly showcase: AutoplayShowcase) {
    setTimeout(() => { this.onopen?.(); showcase.attach(this); }, 0);
  }
  send(_data: string): void { /* This display-only mode cannot control the coach. */ }
  close(): void { this.readyState = 3; this.showcase.detach(this); this.onclose?.(); }
  deliver(message: Message): void { this.onmessage?.({ data: JSON.stringify(message) }); }
}

type LoopState = 'idle' | 'recording' | 'playing';

export class AutoplayShowcase {
  private socket: ShowcaseSocket | null = null;
  private timers: Array<ReturnType<typeof setTimeout>> = [];
  private running = false;
  private loopState: LoopState = 'idle';
  private cycle = 0;
  private frame: Message = {};

  constructor(private readonly manager: SourceManager) {
    manager.onState((frame: StateFrame) => { this.loopState = frame.loop.state; });
    manager.onModeChange(({ mode }) => { if (mode !== 'simulator') this.stop(); });
    manager.onConnection(({ status }) => { if (status === 'stopped' || status === 'error') this.stop(); });
  }

  public socketFactory = (): WebSocket => new ShowcaseSocket(this) as unknown as WebSocket;

  attach(socket: ShowcaseSocket): void {
    this.socket = socket;
    if (this.frame.type) socket.deliver(this.frame);
  }

  detach(socket: ShowcaseSocket): void { if (this.socket === socket) this.socket = null; }

  start(): void {
    if (this.running || this.manager.activeMode !== 'simulator') return;
    this.running = true;
    this.nextCycle();
  }

  stop(): void {
    this.running = false;
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }

  private later(ms: number, action: () => void): void {
    const id = setTimeout(() => {
      if (this.running && this.manager.activeMode === 'simulator') action();
    }, ms);
    this.timers.push(id);
  }

  private loop(expected: LoopState): void {
    if (this.loopState === expected) this.manager.sendControl('loop');
  }

  private publish(changes: Message): void {
    this.frame = { ...this.frame, ...changes, timestamp_ms: Date.now() };
    this.socket?.deliver(this.frame);
  }

  private nextCycle(): void {
    this.timers.forEach(clearTimeout);
    this.timers = [];
    this.cycle += 1;
    // Clear the real browser looper before starting another scripted take.
    if (this.loopState === 'playing') this.loop('playing');
    const first = `showcase-${this.cycle}-first`;
    const second = `showcase-${this.cycle}-second`;
    const goal = 'Get my timing right';
    const drill = { skill: 'swing-the-phrase', title: 'Swing The Third Phrase',
      passage: 'Phrase 3: long-short swing, even attacks', reps: 4,
      pass_rule: 'drift under 40 ms', rig: { bypass: true } };
    const session = (history: number[], done = false) => ({
      mode: done ? 'play' : 'practice', goal,
      plan: [{ title: 'Swing the third phrase', status: done ? 'done' : 'now' }],
      drill: done ? null : { title: 'Swing the third phrase', skill: 'swing-the-phrase', step: 1, of: 1 },
      attempt: done ? null : { n: history.length - 1, of: 3 },
      metric: history.length ? { name: 'timing drift, phrase 3', unit: 'ms', target: 40,
        lower_is_better: true, history } : null,
      next: done ? null : 'Full riff, even attacks',
      summary: done ? 'Scripted example: third-phrase drift improves from 118 to 31 ms.' : null,
      next_time: done ? 'Try the whole riff at full tempo' : null,
    });
    this.frame = {
      version: 1, type: 'coach.frame', timestamp_ms: Date.now(),
      session_id: `showcase-${this.cycle}`, take_id: null, scripted: true,
      state: 'idle', mood: 'encouraging', target: 'player',
      cue: 'Meet Riff. Play a phrase, find the stumble, practise one fix, and try again.',
      todos: [], activity: [], drill_card: null, before_after: null,
      awaiting_approval: null, mark: null, session: session([]),
    };
    this.socket?.deliver(this.frame);
    this.later(4000, () => this.publish({ cue: 'The player wants to tighten their timing. Riff listens while they play.', state: 'listening', mood: 'curious', target: 'loop' }));
    this.later(7000, () => this.loop('idle'));
    this.later(14500, () => this.loop('recording'));
    this.later(15500, () => this.publish({ take_id: first, cue: 'Let me listen back to that.', state: 'thinking', mood: 'concentrating', target: 'loop',
      activity: [{ who: 'ears', what: 'analyze_take', status: 'running' }],
      todos: [{ text: 'Read the timing report', status: 'in_progress' }, { text: 'Choose a drill', status: 'pending' }] }));
    this.later(20500, () => this.publish({ cue: 'The third phrase rushes. Swing it long-short, and keep every attack even.',
      state: 'pointing', mood: 'aha', target: 'loop',
      activity: [{ who: 'ears', what: 'analyze_take', status: 'done' }, { who: 'coach', what: 'write_drill_card swing-the-phrase', status: 'done' }],
      todos: [{ text: 'Read the timing report', status: 'completed' }, { text: 'Choose a drill', status: 'completed' }],
      session: session([118]), drill_card: drill,
      mark: { start_s: 3.5, end_s: 5.3, label: 'Phrase 3 · timing slips' } }));
    this.later(30000, () => this.publish({ cue: 'Riff proposes turning effects off so the player can hear every attack.',
      state: 'speaking', mood: 'encouraging', target: 'bypass',
      awaiting_approval: { id: `showcase-${this.cycle}-approval`, summary: 'Effects off for a focused drill.',
        actions: [{ control: 'bypass' }], expires_unix_ms: Date.now() + 120000 } }));
    this.later(36000, () => {
      this.publish({ awaiting_approval: null, cue: 'Approved in this scripted example. Effects off; now try the phrase again.',
        state: 'pointing', target: 'bypass' });
      this.manager.sendControl('bypass');
    });
    this.later(40500, () => this.loop('playing'));
    this.later(42500, () => this.loop('idle'));
    this.later(50000, () => this.loop('recording'));
    this.later(51500, () => this.publish({ take_id: second, cue: 'Riff compares the second take with the first.',
      state: 'thinking', mood: 'concentrating', target: 'loop', mark: null,
      activity: [{ who: 'ears', what: 'analyze_take', status: 'done' }, { who: 'coach', what: 'compare_takes', status: 'running' }] }));
    this.later(56500, () => this.publish({ cue: 'That is the swing. The third phrase lands much more evenly now.',
      state: 'pleased', mood: 'proud', target: 'player', session: session([118, 31]),
      before_after: { before_take_id: first, after_take_id: second, hesitations: [2, 0],
        worst_gap_ms: [118, 31], tempo_stability: [0.78, 0.95], improved: true },
      activity: [{ who: 'coach', what: 'compare_takes', status: 'done' }] }));
    this.later(67500, () => {
      this.manager.sendControl('bypass');
      this.publish({ cue: 'A focused fix, another take, and progress the player can hear. Riff remembers what to work on next.',
        state: 'idle', mood: 'proud', target: 'player', session: session([118, 31], true), drill_card: null });
    });
    this.later(76000, () => this.nextCycle());
  }
}
