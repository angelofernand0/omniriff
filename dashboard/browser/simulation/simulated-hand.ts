/**
 * Simulated 21-landmark hand generation and geometry.
 * Parity with tools/sim/hand.py.
 */

import type { HandFrame } from '../protocol/types';

// Open right hand in hand units: wrist at origin (0, 0), fingers extending toward -y.
// Index order follows MediaPipe Hand Landmarker:
// 0: wrist; 1-4: thumb; 5-8: index; 9-12: middle; 13-16: ring; 17-20: pinky.
const OPEN_HAND_OFFSETS: ReadonlyArray<[number, number]> = [
  [0.0, 0.0],
  [-0.32, -0.12], [-0.52, -0.3], [-0.66, -0.48], [-0.78, -0.62],
  [-0.22, -0.78], [-0.27, -1.1], [-0.3, -1.3], [-0.32, -1.48],
  [-0.02, -0.82], [-0.02, -1.18], [-0.02, -1.4], [-0.02, -1.6],
  [0.17, -0.77], [0.2, -1.08], [0.22, -1.28], [0.24, -1.44],
  [0.33, -0.66], [0.4, -0.9], [0.44, -1.05], [0.47, -1.18],
];

// Closed right fist offsets in hand units: fingers curled tightly into palm.
// MCP knuckles (5, 9, 13, 17) remain visible while tips (8, 12, 16, 20) curl down into palm.
const FIST_OFFSETS: ReadonlyArray<[number, number]> = [
  [0.0, 0.0], // 0: wrist
  [-0.25, -0.15], [-0.35, -0.32], [-0.25, -0.48], [-0.10, -0.56], // 1-4: thumb across folded fingers
  [-0.22, -0.74], [-0.24, -0.90], [-0.18, -0.80], [-0.15, -0.66], // 5-8: index MCP, PIP, DIP, tip curled in
  [-0.02, -0.76], [-0.02, -0.94], [-0.02, -0.82], [-0.02, -0.68], // 9-12: middle MCP, PIP, DIP, tip curled in
  [0.17, -0.72], [0.18, -0.90], [0.15, -0.78], [0.12, -0.64],   // 13-16: ring MCP, PIP, DIP, tip curled in
  [0.33, -0.64], [0.34, -0.80], [0.30, -0.70], [0.26, -0.56],   // 17-20: pinky MCP, PIP, DIP, tip curled in
];

const PINCH_POINT: [number, number] = [-0.45, -0.95];
const SCALE = 0.2;
const ASPECT = 4 / 3;

export function generateHandPoints(
  x: number,
  y: number,
  pinch: number,
  wobble: number = 0.0,
  fist: number = 0.0
): Array<[number, number]> {
  const pts: Array<[number, number]> = [];

  for (let i = 0; i < OPEN_HAND_OFFSETS.length; i++) {
    let [hx, hy] = OPEN_HAND_OFFSETS[i];
    if (i === 3 || i === 4 || i === 7 || i === 8) {
      const k = pinch * (i === 4 || i === 8 ? 1.0 : 0.6);
      hx = hx + (PINCH_POINT[0] - hx) * k;
      hy = hy + (PINCH_POINT[1] - hy) * k;
    }
    if (fist > 0) {
      const [fx, fy] = FIST_OFFSETS[i];
      hx = hx + (fx - hx) * fist;
      hy = hy + (fy - hy) * fist;
    }
    if (i > 0 && fist < 0.9) {
      hy += 0.03 * Math.sin(wobble + i);
    }
    const px = x + (hx * SCALE) / ASPECT;
    const py = y + hy * SCALE;
    pts.push([
      Math.round(Math.min(1.0, Math.max(0.0, px)) * 10000) / 10000,
      Math.round(Math.min(1.0, Math.max(0.0, py)) * 10000) / 10000,
    ]);
  }

  return pts;
}

export function computePinchRatio(
  pts: Array<[number, number]>,
  width: number = 640,
  height: number = 480
): number {
  if (pts.length < 21) return 1.0;
  const dist = (a: number, b: number) =>
    Math.hypot((pts[a][0] - pts[b][0]) * width, (pts[a][1] - pts[b][1]) * height);
  const palmWidth = dist(5, 17);
  if (palmWidth < 1e-4) return 1.0;
  return dist(4, 8) / palmWidth;
}

export interface GestureObservation {
  present: boolean;
  y: number | null;
  pinch: number | null;
  confidence: number;
  timestamp_ms: number;
}

export class SimulatedHandModel {
  public present: boolean = false;
  public engaged: boolean = false;
  public control: 'filter' | 'reverb' | null = 'filter';
  public value: number | null = null;

  public wristX: number = 0.55;
  public wristY: number = 0.70;
  public pinchAmount: number = 0.0; // 0 = open, 1 = pinched
  public fistAmount: number = 0.0; // 0 = open, 1 = closed fist
  public swapTriggered: boolean = false;

  constructor() {}

  public getObservation(timestampMs: number): GestureObservation {
    if (!this.present) {
      return {
        present: false,
        y: null,
        pinch: null,
        confidence: 0.0,
        timestamp_ms: timestampMs,
      };
    }

    const pts = generateHandPoints(this.wristX, this.wristY, this.pinchAmount, (timestampMs / 1000) * 2.0, this.fistAmount);
    // When curling into a fist, disarm pinch engagement so it doesn't accidentally modulate sliders
    const pinch = this.fistAmount > 0.3 ? 0.85 : computePinchRatio(pts);

    return {
      present: true,
      y: this.wristY,
      pinch,
      confidence: 0.95,
      timestamp_ms: timestampMs,
    };
  }

  public getHandFrame(timestampMs: number): HandFrame {
    if (!this.present) {
      return {
        version: 1,
        type: 'hand',
        timestamp_ms: timestampMs,
        present: false,
        engaged: false,
        confidence: 0.0,
        control: this.control,
        value: null,
        landmarks: [],
      };
    }

    const pts = generateHandPoints(this.wristX, this.wristY, this.pinchAmount, (timestampMs / 1000) * 2.0, this.fistAmount);

    return {
      version: 1,
      type: 'hand',
      timestamp_ms: timestampMs,
      present: true,
      engaged: this.engaged,
      confidence: 0.95,
      control: this.control,
      value: this.value,
      landmarks: pts,
    };
  }
}
