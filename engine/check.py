"""Preflight check for the demo laptop: python -m engine --check.

It opens no audio stream and sends nothing. It checks packages, the Focusrite
device, the Arduino serial port and that the local ports are free, then
prints PASS/WARN/FAIL rows with fix hints. The exit code is 1 if any row FAILs.
"""
from __future__ import annotations

import importlib.util
import socket
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


def format_rows(rows: list[Row]) -> str:
    width = max(len(r.check) for r in rows)
    lines = []
    for r in rows:
        line = f"{r.status:4}  {r.check:<{width}}  {r.detail}"
        if r.fix and r.status != PASS:
            line += f"\n      {'':<{width}}  → {r.fix}"
        lines.append(line)
    fails = sum(r.status == FAIL for r in rows)
    warns = sum(r.status == WARN for r in rows)
    lines.append(f"\n{'READY' if not fails else 'NOT READY'}: {fails} fail, {warns} warn. No audio was opened.")
    return "\n".join(lines)


def main_check(udp_port=47800, ws_port=47801, input_channel=2) -> int:
    rows = run_checks(udp_port=udp_port, ws_port=ws_port, input_channel=input_channel)
    print(format_rows(rows))
    return 1 if any(r.status == FAIL for r in rows) else 0
