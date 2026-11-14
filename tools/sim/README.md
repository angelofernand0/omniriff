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
