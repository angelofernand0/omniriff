# Session evidence index

Turn a folder of completed audio takes into a local index of portable replay
pages. Each take uses the existing offline Ears and exact-window Eyes analyzers;
there are no agent calls, uploads, rig controls or changes to the recordings.

```sh
python -m vision.session_evidence takes/ --hand-log runs/hands.jsonl \
  --limit 20 --label "Local guitar session; camera labels checked" \
  --output /tmp/session-evidence
```

Open `/tmp/session-evidence/index.html`. Select a take to replay its audio
findings beside the wrist evidence. The cards show measured report summaries;
they do not infer improvement across different patterns or intentional rests.
Unjudgeable audio and incomplete wrist evidence remain explicit.

`--hand-log` is one both-hand session log spanning all selected take windows.
Omit it for audio-only pages with wrist evidence unavailable. A supplied missing
or oversized log fails preflight. `--metadata-only` omits copied WAVs. Use the
[R17 logging guide](HAND-LOG.md) and [single-take guide](EVIDENCE.md) for capture
and alignment details. Source labels are operator-supplied: mark generated or
replayed examples as synthetic/replay rather than presenting them as live data.

## Selection and bounds

The scan is nonrecursive. It selects the last N WAV filenames in lexical order
(default 20, configurable 1–100), then orders successful cards by validated Unix
take start. TakeWriter filenames contain time; arbitrary filenames may not be
chronological. The manifest records the selection rule and selected count.
Folders over 10000 entries or 1000 candidate WAVs are rejected before processing.
Choose a narrower session folder when needed.

Each WAV must have its matching version 1 `.json` sidecar and pass the single-take
PCM, payload, identity, clock and analysis bounds (60 seconds / 2,880,000 PCM
channel-samples). The total selected audio copy is limited to 512 MiB; lower the
limit or choose metadata-only if necessary. The optional wrist log is capped at
64 MiB. Processing is sequential and stays outside the live audio callback.

## Partial results are deliberate

A malformed or unfinished take, a duplicate take ID, or a rejected sidecar is
listed in `session.json` and the index. Valid pages remain available. The CLI
returns exit 2 when any file was rejected, even when some pages succeeded.
This is a diagnostic result, not a fully successful export.

The index/manifest are updated atomically after each take. Ctrl-C returns exit 130
and preserves completed pages with an **EXPORT INCOMPLETE** label. The currently
interrupted take may have a partial unlisted folder; it is not counted as a
completed page. Retry into a new output folder. Existing outputs and source
recordings are never replaced. One writer should own a given output folder.

Outputs are `index.html`, `session.json`, and numbered `take-NNN/` replay folders.
Keep the folders together. Original WAVs, including any existing metadata, are
copied unless metadata-only was selected; sharing the bundle shares those
recordings. No generated takes or wrist logs should be committed publicly.
Missing-file diagnostics use basenames rather than embedding the full local
path in the portable index.

The tests use synthetic guitar/wrist data through the production analyzers,
including three aligned take windows in one session log. This does not establish
real camera accuracy, musical causality, physical audio quality or Scarlett
latency. Those remain manual rig checks.
