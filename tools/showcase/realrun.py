"""Drive one real coach session through the hosted coach server, as the website would.

It says a goal, streams looper state, uploads takes of the PLAY-THIS riff (planted chord-change
stall + frozen wrist, getting smaller each take), approves the drill and logs every frame and
voice clip. The coach on the other end is the real one: real Ears/Eyes, real model, real voice.

    python -m coach.server --no-passcode &          # or a hosted URL + --key
    python -m tools.showcase.realrun --out runs/showcase/run-1

The log (<out>/session.jsonl) uses coach/replay.py's format, so it can be replayed or turned
into the scripted coach. It holds coaching text and MP3s; keep it in ignored runs/.
"""
from __future__ import annotations

import argparse
import base64
import json
import time
import uuid
from pathlib import Path

import numpy as np

from .hands import Faults, render

GOAL = "My chord changes feel clunky. I want the Em to Dsus2 progression to flow."
# Each take a little better; the coach's session decides pass / advance / wrap from the measurements.
SCENARIOS = {
    "late-finger": [Faults(late_finger="ring", lag_s=lag) for lag in (0.28, 0.12, 0.05, 0.0, 0.0, 0.0)],
    "late-start": [Faults(start_delay_s=d) for d in (0.25, 0.12, 0.04, 0.0, 0.0, 0.0)],
}


class Client:
    def __init__(self, url: str, out: Path, key: str = ""):
        from websockets.sync.client import connect
        self.ws = connect(url,  # noqa: long-lived client, closed at exit max_size=8 * 1024 * 1024, open_timeout=10,
                          additional_headers={"Origin": "http://127.0.0.1:5173"})
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.log = (out / "session.jsonl").open("x", encoding="utf-8")
        self.t0 = time.monotonic()
        self.log.write(json.dumps({"format": "omniriff.coach.replay", "version": 1,
                                   "captured_at_ms": int(time.time() * 1000),
                                   "input_provenance": "unverified"}) + "\n")
        self.frame: dict = {}
        self.key = key
        self.loop = {"state": "idle"}
        self.bypass = False
        self.controls: list[dict] = []
        self.voice_clips = 0

    def _record(self, message: dict) -> None:
        at = round((time.monotonic() - self.t0) * 1000)
        self.log.write(json.dumps({"at_ms": at, "message": message}, separators=(",", ":")) + "\n")
        self.log.flush()

    def send(self, message: dict) -> None:
        self.ws.send(json.dumps(message, separators=(",", ":")))

    def state(self) -> None:
        self.send({"type": "omniriff.state", "loop": self.loop, "bypass": self.bypass,
                   "filter": {"value": 1.0}, "reverb": {"value": 0.0}})

    def pump(self, seconds: float) -> None:
        """Receive for a while, answering approvals, applying controls and re-sending state."""
        end = time.monotonic() + seconds
        next_state = 0.0
        while time.monotonic() < end:
            if time.monotonic() >= next_state:
                self.state()
                next_state = time.monotonic() + 0.5
            try:
                raw = self.ws.recv(timeout=0.25)
            except TimeoutError:
                continue
            message = json.loads(raw)
            kind = message.get("type")
            if kind == "coach.frame":
                old = self.frame
                self.frame = message
                self._record(message)
                if message.get("cue") and message["cue"] != old.get("cue"):
                    print(f"  RIFF [{message['state']}/{message['mood']}]: {message['cue']}")
                pending = message.get("awaiting_approval")
                if pending and pending != old.get("awaiting_approval"):
                    print(f"  approval asked: {pending.get('summary')}  -> approving")
                    time.sleep(1.5)
                    self.send({"version": 1, "type": "coach.approve", "timestamp_ms": int(time.time() * 1000),
                               "approval_id": pending["id"]})
            elif kind == "coach.audio":
                self.voice_clips += 1
                self._record(message)
            elif kind == "omniriff.control":
                print(f"  rig control from coach: {message}")
                self.controls.append(message)
                if message["control"] == "bypass":
                    self.bypass = not self.bypass
            elif kind == "omniriff.take_ack":
                print(f"  take upload: {message['result']}")

    def settled(self, timeout: float, quiet: float = 6.0) -> None:
        """Wait until Riff is done with a take: not thinking/listening and nothing new for `quiet` s."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            before = self.frame.get("timestamp_ms")
            self.pump(quiet)
            busy = self.frame.get("state") in ("listening", "thinking") or self.frame.get("awaiting_approval")
            running = any(a.get("status") in ("running", "waiting") for a in self.frame.get("activity", []))
            if self.frame.get("timestamp_ms") == before and not busy and not running:
                return
        print("  (timed out waiting for Riff to settle)")

    def take(self, faults: Faults, index: int) -> None:
        audio, sr, started, hands, _ = render(faults)
        self.loop = {"state": "recording"}
        self.pump(1.0)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        self.loop = {"state": "playing"}
        self.state()
        print(f"take {index}: {faults}, {len(audio) / sr:.1f} s")
        self.send({"type": "omniriff.take", "samplerate": sr, "started_unix_ms": started,
                   "pcm16_b64": base64.b64encode(pcm).decode(), "hands": hands})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="ws://127.0.0.1:8787/coach")
    parser.add_argument("--key", default="")
    parser.add_argument("--player", default="showcase-" + uuid.uuid4().hex[:12])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--goal", default=GOAL)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="late-finger")
    parser.add_argument("--max-takes", type=int, default=6)
    args = parser.parse_args(argv)
    url = f"{args.server}?player={args.player}"
    client = Client(url, args.out, args.key)
    client.send({"type": "omniriff.hello", "key": args.key})   # the passcode is never in the URL
    print(f"connected; player {args.player}")
    client.pump(4)
    print(f"say: {args.goal}")
    client.send({"version": 1, "type": "coach.say", "timestamp_ms": int(time.time() * 1000),
                 "text": args.goal, "via": "typed"})
    client.pump(6)
    for index, faults in enumerate(SCENARIOS[args.scenario][: args.max_takes], 1):
        client.take(faults, index)
        client.settled(timeout=180)
        session = client.frame.get("session") or {}
        if session.get("mode") == "play":
            print("session finished; Riff is back in free play")
            break
    summary = {"player": args.player, "controls": client.controls, "voice_clips": client.voice_clips,
               "final_frame": client.frame}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {args.out / 'session.jsonl'} ({client.voice_clips} voice clips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
