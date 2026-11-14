"""One-command demo bring-up: python -m engine.demo [launcher options] [engine options].

Starts the dashboard web server, optionally starts vision as a child process,
then runs the normal engine (same options as `python -m engine`) in the
foreground. Ctrl-C or `q` stops everything; the dashboard and vision are
shut down when the engine exits for any reason.

  python -m engine.demo --open --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM4
  python -m engine.demo --vision --headless                    # no audio hardware
  python -m engine.demo --replay engine/demo-controls.jsonl    # labeled backup
  python -m engine.demo --coach --vision --hand-log runs/hand.jsonl ...  # practice coach too
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import threading
import webbrowser

from . import __main__ as engine_main


def start_child(cmd: list[str], label: str) -> subprocess.Popen | None:
    try:
        return subprocess.Popen(cmd)
    except OSError as exc:
        print(f"demo: could not start {label} ({exc}); continuing without it", flush=True)
        return None


def start_vision(cmd: list[str]) -> subprocess.Popen | None:
    return start_child(cmd, "vision")


def start_coach(cmd: list[str]) -> subprocess.Popen | None:
    return start_child(cmd, "coach")


def stop_process(proc: subprocess.Popen | None, timeout: float = 3.0) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout)


def _ws_port(engine_args: list[str]) -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--ws-port", type=int, default=47801)
    return p.parse_known_args(engine_args)[0].ws_port


def _udp_port(engine_args: list[str]) -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--udp-port", type=int, default=47800)
    return p.parse_known_args(engine_args)[0].udp_port


def vision_command(vision_args: list[str], engine_args: list[str]) -> list[str]:
    """Command for the vision child: always aimed at THIS engine's UDP port.

    If --vision-args already names --port, it is kept, with a warning if it
    differs from the engine's (then vision would feed some other engine).
    """
    udp = _udp_port(engine_args)
    cmd = [sys.executable, "-m", "vision", *vision_args]
    given = argparse.ArgumentParser(add_help=False)
    given.add_argument("--port", type=int)
    explicit = given.parse_known_args(vision_args)[0].port
    if explicit is None:
        cmd += ["--port", str(udp)]
    elif explicit != udp:
        print(f"demo: WARNING vision --port {explicit} differs from the engine's --udp-port {udp}; "
              "its gestures will not reach this engine", flush=True)
    return cmd


DEFAULT_TAKE_DIR = "runs/takes"


def _take_dir(engine_args: list[str]) -> str | None:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--take-dir")
    return p.parse_known_args(engine_args)[0].take_dir


def coach_command(coach_args: list[str], take_dir: str, hand_log: str | None) -> list[str]:
    """Command for the coach child, watching the same take directory the engine writes."""
    cmd = [sys.executable, "-m", "coach", "--take-dir", take_dir]
    if hand_log:
        cmd += ["--hand-log", hand_log]
    return cmd + list(coach_args)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m engine.demo",
        description="Dashboard + optional vision + engine in one command. Unrecognized options go to the engine.")
    p.add_argument("--http-port", type=int, default=8080, help="dashboard port (0 = any free port)")
    p.add_argument("--open", action="store_true", help="open the dashboard in the default browser")
    p.add_argument("--vision", action="store_true", help="also start gesture control (python -m vision)")
    p.add_argument("--vision-args", default="", help='extra arguments for vision, e.g. "--relative --scene bloom"')
    p.add_argument("--coach", action="store_true", help="also start the practice coach (python -m coach) on the engine's takes")
    p.add_argument("--coach-args", default="", help='extra arguments for the coach')
    p.add_argument("--hand-log", help="hand movement log path, passed to both vision and the coach")
    a, engine_args = p.parse_known_args(argv)
    take_dir = _take_dir(engine_args)
    if a.coach and not take_dir:
        take_dir = DEFAULT_TAKE_DIR
        engine_args = [*engine_args, "--take-dir", take_dir]  # the coach needs the engine to save takes

    from dashboard.__main__ import make_server
    try:
        server = make_server(a.http_port)
    except OSError as exc:
        print(f"demo: dashboard port {a.http_port} unavailable ({exc}). Run python -m engine --check.", flush=True)
        return 1
    port = server.server_address[1]
    ws = _ws_port(engine_args)
    url = f"http://127.0.0.1:{port}/" + (f"?ws=ws://127.0.0.1:{ws}" if ws != 47801 else "")
    threading.Thread(target=server.serve_forever, name="omniriff-dashboard", daemon=True).start()
    print(f"demo: dashboard {url}", flush=True)

    vision = None
    if a.vision:
        if importlib.util.find_spec("vision.__main__") is None:
            print("demo: vision/ is not installed on this branch (pending PR #13); continuing without it", flush=True)
        else:
            vision_args = a.vision_args.split() + (["--hand-log", a.hand_log] if a.hand_log else [])
            vision = start_vision(vision_command(vision_args, engine_args))
            if vision:
                print(f"demo: vision started (pid {vision.pid})", flush=True)
    coach = None
    if a.coach:
        if importlib.util.find_spec("coach.__main__") is None:
            print("demo: coach/ is not installed on this branch yet; continuing without it", flush=True)
        else:
            coach = start_coach(coach_command(a.coach_args.split(), take_dir, a.hand_log))
            if coach:
                print(f"demo: coach started (pid {coach.pid}) watching {take_dir}", flush=True)
    if a.open:
        webbrowser.open(url)

    try:
        return engine_main.main(engine_args)
    finally:
        stop_process(coach)
        stop_process(vision)
        server.shutdown()
        server.server_close()
        stopped = ["dashboard"] + (["vision"] if vision else []) + (["coach"] if coach else [])
        print("demo: stopped " + ", ".join(stopped), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
