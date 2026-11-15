/**
 * Demo coach (?coach=demo): the pitch's coaching session, scripted, running in the browser.
 *
 * It plugs into coach.js through the same socket hook as the hosted coach, so Riff's column,
 * voice, plan, loop marker, drill card, approval and before/after render exactly as live.
 * It moves on real events only: what the player says or types to Riff, a finished loop
 * recording (real guitar or simulator), and Y / a held thumbs-up to approve. The words and
 * numbers are written in advance (docs/PITCH.md, "Demo coach"); the voice clips are Riff's
 * ElevenLabs voice, pre-rendered by tools/showcase/demo_voice.py.
 *
 *   "Welcome back, last time..." (memory) -> "I can't get my timing right" -> record -> listen + plan -> "third phrase: swing it,
 *   even attacks" (marked on the loop) -> approve effects off -> fresh take -> before/after ->
 *   effects back on, "pinch the reverb in", saved to memory -> next visit: "last time... the third phrase"
 *
 * Memory: the first visit opens with a seeded previous session (the ring-finger fix); a finished
 * demo replaces it with the third phrase. &fresh=1 starts with no memory (first-time player).
 */
import type { SourceManager } from '../source-manager';
import type { StateFrame } from '../protocol/types';
import type { TrackedHand } from '../vision/hand-tracker';
import { isThumbsUp, ThumbsUpHold } from '../vision/thumbs-up';
import { DEMO_MEMORY, LINES, SEED_MEMORY, type LineId } from './demo-script';

/** Which recorded reply fits what you said (every reply has a clip, so Riff keeps its voice). */
export function replyFor(text: string): LineId {
  const lower = text.toLowerCase();
  if (/speed|fast|tempo|bpm|quick|slow|accelerat/.test(lower)) return 'replySpeed';
  if (/tim(ing|e)|rhythm|groove|drift|metronome|sync|beat|pocket/.test(lower)) return 'replyTiming';
  if (/chord|transition|fret|finger|progression|barre|shape/.test(lower)) return 'replyChords';
  if (/strum|pick|wrist|pluck|attack|dynamics/.test(lower)) return 'replyStrum';
  if (/tone|sound|clean|mute|buzz|clarity|crisp/.test(lower)) return 'replyTone';
  if (/scale|solo|riff|lead|phrasing|improv|bend/.test(lower)) return 'replyPhrasing';
  return 'replyOther';
}

export function generateCoachReply(text: string): string { return LINES[replyFor(text)].text; }

