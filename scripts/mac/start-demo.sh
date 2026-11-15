#!/usr/bin/env bash
# macOS demo launcher: real engine + real camera hand tracking (+ optional coach) + dashboard.
# Run from Terminal.app (macOS only grants the camera to apps launched from Terminal):
#   bash scripts/mac/start-demo.sh                 # silence in, hand tracking, no coach
#   bash scripts/mac/start-demo.sh --coach         # also start the practice coach (needs ANTHROPIC_API_KEY in .env)
#   bash scripts/mac/start-demo.sh --camera 1      # force a camera index (default: first one that is not black)
#   bash scripts/mac/start-demo.sh --audio "--in Focusrite --out Focusrite --input-channel 2"
#   bash scripts/mac/start-demo.sh --virtual-guitar --coach   # SIMULATED looping guitar (audible) through the real engine
#   bash scripts/mac/start-demo.sh --no-vision --dry-run
# Untested on hardware beyond SM's MacBook. It does not use tools.sim, so nothing is scripted.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1

COACH=0; VISION=1; CAMERA=""; AUDIO=""; DRY=0; PYBIN="${OMNIRIFF_PYTHON:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --coach) COACH=1 ;;
    --no-vision) VISION=0 ;;
    --virtual-guitar) AUDIO="--virtual-guitar" ;;
    --camera) CAMERA="${2:?--camera needs an index}"; shift ;;
    --audio) AUDIO="${2:?--audio needs a quoted argument string}"; shift ;;
    --python) PYBIN="${2:?--python needs a path}"; shift ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

# 1. Python with the project's packages (3.12 is what CI tests; mediapipe may lack wheels for newer).
# Other checkouts of this repo (main clone, other worktrees, Codex worktrees) often hold the venv + model already.
MAIN="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)/.." 2>/dev/null && pwd)"
SIBLINGS=()
for d in "$MAIN" "$MAIN"/.claude/worktrees/* "$HOME"/.codex/worktrees/*/omniriff; do
  [ -d "$d" ] && [ "$d" != "$ROOT" ] && SIBLINGS+=("$d")
done
if [ -z "$PYBIN" ]; then
  CANDS=("$ROOT/.venv/bin/python")
  for d in "${SIBLINGS[@]}"; do CANDS+=("$d/.venv/bin/python"); done
  CANDS+=(python3.12 python3)
  for c in "${CANDS[@]}"; do
    p="$(command -v "$c" 2>/dev/null || true)"
    [ -n "$p" ] && "$p" -c 'import websockets, anthropic' 2>/dev/null && PYBIN="$p" && break
  done
fi
[ -n "$PYBIN" ] || { echo "No Python with the engine requirements found. Run: python3.12 -m venv .venv && .venv/bin/python -m pip install -r engine/requirements.txt -r vision/requirements.txt -r coach/requirements.txt  (or pass --python PATH)" >&2; exit 1; }
echo "python: $PYBIN"

# 2. Hand model.
MODEL="models/hand_landmarker.task"
if [ ! -f "$MODEL" ]; then
  for d in "${SIBLINGS[@]}"; do
    if [ -f "$d/$MODEL" ]; then mkdir -p models && cp "$d/$MODEL" "$MODEL" && echo "hand model: copied from $d"; break; fi
  done
fi
if [ "$VISION" = 1 ] && [ ! -f "$MODEL" ]; then
  echo "WARNING: $MODEL missing, starting without vision. Download it (see vision/README.md#setup)." >&2
  VISION=0
fi
if [ "$VISION" = 1 ] && ! "$PYBIN" -c 'import mediapipe, cv2' 2>/dev/null; then
  echo "WARNING: mediapipe/opencv not installed for this Python, starting without vision." >&2
  VISION=0
fi

# 3. Camera: first index that returns real (non-black) frames. Some Macs' index 0 is a black virtual camera.
if [ "$VISION" = 1 ] && [ -z "$CAMERA" ]; then
  CAMERA="$("$PYBIN" - 2>/dev/null <<'PY'
import cv2, time
for i in range(4):
    cap = cv2.VideoCapture(i)
    if not cap.isOpened():
        continue
    best, t0 = 0.0, time.time()
    while time.time() - t0 < 2.5:
        ok, f = cap.read()
        if ok:
            best = max(best, float(f.mean()))
    cap.release()
    if best > 5:
        print(i); break
PY
)"
  if [ -z "$CAMERA" ]; then
    echo "WARNING: no camera gave a non-black picture (camera permission for Terminal? System Settings > Privacy & Security > Camera). Starting without vision." >&2
    VISION=0
  else
    echo "camera: index $CAMERA"
  fi
fi

# 4. Ports: the defaults if free; otherwise shift the whole set so old simulators don't collide.
read -r HTTP UDP WS HAND COACHP < <("$PYBIN" - <<'PY'
import socket
def free(p):
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
    ports = [8080 + off // 10, 47800 + off, 47801 + off, 47802 + off, 47803 + off]
    if all(free(p) for p in ports):
        print(*ports); break
PY
)
[ -n "${HTTP:-}" ] || { echo "No free port set found." >&2; exit 1; }
echo "ports: dashboard $HTTP, control udp $UDP, state ws $WS, hand ws $HAND, coach ws $COACHP"

# 5. Build the command.
CMD=("$PYBIN" -m engine.demo --http-port "$HTTP" --udp-port "$UDP" --ws-port "$WS")
if [ -n "$AUDIO" ]; then read -r -a AUDIO_ARR <<<"$AUDIO"; CMD+=("${AUDIO_ARR[@]}"); else CMD+=(--headless); fi
[ "$VISION" = 1 ] && CMD+=(--vision --vision-args "--model $MODEL --camera $CAMERA --port $UDP --hand-view-port $HAND")
if [ "$COACH" = 1 ]; then
  if [ ! -f .env ] && [ ! -f "$HOME/.config/omniriff/.env" ]; then
    echo "WARNING: no .env with ANTHROPIC_API_KEY found; the coach will not start. See coach/README.md." >&2
  fi
  CMD+=(--coach --coach-args "--state-port $WS --control-port $UDP --feed-port $COACHP")
fi

URL="http://127.0.0.1:$HTTP/?ws=ws://127.0.0.1:$WS&hand=ws://127.0.0.1:$HAND&coachws=ws://127.0.0.1:$COACHP"
echo "dashboard: $URL"
[ "$AUDIO" = "" ] && echo "HEADLESS: processing silence (no guitar audio). Use --virtual-guitar for a simulated guitar, or --audio for an interface."
echo "${CMD[*]}"
[ "$DRY" = 1 ] && exit 0
(sleep 6; open "$URL") &
exec "${CMD[@]}"
