"""python -m tools.latency — measure OmniRiff latency.

Engine-only (no hardware; CPU cost per block):
  python -m tools.latency --engine-only

Loopback (real round trip on the audio host):
  1. Turn speakers/headphones DOWN. Turn the Solo's Direct Monitor OFF.
  2. Patch a cable from the Solo's output (line out / headphone out) into input 2 (INST off, low gain).
  3. python -m tools.latency --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2

The tool plays clicks and times when each returns. The engine is not in the
loop during the measurement (that would feed back), but it runs inside the same
duplex callback in live use, so this round trip is the guitar-to-output latency
the player hears, plus a negligible DSP delay.
"""
from __future__ import annotations

import argparse
import json
import threading

import numpy as np

from .measure import click, find_onsets, summarize_ms, time_engine


def loopback(a) -> dict:
    import sounddevice as sd
    from audio.stream import resolve_device

    in_dev = resolve_device(a.in_dev, a.hostapi, "input")
    out_dev = resolve_device(a.out_dev, a.hostapi, "output")
    sr = a.samplerate
    pulse = click(sr)
    lead = int(0.5 * sr)  # silence first, to measure the noise floor
    spacing = int(a.interval * sr)
    click_frames = [lead + i * spacing for i in range(a.clicks)]
    total = click_frames[-1] + int(0.6 * sr)
    recorded = np.zeros(total, np.float32)
    ch = a.input_channel - 1
    pos = [0]
    xruns = [0]
    done = threading.Event()

    def callback(indata, outdata, frames, time, status):
        if status.input_overflow or status.output_underflow:
            xruns[0] += 1
        s = pos[0]
        outdata.fill(0)
        for f in click_frames:
            if s <= f + len(pulse) and f < s + frames:
                a0 = max(f, s)
                a1 = min(f + len(pulse), s + frames)
                outdata[a0 - s:a1 - s, :] = pulse[a0 - f:a1 - f, None]
        n = min(frames, total - s)
        if n > 0:
            recorded[s:s + n] = indata[:n, ch]
        pos[0] = s + frames
        if pos[0] >= total:
            done.set()

    extra = None
    if a.exclusive:
        extra = (sd.WasapiSettings(exclusive=True), sd.WasapiSettings(exclusive=True))
    with sd.Stream(device=(in_dev, out_dev), samplerate=sr, blocksize=a.blocksize, dtype="float32",
                   channels=(a.input_channel, 2), latency=a.latency, extra_settings=extra,
                   callback=callback) as stream:
        reported = stream.latency
        done.wait(timeout=total / sr + 10)

    result = summarize_ms(find_onsets(recorded, click_frames, sr), sr)
    result.update(
        mode="loopback",
        samplerate=sr,
        blocksize=a.blocksize,
        portaudio_reported_ms={"input": round(reported[0] * 1000, 2), "output": round(reported[1] * 1000, 2)},
        xruns=xruns[0],
        input_device=sd.query_devices(in_dev, "input")["name"] if in_dev is not None else "default",
    )
    if result["detected"] < result["clicks"] // 2:
        result["warning"] = "Most clicks were not detected: check the loopback cable, input channel and gain."
    return result


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m tools.latency", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--engine-only", action="store_true", help="time the engine's CPU cost (no hardware)")
    p.add_argument("--in", dest="in_dev")
    p.add_argument("--out", dest="out_dev")
    p.add_argument("--hostapi")
    p.add_argument("--input-channel", type=int, default=2)
    p.add_argument("--samplerate", type=int, default=48000)
    p.add_argument("--blocksize", type=int, default=128)
    p.add_argument("--latency", default="low")
    p.add_argument("--exclusive", action="store_true")
    p.add_argument("--clicks", type=int, default=20)
    p.add_argument("--interval", type=float, default=0.5, help="seconds between clicks")
    a = p.parse_args(argv)
    try:
        a.latency = float(a.latency)
    except ValueError:
        pass
    if a.engine_only:
        print(json.dumps({"mode": "engine-only", "note": "CPU cost per block; not I/O latency",
                          "results": time_engine(samplerate=a.samplerate)}, indent=1))
        return 0
    print(json.dumps(loopback(a), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