type Msg = Record<string, unknown>;
const MEMORY_KEY = 'omniriff.demo.lastTime';
const voiceFiles = import.meta.glob('./demo-voice/*.mp3', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;

function remember(value?: string | null): string {
  try {
    if (typeof localStorage === 'undefined') return '';
    if (value === undefined) return localStorage.getItem(MEMORY_KEY) || '';
    if (value === null) localStorage.removeItem(MEMORY_KEY); else localStorage.setItem(MEMORY_KEY, value);
  } catch { /* private window: the seeded memory still shows */ }
  return value || '';
}

/** Back to the pitch opening (the remembered ring-finger session). */
export function resetDemoMemory(): void { remember(null); }

/** The WebSocket-shaped object coach.js talks to. */
class DemoSocket {
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(private readonly coach: DemoCoach) { setTimeout(() => { this.onopen?.(); coach.attach(this); }, 0); }
  send(data: string): void { try { this.coach.fromPlayer(JSON.parse(data)); } catch { /* ignore */ } }
  close(): void { this.readyState = 3; }
  deliver(message: Msg): void { this.onmessage?.({ data: JSON.stringify(message) }); }
}

type Step = 'play' | 'goal' | 'take1' | 'thinking1' | 'approval' | 'drill' | 'thinking2' | 'done';

export class DemoCoach {
  private socket: DemoSocket | null = null;
  private frame: Msg;
  private step: Step = 'play';
  private timers: number[] = [];
  private loopState = 'idle';
  private loopSeconds = 0;
  private takeN = 0;
  private audio = new Map<LineId, string>();
  private thumb = new ThumbsUpHold(600);
  private readonly sessionId = 'demo-' + Date.now().toString(36);

  private memory = '';

  constructor(private readonly manager: SourceManager, fresh = false) {
    if (fresh) remember(null);
    this.memory = fresh ? '' : remember() || SEED_MEMORY;
    this.frame = {
      version: 1, type: 'coach.frame', timestamp_ms: Date.now(), session_id: this.sessionId, take_id: null,
      state: 'idle', mood: 'neutral', target: null, cue: null, todos: [], drill_card: null, before_after: null,
      awaiting_approval: null, activity: [], scripted: false, session: null, mark: null,
    };
    manager.onState(frame => this.onState(frame));
    manager.live.tracker.onAllHands = hands => this.onHands(hands);
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', event => {
        if (event.key.toLowerCase() !== 'y' || event.repeat) return;
        if (event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
        if (this.step === 'play') this.startPractice();   // with an approval pending, coach.js sends coach.approve
      });
    }
    void this.loadVoice();
  }

  /** coach.js calls this instead of `new WebSocket(...)`. */
  public socketFactory = (): WebSocket => new DemoSocket(this) as unknown as WebSocket;

  attach(socket: DemoSocket): void {
    this.socket = socket;
    this.publish({ session: this.session({ goal: null, play: true }) });
    if (!this.memory) {
      this.say('freePlay', { state: 'idle', mood: 'neutral', target: 'player' });
      return;
    }
    this.activity('coach', 'read /memories/player.md', 'running');
    this.later(900, () => {
      this.activity('coach', 'read /memories/player.md', 'done');
      this.say(this.memory === DEMO_MEMORY ? 'welcomeBackSwing' : 'welcomeBack', { state: 'speaking', mood: 'encouraging', target: 'player' });
    });
  }

  // ---------- inputs ----------
  fromPlayer(message: Msg): void {
    if (message.type === 'coach.say' && typeof message.text === 'string') this.heard(message.text);
    if (message.type === 'coach.approve' && this.step === 'approval') this.approved();
    if (message.type === 'coach.reject' && this.step === 'approval') {
      this.publish({ awaiting_approval: null });
      this.say('keepSound', { state: 'idle', mood: 'encouraging', target: 'player' });
      this.step = 'drill';
    }
  }

  private onState(frame: StateFrame): void {
    const was = this.loopState;
    this.loopState = frame.loop.state;
    if (frame.loop.state !== 'idle') this.loopSeconds = frame.loop.seconds || this.loopSeconds;
    if (was !== 'recording' && frame.loop.state === 'recording') this.recording();
    if (was === 'recording' && frame.loop.state === 'playing') this.takeFinished();
  }

  private onHands(hands: TrackedHand[]): void {
    if (this.step !== 'approval') { this.thumb.reset(); return; }
    if (this.thumb.update(Date.now(), hands.some(h => isThumbsUp(h.landmarks)))) this.approved();
  }

  // ---------- the script ----------
  private startPractice(): void {
    this.step = 'goal';
    this.publish({ session: this.session({ goal: null }) });
    this.say('whatGoal', { state: 'idle', mood: 'curious', target: 'player' });
  }

  private heard(text: string): void {
    const clean = text.trim().replace(/\s+/g, ' ');
    if (!clean) return;
    const goal = clean.slice(0, 80) || 'Get my timing right';
    this.goal = goal;

    if (this.step === 'play' || this.step === 'goal') {
      this.step = 'take1';
      this.publish({ session: this.session({ goal }), before_after: null, drill_card: null, mark: null, todos: [] });
      this.say('goalTiming', { state: 'speaking', mood: 'encouraging', target: 'player' });
      this.activity('coach', 'write /journal/goal.md', 'done');
      return;
    }

    // Subsequent voice / text input: update session goal and reply conversationally like an AI coach
    const isDrill = this.step === 'drill' || this.step === 'approval';
    const isDone = this.step === 'done';
    const history = isDone ? [118, 31] : isDrill ? [118] : undefined;
    this.publish({ session: this.session({ goal: this.goal, drill: isDrill, history, done: isDone }) });
    this.activity('coach', 'write /journal/goal.md', 'done');

    const id = replyFor(clean), reply = LINES[id].text;
    this.say(id, { state: 'speaking', mood: 'encouraging', target: 'player' });
    this.later(this.lineMs(id), () => {
      if (this.frame.cue === reply) {
        this.publish({ state: 'idle', mood: 'neutral' });
      }
    });
  }
  private goal = 'Get my timing right';

  private recording(): void {
    this.publish({ mark: null });
    if (this.step === 'take1' || this.step === 'drill') this.publish({ state: 'listening', mood: 'concentrating', target: 'loop', cue: null });
  }

  private takeFinished(): void {
    if (this.step === 'play' || this.step === 'goal') this.heard(this.goal);   // played before saying anything: still help
    this.takeN += 1;
    const take = `take-${Date.now()}-${this.takeN}`;
    if (this.step === 'take1') this.diagnose(take);
    else if (this.step === 'drill' || this.step === 'approval') this.compare(take);
  }

  private diagnose(take: string): void {
    this.step = 'thinking1';
    this.firstTake = take;
    this.publish({ take_id: take, activity: [], todos: [], before_after: null, awaiting_approval: null });
    this.say('listenBack', { state: 'listening', mood: 'concentrating', target: 'loop' });
    const plan = ['Read the timing report (Ears)', 'Check both hands on camera (Eyes)', 'Find the phrase where it slips',
      'Pick one drill for it', 'Set up the loop'];
    this.later(900, () => this.activity('ears', 'analyze_take', 'running'));
    this.later(1600, () => this.todos(plan, 0));
    this.later(2600, () => { this.activity('ears', 'analyze_take', 'done'); this.todos(plan, 1); this.publish({ state: 'thinking', mood: 'concentrating', target: 'coach' }); });
    this.later(3600, () => { this.activity('eyes', 'technique: fingers + picking hand', 'done'); this.todos(plan, 2); this.publish({ target: 'hand' }); });
    this.later(4800, () => { this.activity('coach', 'get_take_report', 'done'); this.todos(plan, 3); this.publish({ mood: 'aha', target: 'loop' }); });
    this.later(5800, () => { this.activity('coach', 'open skill swing-the-phrase', 'done'); this.todos(plan, 4); });
    this.later(6600, () => {
      const length = this.loopSeconds > 2 ? this.loopSeconds : 12;
      const mark = { start_s: +(length * 0.5).toFixed(2), end_s: +(length * 0.75).toFixed(2), label: '3rd phrase · straight' };
      const card = { skill: 'swing-the-phrase', title: 'Swing The Third Phrase', passage: 'Phrase 3 only: long-short swing, every strum the same',
        reps: 4, pass_rule: 'drift under 40 ms, even attacks', rig: { bypass: true }, journal_path: `/journal/${this.sessionId}/${take}.md` };
      this.todos(plan, 5);
      this.activity('coach', `write /journal/${take}.md`, 'done');
      this.publish({ mark, drill_card: card, session: this.session({ goal: this.goal, drill: true, history: [118] }) });
      this.activity('coach', 'write_drill_card swing-the-phrase', 'done');
      this.say('diagnosis', { state: 'speaking', mood: 'concerned', target: 'loop' });
    });
    this.later(6600 + this.lineMs('diagnosis'), () => {
      this.step = 'approval';
      this.publish({ awaiting_approval: { id: 'demo-approval-' + this.takeN, summary: 'Effects off, so you can hear your attacks.',
        actions: [{ control: 'bypass' }], expires_unix_ms: Date.now() + 120_000 } });
      this.activity('coach', 'rig_control approval', 'waiting');
      this.say('askEffectsOff', { state: 'speaking', mood: 'encouraging', target: 'bypass' });
    });
  }
  private firstTake = '';

  private approved(): void {
    if (this.step !== 'approval') return;
    this.step = 'drill';
    this.publish({ awaiting_approval: null });
    this.activity('coach', 'rig_control approval', 'done');
    this.publish({ state: 'pointing', mood: 'encouraging', target: 'bypass' });
    this.later(700, () => this.manager.sendControl('bypass'));
    this.later(1300, () => this.say('effectsOff', { state: 'speaking', mood: 'encouraging', target: 'loop' }));
  }

  private compare(take: string): void {
    this.step = 'thinking2';
    this.publish({ take_id: take, mark: null, todos: [] });
    this.say('listenBack', { state: 'listening', mood: 'concentrating', target: 'loop' });
    const plan = ['Read the new take (Ears)', 'Compare phrase 3 with the first take', 'Decide: pass or try again'];
    this.later(1000, () => { this.activity('ears', 'analyze_take', 'done'); this.todos(plan, 1); this.publish({ state: 'thinking', target: 'coach' }); });
    this.later(2200, () => { this.activity('coach', 'compare_takes', 'done'); this.todos(plan, 2); });
    this.later(3300, () => {
      this.todos(plan, 3);
      this.publish({
        before_after: { before_take_id: this.firstTake, after_take_id: take, hesitations: [2, 0], worst_gap_ms: [118, 31],
          tempo_stability: [0.78, 0.95], improved: true },
        session: this.session({ goal: this.goal, drill: true, history: [118, 31], attempt: 1 }),
      });
      this.say('result', { state: 'pleased', mood: 'proud', target: 'player' });
    });
    this.later(3300 + this.lineMs('result'), () => {
      this.manager.sendControl('bypass');
      this.activity('coach', 'write /memories/player.md', 'done');
      remember(DEMO_MEMORY);
      this.step = 'done';
      this.publish({ drill_card: null, session: this.session({ goal: this.goal, history: [118, 31], done: true }) });
      this.say('handBack', { state: 'pointing', mood: 'proud', target: 'reverb' });
    });
    this.later(3300 + this.lineMs('result') + this.lineMs('handBack') + 1500, () =>
      this.publish({ state: 'idle', mood: 'neutral', target: null }));
  }

  // ---------- frames ----------
  private session(o: { goal: string | null; drill?: boolean; history?: number[]; attempt?: number; done?: boolean; play?: boolean }): Msg {
    const title = 'Swing the third phrase';
    return {
      mode: o.done || o.play ? 'play' : 'practice', goal: o.goal,
      plan: o.goal ? [{ title, status: o.done ? 'done' : 'now' }] : [],
      drill: o.drill && !o.done ? { title, skill: 'swing-the-phrase', step: 1, of: 1 } : null,
      attempt: o.drill && !o.done ? { n: o.attempt ?? 0, of: 3 } : null,
      metric: o.history ? { name: 'timing drift, phrase 3', unit: 'ms', target: 40, lower_is_better: true, history: o.history } : null,
      next: o.done || o.play ? null : 'Full riff, even attacks', last_time: o.done ? null : this.memory || null,
      summary: o.done ? 'Phrase 3 drift 118 to 31 ms with even attacks once it swung; the target was met.' : o.play ? this.memory || null : null,
      next_time: o.done ? 'Swing phrase 3 at full tempo, then the whole riff' : null,
    };
  }

  private publish(changes: Msg): void {
    this.frame = { ...this.frame, ...changes, timestamp_ms: Date.now() };
    this.socket?.deliver(this.frame);
  }

  private activity(who: string, what: string, status: string): void {
    const activity = [...(this.frame.activity as Msg[]), { who, what, status }].slice(-8);
    this.publish({ activity });
  }

  private todos(plan: string[], doneCount: number): void {
    this.publish({ todos: plan.map((text, i) => ({ text, status: i < doneCount ? 'completed' : i === doneCount ? 'in_progress' : 'pending' })) });
  }

  private say(id: LineId, frame: Msg): void {
    const text = LINES[id].text;
    this.publish({ ...frame, cue: text });
    const b64 = this.audio.get(id);
    if (b64) this.socket?.deliver({ version: 1, type: 'coach.audio', timestamp_ms: Date.now(), text, mime: 'audio/mpeg', audio_b64: b64 });
  }

  private lineMs(id: LineId): number { return LINES[id].ms; }

  private later(ms: number, fn: () => void): void { this.timers.push(Number(setTimeout(fn, ms))); }

  private async loadVoice(): Promise<void> {
    await Promise.all((Object.keys(LINES) as LineId[]).map(async id => {
      const url = voiceFiles[`./demo-voice/${id}.mp3`];
      if (!url) return;   // no clip: coach.js falls back to the browser voice
      try {
        const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer());
        let text = '';
        for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
        this.audio.set(id, btoa(text));
      } catch { /* offline: browser voice */ }
    }));
  }
}
