# Demo runbook

This is the single sequence for bring-up (Saturday 8 PM onwards) and for every judge on Sunday. Every command below exists on `main` unless it's marked **(pending)**. Record results on issue #1. Deadlines and tracks are in [SUBMISSION.md](SUBMISSION.md), detailed manual checks in [tests/acceptance/MANUAL.md](../tests/acceptance/MANUAL.md), and the Windows install in [engine/README.md](../engine/README.md#windows-11-quickstart--scarlett-solo-3rd-gen).

## 0. Kit on the table
Windows 11 laptop + charger, power strip. Scarlett Solo (3rd gen) + USB cable. Guitar + instrument cable (+ spare). **Something judges can hear**: a powered speaker on the Solo line outs, or a headphone splitter. Webcam, positioned and lit. Arduino + Grove shield + buttons on USB. A second screen for the dashboard (optional).

## 1. Audio path (≈5 min)
Once per laptop: follow the [Windows quickstart](../engine/README.md#windows-11-quickstart--scarlett-solo-3rd-gen) with **Python 3.12** (what CI tests; MediaPipe may not ship wheels for newer Pythons), then `python -m pip install -r engine/requirements.txt -r vision/requirements.txt -r coach/requirements.txt` (the coach needs `ANTHROPIC_API_KEY` in a gitignored `.env`; see coach/README.md).

Windows helpers: [setup.ps1](../scripts/windows/setup.ps1) creates/checks the Python 3.12 venv, installs engine + vision requirements (add `-Coach` for the coach's) and prints preflight results. [start-demo.ps1](../scripts/windows/start-demo.ps1) launches the local dashboard and rig. Both use `.venv\Scripts\python.exe` directly and leave PowerShell execution policy unchanged. **Untested on Windows; PowerShell syntax/execution has not been verified here (`pwsh` unavailable).** Run from the clone in PowerShell:

Windows blocks `.ps1` files by default ("running scripts is disabled"), so start them with a **one-run bypass** that changes no system setting:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\setup.ps1 -Coach
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -SerialPort COM3 -Coach  # use the port --check printed; omit -SerialPort if no pedal, -Coach if the coach isn't set up
# add -StrumHand Left and/or -Camera 1 if that's what the camera rehearsal verified; with -Coach, vision and the coach share runs/hand-<time>.jsonl for Eyes
powershell -ExecutionPolicy Bypass -File .\scripts\windows\start-demo.ps1 -Headless         # alternative: silence processing, no Focusrite output
```

Run only one demo at a time. Download the hand model as described in §2 before the camera check; if it is missing, the launcher warns and starts without vision. `-Headless` skips the audio interface but still starts vision if the model is present and still opens any explicitly supplied serial port. Setup returns the preflight exit code: a device/port FAIL can mean dependencies installed successfully but the rig is not ready. Complete the live checks below before claiming hardware operation.

0. `python -m engine --check`. On the rig, fix every FAIL first (it also prints the Arduino's `--serial-port`). Off the rig, a missing Focusrite/serial FAIL is expected.
1. Solo: guitar in **input 2**, **INST on**, **Direct Monitor off**, speaker or headphone volume low.
2. `python -m audio --list-devices`. Find the Focusrite entries (WASAPI first).
3. `python -m audio --level-check --in Focusrite --hostapi WASAPI --input-channel 2`. Strum normally, then your hardest. Adjust the Solo gain until it says **good** with 0 clipped samples.
4. Latency (once per setup, loopback cable from Solo out → input 2, INST off):
   `python -m tools.latency --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --blocksize 128`
   Try `--blocksize 64` and `--exclusive`. Keep the lowest setting with 0 xruns. **Write down median ± spread**; these are the only latency numbers we quote.

   **Or all the Devpost numbers in two passes:** `powershell -ExecutionPolicy Bypass -File .\scripts\windows\measure.ps1 -Pass Loopback` (loopback cable: preflight, latency, CPU), then re-patch the guitar and run `... measure.ps1 -Pass Guitar` (5-minute soak while you play, then a 20 s take through Ears). Each run writes `runs/measure/<UTC stamp>/results.md` with paste-ready lines for DEVPOST.md; anything that didn't run says "not measured". Cross-platform: `python -m tools.measure --help`.

## 2. Full rig
Vision setup, once: download the MediaPipe Hand Landmarker model to `models/hand_landmarker.task` (link in [vision/README.md](../vision/README.md#setup); `models/` is git-ignored). Then calibrate at the table: `python -m vision --model models/hand_landmarker.task --calibrate` (see vision/README's demo-table section). It saves `vision-calibration.json`, which every later `python -m vision` run loads by default; don't pass a different `--calibration` name, because a missing file silently falls back to defaults. Add `--scene bloom` for Scene Morph or `--setlist vision/setlist-demo.json` for scene switching.

```bash
# one command (dashboard + vision + engine); use the COM port engine --check printed
python -m engine.demo --open --vision --vision-args "--model models/hand_landmarker.task" \
  --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
# or separately:
python -m engine --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
python -m dashboard            # → http://127.0.0.1:8080
python -m vision --model models/hand_landmarker.task   # gesture control + hand view (ws 47802)
```
Engine keys: `b` bypass, `l` loop, `f 0.3` filter, `r 0.3` reverb, `s` status, `q` quit. Check, in order:
- [ ] Dashboard shows ENGINE LIVE; press **D** to open the rig drawer and check the meters move when you play and xruns stay 0 (close it again before judges arrive)
- [ ] Pedal: each switch toggles exactly once
- [ ] Gesture: the clutch sweeps the filter, strumming doesn't; the hand module shows the skeleton and CAM PINCH in the header
- [ ] Unplug the pedal / close vision → audio keeps playing, dashboard shows it offline

## 3. The 2-minute demo (rehearse to time)
From [ROADMAP.md §7](ROADMAP.md). The coach is the centrepiece; pedal and pinch are how player and coach share the rig.

**How to say it** (identity-first talk track, openers by track, prepared answers, roles and the rehearsal plan): [PITCH.md](PITCH.md).

| Time | Beat |
|---|---|
| 0:00–0:15 | **Problem.** "Practising alone, you know you messed up but not why, and every tool makes you stop playing. Never put the guitar down." |
| 0:15–0:35 | **The rig.** The pedal starts a loop; the pinch sweeps the filter over it. Hands never leave the guitar. |
| 0:35–1:20 | **The teacher (the ah-ha).** Play the take with the stumble. Riff thinks (plan on screen; Ears and Eyes run), then: *"Your strumming hand stops at the change."* Riff flies to the loop, sets up the drill and waits. Tap the pedal. Play the drill. Before/after numbers appear. |
| 1:20–1:40 | **It remembers.** Show the journal entry and its "Last time…" opening line. |
| 1:40–2:00 | **Safe by design.** Unplug the camera: the music keeps playing; the AI never touches the sound until you hold the pedal (or press Y). One honest limitation. |

If the coach isn't working on the real rig by the midnight gate, fall back to the instrument story: dry guitar → pedal loop → pinch sweep → dashboard → reliability. Show the coach only on the simulator, **labeled**. Track-specific 20-second angles are in [DEVPOST.md](DEVPOST.md). Likely judge questions with honest answers are in [QA.md](QA.md).

Coach launch, once `coach/` is on main: add `--coach --hand-log runs/hand.jsonl` to the `engine.demo` command in §2 (the coach then watches the engine's takes in `runs/takes`).

## 4. If something fails at the table

Before each judge: run `python -m tools.tablecheck` (Windows: `.\scripts\windows\tablecheck.ps1`); resolve RED rows or explicitly omit unused vision/coach with `--no-vision` / `--no-coach` ([checks and limits](../tools/tablecheck/README.md)).

| Failure | Do this | Say this |
|---|---|---|
| Camera / vision | Keep playing; use the pedal and keyboard `f`/`r` | "The instrument never depends on the camera." |
| Pedal | Keyboard `l`/`b` or dashboard buttons | Same point, about the pedal |
| Dropouts or crackle | Restart the engine with `--blocksize 256` | — |
| Solo / guitar dead | `python -m engine --replay engine/demo-controls.jsonl` (labeled REPLAY on the dashboard), or `python -m tools.virtual_guitar --demo --play` (labeled synthesis) | **Always say it's a replay or simulation.** |
| Everything | Play the labeled backup video, recorded beforehand with `python -m tools.backup_video` (needs `pip install playwright imageio-ffmpeg`; see tools/backup_video/README.md; SIM GUITAR / REPLAY / NO HARDWARE stay on screen) | Same |

## 5. Before Devpost (by 7 AM Sunday)
- [ ] Measured latency + xruns recorded on issue #1 and in DEVPOST.md
- [ ] A track's requirement isn't working → remove that track (SUBMISSION.md rule)
- [ ] Video ≤ 2 min uploaded: record the real rig after 8 PM if it works; otherwise the labeled backup from `python -m tools.backup_video`
- [ ] All four Discord usernames on the submission
