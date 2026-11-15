/**
 * Automated choreography for Browser Simulator mode.
 * Drives the SimulatedHandModel through realistic open/pinch/sweep/re-arm cycles.
 * Allows interactive user override via manual virtual hand controls.
 */

import { SimulatedHandModel } from './simulated-hand';
import type { GestureController } from '../vision/gesture-controller';
import type { Setlist } from '../vision/setlist';

export class SimulatorChoreography {
  public enabled: boolean = true;
  private readonly hand: SimulatedHandModel;
  private readonly controller: GestureController;
  private readonly setlist: Setlist;

  private startTimeMs: number = 0;
  private lastSceneSwitchIndex: number = -1;

  constructor(hand: SimulatedHandModel, controller: GestureController, setlist: Setlist) {
    this.hand = hand;
    this.controller = controller;
    this.setlist = setlist;
  }

  public reset(nowMs: number = performance.now()): void {
    this.startTimeMs = nowMs;
    this.lastSceneSwitchIndex = -1;
  }

  public update(nowMs: number): void {
    if (!this.enabled) return;
    if (this.startTimeMs === 0) this.startTimeMs = nowMs;

    const elapsed = ((nowMs - this.startTimeMs) / 1000) % 18.0; // 18-second looping cycle

    if (elapsed < 1.0) {
      // Step 1: Hand appears open (arming controller)
      this.hand.present = true;
      this.hand.pinchAmount = 0.0; // fully open (pinch ratio >= 0.45)
      this.hand.wristY = 0.70;
      this.hand.wristX = 0.55 + 0.02 * Math.sin(nowMs * 0.002);
    } else if (elapsed < 2.2) {
      // Step 2: Pinch closes (engaging controller)
      const p = Math.min(1.0, (elapsed - 1.0) / 0.8);
      this.hand.present = true;
      this.hand.pinchAmount = p; // 1.0 = pinched (pinch ratio <= 0.25)
      this.hand.wristY = 0.70;
    } else if (elapsed < 6.5) {
      // Step 3: Sweep upward toward high position (modulating filter / scene morph)
      const sweepProgress = (elapsed - 2.2) / 4.3;
      // Smooth sinusoidal sweep from y=0.70 down to y=0.25
      const y = 0.70 - 0.45 * Math.sin(sweepProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
      this.hand.wristX = 0.55 + 0.03 * Math.sin(nowMs * 0.003);
    } else if (elapsed < 8.5) {
      // Step 4: Gentle sweep downward
      const downProgress = (elapsed - 6.5) / 2.0;
      const y = 0.25 + 0.25 * Math.sin(downProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
    } else if (elapsed < 9.5) {
      // Step 5: Release pinch (open hand) -> holds sound
      const relProgress = Math.min(1.0, (elapsed - 8.5) / 0.6);
      this.hand.present = true;
      this.hand.pinchAmount = 1.0 - relProgress;
    } else if (elapsed < 11.0) {
      // Step 6: Scene transition
      if (this.lastSceneSwitchIndex !== 1) {
        this.lastSceneSwitchIndex = 1;
        this.setlist.select(1); // switch to scene 2
        this.controller.rearm(); // scene switch requires open-hand re-arm
      }
      this.hand.present = true;
      this.hand.pinchAmount = 0.0; // open hand for re-arm
      this.hand.wristY = 0.65;
    } else if (elapsed < 12.0) {
      // Step 7: Pinch in new scene
      const p = Math.min(1.0, (elapsed - 11.0) / 0.7);
      this.hand.present = true;
      this.hand.pinchAmount = p;
      this.hand.wristY = 0.65;
    } else if (elapsed < 15.5) {
      // Step 8: Modulate in new scene
      const modProgress = (elapsed - 12.0) / 3.5;
      const y = 0.65 - 0.40 * Math.sin(modProgress * Math.PI);
      this.hand.present = true;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
    } else {
      // Step 9: Hand exits frame
      this.hand.present = false;
      this.hand.pinchAmount = 0.0;
      if (this.lastSceneSwitchIndex !== 0) {
        this.lastSceneSwitchIndex = 0;
        this.setlist.select(0);
        this.controller.rearm();
      }
    }
  }
}
