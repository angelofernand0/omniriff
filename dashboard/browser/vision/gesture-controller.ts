/**
 * Deterministic gesture mapping in TypeScript.
 * Direct mathematical and logical parity with vision/control.py.
 */

import type { ParameterControlEnvelope } from '../protocol/types';

export interface ControllerOptions {
  low?: number;
  high?: number;
  rate?: number;
  confidence?: number;
  deadband?: number;
  tau?: number;
  control?: 'filter' | 'reverb';
  relative?: boolean;
}

export class GestureController {
  public low: number;
  public high: number;
  public rate: number;
  public minConfidence: number;
  public deadband: number;
  public tau: number;
  public control: 'filter' | 'reverb';
  public relative: boolean;

  public active: boolean = false;
  public armed: boolean = false;
  public value: number | null = null;
  public previous: number | null = null;
  public sentAt: number = -Infinity;
  public sentValue: number | null = null;
  public seq: number = 0;
  public pickupY: number | null = null;
  public pickupValue: number | null = null;

  constructor(opts: ControllerOptions = {}) {
    this.low = opts.low ?? 0.8;
    this.high = opts.high ?? 0.2;
    this.rate = opts.rate ?? 20.0;
    this.minConfidence = opts.confidence ?? 0.6;
    this.deadband = opts.deadband ?? 0.015;
    this.tau = opts.tau ?? 0.12;
    this.control = opts.control ?? 'filter';
    this.relative = opts.relative ?? false;

    if (
      !Number.isFinite(this.low) ||
      !Number.isFinite(this.high) ||
      !Number.isFinite(this.rate) ||
      !Number.isFinite(this.minConfidence) ||
      !Number.isFinite(this.deadband) ||
      !Number.isFinite(this.tau)
    ) {
      throw new Error('Controller configuration must be finite');
    }
    if (!(0 <= this.high && this.high < this.low && this.low <= 1) || this.low - this.high < 0.05) {
      throw new Error('Calibration needs separated high and low positions in [0,1]');
    }
    if (this.rate <= 0 || this.rate > 60 || this.minConfidence < 0 || this.minConfidence > 1 || this.deadband < 0 || this.deadband >= 1 || this.tau <= 0) {
      throw new Error('Invalid rate, confidence, deadband or smoothing');
    }
    if (this.control !== 'filter' && this.control !== 'reverb') {
      throw new Error('Unsupported control');
    }
  }

  public rearm(): void {
    this.active = false;
    this.armed = false;
    this.value = null;
    this.previous = null;
    this.sentValue = null;
    this.pickupY = null;
    this.pickupValue = null;
  }

  public update(
    y: number | null,
    pinch: number | null,
    confidence: number | null,
    now: number,
    timestampMs: number
  ): ParameterControlEnvelope | null {
    if (
      y === null ||
      pinch === null ||
      confidence === null ||
      !Number.isFinite(y) ||
      !Number.isFinite(pinch) ||
      !Number.isFinite(confidence) ||
      !Number.isFinite(now) ||
      confidence < 0 ||
      confidence > 1 ||
      confidence < this.minConfidence
    ) {
      this.active = false;
      this.armed = false;
      this.previous = null;
      this.value = null;
      return null;
    }

    if (this.previous !== null && now <= this.previous) {
      return null;
    }

    if (pinch >= 0.45) {
      this.active = false;
      this.armed = true;
      if (!this.relative) {
        this.value = null;
      }
    } else if (this.armed && !this.active && pinch <= 0.25) {
      this.active = true;
      if (this.relative) {
        this.pickupY = y;
        this.pickupValue = this.sentValue;
        if (this.pickupValue === null) {
          this.pickupValue = this.control === 'filter' ? 1.0 : 0.0;
        }
        this.value = this.pickupValue;
      }
    }

    const dt = this.previous === null ? 0 : now - this.previous;
    this.previous = now;

    if (!this.active) {
      return null;
    }

    let target: number;
    if (this.relative && this.pickupValue !== null && this.pickupY !== null) {
      target = this.pickupValue + (this.pickupY - y) / (this.low - this.high);
    } else {
      target = (this.low - y) / (this.low - this.high);
    }

    target = Math.min(1.0, Math.max(0.0, target));

    this.value =
      this.value === null
        ? target
        : this.value + (1.0 - Math.exp(-dt / this.tau)) * (target - this.value);

    if (
      now - this.sentAt < 1.0 / this.rate ||
      (this.sentValue !== null && Math.abs(this.value - this.sentValue) < this.deadband)
    ) {
      return null;
    }

    const event: ParameterControlEnvelope = {
      version: 1,
      source: 'vision',
      seq: this.seq++,
      timestamp_ms: timestampMs,
      type: 'parameter',
      control: this.control,
      value: this.value,
      confidence,
    };

    this.sentAt = now;
    this.sentValue = this.value;
    return event;
  }
}
