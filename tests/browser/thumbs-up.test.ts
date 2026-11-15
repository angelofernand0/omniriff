import { describe, expect, it } from 'vitest';
import { isThumbsUp, ThumbsUpHold, type Point } from '../../dashboard/browser/vision/thumbs-up';

// A schematic right hand, wrist at the bottom (y grows downward), knuckles above it.
function hand({ thumbUp, curled }: { thumbUp: boolean; curled: boolean }): Point[] {
  const p: Point[] = Array.from({ length: 21 }, () => [0.5, 0.5] as Point);
  p[0] = [0.5, 0.7];
  const knuckles: Array<[number, number]> = [[5, 0.46], [9, 0.5], [13, 0.54], [17, 0.58]];
  for (const [k, x] of knuckles) {
    p[k] = [x, 0.6];
    p[k + 1] = curled ? [x, 0.63] : [x, 0.55];
    p[k + 2] = curled ? [x, 0.66] : [x, 0.52];
    p[k + 3] = curled ? [x, 0.65] : [x, 0.49];   // tip back near the palm when curled
  }
  p[1] = [0.44, 0.67];
  if (thumbUp) { p[2] = [0.43, 0.6]; p[3] = [0.43, 0.54]; p[4] = [0.43, 0.49]; }
  else { p[2] = [0.44, 0.62]; p[3] = [0.48, 0.61]; p[4] = [0.52, 0.61]; }   // across the palm, holding a pick
  return p;
}

describe('thumbs-up', () => {
  it('recognises a thumb up over a closed fist', () => {
    expect(isThumbsUp(hand({ thumbUp: true, curled: true }))).toBe(true);
  });
  it('ignores an open hand (fretting) and a pick grip', () => {
    expect(isThumbsUp(hand({ thumbUp: true, curled: false }))).toBe(false);
    expect(isThumbsUp(hand({ thumbUp: false, curled: true }))).toBe(false);
    expect(isThumbsUp([])).toBe(false);
  });
  it('fires once after a hold and re-arms only after release', () => {
    const hold = new ThumbsUpHold(600);
    expect(hold.update(0, true)).toBe(false);
    expect(hold.update(500, true)).toBe(false);
    expect(hold.update(650, true)).toBe(true);
    expect(hold.update(900, true)).toBe(false);
    expect(hold.update(950, false)).toBe(false);
    expect(hold.update(1000, true)).toBe(false);
    expect(hold.update(1700, true)).toBe(true);
  });
});
