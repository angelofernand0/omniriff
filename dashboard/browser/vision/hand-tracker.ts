/**
 * MediaPipe HandLandmarker wrapper for Live Rig webcam tracking.
 * Adheres to safety invariants: nearest-wrist tracking, 0.30 max wrist jump,
 * 15 missed frames reset, open-hand re-arm.
 */

import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';
import type { GestureObservation } from '../simulation/simulated-hand';
import type { HandFrame } from '../protocol/types';
import { absentHand } from '../adapters/connection';


export interface TrackedHand { handedness: 'Left' | 'Right'; confidence: number; landmarks: Array<[number, number]>; }

export class LiveHandTracker {
  private generation = 0;
  private cancelMetadata: (() => void) | null = null;
  private landmarker: HandLandmarker | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private stream: MediaStream | null = null;

  public isRunning: boolean = false;
  /** Called with every visible hand on each processed frame (hosted coach technique analysis). */
  public onAllHands: ((hands: TrackedHand[]) => void) | null = null;
  private isProcessing: boolean = false;
  private lastInferenceTimeMs: number = 0;

  // Safety tracking state
  private lastWrist: [number, number] | null = null;
  private consecutiveMisses: number = 0;
  private readonly maxWristJump: number = 0.30;
  private readonly maxMissedFrames: number = 15;

  // Strum guard & velocity reversal tracking
  private lastStrumY: number | null = null;
  private lastStrumTimeMs: number = 0;
  private lastVelocitySign: number = 0;
  private reversalTimes: number[] = [];
  private strumAnchorY: number | null = null;
  private fistSinceMs: number | null = null;

  public onFistSwap: (() => void) | null = null;
  private fistLatched: boolean = false;
  private lastSwapTimeMs: number = -Infinity;

  private latestObservation: GestureObservation = {
    present: false,
    y: null,
    pinch: null,
    confidence: 0.0,
    timestamp_ms: 0,
  };

  private latestHandFrame: HandFrame = {
    version: 1,
    type: 'hand',
    timestamp_ms: 0,
    present: false,
    engaged: false,
    confidence: 0.0,
    control: 'filter',
    value: null,
    landmarks: [],
  };

  constructor() {}

