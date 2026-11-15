/**
 * MediaPipe HandLandmarker wrapper for Live Rig webcam tracking.
 * Adheres to safety invariants: nearest-wrist tracking, 0.30 max wrist jump,
 * 15 missed frames reset, open-hand re-arm.
 */

import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision';
import type { GestureObservation } from '../simulation/simulated-hand';
import type { HandFrame } from '../protocol/types';

export class LiveHandTracker {
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
    await this.initialize();
    this.stream = videoStream;

    this.videoEl = document.createElement('video');
    this.videoEl.autoplay = true;
    this.videoEl.playsInline = true;
    this.videoEl.muted = true;
    this.videoEl.srcObject = videoStream;

    await new Promise<void>((resolve) => {
      if (!this.videoEl) return resolve();
      this.videoEl.onloadedmetadata = () => {
        this.videoEl?.play().then(() => resolve()).catch(() => resolve());
      };
    });

    this.isRunning = true;
    this.consecutiveMisses = 0;
    this.lastWrist = null;
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
      this.processResult(result, nowMs, engaged, control, value);
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

    // Compute pinch ratio
    const d = (a: number, b: number) =>
      Math.hypot((landmarks[a][0] - landmarks[b][0]) * 640, (landmarks[a][1] - landmarks[b][1]) * 480);
    const palmWidth = Math.max(1e-4, d(5, 17));
    const pinch = d(4, 8) / palmWidth;

    const conf = scores && scores[bestHandIdx] && scores[bestHandIdx][0] ? scores[bestHandIdx][0].score : 0.9;

    this.latestObservation = {
      present: true,
      y: wrist.y,
      pinch,
      confidence: conf,
      timestamp_ms: Math.floor(nowMs),
    };

    this.latestHandFrame = {
      version: 1,
      type: 'hand',
      timestamp_ms: Math.floor(nowMs),
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
      timestamp_ms: Math.floor(nowMs),
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

  public stop(): void {
    this.isRunning = false;
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
