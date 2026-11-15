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
  it('detects closed fist and triggers onFistSwap with 2-second cooldown and anti-flicker protection', () => {
    const tracker: any = new LiveHandTracker();
    let swapCount = 0;
    tracker.onFistSwap = () => { swapCount++; };

    // Fist: fingertips curled into MCPs
    const fist = result();
    fist.landmarks[0][5] = { x: 0.4, y: 0.5 };
    fist.landmarks[0][17] = { x: 0.6, y: 0.5 }; // palmWidth = 0.2
    fist.landmarks[0][9] = { x: 0.5, y: 0.45 };
    fist.landmarks[0][8] = { x: 0.42, y: 0.48 }; // index tip curled
    fist.landmarks[0][12] = { x: 0.50, y: 0.46 }; // middle tip curled
    fist.landmarks[0][16] = { x: 0.56, y: 0.48 }; // ring tip curled
    fist.landmarks[0][20] = { x: 0.60, y: 0.50 }; // pinky tip curled

    tracker.processResult(fist, 1000, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Repeated fist frame at 1500ms (within 2s cooldown) must NOT trigger swap (anti-flicker)
    tracker.processResult(fist, 1500, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Frame at 3100ms (>2s cooldown) but WITHOUT opening hand first must NOT trigger swap (latching)
    tracker.processResult(fist, 3100, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Open hand: fingers extended
    const openHand = result();
    openHand.landmarks[0][5] = { x: 0.4, y: 0.5 };
    openHand.landmarks[0][17] = { x: 0.6, y: 0.5 };
    openHand.landmarks[0][9] = { x: 0.5, y: 0.45 };
    openHand.landmarks[0][8] = { x: 0.4, y: 0.2 };
    openHand.landmarks[0][12] = { x: 0.5, y: 0.15 };
    openHand.landmarks[0][16] = { x: 0.58, y: 0.2 };
    openHand.landmarks[0][20] = { x: 0.65, y: 0.25 };
    tracker.processResult(openHand, 3200, false, 'filter', 0.5);
    expect(swapCount).toBe(1);

    // Now close fist again after cooldown and opening -> triggers second swap!
    tracker.processResult(fist, 3300, false, 'filter', 0.5);
    expect(swapCount).toBe(2);
  });
  it('tracks palm joint y and index-to-thumb pinch for vertical slider control', () => {
    const tracker: any = new LiveHandTracker();
    const handData = result();
    handData.landmarks[0][5] = { x: 0.4, y: 0.5 };
    handData.landmarks[0][17] = { x: 0.6, y: 0.5 }; // palmWidth = 0.2
    handData.landmarks[0][9] = { x: 0.5, y: 0.42 }; // palm center
    handData.landmarks[0][4] = { x: 0.48, y: 0.40 }; // thumb tip
    handData.landmarks[0][8] = { x: 0.50, y: 0.40 }; // index tip (pinch = 0.02 / 0.2 = 0.1)

    tracker.processResult(handData, 1000, false, 'filter', 0.5);
    const obs = tracker.getObservation();
    expect(obs.present).toBe(true);
    expect(obs.y).toBe(0.42);
    expect(obs.pinch).toBeCloseTo(0.10, 2);
  });
});