  public async initialize(): Promise<void> {
    if (this.landmarker) return;

    try {
      const vision = await FilesetResolver.forVisionTasks(
        'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm'
      );

      // Try GPU delegate first, fallback to CPU
      try {
        this.landmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
            delegate: 'GPU',
          },
          runningMode: 'VIDEO',
          numHands: 2,
        });
      } catch (gpuErr) {
        console.warn('GPU delegate failed, falling back to CPU:', gpuErr);
        this.landmarker = await HandLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
            delegate: 'CPU',
          },
          runningMode: 'VIDEO',
          numHands: 2,
        });
      }
    } catch (err) {
      console.error('Failed to initialize MediaPipe HandLandmarker:', err);
      throw new Error('MediaPipe vision initialization failed. Check your internet connection.');
    }
  }

  public async start(videoStream: MediaStream): Promise<void> {
    const generation = ++this.generation;
    this.resetObservation();
    await this.initialize();
    if (generation !== this.generation) { videoStream.getTracks().forEach(t => t.stop()); return; }
    this.stream = videoStream;
    const domVideo = typeof document !== 'undefined' && typeof document.getElementById === 'function' ? (document.getElementById('cameraVideo') as HTMLVideoElement | null) : null;
    const video = domVideo || (typeof document !== 'undefined' && typeof document.createElement === 'function' ? document.createElement('video') : ({} as any));
    this.videoEl = video;
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      let timer: ReturnType<typeof setTimeout>;
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        video.removeEventListener('loadedmetadata', ready);
        video.removeEventListener('error', failed);
        this.cancelMetadata = null;
        if (error) reject(error); else resolve();
      };
      const ready = () => finish();
      const failed = () => finish(new Error('Camera video could not start'));
      this.cancelMetadata = () => finish();
      video.addEventListener('loadedmetadata', ready);
      video.addEventListener('error', failed);
      timer = setTimeout(() => finish(new Error('Camera metadata timed out')), 10000);
      video.srcObject = videoStream;
      if (video.readyState >= 1) ready();
    });
    if (generation !== this.generation) return;
    await video.play();
    if (generation !== this.generation) return;
    this.isRunning = true;
    if (typeof document !== 'undefined' && typeof document.getElementById === 'function') {
      const card = document.getElementById('card-camera');
      const tag = document.getElementById('camTag');
      if (card) card.dataset.cam = 'live';
      if (tag) { tag.textContent = 'LIVE'; tag.classList.add('live'); }
    }
    this.consecutiveMisses = 0;
    this.lastWrist = null;
    this.lastInferenceTimeMs = 0;
  }

  public update(nowMs: number, engaged: boolean, control: 'filter' | 'reverb' | null, value: number | null, gestureArmed = false): void {
    if (!this.isRunning || !this.videoEl || !this.landmarker || this.videoEl.readyState < 2) {
      return;
    }

    // Target ~30 FPS inference and skip if currently processing
    if (this.isProcessing || nowMs - this.lastInferenceTimeMs < 30) {
      return;
    }

    this.isProcessing = true;
    this.lastInferenceTimeMs = nowMs;

    try {
      const result = this.landmarker.detectForVideo(this.videoEl, nowMs);
      if (performance.now() - nowMs > 250) this.onMissedFrame(nowMs);
      else this.processResult(result, nowMs, engaged, control, value, gestureArmed);
    } catch (e) {
      console.warn('Inference error:', e);
      this.onMissedFrame(nowMs);
    } finally {
      this.isProcessing = false;
    }
  }

  private processResult(
    result: any,
    nowMs: number,
    engaged: boolean,
    control: 'filter' | 'reverb' | null,
    value: number | null,
    gestureArmed = false
  ): void {
    const rawHands = result.landmarks;
    const scores = result.handedness;

    if (!rawHands || rawHands.length === 0) {
      this.onMissedFrame(nowMs);
      return;
    }

    // Every visible hand, all 21 points, for the coach's technique analysis (fingers + picking hand).
    if (this.onAllHands) {
      const all: TrackedHand[] = [];
      for (let i = 0; i < rawHands.length; i++) {
        const pts = rawHands[i];
        const label = scores?.[i]?.[0];
        if (!Array.isArray(pts) || pts.length !== 21 || !label) continue;
        if (pts.some((p: any) => !Number.isFinite(p.x) || !Number.isFinite(p.y))) continue;
        const handedness = label.categoryName === 'Left' ? 'Left' : label.categoryName === 'Right' ? 'Right' : null;
        if (!handedness || !Number.isFinite(label.score)) continue;
        all.push({ handedness, confidence: label.score, landmarks: pts.map((p: any) => [p.x, p.y] as [number, number]) });
      }
      if (all.length) this.onAllHands(all);
    }

    // 1. Right-hand filtering: ignore left hand (holding guitar neck) and focus exclusively on right hand.
    const rightCandidates: number[] = [];
    for (let i = 0; i < rawHands.length; i++) {
      const label = scores?.[i]?.[0];
      const cat = (label?.categoryName || label?.displayName || '').toLowerCase();
      if (cat === 'right' && Number.isFinite(label?.score) && label.score >= 0.6 && label.score <= 1) {
        rightCandidates.push(i);
      }
    }

    const candidateIndices = rightCandidates;
    if (candidateIndices.length === 0) {
      // Only left hand present in frame, or no valid hands: fail closed and ignore
      this.onMissedFrame(nowMs);
      return;
    }

    // Pick closest hand if multiple candidates are visible
    let bestHandIdx = candidateIndices[0];
    if (candidateIndices.length > 1) {
      if (this.lastWrist !== null) {
        let minDist = Infinity;
        for (const idx of candidateIndices) {
          const w = rawHands[idx][0];
          const dist = Math.hypot(w.x - this.lastWrist[0], w.y - this.lastWrist[1]);
          if (dist < minDist) {
            minDist = dist;
            bestHandIdx = idx;
          }
        }
      } else {
        let maxScore = -Infinity;
        for (const idx of candidateIndices) {
          const s = scores?.[idx]?.[0]?.score || 0;
          if (s > maxScore) {
            maxScore = s;
            bestHandIdx = idx;
          }
        }
      }
    }

    const hand = rawHands[bestHandIdx];
    if (!Array.isArray(hand) || hand.length !== 21 || hand.some((p: any) =>
      !Number.isFinite(p.x) || !Number.isFinite(p.y) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1)) {
      this.onMissedFrame(nowMs);
      return;
    }
    const wrist = hand[0];
    const wristCoord: [number, number] = [wrist.x, wrist.y];

    // Check maximum wrist jump
    if (this.lastWrist !== null) {
      const jump = Math.hypot(wristCoord[0] - this.lastWrist[0], wristCoord[1] - this.lastWrist[1]);
      if (jump > this.maxWristJump) {
        // Unsafe jump: fail-closed and reset tracking
        this.onMissedFrame(nowMs);
        return;
      }
    }

    this.lastWrist = wristCoord;
    this.consecutiveMisses = 0;

    // Convert to normalized 21 points
    const landmarks: Array<[number, number]> = hand.map((lm: any) => [lm.x, lm.y]);

    // Compute pixel distances
    const d = (a: number, b: number) =>
      Math.hypot((landmarks[a][0] - landmarks[b][0]) * (this.videoEl?.videoWidth || 640),
        (landmarks[a][1] - landmarks[b][1]) * (this.videoEl?.videoHeight || 480));
    const palmWidth = d(5, 17);
    if (palmWidth <= 1) { this.onMissedFrame(nowMs); return; }

    // Index-to-thumb pinch ratio: controls the active slider up and down!
    const pinch = d(4, 8) / palmWidth;

    // Fist curl ratio: average distance of non-thumb fingertips to MCPs and palm center
    const fingerCurl = (d(8, 5) + d(12, 9) + d(16, 13) + d(20, 17)) / (4 * palmWidth);
    const centerCurl = (d(8, 9) + d(12, 9) + d(16, 9) + d(20, 9)) / (4 * palmWidth);
    const curl = (fingerCurl + centerCurl) / 2;

    // 2D Palm Normal / Orientation:
    // Landmark 0: Wrist
    // Landmark 9: Middle MCP (palm axis)
    // Landmark 5: Index MCP
    // Landmark 17: Pinky MCP
    // Vector P = (9 - 0): points along hand from wrist to knuckles
    // Vector K = (17 - 5): knuckle line from index towards pinky
    const px = landmarks[9][0] - landmarks[0][0];
    const py = landmarks[9][1] - landmarks[0][1];
    const kx = landmarks[17][0] - landmarks[5][0];
    const ky = landmarks[17][1] - landmarks[5][1];
    const pDist = Math.hypot(px, py);
    const kDist = Math.hypot(kx, ky);

    // Detection consumes the unmirrored camera video; mirroring is display-only.
    // A right palm facing this camera has index MCP to viewer-right of pinky MCP,
    // so P x K is negative. The old positive-only gate rejected that palm.
    const crossProduct = px * ky - py * kx;
    const sinPhi = (pDist > 1e-4 && kDist > 1e-4) ? crossProduct / (pDist * kDist) : 0;
    const isPalmFacing = sinPhi < -0.08;

    // Background-tab/inference gaps do not count toward a confirmed pose.
    if (nowMs - this.lastStrumTimeMs >= 250) {
      this.lastStrumY = null;
      this.strumAnchorY = null;
      this.lastVelocitySign = 0;
      this.reversalTimes = [];
      this.fistSinceMs = null;
    }

    // Strumming motion detection (rapid velocity reversals across strings)
    let isStrumMotion = false;
    if (this.strumAnchorY === null) this.strumAnchorY = landmarks[9][1];
    if (this.lastStrumY !== null && nowMs > this.lastStrumTimeMs) {
      const dt = (nowMs - this.lastStrumTimeMs) / 1000;
      if (dt > 0 && dt < 0.25) {
        const velY = (landmarks[9][1] - this.lastStrumY) / dt;
        if (Math.abs(velY) > 0.35) {
          const sign = velY > 0 ? 1 : -1;
          if (this.lastVelocitySign !== 0 && sign !== this.lastVelocitySign) {
            // Velocity alone counts tiny landmark jitter as strumming. Require
            // an actual stroke before counting a reversal.
            if (Math.abs(this.lastStrumY - this.strumAnchorY) >= 0.035) {
              this.reversalTimes.push(nowMs);
              this.strumAnchorY = this.lastStrumY;
            }
          }
          this.lastVelocitySign = sign;
        }
      }
    }
    this.lastStrumY = landmarks[9][1];
    this.lastStrumTimeMs = nowMs;

    this.reversalTimes = this.reversalTimes.filter((t) => nowMs - t <= 350);
    if (this.reversalTimes.length >= 2) {
      isStrumMotion = true;
    }

    // A pick-shaped hand entering the guitar zone stays suppressed. An explicit
    // open-hand arm / active clutch may traverse the full slider range; position
    // alone must not disarm it. Back-facing hands and real strumming still win.
    const isStrumZone = landmarks[9][1] >= 0.52;
    const closedFist = curl <= 0.55;
    const deliberateGesture = gestureArmed || engaged || this.fistLatched || (closedFist && this.fistSinceMs !== null);
    const isStrumming = !isPalmFacing || isStrumMotion || (isStrumZone && pinch < 0.35 && !deliberateGesture);
    const isFist = !isStrumming && closedFist;

    // Brief pose confirmation rejects transient curls. A held fist is consumed
    // once; suppression/occlusion cannot unlatch it without an actual open hand.
    if (curl >= 0.68) this.fistLatched = false;
    if (!isFist) this.fistSinceMs = null;
    else if (this.fistSinceMs === null) this.fistSinceMs = nowMs;
    let swapTriggered = false;
    if (isFist && !this.fistLatched && this.fistSinceMs !== null &&
        nowMs - this.fistSinceMs >= 140 && nowMs - this.lastSwapTimeMs >= 1400) {
      this.fistLatched = true;
      this.lastSwapTimeMs = nowMs;
      swapTriggered = true;
      this.onFistSwap?.();
    }
    // Confidence was validated before selection and before any gesture callback.
    const conf = scores[bestHandIdx][0].score;

    const yCoord = landmarks[9][1];

    if (isStrumming || isFist) {
      // Fists never drag a slider while swapping. Guitar playing / strumming: suppress gesture observation so controller disengages and locks DSP parameters
      this.latestObservation = {
        present: false,
        y: null,
        pinch: null,
        confidence: 0.0,
        timestamp_ms: Math.floor(nowMs),
      };
    } else {
      this.latestObservation = {
        present: true,
        y: yCoord,
        pinch,
        confidence: conf,
        timestamp_ms: Math.floor(nowMs),
      };
    }

    this.latestHandFrame = {
      version: 1,
      type: 'hand',
      timestamp_ms: Date.now(),
      present: true,
      engaged: !isStrumming && !isFist && engaged,
      confidence: conf,
      control,
      value,
      landmarks,
      isFist,
      swapTriggered,
      isStrumming,
      isPalmFacing,
    } as any;
  }

  private onMissedFrame(nowMs: number): void {
    this.consecutiveMisses++;
    if (this.consecutiveMisses >= this.maxMissedFrames) {
      this.lastWrist = null;
    }
    this.lastStrumY = null;
    this.strumAnchorY = null;
    this.fistSinceMs = null;
    this.lastVelocitySign = 0;
    this.reversalTimes = [];

    this.latestObservation = {
      present: false,
      y: null,
      pinch: null,
      confidence: 0.0,
      timestamp_ms: Math.floor(nowMs),
    };

    this.latestHandFrame = {
      version: 1,
      type: 'hand',
      timestamp_ms: Date.now(),
      present: false,
      engaged: false,
      confidence: 0.0,
      control: null,
      value: null,
      landmarks: [],
    };
  }

  public getObservation(): GestureObservation {
    return this.latestObservation;
  }

  public getHandFrame(): HandFrame {
    return this.latestHandFrame;
  }

  private resetObservation(): void {
    this.fistLatched = false;
    this.lastSwapTimeMs = -Infinity;
    this.lastStrumY = null;
    this.strumAnchorY = null;
    this.fistSinceMs = null;
    this.lastStrumTimeMs = 0;
    this.lastVelocitySign = 0;
    this.reversalTimes = [];
    this.latestObservation = { present: false, y: null, pinch: null, confidence: 0, timestamp_ms: 0 };
    this.latestHandFrame = absentHand();
  }

  public stop(): void {
    ++this.generation;
    this.cancelMetadata?.();
    this.cancelMetadata = null;
    this.isRunning = false;
    this.resetObservation();
    this.isProcessing = false;
    this.lastStrumY = null;
    this.strumAnchorY = null;
    this.fistSinceMs = null;
    this.lastStrumTimeMs = 0;
    this.lastVelocitySign = 0;
    this.reversalTimes = [];
    if (typeof document !== 'undefined' && typeof document.getElementById === 'function') {
      const card = document.getElementById('card-camera');
      const tag = document.getElementById('camTag');
      if (card) card.dataset.cam = 'off';
      if (tag) { tag.textContent = 'OFF'; tag.classList.remove('live'); }
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.pause();
      this.videoEl.srcObject = null;
      if (this.videoEl.id !== 'cameraVideo') {
        this.videoEl = null;
      }
    }
    this.lastWrist = null;
    this.consecutiveMisses = 0;
  }
}
