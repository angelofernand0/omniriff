import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { PedalTaps, DOUBLE_TAP_MS, type PedalTalk } from '../../dashboard/browser/adapters/pedal-taps';
import { pickVoiceMic } from '../../dashboard/browser/audio/voice-mic';

function fakeTalk(over: Partial<{ can: boolean; listening: boolean }> = {}) {
  const state = { can: true, listening: false, ...over, listens: 0, sends: 0 };
  const talk: PedalTalk = {
    canTalk: () => state.can,
    listening: () => state.listening,
    listen: () => { state.listens++; state.listening = true; },
    sendNow: () => { state.sends++; state.listening = false; },
  };
  return { state, talk };
}

describe('PedalTaps', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('a single tap loops after the double-tap window when Riff can talk', () => {
    const loop = vi.fn();
    const { talk, state } = fakeTalk();
    const taps = new PedalTaps(loop, () => talk);
    taps.tap();
    expect(loop).not.toHaveBeenCalled();
    vi.advanceTimersByTime(DOUBLE_TAP_MS);
    expect(loop).toHaveBeenCalledTimes(1);
    expect(state.listens).toBe(0);
  });

  it('a double tap makes Riff listen and does not loop', () => {
    const loop = vi.fn();
    const { talk, state } = fakeTalk();
    const taps = new PedalTaps(loop, () => talk);
    taps.tap();
    vi.advanceTimersByTime(DOUBLE_TAP_MS - 100);
    taps.tap();
    vi.advanceTimersByTime(DOUBLE_TAP_MS * 2);
    expect(state.listens).toBe(1);
    expect(loop).not.toHaveBeenCalled();
  });

  it('a tap while listening sends instead of looping', () => {
    const loop = vi.fn();
    const { talk, state } = fakeTalk({ listening: true });
    const taps = new PedalTaps(loop, () => talk);
    taps.tap();
    vi.advanceTimersByTime(DOUBLE_TAP_MS * 2);
    expect(state.sends).toBe(1);
    expect(loop).not.toHaveBeenCalled();
  });

  it('loops instantly when talking is not possible (recording, no coach)', () => {
    const loop = vi.fn();
    const { talk } = fakeTalk({ can: false });
    new PedalTaps(loop, () => talk).tap();
    expect(loop).toHaveBeenCalledTimes(1);
    const loop2 = vi.fn();
    new PedalTaps(loop2, () => null).tap();
    expect(loop2).toHaveBeenCalledTimes(1);
  });

  it('two slow taps are two loops', () => {
    const loop = vi.fn();
    const { talk, state } = fakeTalk();
    const taps = new PedalTaps(loop, () => talk);
    taps.tap(); vi.advanceTimersByTime(DOUBLE_TAP_MS + 50);
    taps.tap(); vi.advanceTimersByTime(DOUBLE_TAP_MS + 50);
    expect(loop).toHaveBeenCalledTimes(2);
    expect(state.listens).toBe(0);
  });
});

describe('pickVoiceMic', () => {
  it('prefers the built-in laptop mic over the guitar interface', () => {
    expect(pickVoiceMic([
      { deviceId: 'default', label: 'Default - Focusrite USB Audio' },
      { deviceId: 'fr', label: 'Scarlett Solo USB' },
      { deviceId: 'mb', label: 'MacBook Pro Microphone (Built-in)' },
    ])).toBe('mb');
  });

  it('falls back to a non-interface mic, else null (system default)', () => {
    expect(pickVoiceMic([
      { deviceId: 'fr', label: 'Focusrite USB Audio' },
      { deviceId: 'hs', label: 'AirPods Pro' },
    ])).toBe('hs');
    expect(pickVoiceMic([{ deviceId: 'fr', label: 'Scarlett 2i2 USB' }])).toBeNull();
    expect(pickVoiceMic([{ deviceId: '', label: '' }])).toBeNull();
  });
});
