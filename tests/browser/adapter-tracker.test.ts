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
});
