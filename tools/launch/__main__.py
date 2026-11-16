"""One launcher for every way to run OmniRiff, the same on macOS, Windows and Linux.

  python -m tools.launch                 # a menu
  python -m tools.launch demo            # simulated guitar + real engine + hand tracking + LIVE AI coach
  python -m tools.launch rig             # a real guitar/interface + hand tracking + LIVE AI coach
  python -m tools.launch fallback        # simulated guitar + the SCRIPTED coach (free, no keys)
  python -m tools.launch replay [FILE]   # simulated guitar + a recorded coach session (REPLAY, free, no keys)
  python -m tools.launch quiet           # just the instrument, no coach
  python -m tools.launch check           # what this machine has (paste the output on the board)
  python -m tools.launch setup           # create .venv and install everything (macOS/Linux; Windows: scripts/windows/setup.ps1)

Presets set three things; any can be overridden: --source hardware|virtual|silent, --coach live|scripted|replay|off,
--vision auto|on|off. Switching coach mode is deliberate: stop (Ctrl-C) and start another preset. The LIVE coach
uses Gemini API quota and can ask to change the rig, so it is never run alongside the others.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IS_WIN = os.name == 'nt'
MODEL = Path('models/hand_landmarker.task')
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task'
REPLAYS = ROOT / 'dashboard' / 'replays'
PRESETS = {
    'demo':     dict(source='virtual',  coach='live',     vision='auto'),
    'rig':      dict(source='hardware', coach='live',     vision='auto'),
    'fallback': dict(source='virtual',  coach='scripted', vision='auto'),
    'replay':   dict(source='virtual',  coach='replay',   vision='auto'),
    'quiet':    dict(source='virtual',  coach='off',      vision='auto'),
}
BLURB = {
    'demo': 'simulated guitar + real engine + hand tracking + LIVE Gemini coach (uses API quota)',
    'rig': 'real guitar/interface + hand tracking + LIVE Gemini coach (uses API quota)',
    'fallback': 'simulated guitar + SCRIPTED coach (canned, free, no keys)',
    'replay': 'simulated guitar + a recorded REAL coach session (free, no keys)',
    'quiet': 'just the instrument: simulated guitar, no coach',
}


# ---- finding things -------------------------------------------------------------------------------------
def _venv_python(base: Path) -> Path:
    return base / '.venv' / ('Scripts/python.exe' if IS_WIN else 'bin/python')


def sibling_checkouts() -> list[Path]:
    """Other checkouts of this repo (main clone, worktrees, Codex worktrees) often hold the venv and the model."""
    found: list[Path] = []
    try:
        common = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=ROOT, capture_output=True, text=True,
                                timeout=10).stdout.strip()
        if common:
            main = (ROOT / common).resolve().parent
            found += [main, *sorted((main / '.claude' / 'worktrees').glob('*'))]
    except (OSError, subprocess.SubprocessError):
        pass
    found += sorted((Path.home() / '.codex' / 'worktrees').glob('*/omniriff'))
    return [p for p in found if p.is_dir() and p.resolve() != ROOT]


def can_import(python: str, *modules: str) -> bool:
    code = 'import ' + ', '.join(modules)
    try:
        return subprocess.run([python, '-c', code], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


WANTED = ('websockets', 'numpy', 'sounddevice', 'mediapipe', 'cv2', 'langchain_google_genai', 'deepagents')


def capabilities(python: str) -> set[str]:
    """Which of the packages OmniRiff can use are importable by this Python (one process, not one per module)."""
    code = ('import importlib\n'
            f'for m in {list(WANTED)!r}:\n'
            '    try:\n        importlib.import_module(m); print(m)\n    except Exception:\n        pass\n')
    try:
        return set(subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=90).stdout.split())
    except (OSError, subprocess.SubprocessError):
        return set()


def find_python(explicit: str | None = None) -> str | None:
    """An explicit --python (or OMNIRIFF_PYTHON) wins. Otherwise the candidate that can do the most: this
    checkout's .venv, sibling checkouts' venvs (a fresh worktree has none), then Python on PATH."""
    for c in (explicit, os.environ.get('OMNIRIFF_PYTHON')):
        if c:
            return c
    cands = [str(_venv_python(ROOT))] + [str(_venv_python(p)) for p in sibling_checkouts()]
    for name in ('python3.12', 'python3', 'python'):
        found = shutil.which(name)
        if found:
            cands.append(found)
    best, best_score, seen = None, -1, set()
    for c in cands:
        if c in seen or not Path(c).exists():
            continue
        seen.add(c)
        caps = capabilities(c)
        if 'websockets' in caps and len(caps) > best_score:
            best, best_score = c, len(caps)
    return best


def env_has_key(name: str) -> bool:
    if os.environ.get(name):
        return True
    for f in (ROOT / '.env', Path.home() / '.config' / 'omniriff' / '.env'):
        try:
            if any(line.strip().startswith(name + '=') and line.split('=', 1)[1].strip() for line in f.read_text().splitlines()):
                return True
        except OSError:
            pass
    return False


def env_has_coach_key() -> bool:
    return env_has_key('GOOGLE_API_KEY') or env_has_key('GEMINI_API_KEY')


def free_ports() -> tuple[int, int, int, int, int]:
    """(http, udp, ws, hand, coach): the defaults if free, otherwise the whole set shifted so old sims don't collide."""
    def free(p: int) -> bool:
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            s = socket.socket(socket.AF_INET, kind)
            try:
                s.bind(('127.0.0.1', p))
            except OSError:
                return False
            finally:
                s.close()
        return True
    for off in range(0, 200, 10):
        ports = (8080 + off // 10, 47800 + off, 47801 + off, 47802 + off, 47803 + off)
        if all(free(p) for p in ports):
            return ports
    raise SystemExit('No free port set found (close old OmniRiff windows).')


def pick_camera(python: str) -> int | None:
    """First camera index that returns real (non-black) frames; some Macs' index 0 is a black virtual camera."""
    code = ('import cv2,time\n'
            'for i in range(4):\n'
            '    cap=cv2.VideoCapture(i)\n'
            '    if not cap.isOpened(): continue\n'
            '    best,t0=0.0,time.time()\n'
            '    while time.time()-t0<2.5:\n'
            '        ok,f=cap.read()\n'
            '        if ok: best=max(best,float(f.mean()))\n'
            '    cap.release()\n'
            '    if best>5:\n'
            '        print(i); break\n')
    try:
        out = subprocess.run([python, '-c', code], capture_output=True, text=True, timeout=40).stdout.strip()
        return int(out) if out else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# ---- the plan: pure data, easy to test ------------------------------------------------------------------
@dataclass
class Plan:
    python: str
    source: str
    coach: str
    vision: bool
    camera: int | None
    ports: tuple
    engine_cmd: list[str]
    coach_cmd: list[str] | None
    url: str
    notes: list[str] = field(default_factory=list)
    replay_file: Path | None = None


def resolve_replay(arg: str | None) -> Path:
    if arg:
        p = Path(arg).expanduser()
        if not p.is_file():
            raise SystemExit(f'Replay file not found: {p}')
        if REPLAYS not in p.resolve().parents:
            REPLAYS.mkdir(parents=True, exist_ok=True)
            dest = REPLAYS / p.name
            if not dest.exists():
                shutil.copy2(p, dest)
            p = dest
        return p
    files = sorted(REPLAYS.glob('*.jsonl'), key=lambda f: f.stat().st_mtime, reverse=True) if REPLAYS.is_dir() else []
    if not files:
        raise SystemExit('No recorded session found in dashboard/replays/. Record one with the live coach '
                         '(python -m coach --record ..., see coach/README.md) or pass a file: replay FILE')
    return files[0]


def build_plan(a, python: str, ports: tuple, camera: int | None) -> Plan:
    http, udp, ws, hand, coachp = ports
    notes: list[str] = []
    vision = a.vision in ('auto', 'on')
    if vision and not (ROOT / MODEL).is_file():
        for d in sibling_checkouts():
            if (d / MODEL).is_file():
                (ROOT / MODEL).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(d / MODEL, ROOT / MODEL)
                notes.append(f'hand model copied from {d}')
                break
    if vision and not (ROOT / MODEL).is_file():
        notes.append('WARNING: models/hand_landmarker.task missing, starting without hand tracking '
                     '(download it, see vision/README.md)')
        vision = False
    if vision and not can_import(python, 'mediapipe', 'cv2'):
        notes.append('WARNING: mediapipe/opencv not installed for this Python, starting without hand tracking')
        vision = False
    if vision and camera is None:
        notes.append('WARNING: no camera gave a picture (camera permission? on macOS run from Terminal.app); '
                     'starting without hand tracking')
        vision = False

    cmd = [python, '-m', 'engine.demo', '--http-port', str(http), '--udp-port', str(udp), '--ws-port', str(ws)]
    if a.audio:
        cmd += a.audio.split()
    elif a.source == 'virtual':
        cmd += ['--virtual-guitar']
    elif a.source == 'silent':
        cmd += ['--headless']
    elif IS_WIN:   # the lab laptop's interface (scripts/windows/start-demo.ps1)
        cmd += ['--in', 'Focusrite', '--out', 'Focusrite', '--hostapi', 'WASAPI', '--input-channel', '2']
    if a.serial:
        cmd += ['--serial-port', a.serial]
    if vision:
        handlog = f'runs/hand-{time.strftime("%Y%m%d-%H%M%S")}.jsonl'   # vision writes it; the coach's "eyes" read it
        cmd += ['--hand-log', handlog, '--vision', '--vision-args',
                f'--model {MODEL.as_posix()} --camera {camera} --port {udp} --hand-view-port {hand} --relative']
    coach_cmd = None
    params = [f'ws=ws://127.0.0.1:{ws}']
    params.append(f'hand=ws://127.0.0.1:{hand}' if vision else 'hand=off')
    replay_file = None
    if a.coach == 'live':
        cmd += ['--coach', '--coach-args', f'--state-port {ws} --control-port {udp} --feed-port {coachp}']
        params.append(f'coachws=ws://127.0.0.1:{coachp}')
    elif a.coach == 'scripted':
        coach_cmd = [python, '-m', 'tools.sim', 'coach', '--port', str(coachp), '--engine-ws', f'ws://127.0.0.1:{ws}',
                     '--udp-port', str(udp)]
        params.append(f'coachws=ws://127.0.0.1:{coachp}')
    elif a.coach == 'replay':
        replay_file = resolve_replay(a.replay)
        params.append(f'replay=replays/{replay_file.name}')
    elif a.coach == 'off':
        params.append('coach=off')
    if a.source == 'virtual' and not a.audio:
        params.append('sim=guitar')   # a simulated guitar must say so on screen (BRAND_SPEC voice rule 9)
    url = f'http://127.0.0.1:{http}/?' + '&'.join(params)
    return Plan(python, a.source, a.coach, vision, camera if vision else None, ports, cmd, coach_cmd, url, notes, replay_file)


def preflight_notes(a, python: str) -> list[str]:
    notes = []
    if a.coach == 'live':
        if not can_import(python, 'langchain_google_genai', 'deepagents'):
            raise SystemExit('The live coach needs its packages: python -m pip install -r coach/requirements.txt '
                             '(or use: fallback / replay, which need no keys).')
        if not env_has_coach_key():
            raise SystemExit('The live coach needs GOOGLE_API_KEY or GEMINI_API_KEY in .env (see coach/README.md). '
                             'No key? Use: python -m tools.launch fallback')
        notes.append('Riff uses local browser speech when available, with captions otherwise; no voice API key is needed.')
    if a.source == 'hardware' and not can_import(python, 'sounddevice'):
        raise SystemExit('A real guitar needs sounddevice: python -m pip install -r engine/requirements.txt')
    return notes


# ---- commands ---------------------------------------------------------------------------------------------
def run(a) -> int:
    python = find_python(a.python)
    if python is None:
        print('No Python with the engine packages found. Run: python -m tools.launch setup', file=sys.stderr)
        return 1
    notes = preflight_notes(a, python)
    ports = free_ports()
    camera = a.camera
    wants_camera = a.vision in ('auto', 'on') and camera is None
    if wants_camera and ((ROOT / MODEL).is_file() or any((d / MODEL).is_file() for d in sibling_checkouts())):
        camera = 0 if a.dry_run else pick_camera(python)   # a dry run never opens the camera
    plan = build_plan(a, python, ports, camera)
    plan.notes[:0] = notes
    print(f'OmniRiff · {a.preset or "custom"}: source={plan.source} coach={plan.coach} hand-tracking={"on" if plan.vision else "off"}')
    print(f'python: {plan.python}')
    if plan.camera is not None:
        print(f'camera: index {plan.camera}')
    for n in plan.notes:
        print(n, file=sys.stderr if n.startswith('WARNING') else sys.stdout)
    if plan.coach == 'live':
        print('LIVE coach: uses Gemini API quota and can ask to change your rig (you approve). '
              'Use a free-tier project without billing to avoid provider charges; quota exhaustion stops requests.')
    if plan.coach == 'replay':
        print(f'REPLAY of {plan.replay_file.name}: a recorded session, not live.')
    print(f'dashboard: {plan.url}')
    print(' '.join(plan.engine_cmd))
    if a.dry_run:
        if plan.coach_cmd:
            print(' '.join(plan.coach_cmd))
        return 0
    (ROOT / 'runs').mkdir(exist_ok=True)
    child = subprocess.Popen(plan.coach_cmd, cwd=ROOT) if plan.coach_cmd else None
    if not a.no_open:
        threading.Timer(6.0, lambda: webbrowser.open(plan.url)).start()
    try:
        return subprocess.call(plan.engine_cmd, cwd=ROOT)
    except KeyboardInterrupt:
        return 0
    finally:
        if child is not None and child.poll() is None:
            child.terminate()


def check() -> int:
    print(f'OmniRiff check · {sys.platform} · launcher Python {sys.version.split()[0]}')
    try:
        head = subprocess.run(['git', 'log', '-1', '--format=%h %s'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(['git', 'branch', '--show-current'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        print(f'repo: {branch} @ {head}')
    except OSError:
        pass
    py = find_python()
    print(f'engine python: {py or "NOT FOUND (run: python -m tools.launch setup)"}')
    if py:
        for group, mods in (('engine', ('websockets', 'numpy', 'scipy', 'jsonschema')), ('audio', ('sounddevice',)),
                            ('vision', ('mediapipe', 'cv2')), ('coach', ('deepagents', 'langchain_google_genai'))):
            for m in mods:
                print(f'  {group:<7} {m:<20} {"ok" if can_import(py, m) else "missing"}')
        try:
            out = subprocess.run([py, '-c', 'import sounddevice as sd;print("; ".join(f"{i}:{d[\'name\']}" for i,d in '
                                 'enumerate(sd.query_devices())))'], capture_output=True, text=True, timeout=20).stdout.strip()
            print('audio devices:', out[:400] or 'none listed')
        except (OSError, subprocess.SubprocessError):
            pass
    model = (ROOT / MODEL).is_file() or any((d / MODEL).is_file() for d in sibling_checkouts())
    print(f'hand model: {"found" if model else "MISSING (see vision/README.md)"}')
    print(f'Gemini API key (GOOGLE_API_KEY or GEMINI_API_KEY): {"set" if env_has_coach_key() else "missing (live coach unavailable)"}')
    print('Riff voice: local browser speech when available, captions otherwise (no voice API key)')
    recs = sorted(p.name for p in REPLAYS.glob('*.jsonl')) if REPLAYS.is_dir() else []
    print(f'recorded sessions: {", ".join(recs) or "none"}')
    print(f'ports free from: {free_ports()[0]} (dashboard)')
    if py and model:
        cam = pick_camera(py)
        print(f'camera: {"index " + str(cam) if cam is not None else "none gave a picture (permission? black virtual camera?)"}')
    return 0


def setup() -> int:
    if IS_WIN:
        print('On Windows run: powershell -ExecutionPolicy Bypass -File .\\scripts\\windows\\setup.ps1 -Coach')
        return 0
    base = shutil.which('python3.12') or shutil.which('python3')
    if not base:
        print('Install Python 3.12 first (mediapipe has no wheels for newer versions).', file=sys.stderr)
        return 1
    venv = ROOT / '.venv'
    if not venv.exists():
        subprocess.check_call([base, '-m', 'venv', str(venv)])
    py = str(_venv_python(ROOT))
    subprocess.check_call([py, '-m', 'pip', 'install', '-r', 'engine/requirements.txt', '-r', 'vision/requirements.txt',
                           '-r', 'coach/requirements.txt'], cwd=ROOT)
    if not (ROOT / MODEL).is_file():
        import urllib.request
        (ROOT / MODEL).parent.mkdir(parents=True, exist_ok=True)
        print('downloading the hand model...')
        urllib.request.urlretrieve(MODEL_URL, ROOT / MODEL)
    print('Done. Put GOOGLE_API_KEY (or GEMINI_API_KEY) from a free-tier Gemini API project without billing '
          'in .env for the live coach, then: python -m tools.launch check. No separate voice key is needed.')
    return 0


def menu() -> int:
    names = list(PRESETS)
    print('OmniRiff: what do you want to run?\n')
    for i, n in enumerate(names, 1):
        print(f'  {i}. {n:<9} {BLURB[n]}')
    print(f'  {len(names) + 1}. check     what this machine has')
    print(f'  {len(names) + 2}. setup     install everything\n')
    try:
        pick = input('number or name: ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 0
    if pick.isdigit() and 1 <= int(pick) <= len(names) + 2:
        pick = (names + ['check', 'setup'])[int(pick) - 1]
    if pick == 'check':
        return check()
    if pick == 'setup':
        return setup()
    if pick in PRESETS:
        return main([pick])
    print('unknown choice', file=sys.stderr)
    return 2


def parse(argv) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog='python -m tools.launch', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('preset', nargs='?', choices=[*PRESETS, 'check', 'setup', 'menu'])
    p.add_argument('replay', nargs='?', help='with the replay preset: a recorded session file (default: the newest)')
    p.add_argument('--source', choices=['hardware', 'virtual', 'silent'])
    p.add_argument('--coach', choices=['live', 'scripted', 'replay', 'off'])
    p.add_argument('--vision', choices=['auto', 'on', 'off'])
    p.add_argument('--camera', type=int, help='camera index (default: the first that returns a real picture)')
    p.add_argument('--audio', help='raw engine audio arguments, e.g. "--in Focusrite --out Focusrite --input-channel 2"')
    p.add_argument('--serial', help='serial port of the pedal, e.g. COM3')
    p.add_argument('--python', help='Python to use (default: .venv, sibling checkouts, then PATH)')
    p.add_argument('--no-open', action='store_true', help="don't open the browser")
    p.add_argument('--dry-run', action='store_true', help='print what would run and stop')
    a = p.parse_args(argv)
    a.replay_arg = a.replay
    base = PRESETS.get(a.preset, dict(source='virtual', coach='live', vision='auto'))
    for k, v in base.items():
        if getattr(a, k) is None:
            setattr(a, k, v)
    if a.preset == 'replay' or a.coach == 'replay':
        a.coach = 'replay'
    a.replay = a.replay_arg if a.coach == 'replay' else None
    return a


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return menu() if sys.stdin.isatty() else (parse(['--help']) or 0)
    a = parse(argv)
    if a.preset == 'check':
        return check()
    if a.preset == 'setup':
        return setup()
    if a.preset == 'menu':
        return menu()
    a.preset = a.preset or None
    return run(a)


if __name__ == '__main__':
    raise SystemExit(main())
