# Simulator

Owner: SM's Claude. Everything here is **simulated input**. It proves nothing about hardware, latency or gesture accuracy.

```bash
python -m tools.sim run              # real audio.Engine + engine.Runtime, synthetic guitar input, dashboard on :8080
python -m tools.sim run --demo       # plus scripted pedal presses (source "manual") and pinch sweeps (source "vision", 30 Hz, confidence 0.9)
python -m tools.sim run --silent     # silence instead of the synthetic guitar
```

```bash
python -m tools.sim send loop        # one action over UDP 47800
python -m tools.sim send filter 0.4 --source vision --confidence 0.9
```

- `hand.py`: simulated hand-view feed on ws 47802 (same port as vision/, so don't run both). `run --demo` drives it in step with the scripted pinch sweeps; `--hand-port 0` disables it. A synthetic 21-point hand, not a tracked one.
- `synth.py`: deterministic plucked partials in E minor pentatonic on an eighth-note grid. Bounded to ±0.98.
- `events.py`: builds envelopes, validates them against `protocol/control.schema.json` before sending, and sends them over UDP. `seq` starts at the wall clock in ms, so separate runs never send a duplicate.
- `demo.py`: a 16 s cycle: record 4 s, play, reverb sweep, filter sweep, clear.

The sim reuses `engine.runtime.Runtime` unchanged, so the dashboard sees exactly the real state format. Tests: `tests/test_sim.py`.

## Scripted coach session (no AI)

`python -m tools.sim run --demo --coach-sim` (or `python -m tools.sim coach` against any running engine, sim or real) serves the coach feed on `ws://127.0.0.1:47803` (`protocol/coach.schema.json`) with a **scripted** session. It reacts to real events (the loop pedal, `coach.approve`/`coach.reject` from the dashboard), but the diagnosis, numbers and drill are written in advance. Every frame has `scripted: true`, and the dashboard must label it. On approval it toggles bypass as `source: "coach"` and restores it after the drill take (`--udp-port 0` never touches the rig). Uses: building the dashboard before the coach brain exists, and a **labelled** fallback at the demo table.

**It starts in free play**, like the real coach: Riff is drowsy and silent, and recording or playing a loop does not make it speak. A long pedal press (the `Y` key here), or talking to it (hold `V`), wakes it and starts a practice round. `--coach-round` skips that and starts a round at once (for demos and `tools/layout_check.py`, which need the coach to run a session by itself).

## Manual test mode (`?manual=1`)

`--demo` presses the pedal and sweeps the pinch by itself, which makes it hard to tell what is a bug and what is the script. Add `&manual=1` to the dashboard URL (served by this simulator) and nothing runs by itself:

```
http://127.0.0.1:8080/?manual=1
```

- Stops the scripted demo (pedal presses, pinch sweeps, hand in and out) the moment the page loads.
- A thin **MANUAL TEST** strip appears in the page's bottom margin (it covers nothing): `AUTO` (turn the demo back on), `GUITAR` (mute the synthetic guitar), `HAND` (put a hand in frame), and a **PINCH** pad: pick FILTER or REVERB, press and drag; left is 0, right is 1, letting go lifts the pinch.
- Keys that already exist: `L` loop pedal, `B` FX, `Y` / `N` answer Riff, `V` hold to talk.
- For a completely quiet start, run the simulator without `--demo` (the flag still works the same).
- Needs the simulator's own web server. On any other server the strip says `NO SIM SERVER`.
- **No camera turns on in the simulator**: its hand is synthetic (the HAND button and PINCH pad). To use your real camera, run the simulator with `--hand-port 0` (so the port is free) and start `python -m vision --model /path/to/hand_landmarker.task` in another terminal (see `vision/README.md`; it needs MediaPipe and Google's hand-landmarker model, which is not in the repo). The strip then hides the simulated hand controls.

The flag talks to `/sim/state`, `/sim/auto`, `/sim/guitar`, `/sim/hand`, `/sim/pedal` (see `control.py`; tests in `tests/test_sim_control.py`). Simulated input only.
