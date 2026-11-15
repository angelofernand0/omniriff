/**
 * Continuous scene morphing in TypeScript.
 * Parity with vision/scenes.py.
 */

import type { ParameterControlEnvelope } from '../protocol/types';

export interface SceneEndpoints {
  filter: number;
  reverb: number;
}

export interface SceneConfig {
  name: string;
  from: SceneEndpoints;
  to: SceneEndpoints;
}

export const DEFAULT_SCENES: SceneConfig[] = [
  {
    name: 'Clear to Cosmos',
    from: { filter: 1.0, reverb: 0.0 },
    to: { filter: 0.4, reverb: 0.75 },
  },
  {
    name: 'Underwater to Spotlight',
    from: { filter: 0.12, reverb: 0.55 },
    to: { filter: 1.0, reverb: 0.08 },
  },
  {
    name: 'Dark Room',
    from: { filter: 1.0, reverb: 0.0 },
    to: { filter: 0.2, reverb: 0.35 },
  },
];

export class SceneMorph {
  public readonly name: string;
  public readonly start: SceneEndpoints;
  public readonly end: SceneEndpoints;
  public seq: number = 0;

  constructor(scene: SceneConfig) {
    if (!scene || typeof scene.name !== 'string' || !scene.name.trim()) {
      throw new Error('Scene name must be nonempty');
    }
    for (const end of ['from', 'to'] as const) {
      const vals = scene[end];
      if (!vals || typeof vals.filter !== 'number' || typeof vals.reverb !== 'number') {
        throw new Error('Scene endpoints require filter and reverb numbers');
      }
      if (
        !Number.isFinite(vals.filter) ||
        !Number.isFinite(vals.reverb) ||
        vals.filter < 0 ||
        vals.filter > 1 ||
        vals.reverb < 0 ||
        vals.reverb > 1
      ) {
        throw new Error('Scene values must be finite numbers in [0,1]');
      }
    }

    this.name = scene.name;
    this.start = { ...scene.from };
    this.end = { ...scene.to };
  }

  public values(amount: number): SceneEndpoints {
    if (!Number.isFinite(amount) || amount < 0 || amount > 1) {
      throw new Error('Morph amount must be in [0,1]');
    }
    // Smoothstep: gentle start and finish, exact endpoints
    const t = amount * amount * (3 - 2 * amount);
    return {
      filter: this.start.filter + t * (this.end.filter - this.start.filter),
      reverb: this.start.reverb + t * (this.end.reverb - this.start.reverb),
    };
  }

  public events(gesture: ParameterControlEnvelope): ParameterControlEnvelope[] {
    const morphed = this.values(gesture.value);
    const events: ParameterControlEnvelope[] = [];

    for (const control of ['filter', 'reverb'] as const) {
      events.push({
        version: 1,
        source: 'vision',
        seq: this.seq++,
        timestamp_ms: gesture.timestamp_ms,
        type: 'parameter',
        control,
        value: morphed[control],
        confidence: gesture.confidence,
      });
    }

    return events;
  }
}
