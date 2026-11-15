/**
 * Thumbs-up: the hands-free "yes" to Riff's drill (instead of Y or a pedal hold).
 *
 * Only ever consulted while the coach is waiting for an approval, and it must be held,
 * so normal playing can't trigger it: on the fretboard the fingers are spread, and a
 * hand holding a pick points its thumb across, not up.
 */
export type Point = [number, number];

const dist = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1]);

/** One frame of 21 image-normalised points (y grows downward). */
export function isThumbsUp(lm: Point[]): boolean {
  if (lm.length !== 21) return false;
  const hand = dist(lm[0], lm[9]);
  if (!(hand > 0.01)) return false;
  const [tip, ip, mcp] = [lm[4], lm[3], lm[2]];
  const thumbUp = tip[1] < ip[1] && ip[1] < mcp[1]          // pointing up the image
    && lm[5][1] - tip[1] > 0.45 * hand                      // well above the index knuckle
    && Math.abs(tip[0] - mcp[0]) < 0.6 * hand;              // up, not across
  if (!thumbUp) return false;
  // the four fingers are curled into the palm: each tip is no farther from the wrist than its knuckle
  return [[8, 5], [12, 9], [16, 13], [20, 17]].every(([t, k]) => dist(lm[t], lm[0]) < 1.05 * dist(lm[k], lm[0]));
}

/** Fires once when a thumbs-up has been held for `holdMs`; resets when the hand changes. */
export class ThumbsUpHold {
  private since: number | null = null;
  private fired = false;
  constructor(private readonly holdMs = 600) {}

  update(nowMs: number, up: boolean): boolean {
    if (!up) { this.since = null; this.fired = false; return false; }
    if (this.since === null) this.since = nowMs;
    if (!this.fired && nowMs - this.since >= this.holdMs) { this.fired = true; return true; }
    return false;
  }

  reset(): void { this.since = null; this.fired = false; }
  get holding(): number { return this.since === null ? 0 : 1; }
}
