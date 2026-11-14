# Demo runbook

This is the single sequence for bring-up (Saturday 8 PM onwards) and for every judge on Sunday. Every command below exists on `main` unless it's marked **(pending)**. Record results on issue #1. Deadlines and tracks are in [SUBMISSION.md](SUBMISSION.md), detailed manual checks in [tests/acceptance/MANUAL.md](../tests/acceptance/MANUAL.md), and the Windows install in [engine/README.md](../engine/README.md#windows-11-quickstart--scarlett-solo-3rd-gen).

## 0. Kit on the table
Windows 11 laptop + charger, power strip. Scarlett Solo (3rd gen) + USB cable. Guitar + instrument cable (+ spare). **Something judges can hear**: a powered speaker on the Solo line outs, or a headphone splitter. Webcam, positioned and lit. Arduino + Grove shield + buttons on USB. A second screen for the dashboard (optional).

## 1. Audio path (≈5 min)
Once per laptop: follow the [Windows quickstart](../engine/README.md#windows-11-quickstart--scarlett-solo-3rd-gen) with **Python 3.12** (what CI tests; MediaPipe may not ship wheels for newer Pythons), then `python -m pip install -r engine/requirements.txt -r vision/requirements.txt`.
0. `python -m engine --check`. Fix every FAIL first (it also prints the Arduino's `--serial-port`).
1. Solo: guitar in **input 2**, **INST on**, **Direct Monitor off**, speaker or headphone volume low.
2. `python -m audio --list-devices`. Find the Focusrite entries (WASAPI first).
3. `python -m audio --level-check --in Focusrite --hostapi WASAPI --input-channel 2`. Strum normally, then your hardest. Adjust the Solo gain until it says **good** with 0 clipped samples.
4. Latency (once per setup, loopback cable from Solo out → input 2, INST off):
   `python -m tools.latency --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --blocksize 128`
   Try `--blocksize 64` and `--exclusive`. Keep the lowest setting with 0 xruns. **Write down median ± spread**; these are the only latency numbers we quote.

## 2. Full rig
Vision setup, once: download the MediaPipe Hand Landmarker model to `models/hand_landmarker.task` (link in [vision/README.md](../vision/README.md#setup); `models/` is git-ignored). Then calibrate at the table: `python -m vision --model models/hand_landmarker.task --calibrate` (see vision/README's demo-table section). Add `--scene bloom` for Scene Morph or `--setlist vision/setlist-demo.json` for scene switching.

```bash
# one command (dashboard + vision + engine); use the COM port engine --check printed
python -m engine.demo --open --vision --vision-args "--model models/hand_landmarker.task --calibration calibration.json" \
  --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
# or separately:
python -m engine --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --serial-port COM3
python -m dashboard            # → http://127.0.0.1:8080
python -m vision --model models/hand_landmarker.task --calibration calibration.json   # gesture control + hand view (ws 47802)
```
Engine keys: `b` bypass, `l` loop, `f 0.3` filter, `r 0.3` reverb, `s` status, `q` quit. Check, in order:
- [ ] Dashboard header shows ENGINE LIVE, meters move when you play, 0 xruns
- [ ] Pedal: each switch toggles exactly once
- [ ] Gesture: the clutch sweeps the filter, strumming doesn't; the hand module shows the skeleton and CAM PINCH in the header
- [ ] Unplug the pedal / close vision → audio keeps playing, dashboard shows it offline

## 3. The 2-minute demo (rehearse to time)
| Time | Beat |
|---|---|
| 0:00–0:15 | **"Never put the guitar down."** Guitarists' hands are busy; knobs and pedalboards make you stop, look down or bend over. That's harder still with limited mobility. |
| 0:15–0:40 | **Dry guitar**, then a pedal press to start a loop. Play over it. |
| 0:40–1:10 | **Gesture**: pinch and raise the hand, and the filter sweeps over the loop. Second control on reverb (or Scene Morph). Point at the HAND panel. |
| 1:10–1:25 | **Dashboard**: what the rig hears and sees. Mention the coach if it's built: it listens between takes and sets the next drill. |
| 1:25–1:50 | **Why it's reliable**: audio never waits on the camera or AI, unsafe or stale controls are dropped, and manual bypass always works. Quote the measured latency. |
| 1:50–2:00 | One honest limitation + what's next. |

Keep the two-minute story to **one gesture (pinch) + one pedal + the coach**. Scene Morph, setlists, DualAxis, the gesture looper and Tone Match are for Q&A or track-specific visits. Track-specific 20-second angles are in [DEVPOST.md](DEVPOST.md). Likely judge questions with honest answers are in [QA.md](QA.md).

## 4. If something fails at the table
| Failure | Do this | Say this |
|---|---|---|
| Camera / vision | Keep playing; use the pedal and keyboard `f`/`r` | "The instrument never depends on the camera." |
| Pedal | Keyboard `l`/`b` or dashboard buttons | Same point, about the pedal |
| Dropouts or crackle | Restart the engine with `--blocksize 256` | — |
| Solo / guitar dead | `python -m engine --replay engine/demo-controls.jsonl` (labeled REPLAY on the dashboard), or `python -m tools.virtual_guitar --demo --play` (labeled synthesis) | **Always say it's a replay or simulation.** |
| Everything | Play the labeled backup video **(pending B16)** | Same |

## 5. Before Devpost (by 7 AM Sunday)
- [ ] Measured latency + xruns recorded on issue #1 and in DEVPOST.md
- [ ] A track's requirement isn't working → remove that track (SUBMISSION.md rule)
- [ ] Video ≤ 2 min uploaded (real hardware preferred; label any simulation)
- [ ] All four Discord usernames on the submission
