"""Single control-side validation gate; never called by the audio callback."""
from __future__ import annotations
import json
import math
import time
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = Draft202012Validator(json.loads((ROOT / 'protocol/control.schema.json').read_text()))
MAX_MESSAGE = 4096


def decode(raw):
    if len(raw) > MAX_MESSAGE:
        raise ValueError('control message exceeds 4096 bytes')
    def bad(value):
        raise ValueError('non-finite JSON number')
    event = json.loads(raw, parse_constant=bad)
    # JSON's numeric exponent syntax can overflow without parse_constant.
    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non-finite number')
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        if isinstance(value, list):
            for v in value: finite(v)
    finite(event)
    return event


class Router:
    def __init__(self, audio, *, clock=None, monotonic=None, stale_ms=250, restart_ms=1000):
        self.audio = audio
        self.clock = clock or (lambda: int(time.time() * 1000))
        self.monotonic = monotonic or (lambda: int(time.monotonic() * 1000))
        self.stale_ms, self.restart_ms = stale_ms, restart_ms
        self.counts = dict.fromkeys(['accepted', 'invalid', 'stale', 'future', 'duplicate', 'low_confidence', 'audio_rejected'], 0)
        self.sources = {}
        self.last = {}

    def reset(self, source):
        self.last.pop(source, None)
        if source in self.sources:
            self.sources[source]['session'] += 1

    def reject(self, reason, source=None):
        self.counts[reason] += 1
        if source in self.sources:
            self.sources[source]['dropped'] += 1
        return False

    def ingest(self, raw, *, expected_source=None):
        try:
            event = decode(raw)
            if not VALIDATOR.is_valid(event):
                return self.reject('invalid')
            if expected_source and event['source'] != expected_source:
                return self.reject('invalid')
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            return self.reject('invalid')
        source = event['source']
        now, tick = self.clock(), self.monotonic()
        health = self.sources.setdefault(source, dict(last_seen_ms=None, last_accepted_ms=None, accepted=0, dropped=0, session=1))
        health['last_seen_ms'] = now
        age = now - event['timestamp_ms']
        if age > self.stale_ms: return self.reject('stale', source)
        if age < -self.stale_ms: return self.reject('future', source)
        previous = self.last.get(source)
        if previous:
            seq, stamp, received = previous
            restarted = event['seq'] == 0 and tick - received >= self.restart_ms and event['timestamp_ms'] > stamp
            if restarted:
                health['session'] += 1
            elif event['seq'] <= seq or event['timestamp_ms'] < stamp:
                return self.reject('duplicate', source)
        # Consume ordering even for low confidence/rejected commands, preventing retries
        # of the same identity from changing its meaning later.
        self.last[source] = (event['seq'], event['timestamp_ms'], tick)
        minimum = getattr(getattr(self.audio, 'config', None), 'min_confidence', 0.6)
        if event['type'] == 'parameter' and event['confidence'] < minimum:
            return self.reject('low_confidence', source)
        if not self.audio.submit(event): return self.reject('audio_rejected', source)
        self.counts['accepted'] += 1
        health['accepted'] += 1
        health['last_accepted_ms'] = now
        return True
