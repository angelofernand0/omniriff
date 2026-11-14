# Manual play test (Windows 11 laptop + Scarlett Solo)

Run this before the demo and after any change to audio/ or engine/. Write down the results (date, settings, pass/fail, numbers) on issue #1.

## Setup
- [ ] Focusrite driver installed. Solo connected by USB.
- [ ] Guitar in **input 2**, INST on, gain set so hard strums light the halo green/amber but never red.
- [ ] **Direct Monitor off.** Headphones or speaker on the Solo outputs, volume low to start.

## Latency (record the numbers)
- [ ] Loopback cable from the Solo's output → input 2, INST off. Run `python -m tools.latency --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2` at block sizes 128 and 64, with and without `--exclusive`.
- [ ] Record median ± spread and detected/total for each. Pick the lowest setting with 0 xruns.

## Sustained play (pick the settings from above)
- [ ] `python -m audio --in Focusrite --out Focusrite --hostapi WASAPI --input-channel 2 --status-every 2`
- [ ] Play continuously for **5 minutes**. Pass: `xruns` stays 0 (or doesn't grow), no crackles, no hangs, output never pinned at the ceiling.
- [ ] `f 0` → `f 1` sweeps smoothly with no zipper noise. `r 0.4` adds a tail; `r 0` removes it without a click.
- [ ] `l` records, `l` plays, `l` clears, 5 times in a row; the loop seam has no click.
- [ ] `b` bypass on and off during a loud chord: no click.

## Controls and disconnects (once engine/, vision/ and the pedal are in)
- [ ] Pedal: each press toggles exactly once. Hold through an Arduino reset: no extra toggle.
- [ ] Gesture: the clutch gesture sweeps the filter; strumming and fretting without the clutch don't.
- [ ] Move out of frame: the filter holds and doesn't sweep.
- [ ] Unplug the Arduino, close vision and close the dashboard, one at a time: audio keeps playing every time and keyboard bypass still works.
- [ ] Plug them back in: each reconnects without restarting the engine.

## Live hand view on dashboard
- [ ] Start engine and serve dashboard (`http://localhost:8080`).
- [ ] Start vision (`ws://127.0.0.1:47802`). The dashboard HAND panel lights up.
- [ ] No hand in frame: panel reads `NO HAND`.
- [ ] Hand in frame, open palm: panel displays mirrored skeleton and reads `SEEN` (never `armed`).
- [ ] Pinch thumb and index: panel turns pink, boxes the pinch and shows the control and value (e.g. `FILTER 60%`, or `MORPH 65%` in Scene Morph).
- [ ] Stop vision: panel ages out within 500 ms and displays `NO CAMERA`. The status pill still shows `LIVE` (rig drawer `D`: ENGINE LIVE); audio is unaffected.

## Scene Morph & Tone Match auditions
- [ ] Start vision with `--scene bloom` (Clear to Cosmos).
- [ ] Pinch at bottom: audio is bright and dry (filter 1.0, reverb 0.0).
- [ ] Sweep upward: continuous, smooth transition into ambient wash (filter 0.40, reverb 0.75).
- [ ] Open hand mid-sweep: parameters hold steady without jumping or audio artifacts.
- [ ] Re-pinch: requires open hand first (open-then-pinch clutching).
- [ ] Repeat with `--scene rise` (Underwater to Spotlight) and confirm inverted dark-to-bright trajectory.

## Performance setlists
- [ ] Start vision with `--setlist vision/setlist-demo.json`. Camera overlay displays `SCENE 1/3`.
- [ ] With camera window focused, press `2` (or `n` for next): scene switches immediately without restarting camera capture.
- [ ] Verify sound holds previous scene parameters; new scene does not emit until hand opens and pinches again.
- [ ] Press `p`: wraps backward to previous scene. Sequence numbers in emitted packets stay strictly increasing.

## StrumGuard & Performance Zones
- [ ] Start vision with `--strum-guard` (or `python -m vision.spatial --strum-guard`).
- [ ] Hold guitar pick (pinched thumb and index) inside the lower guitar zone and strum:
  - Overlay shows `STRUM GUARD: MUTED`.
  - Zero filter/reverb parameter events emitted over UDP.
- [ ] Move hand above strings into upper air expression zone: overlay clears to LIVE; pinch engages filter sweep.
- [ ] Rapid strumming in air (> 2.5 m/s or rapid direction reversals): motion detector suppresses false clutch triggers.

## DualAxis 3D Control
- [ ] Run `python -m vision.spatial --dual-axis`.
- [ ] Open hand, then pinch:
  - Vertical elevation ($Y$-axis) sweeps primary filter cutoff.
  - Knuckle roll tilt (twisting wrist $0^\circ \rightarrow 60^\circ$) smoothly injects secondary reverb depth.
- [ ] Confirm single-hand 2D acoustic control without audible clicks or dropped frames.

## Replay Banner & Scripted Control Mode
- [ ] Launch engine with recorded take: `python -m engine --headless --replay engine/demo-controls.jsonl`.
- [ ] Dashboard displays visible `REPLAY` banner.
- [ ] Terminal logs report: `REPLAY CONTROL MODE: scripted controls, not live camera/pedal input`.
- [ ] When replay script concludes: `REPLAY` indicator persists in telemetry and engine holds last state safely.
