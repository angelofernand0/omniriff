# Thirty-second native-camera rehearsal

Run this on the demo laptop before collecting the camera numbers for Devpost.
It adds a guided overlay to the existing **`python -m vision`** capture path;
it does not replace the engine, coach, audio test or manual bypass.

```sh
mkdir -p runs
python -m vision --model models/hand_landmarker.task --relative --strum-guard \
  --rehearsal --strum-hand Right --metrics-json runs/gesture-rehearsal.json
```

On the Windows demo laptop (PowerShell), use a single-line Python command:

```powershell
New-Item -ItemType Directory -Force runs | Out-Null
python -m vision --model models/hand_landmarker.task --relative --strum-guard --rehearsal --strum-hand Right --metrics-json runs/gesture-rehearsal.json
```

Use a new metrics filename each time. The command sends ordinary filter controls
to the local engine on UDP 47800; start the engine separately and set `--port` if
it uses another port. Add `--dry-run` to print controls instead of sending them;
the result clearly labels that choice. `--hand-log runs/hands.jsonl` can also
capture the wrist metadata for R17, without saving images or audio.

## Walk through the overlay

1. Light the hand from the front. Raise only the strumming hand so you can match
   the displayed **Left/Right** name to the intended hand. MediaPipe labels can
   change meaning with camera orientation/mirroring. The configured label is
   marked `[STRUM LABEL]`. Press **C** only when that label names the intended
   hand. A missing, low-confidence or ambiguous configured label cannot confirm.
   If it is wrong, quit and restart with `--strum-hand Left` (or Right).
2. Position the camera so the guitar/strumming area is below the horizontal
   **y=0.55** line. Put the strumming wrist below that line and check the guard
   indicator while strumming; confirm the physical framing with **Z**. The
   configured wrist must be seen below the line to accept Z. This is a human
   confirmation, not automatic recognition of a guitar or strumming.
3. After both confirmations, the **30-second measurement** starts. Move into
   the upper expression area, show an open hand, then pinch and drag. Move the
   filter at least five percentage points, release to hold, and re-pinch. Repeat
   deliberate movement through the interval. If motion history is suppressing
   control, pause briefly, open, and pinch again. At 100%, move down first.
4. The run exits automatically and writes JSON plus a short stderr summary.
   **Q** or Ctrl-C ends early and records an incomplete check. Keep the camera
   window focused so the keys reach it.

Rehearsal requires `--relative`, `--strum-guard`, `--metrics-json` and the overlay;
calibration, scenes, setlists and reverb-only mode are excluded to keep this one
filter check unambiguous. Use normal native calibration separately if needed.

## Read the result honestly

The top-level metrics retain the whole run, including setup. The nested
`rehearsal.metrics` measures the interval **after the human confirmations**, with
actual processed FPS, actual emitted control rate, mean and p95 processing time,
and frame counts. Rate denominators include interframe waits. Processing spans
frame availability to local send/print, excluding camera exposure and audio
latency. Percentiles use the bounded most recent 2048-frame window.

The rehearsal result passes only when all listed checks pass:

- Both human confirmations were made with the required visible wrist evidence.
- The full interval finished using a webcam-device input.
- The configured strumming hand was observed during measurement.
- The configured hand was visible in ≥80% of measured frames, with no
  frame-availability gap over 500 ms.
- At least two controls from that configured hand were emitted across ≥0.05
  normalized filter range. Other-hand output is counted separately and cannot
  satisfy this movement check.
- No frames expired, and no measured processing interval exceeded 250 ms.

These are rehearsal criteria, not validated accuracy or musical-quality scores.
The 80% visibility / 500 ms gap / 5-point movement thresholds are explicit
readiness criteria, not calibrated detector accuracy. Release/re-pinch steps are
instructions for the human to assess, not an automatically verified sequence.
If another hand owns the tracker, start with the intended control hand visible
and avoid crossing wrists; the report lists output counts by detected label.
The program cannot verify that the human matched the intended physical hand,
recognized the guitar framing correctly, or deliberately strummed. It does not
check UDP acknowledgments, actual audible output, pedal behavior or Scarlett
latency. A passing check covers only the listed conditions.

`--video` can exercise the same overlay/report, but is labeled `recorded-video`
and **never passes the live-input condition**. Automated tests use injected
capture/detector fixtures and a synthetic clock; they are not real-camera proof.
If no usable interval ran, rates/times say **not measured** rather than invented
zero-latency results.

The summary prints the exact invoked command. JSON preserves its argument list,
plus Python/OpenCV/MediaPipe versions and observed frame dimensions. Run from the
checkout root when reproducing relative paths.

For Devpost, paste the measured summary together with **input source**, **UDP or
dry-run**, the camera/computer used, and whether the manual checks passed. A
low whole-run event rate may simply reflect release/hold periods; it is actual
output, not a claimed maximum detector rate. Do not replace missing live-hand
results with a static-image/replay benchmark. Audio round-trip latency still
comes from the separate physical loopback measurement.
