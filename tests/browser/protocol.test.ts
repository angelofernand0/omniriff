import { describe, expect, it } from 'vitest';
import Ajv2020 from 'ajv/dist/2020.js';
import stateSchema from '../../protocol/state.schema.json';
import handSchema from '../../protocol/hand.schema.json';
import { BrowserSimulatorAdapter } from '../../dashboard/browser/adapters/browser-simulator';
import { BrowserLiveAdapter } from '../../dashboard/browser/adapters/browser-live';

// The Python/firmware contracts remain authoritative. Check actual browser
// producers against those schemas, rather than a second hand-written type list.
const ajv = new Ajv2020({ strict: false, allErrors: true });
const state = ajv.compile(stateSchema);
const hand = ajv.compile(handSchema);

describe('browser producers share protocol v1', () => {
  it('emits valid simulator and live state without starting media', () => {
    const now = Date.now();
    for (const frame of [new BrowserSimulatorAdapter().buildStateFrame(now), new BrowserLiveAdapter().buildStateFrame(now, 0)]) {
      expect(state(frame), JSON.stringify(state.errors)).toBe(true);
      expect(frame.timestamp_ms).toBe(now);
    }
  });

  it('emits valid generated hands both present and absent', () => {
    const simulator = new BrowserSimulatorAdapter();
    for (const present of [false, true]) {
      simulator.hand.present = present;
      const frame = simulator.hand.getHandFrame(Date.now());
      expect(hand(frame), JSON.stringify(hand.errors)).toBe(true);
      expect(frame.landmarks).toHaveLength(present ? 21 : 0);
    }
  });
});
