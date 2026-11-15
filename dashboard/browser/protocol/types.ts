/**
 * OmniRiff Protocol v1 types.
 * Authoritative schemas: protocol/state.schema.json, protocol/control.schema.json, protocol/hand.schema.json.
 */

export interface LoopState {
  state: 'idle' | 'recording' | 'playing';
  seconds: number;
  max_seconds: number;
}

export interface FilterState {
  target: number;
  value: number;
  cutoff_hz: number;
}

export interface ReverbState {
  target: number;
  value: number;
  dsp: boolean;
}

export interface StateEvents {
  accepted: number;
  rejected: number;
  low_confidence: number;
}

export interface StateControls {
  accepted: number;
  invalid: number;
  stale: number;
  future: number;
  duplicate: number;
  low_confidence: number;
  audio_rejected: number;
}

export interface AdapterStatus {
  status: 'disabled' | 'starting' | 'running' | 'retrying' | 'error' | 'stopped';
  errors: number;
  last_error: string | null;
}

export interface StateSources {
  arduino?: {
    last_seen_ms: number | null;
    last_accepted_ms: number | null;
    accepted: number;
    dropped: number;
    session: number | null;
  };
  vision?: {
    last_seen_ms: number | null;
    last_accepted_ms: number | null;
    accepted: number;
    dropped: number;
    confidence: number | null;
  };
  sensecap?: {
    last_seen_ms: number | null;
    last_accepted_ms: number | null;
    accepted: number;
    dropped: number;
  };
}

export interface StateFrame {
  version: 1;
  timestamp_ms: number;
  samplerate: number;
  bypass: boolean;
  loop: LoopState;
  filter: FilterState;
  reverb: ReverbState;
  input_peak_dbfs: number;
  output_peak_dbfs: number;
  xruns: number;
  clipped_samples: number;
  blocks: number;
  events: StateEvents;
  controls: StateControls;
  sources: StateSources;
  adapters: {
    udp: AdapterStatus;
    serial: AdapterStatus;
    websocket: AdapterStatus;
  };
  replay?: {
    label: 'REPLAY';
    active: boolean;
    status: 'playing' | 'completed' | 'error' | 'stopped';
    position: number;
    total: number;
  };
  live?: {
    strums_last_s: number;
    last_strum_ms: number | null;
    steady: boolean | null;
  };
  pedal?: {
    practice_count: number;
    last_practice_ms: number;
  };
}

export interface HandFrame {
  version: 1;
  type: 'hand';
  timestamp_ms: number;
  present: boolean;
  engaged: boolean;
  confidence: number;
  control: 'filter' | 'reverb' | null;
  value: number | null;
  landmarks: Array<[number, number]>;
}

export type ControlSource = 'arduino' | 'vision' | 'sensecap' | 'dashboard' | 'manual' | 'coach';

export interface ParameterControlEnvelope {
  version: 1;
  source: ControlSource;
  seq: number;
  timestamp_ms: number;
  type: 'parameter';
  control: 'filter' | 'reverb';
  value: number;
  confidence: number;
}

export interface ActionControlEnvelope {
  version: 1;
  source: ControlSource;
  seq: number;
  timestamp_ms: number;
  type: 'action';
  control: 'loop' | 'bypass';
}

export interface PracticeControlEnvelope {
  version: 1;
  source: 'arduino' | 'dashboard' | 'manual';
  seq: number;
  timestamp_ms: number;
  type: 'action';
  control: 'practice';
}

export type ControlEnvelope = ParameterControlEnvelope | ActionControlEnvelope | PracticeControlEnvelope;
