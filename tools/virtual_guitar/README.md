# Virtual guitar test rig

This tool makes the real OmniRiff DSP audible and measurable without a guitar
or input interface. It is explicitly a **simulation**, not hardware validation.

```bash
python -m pip install -r tools/virtual_guitar/requirements.txt
python -m tools.virtual_guitar --demo --output outputs/virtual-guitar.wav
```

The default input is deterministic plucked synthesis. The command runs it
through `audio.Engine`, applies the same validated control replay used by the
backup demo, writes a processed stereo WAV, and prints a JSON report with
levels, spectral brightness, limiter/clipping counters, control counts and
render speed. Listen with any player, or add `--play` to use the laptop's
speakers/headphones after rendering.

For more realistic tuning, provide a clean guitar/DI PCM WAV:

```bash
python -m tools.virtual_guitar \
  --input-wav clean-guitar-di.wav \
  --demo \
  --output outputs/di-demo.wav \
  --report outputs/di-demo.json \
  --play
```

Use a constant setting for quick A/B renders:

```bash
python -m tools.virtual_guitar --seconds 6 --filter 1.0 --reverb 0.0 --output outputs/open-dry.wav
python -m tools.virtual_guitar --seconds 6 --filter 0.2 --reverb 0.6 --output outputs/dark-space.wav
```

`--controls PATH` accepts the replay JSONL format documented in
`engine/README.md`; timestamps become offsets from the start. This lets a
captured/synthetic gesture script drive the same audio engine reproducibly.

What this can validate:

- filter, reverb, loop, bypass, limiter and control timing through the real DSP;
- finite/bounded output, event acceptance and reproducible audio comparisons;
- future agent control plans without needing a live instrument.

What still requires hardware:

- Scarlett/driver behavior, guitar and interface gain staging, measured
  round-trip latency/xruns, feedback/noise, pedal wiring and final play feel.
