"""python -m tools.ears TAKE.wav [--sidecar TAKE.json] [--output report.json]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .analyze import analyze_take


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.ears", description="Strum timing report for a captured take")
    p.add_argument("wav", type=Path)
    p.add_argument("--sidecar", type=Path, help="defaults to the .json next to the WAV")
    p.add_argument("--output", type=Path, help="write the TakeReport JSON here (refuses to overwrite)")
    a = p.parse_args(argv)
    report = analyze_take(a.wav, a.sidecar).to_json()
    if a.output:
        if a.output.exists():
            raise SystemExit(f"refusing to overwrite {a.output}")
        a.output.write_text(report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
