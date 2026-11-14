"""Build, validate and send v1 control envelopes over UDP (protocol/README.md)."""
from __future__ import annotations

import json
import socket
import time
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = Draft202012Validator(json.loads((ROOT / 'protocol/control.schema.json').read_text()))


def now_ms() -> int:
    return int(time.time() * 1000)


class Sender:
    """One producer per source. seq starts at the wall clock in ms so separate CLI
    runs stay strictly increasing for the engine's duplicate gate."""

    def __init__(self, source: str, host: str = '127.0.0.1', port: int = 47800, clock=now_ms):
        self.source, self.addr, self.clock = source, (host, port), clock
        self.seq = clock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def envelope(self, control: str, value: float | None = None, confidence: float | None = None) -> dict:
        self.seq += 1
        event = dict(version=1, source=self.source, seq=self.seq, timestamp_ms=self.clock(), control=control)
        if control in ('filter', 'reverb'):
            event.update(type='parameter', value=float(value), confidence=1.0 if confidence is None else float(confidence))
        else:
            event['type'] = 'action'
        VALIDATOR.validate(event)  # senders validate before sending
        return event

    def send(self, control: str, value: float | None = None, confidence: float | None = None) -> dict:
        event = self.envelope(control, value, confidence)
        self.sock.sendto(json.dumps(event).encode(), self.addr)
        return event

    def close(self) -> None:
        self.sock.close()
