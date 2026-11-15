/**
 * MediaPipe HandLandmarker wrapper for Live Rig webcam tracking.
 * Adheres to safety invariants: nearest-wrist tracking, 0.30 max wrist jump,
 * 15 missed frames reset, open-hand re-arm.
 */

import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';
import type { GestureObservation } from '../simulation/simulated-hand';
import type { HandFrame } from '../protocol/types';
import { absentHand } from '../adapters/connection';

export class LiveHandTracker {
  private generation = 0;
  private cancelMetadata: (() => void) | null = null;
  private landmarker: HandLandmarker | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private stream: MediaStream | null = null;

  public isRunning: boolean = false;
  private isProcessing: boolean = false;
  private lastInferenceTimeMs: number = 0;

  // Safety tracking state
  private lastWrist: [number, number] | null = null;
  private consecutiveMisses: number = 0;
  private readonly maxWristJump: number = 0.30;
  private readonly maxMissedFrames: number = 15;

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
    const video = document.createElement('video');
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
    this.consecutiveMisses = 0;
    this.lastWrist = null;
    this.lastInferenceTimeMs = 0;
  }

  public update(nowMs: number, engaged: boolean, control: 'filter' | 'reverb' | null, value: number | null): void {
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
      else this.processResult(result, nowMs, engaged, control, value);
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
    value: number | null
  ): void {
    const rawHands = result.landmarks;
    const scores = result.handedness;

    if (!rawHands || rawHands.length === 0) {
      this.onMissedFrame(nowMs);
      return;
    }

    // Pick closest hand if multiple hands are visible
    let bestHandIdx = 0;
    if (rawHands.length > 1 && this.lastWrist !== null) {
      let minDist = Infinity;
      for (let i = 0; i < rawHands.length; i++) {
        const w = rawHands[i][0];
        const dist = Math.hypot(w.x - this.lastWrist[0], w.y - this.lastWrist[1]);
        if (dist < minDist) {
          minDist = dist;
          bestHandIdx = i;
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

    // Closed fist swaps between Filter and Reverb with 2-second anti-flicker cooldown and latching
    const isFist = curl <= 0.60;
    const isOpenHand = curl >= 0.78;

    if (nowMs - this.lastSwapTimeMs >= 2000 && isOpenHand) {
      this.fistLatched = false;
    }

    if (isFist && !this.fistLatched && (nowMs - this.lastSwapTimeMs >= 2000)) {
      this.fistLatched = true;
      this.lastSwapTimeMs = nowMs;
      this.onFistSwap?.();
    }

    const conf = scores && scores[bestHandIdx] && scores[bestHandIdx][0] ? scores[bestHandIdx][0].score : 0;
    if (!Number.isFinite(conf) || conf < 0 || conf > 1) { this.onMissedFrame(nowMs); return; }

    // Use palm joint (middle MCP landmark 9) for vertical drag coordinate
    // Landmark 9 stays in frame even when hand is lowered near camera bottom edge
    const yCoord = landmarks[9][1];

    this.latestObservation = {
      present: true,
      y: yCoord,
      pinch,
      confidence: conf,
      timestamp_ms: Math.floor(nowMs),
    };

    this.latestHandFrame = {
      version: 1,
      type: 'hand',
      timestamp_ms: Date.now(),
      present: true,
      engaged,
      confidence: conf,
      control,
      value,
      landmarks,
    };
  }

  private onMissedFrame(nowMs: number): void {
    this.consecutiveMisses++;
    if (this.consecutiveMisses >= this.maxMissedFrames) {
      this.lastWrist = null;
    }

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
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.pause();
      this.videoEl.srcObject = null;
      this.videoEl = null;
    }
    this.lastWrist = null;
    this.consecutiveMisses = 0;
  }
}
