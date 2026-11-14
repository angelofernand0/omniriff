# tools/ears — strum timing from a take (coach Piece B)

```bash
python -m audio --input-wav guitar.wav --output-wav out.wav --loop-at 0.5,8 --take-dir takes   # or engine --take-dir
python -m tools.ears takes/take-<time>-<n>.wav            # prints a TakeReport (reads the .json sidecar next to it)
python -m tools.ears takes/take-….wav --output report.json
```

**TakeReport v1** (`source: "tools.ears"`), banded like `vision/eyes.py`'s HandReport:

| field | meaning |
|---|---|
| `take_id`, `started_unix_ms`, `samplerate`, `duration_s` | from the take and its sidecar (unix ms lines up with HandReport / session log) |
| `strum_count`, `onsets_ms` | detected strums, ms from take start (the first 20 ms are ignored: the take's seam fade-in) |
| `intervals_ms`, `median_interval_ms`, `strum_rate_per_min` | spacing between strums |
| `tempo_stability` | 1 − coefficient of variation of the steady intervals, 0..1 |
| `findings[]` | `{type: hesitation\|late\|early, at_ms, gap_ms, expected_ms, extra_ms, severity: minor\|moderate\|severe, message}`, compared with the local median interval; severity bands match Eyes (<250, 250–400, >400 ms) |
| `summary` | one plain sentence |

**Method:** 3 kHz high-pass (the pick attack), 5 ms log-energy frames, a ≥9 dB rise within 25 dB of the take's loud level that also beats the loudest frame 20–60 ms earlier (so steady overtone beating isn't a strum), attacks merged within 70 ms (one strum = one onset). See the docstring in `analyze.py`.

**Honest limits:** an intended rest looks like a hesitation; timing is ±15 ms; tuned and tested on the virtual guitar's string model (labeled synthetic), **not yet on real DI takes from the Scarlett**. Re-check there, and lower `highpass_hz` for dark pickups.
