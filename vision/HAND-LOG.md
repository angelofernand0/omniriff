# Both-hand logs and take-aligned Eyes reports (R17)

The control feed shows one selected hand. The coach needs the strumming hand,
which may be the other one. Opt into a separate metadata log for both detected
wrists; it does not change the control hand, clutch, engine, or dashboard feed.

```sh
mkdir -p runs
python -m vision --model models/hand_landmarker.task --relative \
  --hand-log runs/hands.jsonl --strum-hand Right
```

`--strum-hand` is a **MediaPipe handedness label**, not an inferred playing role.
Use `Left` if that is the label assigned to your strumming hand in this camera
orientation. Check the logged coordinates/labels while moving only that hand.
Mirroring and camera orientation can change the apparent assignment. We do not
identify which hand is strumming from speed, position, or which hand clutches.
The default is Right for compatibility with the agreed coach fixtures.

One newline-terminated JSON record per processed frame:

```json
{"timestamp_ms":1794680000000,"hands":[{"handedness":"Left","wrist":[0.3,0.6],"confidence":0.95},{"handedness":"Right","wrist":[0.7,0.5],"confidence":0.97}],"strum_hand":"Right"}
```

`hands: []` explicitly records no detected hand. Only normalized wrist x/y and
handedness confidence are saved: no camera images, full landmarks, or audio.
Handedness confidence is not a calibrated measure of wrist-position accuracy.
The timestamp is local Unix wall time when the frame is available for processing;
this aligns clocks with take sidecars, not camera exposure with audio samples.
Recorded-video input is replayed in current wall time, not its original capture
time. Label such runs as replay when presenting results.

The writer appends without truncation, flushes completed lines for a live coach,
and has a 256-entry queue and 64 MiB file bound. A full queue or disk error stops
logging with a warning; capture/control continue. An incomplete existing final
line is rejected so a new run cannot concatenate onto it. Choose a new path or
repair that file explicitly. Use one writer per file. Logs under `runs/` are
ignored by Git; keep personal recordings/metadata out of public commits.

## Exact take-window API

```python
from vision.eyes import report_for_window
report = report_for_window(
    "runs/hands.jsonl", sidecar["started_unix_ms"], sidecar["ended_unix_ms"],
    sidecar["take_id"], hand="strum",
)
```

The existing coach runner already calls this signature for non-fixture takes.
For a local diagnostic with no coach or paid model call:

```sh
python -m vision.hand_window runs/hands.jsonl takes/take-id.json --output hand-report.json
```

The report file must be new; omit `--output` to print JSON.

`hand="strum"` reads the explicit `strum_hand` label in the log (Right for older
fixture rows). `hand="Left"` or `"Right"` overrides it. The returned dictionary
keeps HandReport's existing fields and adds `take_id`, `started_unix_ms`,
`ended_unix_ms`, `available`, `selected_hand`, `coverage`, `observed_seconds`,
`tracking_gaps`, `rejected_rows`, and `selection_changed`. Each stall has integer
`start_ms`/`end_ms` relative to **the take start**, matching Ears' `at_ms` time base.

No data is interpolated across missing/low-confidence/ambiguous hands, intervals
longer than 150 ms, or wrist jumps greater than 0.3 normalized units. Those split
the analysis instead of producing false stationary spans. Duplicate/backward
rows are rejected. Multiple continuous segments do not produce a combined tempo
estimate. A report is available only with ≥50% analyzed time and at least one
continuous segment of five frames over 100 ms; this is a coverage heuristic,
not validated detector accuracy. A selection change within the take makes the
report unavailable. Incomplete reports retain diagnostics and an explicit warning.
Input windows are limited to one hour, 250000 wrist samples, and a 64 MiB log;
the reader snapshots file size so it cannot chase a live writer indefinitely.
`coverage` uses only analyzable continuous segments (at least five frames over
100 ms). `observed_seconds`/`observed_coverage` also include shorter visible spans;
those cannot make an otherwise incomplete take available. `analyzed_seconds`
provides the denominator used for coverage and continuity.

A still wrist can be an intentional rest. This API reports temporal evidence;
it does not diagnose why a musical hesitation occurred or assign guitar skill.
A synthetic before/clean/after fixture aligns three 400 ms audio pauses with three
roughly 366 ms measured wrist spans; the clean fixture has neither, and 120 ms
shortened delays stay below the wrist-stall threshold. **Real strumming-camera
and guitar/Scarlett checks remain manual.**

The browser play room currently does not write this log; use native `python -m
vision` for R17 capture. Browser logging needs a separate owner-coordinated follow-up.

For a portable, listenable comparison of Ears and Eyes reports, use the
[take evidence viewer](EVIDENCE.md). It checks take identity/start clocks and
shows incomplete coverage explicitly.
