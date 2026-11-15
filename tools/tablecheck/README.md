# Before each judge

With the rig already running, from the checkout root:

```sh
python -m tools.tablecheck
```

Windows PowerShell uses the installed project venv without activating it:

```powershell
.\scripts\windows\tablecheck.ps1
.\scripts\windows\tablecheck.ps1 --no-coach --hand-port 47812
```

The Windows helper forwards arguments to Python and returns its exit code.
PowerShell execution has not been verified here; use the documented Windows
setup/launch procedure in [DEMO.md](../../docs/DEMO.md).

Each required item prints one GREEN/RED line. Exit 0 means all required checks
are GREEN; exit 1 means at least one RED; invalid flags exit 2. Network probes
run concurrently with a default 1.5-second deadline per check (configurable
`--timeout 0.1..3`). Connect, receive and close are bounded; local blocking
probes run in daemon workers so a stalled path cannot hold the CLI open.
Normal local runs finish under five seconds, including when all feeds are silent.

| Item | What it checks |
|---|---|
| Engine | Schema-valid state on WS 47801, timestamp within 1 second (up to 1 second future-clock tolerance); reports cumulative xruns/clipped samples, latest input peak, loop and adapter statuses. Nonzero xruns or starting/retrying/error/stopped adapters are RED; UDP/WebSocket must be running; a disabled serial adapter is allowed. |
| Dashboard | HTTP 8080 serves OmniRiff HTML; follows at most one redirect within the same loopback endpoint (including the simulator's source-label redirect). |
| Hand | WS 47802 sends a schema-valid frame within the deadline, timestamp within 500 ms. A fresh `present:false` is GREEN and says “no hand seen”; a connected but silent socket is RED. |
| Coach | WS 47803 supplies a schema-valid `coach.frame`. Reports SCRIPTED vs LIVE feed and the cached snapshot's age/state. An explicit “out of credit” cue is RED. Cached idle frames may be old; no model is called and no API balance is queried. |
| Takes | `runs/takes` exists and allows a unique empty temporary file to be created/closed/deleted. No existing take is opened or changed, and no directory is created. |
| Model | `models/hand_landmarker.task` is a nonempty readable regular file. The model is not loaded. |

Overrides: `--engine-port`, `--dashboard-port`, `--hand-port`, `--coach-port`,
`--take-dir`, `--model`, `--timeout`. All network targets stay at `127.0.0.1`;
WebSocket clients use origin `http://127.0.0.1:8080` even with port overrides.
`--no-vision` skips both hand and model checks. `--no-coach` skips the coach.
Skipped components say SKIPPED and do not affect the exit code.

The instrument is read-only: no control, approval or speech messages, no loop
clear, no audio stream, no camera access, no model calls. The one local write
exception is the automatic take-directory permission probe described above.
For unavailable take folders, create the intended local folder before checking.
A filesystem operation already in progress may finish cleanup after a timeout.

GREEN verifies the listed connections/reports/paths, not audible guitar output,
a working pedal, camera accuracy or useful AI coaching. A LIVE feed is not proof
of a successful model call. SCRIPTED can be GREEN as a connection check and is
always named explicitly. Input peak is a single snapshot; silence is valid
before playing. Xruns are cumulative, never reset by this command, and do not
measure hardware latency. Inspect a RED xrun total before deciding whether to
restart/rehearse. Finish the manual stage reset and audible checks separately.

Tests use ephemeral local fake servers and temporary files:

```sh
python -m unittest discover -s tests -p test_tablecheck.py -v
```
