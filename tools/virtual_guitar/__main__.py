"""Render and audition OmniRiff without a guitar or audio interface.

Examples:
  python -m tools.virtual_guitar --demo --output outputs/virtual-guitar.wav
  python -m tools.virtual_guitar --input-wav clean-di.wav --demo --output outputs/processed.wav
  python -m tools.virtual_guitar --seconds 6 --filter 0.2 --reverb 0.6 --play
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

from audio.fileio import read_wav, write_wav

from .render import load_control_script, render_virtual_guitar, synthetic_signal


ROOT = Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.virtual_guitar",
        description="Render a labeled virtual guitar through the real OmniRiff DSP (no input hardware).",
    )
    parser.add_argument("--input-wav", help="optional 16/24/32-bit PCM guitar/DI WAV; defaults to synthesis")
    parser.add_argument("--seconds", type=float, help="synthetic duration, or crop input WAV to this duration")
    parser.add_argument("--tail-seconds", type=float, default=2.0, help="silence after input for reverb/loop tail")
    parser.add_argument("--samplerate", type=int, default=48000, help="synthetic input sample rate")
    parser.add_argument("--blocksize", type=int, default=128)
    parser.add_argument("--bpm", type=float, default=92.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--level", type=float, default=0.28)
    parser.add_argument("--gain-db", type=float, default=0.0)
    parser.add_argument("--filter", type=float, default=1.0)
    parser.add_argument("--reverb", type=float, default=0.0)
    parser.add_argument("--controls", help="validated v1 control-envelope JSONL; timestamps are relative")
    parser.add_argument("--demo", action="store_true", help="use engine/demo-controls.jsonl")
    parser.add_argument("--output", default="outputs/virtual-guitar.wav", help="processed WAV path")
    parser.add_argument("--report", help="optional JSON report path")
    parser.add_argument("--play", action="store_true", help="play the rendered result through laptop speakers")
    parser.add_argument("--out", dest="out_dev", help="with --play: output device index/name substring")
    parser.add_argument("--hostapi", help="with --play: host API filter")
    parser.add_argument("--live", action="store_true", help="audible interactive demo + dashboard; no input device")
    parser.add_argument("--headless", action="store_true", help="with --live: process audio without speaker output")
    parser.add_argument("--http-port", type=int, default=8080)
    parser.add_argument("--ws-port", type=int, default=47801)
    parser.add_argument("--udp-port", type=int, default=47800)
    parser.add_argument("--hand-port", type=int, default=47802, help="real hand-view WebSocket")
    parser.add_argument("--model", default="models/hand_landmarker.task", help="MediaPipe hand model for browser webcam")
    parser.add_argument("--scene", choices=("bloom", "rise"), default=None, help="opt into advanced Scene Morph; default is pinch/drag filter slider")
    parser.add_argument("--volume", type=float, default=0.35, help="live listening level, 0..1; after DSP")
    parser.add_argument("--duration", type=float, help="stop live demo after this many seconds")
    parser.add_argument("--open", action="store_true", help="open the live demo in the default browser")
    args = parser.parse_args(argv)

    if args.demo and args.controls:
        parser.error("choose --demo or --controls, not both")
    for name in ('seconds', 'duration', 'bpm'):
        value = getattr(args, name)
        if value is not None and (not math.isfinite(value) or value <= 0):
            parser.error(f"--{name} must be finite and positive")
    for name in ('level', 'volume', 'filter', 'reverb'):
        if not 0 <= getattr(args, name) <= 1:
            parser.error(f"--{name} must be in [0, 1]")
    if not math.isfinite(args.gain_db) or not -60 <= args.gain_db <= 24:
        parser.error('--gain-db must be finite and in [-60, 24]')
    if not math.isfinite(args.tail_seconds) or args.tail_seconds < 0:
        parser.error('--tail-seconds must be finite and nonnegative')
    if not 8000 <= args.samplerate <= 192000 or not 32 <= args.blocksize <= 4096:
        parser.error('samplerate must be 8000..192000 and blocksize 32..4096')
    if args.live and (args.demo or args.controls or args.play):
        parser.error('--live uses interactive controls; omit --demo, --controls and --play')
    if not args.live and (args.headless or args.open or args.duration is not None):
        parser.error('--headless, --open and --duration require --live')
    if any(not 1 <= port <= 65535 for port in (args.http_port, args.ws_port, args.udp_port, args.hand_port)):
        parser.error('ports must be in 1..65535')
    if not 0 <= args.level <= 1:
        parser.error("--level must be in [0, 1]")

    if args.input_wav:
        frames, samplerate = read_wav(args.input_wav)
        mono = frames.mean(axis=1)
        if args.seconds is not None:
            mono = mono[: int(round(args.seconds * samplerate))]
        input_label = str(Path(args.input_wav))
    else:
        samplerate = args.samplerate
        seconds = args.seconds if args.seconds is not None else (16 * 60 / args.bpm if args.live else 8.0)
        mono = synthetic_signal(seconds, samplerate, args.bpm, args.seed, args.level, args.blocksize)
        input_label = f"deterministic synthesis (seed={args.seed})"

    if args.live:
        from .live import run_live
        try:
            return asyncio.run(run_live(args, mono, samplerate, input_label))
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            parser.error(f'live demo could not run: {exc}')

    control_path = ROOT / "engine" / "demo-controls.jsonl" if args.demo else args.controls
    controls = load_control_script(control_path) if control_path else []
    output, report = render_virtual_guitar(
        mono,
        samplerate,
        controls=controls,
        blocksize=args.blocksize,
        tail_seconds=args.tail_seconds,
        input_gain_db=args.gain_db,
        filter_value=args.filter,
        reverb_value=args.reverb,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(output_path, output, samplerate)
    report.update(input_source=input_label, output_wav=str(output_path), control_script=str(control_path or "none"))
    rendered = json.dumps(report, indent=2, allow_nan=False)
    print(rendered)

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered + "\n")

    if args.play:
        try:
            from audio.stream import resolve_device, sd
            device = resolve_device(args.out_dev, args.hostapi, "output")
            sd.play(output, samplerate, device=device, blocking=True)
        except Exception as exc:
            parser.error(f"rendered {output_path}, but playback failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
