/**
 * The mic Riff listens to when you talk. It is separate from the guitar input: the audio
 * interface (Focusrite, channel 2) carries the guitar, so speech goes through the laptop's
 * own mic by default. coach.js asks for one track per talk and hands it to Chrome's speech
 * recognition (SpeechRecognition.start(track)); older browsers ignore the track and use the
 * system default mic.
 */

export const VOICE_MIC_KEY = 'omniriff.voiceMic';
/** '' = automatic (the laptop's built-in mic when there is one). */
export type VoiceMicChoice = string;

export interface MicInfo { deviceId: string; label: string; }

const BUILT_IN = /built-?in|macbook|internal|laptop|integrated/i;
const INTERFACE = /focusrite|scarlett|interface|usb audio|line|instrument|virtual|blackhole|loopback|aggregate/i;

/** The automatic pick: a built-in mic first, then anything that is not an audio interface. */
export function pickVoiceMic(mics: MicInfo[]): string | null {
  const real = mics.filter(m => m.deviceId && m.deviceId !== 'default' && m.deviceId !== 'communications');
  const builtIn = real.find(m => BUILT_IN.test(m.label));
  if (builtIn) return builtIn.deviceId;
  const other = real.find(m => m.label && !INTERFACE.test(m.label));
  return other ? other.deviceId : null;
}

export function savedVoiceMic(): VoiceMicChoice {
  try { return localStorage.getItem(VOICE_MIC_KEY) || ''; } catch { return ''; }
}

export function saveVoiceMic(choice: VoiceMicChoice): void {
  try { localStorage.setItem(VOICE_MIC_KEY, choice); } catch { /* private window: this page only */ }
}

async function listMics(): Promise<MicInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter(d => d.kind === 'audioinput').map(d => ({ deviceId: d.deviceId, label: d.label }));
}

/** The device the next talk will use (null = system default). */
export async function resolveVoiceMic(choice: VoiceMicChoice = savedVoiceMic()): Promise<string | null> {
  const mics = await listMics();
  if (choice && mics.some(m => m.deviceId === choice)) return choice;
  return pickVoiceMic(mics);
}

/**
 * One live mic track for a talk, or null (then speech recognition uses the default mic).
 * The caller stops the track when the talk ends.
 */
export async function voiceTrack(): Promise<MediaStreamTrack | null> {
  if (!navigator.mediaDevices?.getUserMedia) return null;
  const speech = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
  try {
    let deviceId = await resolveVoiceMic();
    if (deviceId === null) {
      // Labels are hidden until mic permission is granted; ask once, then pick again.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: speech });
      deviceId = await resolveVoiceMic();
      if (deviceId === null) return probe.getAudioTracks()[0] ?? null;
      probe.getTracks().forEach(t => t.stop());
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { ...speech, deviceId: { exact: deviceId } } });
    return stream.getAudioTracks()[0] ?? null;
  } catch (err) {
    console.warn('Voice mic unavailable, speech uses the default mic:', err);
    return null;
  }
}

/** Shared with the classic coach.js script. */
export function installVoiceMic(): void {
  const w = window as any;
  w.OmniRiff = w.OmniRiff || {};
  w.OmniRiff.voiceMic = { track: voiceTrack };
}
