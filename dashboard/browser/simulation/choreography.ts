/**
 * Automated choreography for Browser Simulator mode.
 * Drives the SimulatedHandModel through realistic open/pinch/sweep/fist-swap cycles.
 * Demonstrates both Filter and Reverb modulation with realistic closed-fist effect swaps.
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
  private readonly onSwap?: (target: 'filter' | 'reverb') => void;

  private startTimeMs: number | null = null;
  public currentTarget: 'filter' | 'reverb' = 'filter';
  private lastSwapStep: number = -1;

  constructor(
    hand: SimulatedHandModel,
    controller: GestureController,
    setlist: Setlist,
    onSwap?: (target: 'filter' | 'reverb') => void
  ) {
    this.hand = hand;
    this.controller = controller;
    this.setlist = setlist;
    this.onSwap = onSwap;
  }

  public reset(nowMs?: number): void {
    this.startTimeMs = typeof nowMs === 'number' ? nowMs : null;
    this.currentTarget = 'filter';
    this.lastSwapStep = -1;
    this.hand.fistAmount = 0.0;
    this.hand.pinchAmount = 0.0;
    this.hand.swapTriggered = false;
  }

  public update(nowMs: number): void {
    if (!this.enabled) return;
    if (this.startTimeMs === null) this.startTimeMs = nowMs;

    const elapsed = ((nowMs - this.startTimeMs) / 1000) % 22.0; // 22-second full demonstration cycle
    this.hand.swapTriggered = false;

    if (elapsed < 1.0) {
      // Step 1: Open hand on Filter (arming controller)
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 0.0;
      this.hand.wristY = 0.70;
      this.hand.wristX = 0.55 + 0.02 * Math.sin(nowMs * 0.002);
      if (this.lastSwapStep !== 0) {
        this.lastSwapStep = 0;
        if (this.currentTarget !== 'filter') {
          this.currentTarget = 'filter';
          this.onSwap?.('filter');
        }
      }
    } else if (elapsed < 2.0) {
      // Step 2: Pinch closes on Filter (engaging controller)
      const p = Math.min(1.0, (elapsed - 1.0) / 0.8);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = p;
      this.hand.wristY = 0.70;
    } else if (elapsed < 5.5) {
      // Step 3: Sweep upward toward high position (opening low-pass filter)
      const sweepProgress = (elapsed - 2.0) / 3.5;
      const y = 0.70 - 0.45 * Math.sin(sweepProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
      this.hand.wristX = 0.55 + 0.03 * Math.sin(nowMs * 0.003);
    } else if (elapsed < 7.5) {
      // Step 4: Sweep downward (filter rolls off)
      const downProgress = (elapsed - 5.5) / 2.0;
      const y = 0.25 + 0.35 * Math.sin(downProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
    } else if (elapsed < 8.5) {
      // Step 5: Release pinch (open hand) -> holds filter sound
      const relProgress = Math.min(1.0, (elapsed - 7.5) / 0.6);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0 - relProgress;
      this.hand.wristY = 0.60;
    } else if (elapsed < 9.3) {
      // Step 6: Hand curls into a CLOSED FIST to swap effect!
      const fProgress = Math.min(1.0, (elapsed - 8.5) / 0.7);
      this.hand.present = true;
      this.hand.pinchAmount = 0.0;
      this.hand.fistAmount = fProgress;
      this.hand.wristY = 0.60;
    } else if (elapsed < 10.8) {
      // Step 7: Full closed fist held -> trigger swap to Reverb!
      this.hand.present = true;
      this.hand.pinchAmount = 0.0;
      this.hand.fistAmount = 1.0;
      this.hand.wristY = 0.60;
      if (this.lastSwapStep !== 1) {
        this.lastSwapStep = 1;
        this.currentTarget = 'reverb';
        this.hand.swapTriggered = true;
        this.onSwap?.('reverb');
        this.controller.rearm();
      }
    } else if (elapsed < 11.8) {
      // Step 8: Fist uncurls back to open hand (re-arming controller for Reverb)
      const uncurlProgress = Math.min(1.0, (elapsed - 10.8) / 0.7);
      this.hand.present = true;
      this.hand.fistAmount = 1.0 - uncurlProgress;
      this.hand.pinchAmount = 0.0;
      this.hand.wristY = 0.70;
    } else if (elapsed < 12.8) {
      // Step 9: Pinch closes on Reverb!
      const p = Math.min(1.0, (elapsed - 11.8) / 0.8);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = p;
      this.hand.wristY = 0.70;
    } else if (elapsed < 16.0) {
      // Step 10: Sweep upward modulating Reverb wet mix!
      const sweepProgress = (elapsed - 12.8) / 3.2;
      const y = 0.70 - 0.45 * Math.sin(sweepProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
      this.hand.wristX = 0.55 + 0.03 * Math.sin(nowMs * 0.003);
    } else if (elapsed < 18.0) {
      // Step 11: Sweep downward (reverb mix lowers)
      const downProgress = (elapsed - 16.0) / 2.0;
      const y = 0.25 + 0.35 * Math.sin(downProgress * Math.PI * 0.5);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0;
      this.hand.wristY = y;
    } else if (elapsed < 19.0) {
      // Step 12: Release pinch (open hand) -> holds reverb sound
      const relProgress = Math.min(1.0, (elapsed - 18.0) / 0.6);
      this.hand.present = true;
      this.hand.fistAmount = 0.0;
      this.hand.pinchAmount = 1.0 - relProgress;
      this.hand.wristY = 0.60;
    } else if (elapsed < 19.8) {
      // Step 13: Hand curls into a CLOSED FIST to swap back to Filter!
      const fProgress = Math.min(1.0, (elapsed - 19.0) / 0.7);
      this.hand.present = true;
      this.hand.pinchAmount = 0.0;
      this.hand.fistAmount = fProgress;
      this.hand.wristY = 0.60;
    } else if (elapsed < 21.0) {
      // Step 14: Full closed fist held -> trigger swap back to Filter!
      this.hand.present = true;
      this.hand.pinchAmount = 0.0;
      this.hand.fistAmount = 1.0;
      this.hand.wristY = 0.60;
      if (this.lastSwapStep !== 2) {
        this.lastSwapStep = 2;
        this.currentTarget = 'filter';
        this.hand.swapTriggered = true;
        this.onSwap?.('filter');
        this.controller.rearm();
      }
    } else {
      // Step 15: Fist uncurls back to open hand, ready for next loop cycle
      const uncurlProgress = Math.min(1.0, (elapsed - 21.0) / 0.8);
      this.hand.present = true;
      this.hand.fistAmount = 1.0 - uncurlProgress;
      this.hand.pinchAmount = 0.0;
      this.hand.wristY = 0.70;
    }
  }
}
