/**
 * The footswitch sends one event per tap ("loop" on release) and "practice" after a 700 ms hold.
 * It never reports a release, so talking can't be press-and-hold like the V key. Instead:
 *
 *   double tap          Riff listens (hands-free; it sends when you stop talking)
 *   tap while listening send what you said now
 *   single tap          loop, as before
 *
 * Telling a single tap from a double tap means a single tap waits DOUBLE_TAP_MS before it loops.
 * That wait only happens when talking is possible (Riff is awake and you are not recording), so
 * stopping a take is always instant.
 */

export const DOUBLE_TAP_MS = 350;

export interface PedalTalk {
  /** Riff can listen right now (awake, connected, not recording). */
  canTalk(): boolean;
  /** Riff is listening right now. */
  listening(): boolean;
  listen(): void;
  sendNow(): void;
}

export class PedalTaps {
  private pending: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly loop: () => void,
    private readonly talk: () => PedalTalk | null,
    private readonly windowMs = DOUBLE_TAP_MS,
  ) {}

  tap(): void {
    const talk = this.talk();
    if (talk?.listening()) { this.cancel(); talk.sendNow(); return; }
    if (this.pending !== null) { this.cancel(); talk?.listen(); return; }   // second tap
    if (!talk || !talk.canTalk()) { this.loop(); return; }                 // no wait needed
    this.pending = setTimeout(() => { this.pending = null; this.loop(); }, this.windowMs);
  }

  cancel(): void {
    if (this.pending !== null) clearTimeout(this.pending);
    this.pending = null;
  }
}

/** coach.js publishes its talk controls on window.OmniRiff.coachFeed. */
export function coachTalk(): PedalTalk | null {
  const feed = typeof window !== 'undefined' ? (window as any).OmniRiff?.coachFeed : null;
  if (!feed || typeof feed.listen !== 'function') return null;
  return {
    canTalk: () => !!feed.canTalk?.(),
    listening: () => feed.talk?.() === 'listening',
    listen: () => feed.listen(),
    sendNow: () => feed.sendNow(),
  };
}
