"""Preflight check for the demo laptop: python -m engine --check.

By default it opens no audio stream and sends nothing. It checks packages, the Focusrite
device, the Arduino serial port and that the local ports are free, then
prints PASS/WARN/FAIL rows with fix hints. The exit code is 1 if any row FAILs.
"""
from __future__ import annotations

import importlib.util
import math
import socket
import time
from dataclasses import dataclass

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

REQUIRED = [("numpy", "numpy"), ("scipy", "scipy"), ("sounddevice", "sounddevice"),
            ("jsonschema", "jsonschema"), ("websockets", "websockets"), ("serial", "pyserial")]
OPTIONAL = [("mediapipe", "mediapipe (vision/)"), ("cv2", "opencv-python (vision/)")]

# USB vendor IDs of common Arduino boards and their USB-serial chips.
ARDUINO_VIDS = {0x2341: "Arduino", 0x2A03: "Arduino.org", 0x1A86: "CH340 (clone)",
                0x0403: "FTDI", 0x10C4: "CP210x", 0x239A: "Adafruit"}


@dataclass
class Row:
    check: str
    status: str
    detail: str
    fix: str = ""


@dataclass
class OpenTest:
    seconds: float
    in_dev: str = 'Focusrite'
    out_dev: str = 'Focusrite'
    hostapi: str | None = None
    samplerate: int = 48000
    blocksize: int = 128
    input_channel: int = 2
    out_channels: int = 2
    latency: str = 'low'
    exclusive: bool = False

    def __post_init__(self):
        if not math.isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError('--open-test seconds must be finite and positive')
        if min(self.samplerate, self.blocksize, self.input_channel, self.out_channels) <= 0:
            raise ValueError('sample rate, block size and channel counts must be positive')
        if not self.in_dev.strip() or not self.out_dev.strip():
            raise ValueError('device names/indexes must not be empty; default is Focusrite')


def check_stream(options: OpenTest) -> list[Row]:
    """Explicit opt-in: duplex stream with silent output, no DSP or recording."""
    try:
        import sounddevice as sd
        from audio import stream
        source = stream.resolve_device(options.in_dev, options.hostapi, 'input')
        target = stream.resolve_device(options.out_dev, options.hostapi, 'output')
        extra_in = stream._extra_settings(source, options.exclusive)
        extra_out = stream._extra_settings(target, options.exclusive)
        extra = (extra_in, extra_out) if extra_in or extra_out else None
        try: latency = float(options.latency)
        except ValueError: latency = options.latency
        probe = dict(frames=0, peak=0.0, xruns=0, nonfinite=False)
        channel = options.input_channel - 1

        def callback(indata, outdata, frames, timing, status):
            outdata.fill(0)
            if status.input_overflow or status.output_underflow:
                probe['xruns'] += 1
            if frames:
                # Scalar reductions avoid copying or storing the input buffer.
                low, high = float(indata[:, channel].min()), float(indata[:, channel].max())
                if math.isfinite(low) and math.isfinite(high):
                    probe['peak'] = max(probe['peak'], abs(low), abs(high))
                else:
                    probe['nonfinite'] = True
                probe['frames'] += frames

        with sd.Stream(device=(source, target), samplerate=options.samplerate,
                       blocksize=options.blocksize, channels=(options.input_channel, options.out_channels),
                       dtype='float32', latency=latency, extra_settings=extra, callback=callback) as opened:
            time.sleep(options.seconds)
            active = opened.active
        if not active or not probe['frames'] or probe['nonfinite']:
            raise RuntimeError('stream stopped, delivered no frames, or supplied nonfinite samples')
        peak_db = 20 * math.log10(max(probe['peak'], 1e-9))
        quiet, hot = peak_db < -60, peak_db > -6
        return [Row('audio open-test', PASS, f"{options.seconds:g}s; {probe['frames']} frames; output was silence"),
                Row('audio open-test xruns', FAIL if probe['xruns'] else PASS, str(probe['xruns']),
                    'try a larger --blocksize and close other audio apps' if probe['xruns'] else ''),
                Row('audio open-test input peak', WARN if quiet or hot else PASS, f'{peak_db:.1f} dBFS (raw input)',
                    'play normally; check cable, input channel and gain' if quiet else 'turn input gain down' if hot else '')]
    except (Exception, SystemExit) as exc:
        return [Row('audio open-test', FAIL, f'{type(exc).__name__}: {exc}'[:240],
                    'check --in/--out, --hostapi, channel counts and driver; python -m audio --list-devices')]


def check_packages(find_spec=importlib.util.find_spec) -> list[Row]:
    rows = []
    for module, name in REQUIRED:
        ok = find_spec(module) is not None
        rows.append(Row(f"package {name}", PASS if ok else FAIL, "installed" if ok else "missing",
                        "" if ok else "python -m pip install -r engine/requirements.txt"))
    for module, name in OPTIONAL:
        ok = find_spec(module) is not None
        rows.append(Row(f"package {name}", PASS if ok else WARN, "installed" if ok else "missing",
                        "" if ok else "python -m pip install -r vision/requirements.txt (only for gesture control)"))
    return rows


def check_port(kind: str, port: int, host: str = "127.0.0.1") -> tuple[bool, str]:
    sock_type = socket.SOCK_DGRAM if kind == "udp" else socket.SOCK_STREAM
    s = socket.socket(socket.AF_INET, sock_type)
    try:
        s.bind((host, port))
        return True, "free"
    except OSError as exc:
        return False, f"in use ({exc.strerror or exc})"
    finally:
        s.close()


def check_ports(ports: dict[str, tuple[str, int]], probe=check_port) -> list[Row]:
    rows = []
    for name, (kind, port) in ports.items():
        ok, detail = probe(kind, port)
        rows.append(Row(f"port {kind.upper()} {port} ({name})", PASS if ok else FAIL, detail,
                        "" if ok else "another engine/sim/demo is still running: close it (or pass a different port)"))
    return rows


