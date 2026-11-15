import { describe, it, expect, vi } from 'vitest';
vi.mock('@mediapipe/tasks-vision', () => ({ FilesetResolver: {}, HandLandmarker: {} }));
import { LiveHandTracker } from '../../dashboard/browser/vision/hand-tracker';
import { GestureController } from '../../dashboard/browser/vision/gesture-controller';

// Anatomical right hand in raw, unmirrored camera coordinates. Move the WHOLE
// hand so palm orientation does not accidentally change when testing the zone.
function pose(kind: 'open' | 'pinch' | 'fist', y = .4, score = .95, label = 'Right') {
  const points = Array.from({ length: 21 }, () => ({ x: .5, y: y+.05 }));
  points[0] = { x: .5, y: y+.2 };
  for (const [i,x] of [[5,.60],[9,.535],[13,.465],[17,.40]]) points[i] = { x, y };
  for (const [tip,mcp] of [[8,5],[12,9],[16,13],[20,17]]) {
    points[tip] = { x: points[mcp].x, y: y+(kind === 'fist' ? .025 : -.18) };
  }
  points[4] = { x: .72, y: y-.08 };
  if (kind === 'pinch') points[4] = { x: points[8].x-.012, y: points[8].y };
  if (kind === 'fist') points[4] = { x: .55, y: y+.025 };
  return { landmarks: [points], handedness: [[{ categoryName: label, score }]] };
}
function harness() {
  const tracker: any = new LiveHandTracker();
  tracker.videoEl = { videoWidth: 640, videoHeight: 480 };
  const controller = new GestureController({ tau: .03 });
  const swap = vi.fn(() => controller.rearm()); tracker.onFistSwap = swap;
  const frame = (data: ReturnType<typeof pose>, time: number) => {
    tracker.processResult(data,time,controller.active,controller.control,controller.value,controller.armed);
    const obs = tracker.getObservation();
    return controller.update(obs.y,obs.pinch,obs.confidence,time/1000,time);
  };
  return { tracker,controller,swap,frame };
}

describe('right-hand controls survive strum guards', () => {
  it('arms and pinches in the lower half, then reaches the full slider range', () => {
    const h = harness();
    h.frame(pose('open',.65),1000);
    expect(h.controller.armed).toBe(true);
    expect(h.frame(pose('pinch',.65),1050)).not.toBeNull();
    for (let n=1;n<=8;n++) h.frame(pose('pinch',.65+n*.01875),1050+n*80);
    expect(h.controller.active).toBe(true);
    expect(h.controller.value).toBeLessThan(.05);
    for (let n=1;n<=12;n++) h.frame(pose('pinch',.8-n*.05),1800+n*100);
    expect(h.controller.value).toBeGreaterThan(.95);
    expect(h.swap).not.toHaveBeenCalled();
  });
  it('ignores a pick-shaped pinch entering the guitar zone without an open-hand arm', () => {
    const h = harness();
    h.frame(pose('pinch',.65),1000);
    expect(h.tracker.getObservation().present).toBe(false);
    expect(h.controller.active).toBe(false); expect(h.swap).not.toHaveBeenCalled();
  });
  it('still suppresses rhythmic strumming during an active deliberate clutch', () => {
    const h=harness(); h.frame(pose('open',.4),1000);h.frame(pose('pinch',.4),1050);
    h.frame(pose('pinch',.45),1100);h.frame(pose('pinch',.39),1150);h.frame(pose('pinch',.45),1200);
    expect(h.tracker.getHandFrame().isStrumming).toBe(true);
    expect(h.controller.active).toBe(false);
  });
  it('does not classify tiny fast landmark jitter as strumming', () => {
    const h=harness();h.frame(pose('open',.4),1000);h.frame(pose('pinch',.4),1050);
    for(let n=1;n<=12;n++)h.frame(pose('pinch',.4+(n%2 ? .008 : -.008)),1050+n*33);
    expect(h.controller.active).toBe(true);expect(h.tracker.getHandFrame().isStrumming).toBe(false);
  });
  it('confirms a fist, stops slider dragging, and consumes it only once', () => {
    const h=harness();h.frame(pose('open',.65),1000);
    h.frame(pose('fist',.65),1050);expect(h.swap).not.toHaveBeenCalled();
    h.frame(pose('fist',.65),1200);expect(h.swap).toHaveBeenCalledTimes(1);
    expect(h.controller.active).toBe(false);
    // A single back-facing frame must not re-arm a still-closed fist.
    const back=pose('fist',.65);back.landmarks[0]=back.landmarks[0].map(p=>({...p,x:1-p.x}));
    h.frame(back,2700);h.frame(pose('fist',.65),2750);h.frame(pose('fist',.65),2950);
    expect(h.swap).toHaveBeenCalledTimes(1);
    h.frame(pose('open',.65),3100);h.frame(pose('fist',.65),3150);h.frame(pose('fist',.65),3300);
    expect(h.swap).toHaveBeenCalledTimes(2);
  });
  it('does not count a paused camera as a continuously held fist', () => {
    const h=harness();h.frame(pose('fist',.4),1000);h.frame(pose('fist',.4),5000);
    expect(h.swap).not.toHaveBeenCalled();
    h.frame(pose('fist',.4),5150);expect(h.swap).toHaveBeenCalledTimes(1);
  });
  it.each([.2,NaN,Infinity,-1,1.1])('never swaps on invalid/low confidence %s', score => {
    const h=harness();h.frame(pose('fist',.4,score),1000);h.frame(pose('fist',.4,score),1300);
    expect(h.swap).not.toHaveBeenCalled();expect(h.tracker.getObservation().present).toBe(false);
  });
  it.each(['Left','Unknown',''])('ignores %s classification for controls and fist swaps', label => {
    const h=harness();h.frame(pose('open',.4,.99,label),1000);h.frame(pose('fist',.4,.99,label),1100);h.frame(pose('fist',.4,.99,label),1300);
    expect(h.swap).not.toHaveBeenCalled();expect(h.controller.armed).toBe(false);
  });
});
