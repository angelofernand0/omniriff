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

- `synth.py`: deterministic plucked partials in E minor pentatonic on an eighth-note grid. Bounded to ±0.98.
- `events.py`: builds envelopes, validates them against `protocol/control.schema.json` before sending, and sends them over UDP. `seq` starts at the wall clock in ms, so separate runs never send a duplicate.
- `demo.py`: a 16 s cycle: record 4 s, play, reverb sweep, filter sweep, clear.

The sim reuses `engine.runtime.Runtime` unchanged, so the dashboard sees exactly the real state format. Tests: `tests/test_sim.py`.
