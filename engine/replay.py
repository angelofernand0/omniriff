"""Explicitly labeled, one-shot control replay. No audio is stored or played here."""
from __future__ import annotations
import asyncio
import logging
import json
from pathlib import Path
import time
from .router import MAX_MESSAGE, VALIDATOR, decode

LOG = logging.getLogger('omniriff.replay')


class Replay:
    def __init__(self, entries):
        self.entries = entries
        self.state = dict(label='REPLAY', active=False, status='stopped', position=0, total=len(entries))

    @classmethod
    def load(cls, path):
        """Validate the entire script before any devices or servers start.

        Input: one existing v1 control envelope per JSONL line, in nondecreasing
        timestamp order. Timestamps establish relative timing, not current age.
        """
        entries = []
        first = previous = None
        sequences = {}
        with Path(path).open('rb') as file:
            number = 0
            while raw := file.readline(MAX_MESSAGE + 2):
                number += 1
                try:
                    if len(raw) > MAX_MESSAGE: raise ValueError('line exceeds 4096 bytes')
                    if not raw.strip(): continue
                    event = decode(raw)
                    if not VALIDATOR.is_valid(event): raise ValueError('not a v1 control envelope')
                    source, seq = event['source'], event['seq']
                    if source in sequences and seq <= sequences[source]:
                        raise ValueError('recorded source sequence repeats or goes backwards; trim resets/retries')
                    sequences[source] = seq
                    stamp = event['timestamp_ms']
                    if previous is not None and stamp < previous: raise ValueError('timestamps go backwards')
                    if first is None: first = stamp
                    offset = stamp - first
                    if offset > 3600000: raise ValueError('script exceeds one hour')
                    if len(entries) >= 10000: raise ValueError('script exceeds 10000 events')
                    entries.append((offset, event))
                    previous = stamp
                except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                    raise ValueError(f'replay line {number}: {exc}') from exc
        if not entries: raise ValueError('replay script is empty')
        return cls(entries)

    async def run(self, router):
        self.state.update(active=True, status='playing', position=0)
        LOG.warning('REPLAY CONTROL MODE: scripted controls, not live camera/pedal input (%d events)', len(self.entries))
        wall_start, mono_start = router.clock(), time.monotonic()
        try:
            for index, (offset, stored) in enumerate(self.entries):
                await asyncio.sleep(max(0, mono_start + offset / 1000 - time.monotonic()))
                event = dict(stored, source='manual', seq=index, timestamp_ms=wall_start + offset)
                # Keep the scheduled timestamp: a delayed event must go through
                # the usual stale gate rather than arriving as a fresh toggle.
                accepted = router.ingest(json.dumps(event))
                self.state['position'] = index + 1
                if not accepted:
                    self.state.update(active=False, status='error')
                    LOG.error('REPLAY CONTROL MODE stopped at event %d/%d (%s %s): '
                              'control rejected; inspect state.controls drop counters. '
                              'Audio and manual controls remain independent.',
                              index + 1, len(self.entries), event['type'], event['control'])
                    return
            self.state.update(active=False, status='completed')
            LOG.warning('REPLAY CONTROL MODE completed; replay label remains in state')
        except asyncio.CancelledError:
            self.state.update(active=False, status='stopped')
            LOG.warning('REPLAY CONTROL MODE stopped')
            raise
        except Exception:
            self.state.update(active=False, status='error')
            LOG.exception('REPLAY CONTROL MODE failed; audio and manual keyboard remain independent')
