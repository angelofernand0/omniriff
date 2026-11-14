# Take evidence replay

Inspect the coach's Ears and Eyes reports on the same take timeline, with optional
local WAV playback. The page shows when an audio finding and a stationary wrist
span occurred. Buttons replay from one second before each audio finding. No rig
commands, agent calls, uploads or external assets are involved.

Use completed reports from the coach workspace (`takes/<take_id>/take.json` and
`hand.json`), or produce them with the existing offline tools:

```sh
python -m tools.ears takes/take-id.wav > /tmp/ears.json
python -m vision.hand_window runs/hands.jsonl takes/take-id.json --output /tmp/hands.json
python -m vision.evidence --ears /tmp/ears.json --hands /tmp/hands.json \
  --audio takes/take-id.wav --label "Local guitar take; camera orientation checked" \
  --output /tmp/take-evidence
```

Open `/tmp/take-evidence/index.html`. To serve the chosen result folder locally:

```sh
python -m http.server 8090 --bind 127.0.0.1 --directory /tmp/take-evidence
```

The output is a portable folder: `index.html`, `evidence.json`, and `take.wav` if
`--audio` was supplied. Keep them together. Audio is optional; omit it for a
metadata-only report. The viewer only accepts matching nonempty take IDs,
identical Unix start timestamps, and durations within 100 ms. It checks finding
and wrist-span times, report-size bounds and PCM WAV duration/payload. Existing
output folders are preserved. HTML text is rendered safely from the reports.

**Labels are supplied by the operator, not verified by the viewer.** Mark
synthetic/replay runs explicitly, e.g. `--label "SYNTHETIC GUITAR + HAND FIXTURE"`.
The viewer cannot prove that a WAV belongs to a report; it checks the duration,
while the two reports must match each other by take and start clock. Choose the
correct original take file. The WAV is copied unchanged, including any metadata
it already contains; share the result only as deliberately as the source take.
No generated take/recording should be committed to the public repository.

Pink shaded spans show positive extra gap duration immediately before the
reported onset, and white markers show the onset. Early findings can have no
positive extra gap and are shown as markers. Purple spans are the selected
wrist's stationary observations. Incomplete hand coverage is prominently labeled;
its spans are dimmed. An unjudgeable audio report is also flagged. Missing hand
tracking is not drawn as stillness. On HTTP, the bounded local WAV is buffered
for reliable seeking on servers without byte-range support; file playback uses
the WAV directly.

A still wrist or longer audio interval may be an intentional rest. Alignment
supports review and comparison; it does not establish cause, guitar proficiency,
live-camera accuracy, or physical audio latency. Frame-availability timestamps
are not sample-accurate camera exposure times. Real guitar/Scarlett and moving-hand
validation remain separate manual checks.
