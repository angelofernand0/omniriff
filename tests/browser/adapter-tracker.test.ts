import { describe, it, expect, vi, afterEach } from 'vitest';
vi.mock('@mediapipe/tasks-vision', () => ({ FilesetResolver: {}, HandLandmarker: {} }));
import { LiveHandTracker } from '../../dashboard/browser/vision/hand-tracker';
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function result() {
  const hand = Array.from({ length: 21 }, () => ({ x: .5, y: .5 }));
  hand[5].x = .4; hand[17].x = .6; hand[8].x = .55;
  return { landmarks: [hand], handedness: [[{ score: .95, categoryName: 'Right' }]] as any };
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

  it('ignores left hand (holding guitar neck) and only tracks right hand', () => {
    const tracker: any = new LiveHandTracker();

    // 1. Only left hand in frame (fretting guitar neck): must be ignored completely
    const leftHand = result();
    leftHand.handedness = [[{ categoryName: 'Left', score: 0.98 }]];
    tracker.processResult(leftHand, 1000, false, 'filter', 0.5);
    expect(tracker.getObservation().present).toBe(false);
    expect(tracker.getObservation().y).toBeNull();
    expect(tracker.getObservation().pinch).toBeNull();

    // 2. Both hands in frame: Left hand (neck) at idx 0, Right hand (air/strum) at idx 1
    const rightHand = result();
    rightHand.landmarks[0][9] = { x: 0.5, y: 0.35 }; // Right hand in air at y=0.35
    const twoHands = {
      landmarks: [leftHand.landmarks[0], rightHand.landmarks[0]],
      handedness: [
        [{ categoryName: 'Left', score: 0.98 }],
        [{ categoryName: 'Right', score: 0.94 }],
      ],
    };

    tracker.processResult(twoHands, 1050, false, 'filter', 0.5);
    const obs = tracker.getObservation();
    expect(obs.present).toBe(true);
    expect(obs.y).toBe(0.35); // Selected Right hand, completely ignored Left hand!
  });

  it('rejects back-of-hand (dorsal orientation) while playing guitar to prevent false pinches and swaps', () => {
    const tracker: any = new LiveHandTracker();
    let swapCount = 0;
    tracker.onFistSwap = () => { swapCount++; };

    // Back of right hand facing camera: knuckles inverted (index on right, pinky on left)
    const backOfHand = result();
    backOfHand.handedness = [[{ categoryName: 'Right', score: 0.95 }]];
    backOfHand.landmarks[0][0] = { x: 0.5, y: 0.5 }; // wrist
    backOfHand.landmarks[0][9] = { x: 0.5, y: 0.45 }; // middle MCP
    backOfHand.landmarks[0][5] = { x: 0.6, y: 0.5 }; // index MCP on right
    backOfHand.landmarks[0][17] = { x: 0.4, y: 0.5 }; // pinky MCP on left (cross product < 0: dorsal)

    // Fingers curled / holding pick (would look like a fist or pinch if orientation wasn't checked)
    backOfHand.landmarks[0][4] = { x: 0.52, y: 0.46 }; // thumb
    backOfHand.landmarks[0][8] = { x: 0.53, y: 0.46 }; // index (pinch = 0.05)
    backOfHand.landmarks[0][12] = { x: 0.50, y: 0.46 };
    backOfHand.landmarks[0][16] = { x: 0.46, y: 0.48 };
    backOfHand.landmarks[0][20] = { x: 0.42, y: 0.50 };

    tracker.processResult(backOfHand, 1000, false, 'filter', 0.5);

    // Must be marked as strumming, suppressed observation, and NO fist swap!
    expect(tracker.getObservation().present).toBe(false);
    expect(tracker.getObservation().y).toBeNull();
    expect(tracker.getObservation().pinch).toBeNull();
    expect(tracker.getHandFrame().isStrumming).toBe(true);
    expect(tracker.getHandFrame().isPalmFacing).toBe(false);
    expect(swapCount).toBe(0);
  });

  it('suppresses false triggers in guitar strumming zone (y >= 0.52) while holding a pick', () => {
    const tracker: any = new LiveHandTracker();
    let swapCount = 0;
    tracker.onFistSwap = () => { swapCount++; };

    // Hand in guitar zone (y = 0.65) holding a pick (pinch = 0.15)
    const strummingHand = result();
    strummingHand.handedness = [[{ categoryName: 'Right', score: 0.95 }]];
    strummingHand.landmarks[0][9] = { x: 0.5, y: 0.65 };
    strummingHand.landmarks[0][4] = { x: 0.48, y: 0.63 };
    strummingHand.landmarks[0][8] = { x: 0.51, y: 0.63 }; // pinch = 0.03 / 0.2 = 0.15

    tracker.processResult(strummingHand, 1000, false, 'filter', 0.5);
    expect(tracker.getObservation().present).toBe(false);
    expect(tracker.getHandFrame().isStrumming).toBe(true);
    expect(swapCount).toBe(0);
  });

  it('detects rhythmic strumming oscillation across strings and suppresses gestures', () => {
    const tracker: any = new LiveHandTracker();
    const frame = () => {
      const h = result();
      h.handedness = [[{ categoryName: 'Right', score: 0.95 }]];
      return h;
    };

    // Strum downstroke -> upstroke -> downstroke
    const f1 = frame(); f1.landmarks[0][9] = { x: 0.5, y: 0.40 };
    tracker.processResult(f1, 1000, false, 'filter', 0.5);

    const f2 = frame(); f2.landmarks[0][9] = { x: 0.5, y: 0.44 }; // dy/dt = +0.8
    tracker.processResult(f2, 1050, false, 'filter', 0.5);

    const f3 = frame(); f3.landmarks[0][9] = { x: 0.5, y: 0.39 }; // dy/dt = -1.0 (reversal 1)
    tracker.processResult(f3, 1100, false, 'filter', 0.5);

    const f4 = frame(); f4.landmarks[0][9] = { x: 0.5, y: 0.44 }; // dy/dt = +1.0 (reversal 2)
    tracker.processResult(f4, 1150, false, 'filter', 0.5);

    expect(tracker.getHandFrame().isStrumming).toBe(true);
    expect(tracker.getObservation().present).toBe(false);
  });

  it('allows intentional air gestures (y < 0.50, palm facing camera) to control parameters and trigger fist swap', () => {
    const tracker: any = new LiveHandTracker();
    let swapCount = 0;
    tracker.onFistSwap = () => { swapCount++; };

    // Intentional air hand: y = 0.35, palm facing camera, open hand
    const airHand = result();
    airHand.handedness = [[{ categoryName: 'Right', score: 0.96 }]];
    airHand.landmarks[0][9] = { x: 0.5, y: 0.35 };
    airHand.landmarks[0][8] = { x: 0.4, y: 0.15 }; // fingers open
    airHand.landmarks[0][12] = { x: 0.5, y: 0.12 };

    tracker.processResult(airHand, 1000, false, 'filter', 0.5);
    expect(tracker.getObservation().present).toBe(true);
    expect(tracker.getObservation().y).toBe(0.35);
    expect(tracker.getHandFrame().isStrumming).toBe(false);
    expect(tracker.getHandFrame().isPalmFacing).toBe(true);

    // Intentional fist in air (y = 0.35, palm facing camera)
    const airFist = result();
    airFist.handedness = [[{ categoryName: 'Right', score: 0.96 }]];
    airFist.landmarks[0][9] = { x: 0.5, y: 0.35 };
    airFist.landmarks[0][8] = { x: 0.42, y: 0.38 };
    airFist.landmarks[0][12] = { x: 0.50, y: 0.36 };
    airFist.landmarks[0][16] = { x: 0.56, y: 0.38 };
    airFist.landmarks[0][20] = { x: 0.60, y: 0.40 };

    tracker.processResult(airFist, 1100, false, 'filter', 0.5);
    expect(swapCount).toBe(1);
    expect(tracker.getHandFrame().isFist).toBe(true);
  });
});