def check_audio(devices: list[dict], hostapis: list[dict], input_channel: int) -> list[Row]:
    """`devices`/`hostapis` are sounddevice.query_devices()/query_hostapis() results."""
    def api(d):
        return hostapis[d["hostapi"]]["name"]

    focus = [d for d in devices if any(k in d["name"].lower() for k in ("focusrite", "scarlett"))]
    rows = []
    if not focus:
        rows.append(Row("audio Focusrite device", FAIL, "not found",
                        "plug in the Solo, install Focusrite Control/driver, then rerun (python -m audio --list-devices)"))
    else:
        ins = [d for d in focus if d["max_input_channels"] >= input_channel]
        outs = [d for d in focus if d["max_output_channels"] >= 2]
        names = sorted({f'{d["name"]} ({api(d)})' for d in focus})
        rows.append(Row("audio Focusrite device", PASS, "; ".join(names)[:160]))
        rows.append(Row(f"audio input channel {input_channel}", PASS if ins else FAIL,
                        f"{len(ins)} Focusrite input(s) with ≥{input_channel} channels",
                        "" if ins else "use the Solo's 2-channel input device, or pick a different --input-channel"))
        rows.append(Row("audio stereo output", PASS if outs else WARN, f"{len(outs)} Focusrite output(s)",
                        "" if outs else "outputs may be on another device; pass --out explicitly"))
        wasapi = [d for d in focus if "WASAPI" in api(d)]
        asio = [d for d in focus if "ASIO" in api(d)]
        if wasapi:
            rows.append(Row("audio WASAPI", PASS, "available (use --hostapi WASAPI)"))
        else:
            rows.append(Row("audio WASAPI", WARN, "no Focusrite WASAPI entry",
                            "on Windows, use the WASAPI entry; on macOS this is expected (Core Audio)"))
        rows.append(Row("audio ASIO", PASS if asio else WARN,
                        "available" if asio else "not exposed by this PortAudio build (WASAPI is fine)"))
    return rows


def check_serial(ports: list) -> list[Row]:
    """`ports` are serial.tools.list_ports.comports() results (device, description, vid)."""
    likely = [p for p in ports if getattr(p, "vid", None) in ARDUINO_VIDS
              or "arduino" in (getattr(p, "description", "") or "").lower()]
    if likely:
        p = likely[0]
        chip = ARDUINO_VIDS.get(getattr(p, "vid", None), "Arduino")
        return [Row("serial Arduino", PASS, f"{p.device} ({chip}: {p.description})",
                    f"pass --serial-port {p.device}")]
    if ports:
        listed = ", ".join(p.device for p in ports)[:120]
        return [Row("serial Arduino", WARN, f"no Arduino recognized; ports: {listed}",
                    "plug in the pedal's USB cable; the keyboard l/b keys work without it")]
    return [Row("serial Arduino", WARN, "no serial ports",
                "plug in the pedal (optional: the keyboard l/b keys and the dashboard cover loop/bypass)")]


def check_model(path: str = "models/hand_landmarker.task") -> list[Row]:
    from pathlib import Path
    ok = Path(path).is_file()
    return [Row("vision hand model", PASS if ok else WARN, path if ok else f"{path} not found",
                "" if ok else "download the MediaPipe Hand Landmarker model (vision/README.md#setup); only needed for gesture control")]


def run_checks(udp_port=47800, ws_port=47801, hand_port=47802, http_port=8080, input_channel=2) -> list[Row]:
    rows = check_packages()
    rows += check_model()
    rows += check_ports({"controls": ("udp", udp_port), "state": ("tcp", ws_port),
                         "hand view": ("tcp", hand_port), "dashboard": ("tcp", http_port)})
    try:
        import sounddevice as sd
        rows += check_audio(list(sd.query_devices()), list(sd.query_hostapis()), input_channel)
    except Exception as exc:  # PortAudio missing or broken
        rows.append(Row("audio PortAudio", FAIL, f"{type(exc).__name__}: {exc}"[:160],
                        "python -m pip install sounddevice (it bundles PortAudio on Windows/macOS)"))
    try:
        from serial.tools import list_ports
        rows += check_serial(list(list_ports.comports()))
    except Exception as exc:
        rows.append(Row("serial Arduino", WARN, f"cannot list ports: {exc}"[:160], "python -m pip install pyserial"))
    return rows


def format_rows(rows: list[Row], *, open_test_requested=False) -> str:
    width = max(len(r.check) for r in rows)
    lines = []
    for r in rows:
        line = f"{r.status:4}  {r.check:<{width}}  {r.detail}"
        if r.fix and r.status != PASS:
            line += f"\n      {'':<{width}}  → {r.fix}"
        lines.append(line)
    fails = sum(r.status == FAIL for r in rows)
    warns = sum(r.status == WARN for r in rows)
    note = 'Device-open test requested; see rows above. Not round-trip latency.' if open_test_requested else 'No audio was opened.'
    lines.append(f"\n{'READY' if not fails else 'NOT READY'}: {fails} fail, {warns} warn. {note}")
    return "\n".join(lines)


def main_check(udp_port=47800, ws_port=47801, input_channel=2, open_test: OpenTest | None = None) -> int:
    rows = run_checks(udp_port=udp_port, ws_port=ws_port, input_channel=input_channel)
    if open_test is not None:
        print(f'OPEN TEST requested: {open_test.seconds:g}s, output silence. Play to check raw input peak.', flush=True)
        rows += check_stream(open_test)
    print(format_rows(rows, open_test_requested=open_test is not None))
    return 1 if any(r.status == FAIL for r in rows) else 0
