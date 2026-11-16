import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { afterEach, describe, expect, it, vi } from 'vitest';

const source = readFileSync(new URL('../../dashboard/coach.js', import.meta.url), 'utf8');
const localVoice = { name: 'Installed voice', lang: 'en-US', default: true, localService: true };
const remoteVoice = { name: 'Hosted voice', lang: 'en-US', default: true, localService: false };

function dashboard(voices: any[] = [remoteVoice, localVoice], speechAvailable = true) {
  const events = new Map<string, Array<(event: any) => void>>();
  const line = { dataset: {}, textContent: '' };
  const set = vi.fn();
  const node = () => ({ dataset: {}, style: {}, setAttribute: vi.fn(), appendChild: vi.fn() });
  const socket: any = { readyState: 1, send: vi.fn() };
  const synth: any = {
    speaking: false, getVoices: vi.fn(() => voices),
    speak: vi.fn((utterance: any) => { synth.speaking = true; utterance.onstart?.(); }),
    cancel: vi.fn(() => { synth.speaking = false; }),
  };
  const audio = vi.fn(function () { throw new Error('Unexpected prerecorded audio playback'); });
  const window: any = {
    OmniRiff: { coach: { set } }, OmniCoachSocket: () => socket,
    addEventListener: (name: string, cb: (event: any) => void) => events.set(name, [...(events.get(name) || []), cb]),
    dispatchEvent: vi.fn(),
  };
  if (speechAvailable) {
    window.speechSynthesis = synth;
    window.SpeechSynthesisUtterance = class { text: string; constructor(text: string) { this.text = text; } };
  }
  runInNewContext(source, {
    window, document: {
      getElementById: (id: string) => id === 'coachLine' ? line : null,
      querySelector: () => null, createElement: node, body: node(),
    },
    location: { search: '' }, localStorage: { getItem: () => null, setItem: vi.fn() },
    URLSearchParams, URL, Audio: audio, Uint8Array, SpeechSynthesisUtterance: window.SpeechSynthesisUtterance,
    speechSynthesis: synth, CustomEvent: class { constructor(_type: string, _options: any) {} },
    setTimeout, clearTimeout, setInterval, clearInterval, performance,
    requestAnimationFrame: vi.fn(() => 1), cancelAnimationFrame: vi.fn(),
  });
  const deliver = (message: any) => socket.onmessage({ data: JSON.stringify(message) });
  const cue = (text: string, extra: any = {}) => deliver({
    version: 1, type: 'coach.frame', state: 'speaking', cue: text,
    session_id: 'live-session', scripted: false, ...extra,
  });
  socket.onopen();
  cue('Already in progress'); // joining an existing session stays quiet
  return { window, socket, synth, audio, line, set, deliver, cue,
    key: (key: string) => { for (const cb of events.get('keydown') || []) cb({ key, preventDefault: vi.fn() }); } };
}

describe('Riff local browser voice', () => {
  afterEach(() => { vi.useRealTimers(); });

  it('selects an installed voice for live cues and ignores arriving server audio', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.cue('Try the chord change slowly.');
    ui.deliver({ version: 1, type: 'coach.audio', text: 'Try the chord change slowly.', audio_b64: 'not-used', mime: 'audio/mpeg' });
    vi.advanceTimersByTime(151);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    expect(ui.synth.speak.mock.calls[0][0].voice).toBe(localVoice);
    expect(ui.synth.speak.mock.calls[0][0].text).toBe('Try the chord change slowly.');
    expect(ui.audio).not.toHaveBeenCalled();
    expect(ui.set).toHaveBeenLastCalledWith(expect.objectContaining({ cue: 'Try the chord change slowly.' }));
  });

  it('uses the same local speech path for the scripted demo', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.cue('Keep your wrist relaxed.', { session_id: 'demo-example' });
    vi.advanceTimersByTime(151);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    expect(ui.synth.speak.mock.calls[0][0].voice.localService).toBe(true);
    expect(ui.audio).not.toHaveBeenCalled();
  });

  it.each([false, true])('keeps cues readable without local speech (speech available: %s)', available => {
    vi.useFakeTimers();
    const ui = dashboard([remoteVoice], available);
    ui.cue('One clear note at a time.');
    vi.advanceTimersByTime(151);
    expect(ui.synth.speak).not.toHaveBeenCalled();
    expect(ui.line.textContent).toBe('One clear note at a time.');
    expect(ui.window.OmniRiff.coachFeed.speaking()).toBe(false);
  });

  it('cancels and clears queued speech on mute, even if a stale end event arrives', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.cue('First cue.'); vi.advanceTimersByTime(151);
    const first = ui.synth.speak.mock.calls[0][0];
    ui.cue('Queued cue.'); vi.advanceTimersByTime(151);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    ui.key('m');
    first.onend();
    vi.advanceTimersByTime(1000);
    expect(ui.synth.cancel).toHaveBeenCalledOnce();
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    expect(ui.window.OmniRiff.coachFeed.speaking()).toBe(false);
    ui.cue('Muted cue.'); vi.advanceTimersByTime(1000);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
  });

  it('stays silent during the autoplay showcase and stops any previous cue', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.cue('Current live cue.'); vi.advanceTimersByTime(151);
    ui.cue('Illustrative showcase cue.', { session_id: 'showcase-example', scripted: true });
    vi.advanceTimersByTime(1000);
    expect(ui.synth.cancel).toHaveBeenCalledOnce();
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    expect(ui.line.textContent).toBe('Illustrative showcase cue.');
  });

  it('does not restart a deferred cue after mute and unmute', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.cue('First cue.'); vi.advanceTimersByTime(151);
    const first = ui.synth.speak.mock.calls[0][0];
    ui.cue('Second cue.'); vi.advanceTimersByTime(151);
    ui.synth.speaking = false;
    first.onend(); // the second cue is scheduled after a brief pause
    ui.key('m'); ui.key('m');
    vi.advanceTimersByTime(1000);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
  });

  it('falls back to text on speech API failures and cancels speech on disconnect', () => {
    vi.useFakeTimers();
    const ui = dashboard();
    ui.synth.getVoices.mockImplementationOnce(() => { throw new Error('API restricted'); });
    ui.cue('Readable without speech.'); vi.advanceTimersByTime(151);
    expect(ui.line.textContent).toBe('Readable without speech.');
    expect(ui.synth.speak).not.toHaveBeenCalled();
    ui.cue('A later cue.'); vi.advanceTimersByTime(151);
    expect(ui.synth.speak).toHaveBeenCalledOnce();
    ui.socket.onclose();
    expect(ui.synth.cancel).toHaveBeenCalledOnce();
    expect(ui.window.OmniRiff.coachFeed.speaking()).toBe(false);
  });
});
