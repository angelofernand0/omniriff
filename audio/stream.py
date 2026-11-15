"""Live audio via sounddevice/PortAudio. Imported only when a device is used."""
from __future__ import annotations

import threading

import numpy as np
import sounddevice as sd

from .engine import Engine


def list_devices() -> str:
    apis = sd.query_hostapis()
    lines = []
    for i, d in enumerate(sd.query_devices()):
        api = apis[d["hostapi"]]["name"]
        lines.append(
            f"[{i:2d}] {d['name']}  ({api})  in={d['max_input_channels']} out={d['max_output_channels']}"
            f"  default_sr={d['default_samplerate']:.0f}"
        )
    return "\n".join(lines)


def resolve_device(spec: str | None, hostapi: str | None, kind: str) -> int | None:
    """Find a device by index or case-insensitive name substring, optionally filtered by host API."""
    if spec is None and hostapi is None:
        return None
    if spec is not None and spec.isdigit():
        return int(spec)
    apis = sd.query_hostapis()
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    for i, d in enumerate(sd.query_devices()):
        if d[key] <= 0:
            continue
        if spec and spec.lower() not in d["name"].lower():
            continue
        if hostapi and hostapi.lower() not in apis[d["hostapi"]]["name"].lower():
            continue
        return i
    raise SystemExit(f"No {kind} device matches name={spec!r} hostapi={hostapi!r}. Run with --list-devices.")


def _extra_settings(device: int | None, exclusive: bool):
    if not exclusive or device is None:
        return None
    api = sd.query_hostapis()[sd.query_devices(device)["hostapi"]]["name"]
    if "WASAPI" not in api:
        raise SystemExit("--exclusive only applies to WASAPI devices.")
    return sd.WasapiSettings(exclusive=True)


def run_live(
    engine: Engine,
    input_device: int | None,
    output_device: int | None,
    input_channel: int,
    out_channels: int,
    blocksize: int,
    latency,
    exclusive: bool,
    stop: threading.Event,
) -> dict:
    """Run guitar -> engine -> output until `stop` is set. Returns stream info."""
    ch = input_channel - 1
    extra_in = _extra_settings(input_device, exclusive)
    extra_out = _extra_settings(output_device, exclusive)
    extra = (extra_in, extra_out) if (extra_in or extra_out) else None

    def callback(indata, outdata, frames, time, status):
        if status.input_overflow or status.output_underflow:
            engine.note_xrun()
        engine.process(indata[:, ch], outdata)

    with sd.Stream(
        device=(input_device, output_device),
        samplerate=engine.config.samplerate,
        blocksize=blocksize,
        dtype="float32",
        channels=(input_channel, out_channels),
        latency=latency,
        extra_settings=extra,
        callback=callback,
    ) as stream:
        info = {"latency_s": stream.latency, "samplerate": stream.samplerate, "blocksize": stream.blocksize}
        stop.wait()
    return info


def play(engine: Engine, mono: np.ndarray, output_device: int | None, out_channels: int,
         blocksize: int, stop: threading.Event) -> None:
    """Stream a file through the engine to the speakers (no input device needed)."""
    pos = [0]
    done = threading.Event()

    def callback(outdata, frames, time, status):
        if status.output_underflow:
            engine.note_xrun()
        s = pos[0]
        chunk = mono[s:s + frames]
        if len(chunk) < frames:
            outdata.fill(0)
            done.set()
            if not len(chunk):
                return
        engine.process(chunk, outdata[:len(chunk)])
        pos[0] = s + frames

    with sd.OutputStream(device=output_device, samplerate=engine.config.samplerate, blocksize=blocksize,
                         dtype="float32", channels=out_channels, callback=callback):
        while not (done.is_set() or stop.is_set()):
            stop.wait(0.1)


def run_virtual(engine: Engine, mono: np.ndarray, output_device: int | None, out_channels: int,
                blocksize: int, stop: threading.Event, volume: float = 0.35) -> dict:
    """Loop a synthetic guitar `mono` through the real engine to the speakers until `stop` is set.

    A SIMULATED input for demos/tests without a guitar or interface: the engine, looper, takes and
    controls are the real ones. `volume` scales the speaker output after the DSP (not the DSP input).
    """
    if not len(mono):
        raise ValueError("virtual guitar signal is empty")
    pos = [0]

    def callback(outdata, frames, time, status):
        if status.output_underflow:
            engine.note_xrun()
        chunk = np.empty(frames, dtype=np.float32)
        filled = 0
        while filled < frames:  # wrap around so the performance repeats forever
            n = min(frames - filled, len(mono) - pos[0])
            chunk[filled:filled + n] = mono[pos[0]:pos[0] + n]
            filled += n
            pos[0] = (pos[0] + n) % len(mono)
        engine.process(chunk, outdata)
        outdata *= volume

    with sd.OutputStream(device=output_device, samplerate=engine.config.samplerate, blocksize=blocksize,
                         dtype="float32", channels=out_channels, callback=callback) as stream:
        info = {"latency_s": stream.latency, "samplerate": stream.samplerate, "blocksize": stream.blocksize}
        stop.wait()
    return info


def record_input(input_device: int | None, input_channel: int, seconds: float, samplerate: int) -> np.ndarray:
    """Record one input channel for `seconds` (blocking; never used in the audio callback)."""
    frames = int(seconds * samplerate)
    data = sd.rec(frames, samplerate=samplerate, channels=input_channel, dtype="float32", device=input_device)
    sd.wait()
    return data[:, input_channel - 1].copy()
