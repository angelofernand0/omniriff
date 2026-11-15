import type { HandFrame } from '../protocol/types';

export type ConnectionStatus = 'starting' | 'connected' | 'disconnected' | 'error' | 'stopped';
export interface AdapterConnection { status: ConnectionStatus; message?: string }
export type ConnectionCallback = (connection: AdapterConnection) => void;
export const absentHand = (): HandFrame => ({ version: 1, type: 'hand', timestamp_ms: Date.now(),
  present: false, engaged: false, confidence: 0, control: null, value: null, landmarks: [] });

const object = (v: unknown): v is Record<string, any> => v !== null && typeof v === 'object' && !Array.isArray(v);
const integer = (v: unknown): boolean => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const finite = (v: unknown): boolean => typeof v === 'number' && Number.isFinite(v);
const unit = (v: unknown): boolean => finite(v) && (v as number) >= 0 && (v as number) <= 1;

/** Check the consumed state contract before it reaches the renderer; no invented defaults. */
export function isStateFrame(v: unknown): v is import('../protocol/types').StateFrame {
  if (!object(v) || v.version !== 1 || !integer(v.timestamp_ms) || !integer(v.samplerate) || v.samplerate < 1 ||
      typeof v.bypass !== 'boolean' || !['xruns','clipped_samples','blocks'].every(k => integer(v[k])) ||
      !finite(v.input_peak_dbfs) || !finite(v.output_peak_dbfs)) return false;
  if (!object(v.loop) || !['idle','recording','playing'].includes(v.loop.state) || !finite(v.loop.seconds) ||
      v.loop.seconds < 0 || !finite(v.loop.max_seconds) || v.loop.max_seconds <= 0) return false;
  if (!object(v.filter) || !unit(v.filter.target) || !unit(v.filter.value) || !finite(v.filter.cutoff_hz) || v.filter.cutoff_hz < 0 ||
      !object(v.reverb) || !unit(v.reverb.target) || !unit(v.reverb.value) || typeof v.reverb.dsp !== 'boolean') return false;
  if (!object(v.events) || !['accepted','rejected','low_confidence'].every(k => integer(v.events[k])) ||
      !object(v.controls) || !['accepted','invalid','stale','future','duplicate','low_confidence','audio_rejected'].every(k => integer(v.controls[k])) ||
      !object(v.sources) || !object(v.adapters)) return false;
  return ['udp','serial','websocket'].every(k => object(v.adapters[k]) &&
    ['disabled','starting','running','retrying','error','stopped'].includes(v.adapters[k].status) &&
    integer(v.adapters[k].errors) && (v.adapters[k].last_error === null || typeof v.adapters[k].last_error === 'string'));
}

export function isHandFrame(v: unknown): v is HandFrame {
  return object(v) && v.version === 1 && v.type === 'hand' && integer(v.timestamp_ms) &&
    typeof v.present === 'boolean' && typeof v.engaged === 'boolean' && unit(v.confidence) &&
    ['filter','reverb',null].includes(v.control) && (v.value === null || unit(v.value)) &&
    Array.isArray(v.landmarks) && v.landmarks.length === (v.present ? 21 : 0) &&
    v.landmarks.every((p: unknown) => Array.isArray(p) && p.length === 2 && p.every(unit));
}
