"""Watch the OmniRiff pedal's USB serial stream without starting the engine."""

import argparse
import json
import sys
import time


BAUD_RATE = 115200
MAX_LINE_BYTES = 256
ACTIONS = {"loop": "TAP", "practice": "HOLD", "bypass": "PRESS"}
GUIDE = "https://github.com/angelofernand0/omniriff/blob/main/firmware/README.md"


def read_events(port):
    pending = bytearray()
    discarding = False
    while True:
        chunk = port.read_until(size=MAX_LINE_BYTES)
        if not chunk:
            continue

        complete = chunk.endswith(b"\n")
        if discarding:
            discarding = not complete
            continue
        if len(pending) + len(chunk) > MAX_LINE_BYTES:
            pending.clear()
            discarding = not complete
            yield None
            continue

        pending.extend(chunk)
        if not complete:
            continue
        line = bytes(pending)
        pending.clear()
        try:
            event = json.loads(line)
        except ValueError:
            yield None
            continue
        if (
            isinstance(event, dict)
            and event.keys() == {"seq", "type", "control"}
            and event["type"] == "action"
            and type(event["seq"]) is int
            and event["seq"] >= 0
            and isinstance(event["control"], str)
            and event["control"] in ACTIONS
        ):
            yield event
        else:
            yield None


def monitor(port, clock=time.monotonic):
    start = clock()
    previous = None
    for event in read_events(port):
        if event is None:
            print("Ignored malformed or unsupported pedal line.", file=sys.stderr, flush=True)
            continue
        received = clock()
        gap = "first event" if previous is None else f"gap {(received - previous) * 1000:.1f} ms"
        control = event["control"]
        print(
            f"[{(received - start) * 1000:9.1f} ms] "
            f"{ACTIONS[control]} -> {control}  seq={event['seq']}  ({gap})",
            flush=True,
        )
        previous = received


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Read tap, hold, and bypass events at 115200 baud without the engine.",
        epilog=f"Times are host receive times, not press durations. Wiring and flashing: {GUIDE}",
    )
    parser.add_argument("--port", required=True, help="serial port, for example COM3")
    args = parser.parse_args(argv)
    try:
        import serial
    except ImportError:
        print('Install pySerial with: python -m pip install "pyserial>=3.5,<4"', file=sys.stderr)
        return 1

    try:
        with serial.Serial(args.port, BAUD_RATE, timeout=0.25) as port:
            print(f"Listening on {args.port} at {BAUD_RATE} baud. Ctrl+C to stop.", flush=True)
            monitor(port)
    except KeyboardInterrupt:
        return 0
    except OSError as error:
        print(f"{args.port}: {error}. Check the port and close other serial readers.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
