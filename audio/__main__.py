"""python -m audio — run the OmniRiff audio engine.

Examples:
  python -m audio --list-devices
  python -m audio --make-test-wav test.wav
  python -m audio --level-check --in Focusrite --hostapi WASAPI --input-channel 2
  python -m audio --input-wav test.wav --output-wav out.wav --sweep 4 --loop-at 0.5,2.5,5
  python -m audio --input-wav test.wav --play --sweep 4
  python -m audio --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from .engine import Engine, EngineConfig
from .fileio import read_wav, write_test_wav, write_wav
from .levels import analyze_levels
from .offline import render, sweep_value

KEYS = "keys: b=bypass  l=loop  f <0..1>=filter  r <0..1>=reverb  s=status  q=quit"


def _parse_times(text: str) -> tuple[float, ...]:
    return tuple(float(x) for x in text.split(",") if x.strip()) if text else ()


def _keyboard(engine: Engine, stop: threading.Event) -> None:
    print(KEYS, flush=True)
    for line in sys.stdin:
        cmd = line.strip().split()
        if not cmd:
            continue
        if cmd[0] == "q":
            break
        if cmd[0] == "b":
            engine.toggle_bypass()
        elif cmd[0] == "l":
            engine.toggle_loop()
        elif cmd[0] in ("f", "r") and len(cmd) == 2:
            setter = engine.set_filter if cmd[0] == "f" else engine.set_reverb
            try:
                ok = setter(float(cmd[1]))
            except ValueError:
                ok = False
            if not ok:
                print("value needs a number in [0, 1]", flush=True)
        elif cmd[0] == "s":
            print(json.dumps(engine.snapshot(), indent=1), flush=True)
        else:
            print(KEYS, flush=True)
    stop.set()


def _sweeper(engine: Engine, period: float, stop: threading.Event) -> None:
    start = time.monotonic()
    while not stop.wait(0.02):
        engine.set_filter(sweep_value(time.monotonic() - start, period))


def _status(engine: Engine, every: float, stop: threading.Event) -> None:
    while not stop.wait(every):
        s = engine.snapshot()
        print(
            f"in {s['input_peak_dbfs']:6.1f} dBFS  out {s['output_peak_dbfs']:6.1f} dBFS  "
            f"cutoff {s['filter']['cutoff_hz']:7.0f} Hz  bypass={s['bypass']}  loop={s['loop']['state']}  "
            f"xruns={s['xruns']}",
            flush=True,
        )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m audio", description="OmniRiff audio engine")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--make-test-wav", metavar="PATH", help="write a synthetic test chord and exit")
    p.add_argument("--level-check", nargs="?", const=10.0, type=float, metavar="SECONDS",
                   help="listen to the input (or --input-wav) and advise on the Solo gain knob; default 10 s")
    p.add_argument("--input-wav", metavar="PATH", help="process a WAV file instead of a live input")
    p.add_argument("--output-wav", metavar="PATH", help="with --input-wav: render to this file (no device)")
    p.add_argument("--play", action="store_true", help="with --input-wav: play through the speakers")
    p.add_argument("--in", dest="in_dev", help="input device index or name substring")
    p.add_argument("--out", dest="out_dev", help="output device index or name substring")
    p.add_argument("--hostapi", help="host API filter, e.g. WASAPI, ASIO, MME, 'Core Audio'")
    p.add_argument("--input-channel", type=int, default=1,
                   help="1-based input channel (Scarlett Solo: 2 = instrument jack)")
    p.add_argument("--out-channels", type=int, default=2)
    p.add_argument("--samplerate", type=int, default=48000)
    p.add_argument("--blocksize", type=int, default=128)
    p.add_argument("--latency", default="low", help="'low', 'high' or seconds")
    p.add_argument("--exclusive", action="store_true", help="WASAPI exclusive mode")
    p.add_argument("--gain-db", type=float, default=0.0, help="input gain in dB")
    p.add_argument("--gate-db", type=float, default=None,
                   help="optional noise gate open threshold in dBFS (e.g. -50); off by default")
    p.add_argument("--sweep", type=float, metavar="SECONDS", help="automate a filter sweep with this period")
    p.add_argument("--reverb", type=float, default=0.0, help="initial reverb amount 0..1")
    p.add_argument("--loop-at", default="", help="file modes: comma-separated loop toggle times (s)")
    p.add_argument("--status-every", type=float, default=0.0, help="live modes: print levels every N s")
    a = p.parse_args(argv)

    if a.make_test_wav:
        print(write_test_wav(a.make_test_wav, samplerate=a.samplerate))
        return 0

    if a.level_check is not None and a.input_wav:
        data, _ = read_wav(a.input_wav)
        print(json.dumps(analyze_levels(data.mean(axis=1)), indent=1))
        return 0

    if a.input_wav and a.output_wav:
        data, sr = read_wav(a.input_wav)
        engine = Engine(EngineConfig(samplerate=sr, input_gain_db=a.gain_db, gate_open_db=a.gate_db))
        engine.set_reverb(a.reverb)
        out = render(engine, data.mean(axis=1), a.blocksize, a.out_channels, a.sweep, _parse_times(a.loop_at))
        write_wav(a.output_wav, out, sr)
        print(json.dumps(engine.snapshot(), indent=1))
        return 0

    from . import stream  # needs PortAudio; keep file mode usable without it

    if a.list_devices:
        print(stream.list_devices())
        return 0

    if a.level_check is not None:
        in_dev = stream.resolve_device(a.in_dev, a.hostapi, "input")
        print(f"Strum normally, then your hardest, for {a.level_check:.0f} s...", flush=True)
        mono = stream.record_input(in_dev, a.input_channel, a.level_check, a.samplerate)
        print(json.dumps(analyze_levels(mono), indent=1))
        return 0

    try:
        latency = float(a.latency)
    except ValueError:
        latency = a.latency

    stop = threading.Event()
    workers = []
    out_dev = stream.resolve_device(a.out_dev, a.hostapi, "output")

    if a.input_wav:
        data, sr = read_wav(a.input_wav)
        engine = Engine(EngineConfig(samplerate=sr, input_gain_db=a.gain_db, gate_open_db=a.gate_db))
        target = lambda: stream.play(engine, data.mean(axis=1), out_dev, a.out_channels, a.blocksize, stop)
    else:
        in_dev = stream.resolve_device(a.in_dev, a.hostapi, "input")
        engine = Engine(EngineConfig(samplerate=a.samplerate, input_gain_db=a.gain_db, gate_open_db=a.gate_db))
        name = stream.sd.query_devices(in_dev, "input")["name"]
        if "scarlett" in name.lower() and a.input_channel == 1:
            print("Note: on a Scarlett Solo the guitar jack is input 2; pass --input-channel 2.", flush=True)

        def target():
            info = stream.run_live(engine, in_dev, out_dev, a.input_channel, a.out_channels,
                                   a.blocksize, latency, a.exclusive, stop)
            print(f"stream closed: {info}", flush=True)

    if not engine.set_reverb(a.reverb):
        raise SystemExit("--reverb needs a number in [0, 1]")
    workers.append(threading.Thread(target=_keyboard, args=(engine, stop), daemon=True))
    if a.sweep:
        workers.append(threading.Thread(target=_sweeper, args=(engine, a.sweep, stop), daemon=True))
    if a.status_every:
        workers.append(threading.Thread(target=_status, args=(engine, a.status_every, stop), daemon=True))
    for w in workers:
        w.start()
    try:
        target()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
    print(json.dumps(engine.snapshot(), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
