import { describe, it, expect, vi } from 'vitest';
import { WebSerialPedalAdapter } from '../../dashboard/browser/adapters/web-serial';

describe('WebSerialPedalAdapter', () => {
  it('parses valid loop action lines and updates telemetry', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedLine('{"seq":0,"type":"action","control":"loop"}');

    expect(actions).toEqual(['loop']);
    expect(adapter.accepted).toBe(1);
    expect(adapter.dropped).toBe(0);
    expect(adapter.session).toBe(0);
    expect(adapter.lastSeenMs).not.toBeNull();
    expect(adapter.lastAcceptedMs).not.toBeNull();
  });

  it('handles bypass and practice actions', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedLine('{"seq":0,"type":"action","control":"bypass"}');
    adapter.feedLine('{"seq":1,"type":"action","control":"practice"}');

    expect(actions).toEqual(['bypass', 'practice']);
    expect(adapter.accepted).toBe(2);
    expect(adapter.practiceCount).toBe(1);
    expect(adapter.lastPracticeMs).not.toBeNull();
    expect(adapter.pedalTelemetry).toEqual({
      practice_count: 1,
      last_practice_ms: adapter.lastPracticeMs,
    });
  });

  it('drops duplicate and out-of-order sequence numbers', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedLine('{"seq":5,"type":"action","control":"loop"}');
    adapter.feedLine('{"seq":5,"type":"action","control":"loop"}'); // duplicate
    adapter.feedLine('{"seq":4,"type":"action","control":"bypass"}'); // older seq

    expect(actions).toEqual(['loop']);
    expect(adapter.accepted).toBe(1);
    expect(adapter.dropped).toBe(2);
  });

  it('detects microcontroller reset and increments session', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedLine('{"seq":10,"type":"action","control":"loop"}');
    expect(adapter.session).toBe(0);

    // Board restarts with seq 0
    adapter.feedLine('{"seq":0,"type":"action","control":"bypass"}');
    expect(actions).toEqual(['loop', 'bypass']);
    expect(adapter.session).toBe(1);
    expect(adapter.accepted).toBe(2);
  });

  it('rejects malformed json, non-actions, and invalid controls', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedLine('not json at all');
    adapter.feedLine('{"seq":0,"type":"status"}');
    adapter.feedLine('{"seq":0,"type":"action","control":"volume"}'); // unknown control
    adapter.feedLine('{"seq":-1,"type":"action","control":"loop"}'); // negative seq

    expect(actions).toHaveLength(0);
    expect(adapter.accepted).toBe(0);
    expect(adapter.dropped).toBe(4);
  });

  it('reassembles NDJSON stream chunks across boundaries', () => {
    const adapter = new WebSerialPedalAdapter();
    const actions: string[] = [];
    adapter.onAction(action => actions.push(action));

    adapter.feedChunk('{"seq":0,"type":"ac');
    expect(actions).toHaveLength(0);

    adapter.feedChunk('tion","control":"loop"}\n{"seq":1,"type":"action","control":"bypass"}\n');
    expect(actions).toEqual(['loop', 'bypass']);
    expect(adapter.accepted).toBe(2);
  });

  it('provides StateSources arduino telemetry matching schema', () => {
    const adapter = new WebSerialPedalAdapter();
    adapter.status = 'running';
    adapter.feedLine('{"seq":0,"type":"action","control":"loop"}');

    const sources = adapter.sourcesArduino;
    expect(sources).toBeDefined();
    expect(sources?.accepted).toBe(1);
    expect(sources?.dropped).toBe(0);
    expect(sources?.session).toBe(0);
    expect(typeof sources?.last_seen_ms).toBe('number');
    expect(typeof sources?.last_accepted_ms).toBe('number');

    const status = adapter.adapterStatus;
    expect(status.status).toBe('running');
    expect(status.errors).toBe(0);
    expect(status.last_error).toBeNull();
  });

  it('connects to serial port, reads chunks, and disconnects cleanly', async () => {
    const adapter = new WebSerialPedalAdapter();
    const mockPort = {
      open: vi.fn(async () => {}),
      close: vi.fn(async () => {}),
      readable: {
        getReader: () => {
          let readCount = 0;
          return {
            read: vi.fn(async () => {
              readCount++;
              if (readCount === 1) {
                return { value: new TextEncoder().encode('{"seq":0,"type":"action","control":"loop"}\n'), done: false };
              }
              return { value: undefined, done: true };
            }),
            releaseLock: vi.fn(),
            cancel: vi.fn(async () => {}),
          };
        },
      },
    };

    await adapter.connect(mockPort);
    expect(mockPort.open).toHaveBeenCalledWith({ baudRate: 115200 });
    expect(adapter.isConnected).toBe(true);

    // Yield to let the async readLoop process the chunk
    await new Promise(resolve => setTimeout(resolve, 20));

    expect(adapter.accepted).toBe(1);

    await adapter.disconnect();
    expect(adapter.isConnected).toBe(false);
    expect(mockPort.close).toHaveBeenCalled();
  });
});
