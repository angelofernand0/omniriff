"""python -m tools.measure — the Devpost hardware numbers in one run.

On the demo laptop, with the Scarlett Solo connected:
  python -m tools.measure --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2

Steps, in order (each reports pass/fail/skipped on its own):
  check    engine preflight (devices, ports, packages, model)
  latency  tools.latency loopback: patch the Solo's output into input 2, speakers DOWN,
           Direct Monitor OFF, INST off and low gain (see tools/latency/README.md)
  cpu      engine CPU per block at --blocksize (no hardware)
  soak     play through the real engine for --soak-minutes and count xruns
           (re-patch: guitar in input 2, INST on, speakers low, and keep playing)
  take     --take-seconds N: record a dry take (no playback) and run Ears on it

The latency and soak steps need different cabling, so run them as two passes if
you prefer: --skip-soak first (loopback cable), then --skip-check --skip-latency
--skip-cpu --soak-minutes 5 --take-seconds 20 (guitar). Results go to
runs/measure/<UTC stamp>/results.json and results.md; nothing is overwritten,
and any step that didn't run says "not measured".
"""
from __future__ import annotations

import argparse
import sys

from .core import run


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m tools.measure", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--in", dest="in_dev", help="input device name substring or index (e.g. Focusrite)")
    p.add_argument("--out", dest="out_dev", help="output device name substring or index")
    p.add_argument("--hostapi", help="e.g. WASAPI or ASIO")
    p.add_argument("--input-channel", type=int, default=2, help="Scarlett Solo instrument jack = 2")
    p.add_argument("--samplerate", type=int, default=48000)
    p.add_argument("--blocksize", type=int, default=128)
    p.add_argument("--latency", default="low", help="'low', 'high' or seconds")
    p.add_argument("--exclusive", action="store_true", help="WASAPI exclusive mode")
    p.add_argument("--clicks", type=int, default=20, help="latency loopback clicks")
    p.add_argument("--soak-minutes", type=float, default=5.0, help="0 skips the soak")
    p.add_argument("--take-seconds", type=float, default=0.0, help="record a take this long and run Ears (0 = skip)")
    p.add_argument("--skip-check", action="store_true")
    p.add_argument("--skip-latency", action="store_true")
    p.add_argument("--skip-cpu", action="store_true")
    p.add_argument("--skip-soak", action="store_true", help="same as --soak-minutes 0")
    p.add_argument("--out-dir", dest="out", default="runs/measure", help="parent folder for the results")
    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    a = parser().parse_args(argv)
    if a.skip_soak:
        a.soak_minutes = 0.0
    if a.soak_minutes < 0 or a.take_seconds < 0 or a.clicks < 1:
        parser().error("--soak-minutes/--take-seconds must be >= 0 and --clicks >= 1")
    try:
        a.latency = float(a.latency)
    except ValueError:
        pass
    out = run(a, argv)
    print((out / "results.md").read_text(encoding="utf-8"))
    print(f"measure: wrote {out / 'results.json'} and results.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
