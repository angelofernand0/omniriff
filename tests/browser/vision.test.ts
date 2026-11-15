import { describe, it, expect } from 'vitest';
import { GestureController } from '../../dashboard/browser/vision/gesture-controller';
import { SceneMorph, DEFAULT_SCENES } from '../../dashboard/browser/vision/scenes';
import { Setlist } from '../../dashboard/browser/vision/setlist';

describe('GestureController parity tests', () => {
  it('requires open-hand re-arm (pinch >= 0.45) before pinch engagement (pinch <= 0.25)', () => {
    const ctrl = new GestureController({ low: 0.8, high: 0.2, rate: 20 });
    let t = 1.0;

    // Direct pinch without opening first should NOT engage
    let ev = ctrl.update(0.5, 0.20, 0.9, t++, 1000);
    expect(ev).toBeNull();
    expect(ctrl.active).toBe(false);
    expect(ctrl.armed).toBe(false);

    // Open hand (pinch >= 0.45) -> arms controller
    ev = ctrl.update(0.5, 0.50, 0.9, t++, 2000);
    expect(ev).toBeNull();
    expect(ctrl.armed).toBe(true);
    expect(ctrl.active).toBe(false);

    // Now pinch (pinch <= 0.25) -> engages and emits event!
    ev = ctrl.update(0.5, 0.20, 0.9, t++, 3000);
    expect(ev).not.toBeNull();
    expect(ctrl.active).toBe(true);
    expect(ev?.control).toBe('filter');
    expect(ev?.value).toBeCloseTo(0.5, 2); // 0.5 is halfway between 0.8 and 0.2
  });

  it('rejects low confidence frames and disarms immediately', () => {
    const ctrl = new GestureController({ confidence: 0.6 });
    let t = 1.0;

    ctrl.update(0.5, 0.50, 0.9, t++, 1000);
    expect(ctrl.armed).toBe(true);

    // Low confidence frame (< 0.6)
    const ev = ctrl.update(0.5, 0.20, 0.4, t++, 2000);
    expect(ev).toBeNull();
    expect(ctrl.armed).toBe(false);
    expect(ctrl.active).toBe(false);
  });

  it('rearm resets active and armed states for scene transitions', () => {
    const ctrl = new GestureController();
    ctrl.update(0.5, 0.50, 0.9, 1.0, 1000);
    ctrl.update(0.5, 0.20, 0.9, 1.1, 1100);
    expect(ctrl.active).toBe(true);

    ctrl.rearm();
    expect(ctrl.active).toBe(false);
    expect(ctrl.armed).toBe(false);

    // Moving pinched hand without re-opening does not emit
    const ev = ctrl.update(0.4, 0.20, 0.9, 1.2, 1200);
    expect(ev).toBeNull();
  });

  it('disengages crisply on pinch release (pinch >= 0.32) without dragging down', () => {
    const ctrl = new GestureController({ low: 0.8, high: 0.2, rate: 20 });
    let t = 1.0;

    // Arm with open hand
    ctrl.update(0.5, 0.50, 0.9, t++, 1000);
    // Engage with pinch
    let ev = ctrl.update(0.35, 0.20, 0.9, t++, 1100);
    expect(ev).not.toBeNull();
    expect(ctrl.active).toBe(true);

    // Release pinch slightly (pinch = 0.33 >= 0.32): must disengage immediately
    ev = ctrl.update(0.35, 0.33, 0.9, t++, 1200);
    expect(ev).toBeNull();
    expect(ctrl.active).toBe(false);

    // Hand lowers down to guitar (y = 0.5, 0.7, 0.9): must NEVER emit downward drag events
    ev = ctrl.update(0.50, 0.35, 0.9, t++, 1300);
    expect(ev).toBeNull();
    ev = ctrl.update(0.70, 0.38, 0.9, t++, 1400);
    expect(ev).toBeNull();
    ev = ctrl.update(0.90, 0.45, 0.9, t++, 1500);
    expect(ev).toBeNull();
  });

  it('detects downward motion while relaxing pinch (pinch > 0.27 && dy > 0) and releases immediately', () => {
    const ctrl = new GestureController({ low: 0.8, high: 0.2, rate: 20 });
    let t = 1.0;

    // Arm & engage
    ctrl.update(0.5, 0.50, 0.9, t++, 1000);
    let ev = ctrl.update(0.30, 0.20, 0.9, t++, 1100);
    expect(ctrl.active).toBe(true);

    // Hand starts moving downward to guitar while relaxing grip (y: 0.30 -> 0.35, pinch: 0.28)
    ev = ctrl.update(0.35, 0.28, 0.9, t++, 1200);
    expect(ev).toBeNull();
    expect(ctrl.active).toBe(false);
  });
});

describe('SceneMorph and Setlist tests', () => {
  it('interpolates endpoints with smoothstep curve', () => {
    const morph = new SceneMorph({
      name: 'Test Scene',
      from: { filter: 1.0, reverb: 0.0 },
      to: { filter: 0.2, reverb: 0.8 },
    });

    // Endpoints
    const start = morph.values(0.0);
    expect(start.filter).toBe(1.0);
    expect(start.reverb).toBe(0.0);

    const end = morph.values(1.0);
    expect(end.filter).toBeCloseTo(0.2, 5);
    expect(end.reverb).toBeCloseTo(0.8, 5);

    // Midpoint 0.5: t = 0.5 * 0.5 * (3 - 2 * 0.5) = 0.25 * 2 = 0.5
    const mid = morph.values(0.5);
    expect(mid.filter).toBeCloseTo(0.6, 4);
    expect(mid.reverb).toBeCloseTo(0.4, 4);
  });

  it('setlist cycles scenes with next, previous and number keys', () => {
    const setlist = new Setlist(DEFAULT_SCENES);
    expect(setlist.scenes.length).toBe(3);
    expect(setlist.index).toBe(0);
    expect(setlist.current.name).toBe('Clear to Cosmos');

    // Key 'n' -> next scene
    expect(setlist.key('n')).toBe(true);
    expect(setlist.index).toBe(1);
    expect(setlist.current.name).toBe('Underwater to Spotlight');

    // Key 'n' -> next scene
    expect(setlist.key('n')).toBe(true);
    expect(setlist.index).toBe(2);

    // Wraparound to 0
    expect(setlist.key('n')).toBe(true);
    expect(setlist.index).toBe(0);

    // Key 'p' -> previous wraps to 2
    expect(setlist.key('p')).toBe(true);
    expect(setlist.index).toBe(2);

    // Direct key '1' -> index 0
    expect(setlist.key('1')).toBe(true);
    expect(setlist.index).toBe(0);

    // Same scene selection returns false
    expect(setlist.key('1')).toBe(false);
  });
});
