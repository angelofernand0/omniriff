import { describe, it, expect, vi, afterEach } from 'vitest';
vi.mock('@mediapipe/tasks-vision', () => ({ FilesetResolver: {}, HandLandmarker: {} }));
import { LiveHandTracker } from '../../dashboard/browser/vision/hand-tracker';
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function result() {
  const hand = Array.from({ length: 21 }, () => ({ x: .5, y: .5 }));
  hand[5].x = .4; hand[17].x = .6; hand[8].x = .55;
  return { landmarks: [hand], handedness: [[{ score: .95 }]] };
}
describe('Live hand tracker guards without camera access', () => {
  it('clears observations on stop and never invents missing confidence', () => {
    const tracker: any = new LiveHandTracker(); const data = result(); data.handedness = [];
    tracker.processResult(data, 1000, true, 'filter', .5);
    expect(tracker.getObservation().confidence).toBe(0);
    tracker.stop(); expect(tracker.getObservation().present).toBe(false);
    expect(tracker.getHandFrame()).toMatchObject({ present: false, engaged: false, landmarks: [] });
  });
  it('rejects expired inference and collapsed or nonfinite landmark geometry', () => {
    const tracker: any = new LiveHandTracker(); tracker.isRunning = true;
    tracker.videoEl = { readyState: 2, videoWidth: 640, videoHeight: 480 };
    tracker.landmarker = { detectForVideo: () => result() };
    vi.spyOn(performance, 'now').mockReturnValue(1300); tracker.update(1000, true, 'filter', .5);
    expect(tracker.getObservation().present).toBe(false);
    const collapsed = result(); collapsed.landmarks[0][5].x = .6;
    tracker.processResult(collapsed, 1400, false, 'filter', .5); expect(tracker.getObservation().present).toBe(false);
    const invalid = result(); invalid.landmarks[0][2].x = Number.NaN;
    tracker.processResult(invalid, 1500, false, 'filter', .5); expect(tracker.getObservation().present).toBe(false);
  });
  it('cancels metadata startup, stops the acquired stream and never starts video after stop', async () => {
    const tracker: any = new LiveHandTracker(); tracker.initialize = vi.fn(async () => {});
    const video = { readyState: 0, autoplay: false, playsInline: false, muted: false, srcObject: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(), pause: vi.fn(), play: vi.fn(async () => {}) };
    vi.stubGlobal('document', { createElement: () => video });
    const track = { stop: vi.fn() }; const stream = { getTracks: () => [track] };
    const pending = tracker.start(stream); await Promise.resolve(); tracker.stop(); await pending;
    expect(track.stop).toHaveBeenCalledOnce(); expect(video.play).not.toHaveBeenCalled(); expect(tracker.isRunning).toBe(false);
  });
  it('detects index-to-thumb pinch and triggers onPinchSwap with latching', () => {
    const tracker: any = new LiveHandTracker();
    let swapCount = 0;
    tracker.onPinchSwap = () => { swapCount++; };

    const pinched = result();
    pinched.landmarks[0][4] = { x: 0.50, y: 0.50 };
    pinched.landmarks[0][8] = { x: 0.51, y: 0.50 };
    tracker.processResult(pinched, 1000, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Repeated frame while still pinched should NOT trigger another swap (latched)
    tracker.processResult(pinched, 1030, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Release pinch (pinch >= 0.42): thumb tip and index tip separated
    const released = result();
    released.landmarks[0][4] = { x: 0.35, y: 0.50 };
    released.landmarks[0][8] = { x: 0.65, y: 0.50 };
    tracker.processResult(released, 1060, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Pinch again -> second swap!
    tracker.processResult(pinched, 1090, false, 'filter', 0.5);
    expect(swapCount).toBe(2);
  });
  it('computes fist curl and palm center y for vertical drag', () => {
    const tracker: any = new LiveHandTracker();
    const openHand = result();
    openHand.landmarks[0][5] = { x: 0.4, y: 0.5 };
    openHand.landmarks[0][17] = { x: 0.6, y: 0.5 };
    openHand.landmarks[0][9] = { x: 0.5, y: 0.45 };
    openHand.landmarks[0][8] = { x: 0.4, y: 0.2 };
    openHand.landmarks[0][12] = { x: 0.5, y: 0.15 };
    openHand.landmarks[0][16] = { x: 0.58, y: 0.2 };
    openHand.landmarks[0][20] = { x: 0.65, y: 0.25 };
    tracker.processResult(openHand, 1000, false, 'filter', 0.5);
    const openObs = tracker.getObservation();
    expect(openObs.present).toBe(true);
    expect(openObs.y).toBe(0.45);
    expect(openObs.pinch).toBeGreaterThanOrEqual(0.45);

    const fistHand = result();
    fistHand.landmarks[0][5] = { x: 0.4, y: 0.5 };
    fistHand.landmarks[0][17] = { x: 0.6, y: 0.5 };
    fistHand.landmarks[0][9] = { x: 0.5, y: 0.45 };
    fistHand.landmarks[0][8] = { x: 0.42, y: 0.48 };
    fistHand.landmarks[0][12] = { x: 0.50, y: 0.46 };
    fistHand.landmarks[0][16] = { x: 0.56, y: 0.48 };
    fistHand.landmarks[0][20] = { x: 0.60, y: 0.50 };
    tracker.processResult(fistHand, 1030, false, 'filter', 0.5);
    const fistObs = tracker.getObservation();
    expect(fistObs.present).toBe(true);
    expect(fistObs.y).toBe(0.45);
    expect(fistObs.pinch).toBeLessThanOrEqual(0.25);
  });
});
