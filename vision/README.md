# Gesture control

Uses Google's pretrained MediaPipe Hand Landmarker (Tasks API), not a custom trained model. Pinch thumb and index finger after opening the hand to engage; move the wrist upward to increase filter. Opening the hand disengages. Loss of hand or low confidence requires opening again before re-engagement. The control mapping is manual.

## Setup

From the repository root, using Python supported by MediaPipe:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r vision/requirements.txt
```

Download the Hand Landmarker task model from Google's official guide:
https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python
Keep the model outside tracked source (e.g. `models/hand_landmarker.task`); supply its path explicitly.

```bash
python -m vision --model /path/to/hand_landmarker.task --calibrate
python -m vision --model /path/to/hand_landmarker.task
python -m vision --model /path/to/hand_landmarker.task --video recordings/hand.mp4 --dry-run
```

On Windows activate `.venv\Scripts\Activate.ps1` instead. Calibration: put the wrist at the bottom of its comfortable range and press `l`, then at the top and press `h`, then `s` to save. No events are transmitted during calibration. Default range is normalized image y=0.8 to y=0.2. Keep the calibration JSON local. `q` exits. `--no-overlay` supports headless recorded-video runs; video playback is paced using its reported FPS. `--control reverb` selects the alternate parameter, rather than transmitting both at once.

Use `--relative` to avoid a position jump when pinching: the filter picks up from its open default (or last sent value after a prior clutch), and reverb picks up from zero. Move your wrist from the pinch position to change the value. This is optional; absolute calibrated mapping remains the default.

Default output: v1 JSON UDP datagrams to 127.0.0.1:47800, at most 20 events/s. Each is validated with the repository schema. Deadband suppresses small changes; an exponential filter smooths wrist movement. Pinch hysteresis uses thumb/index distance divided by palm width, with engage at 0.25 and release at 0.45. The model gates detection, presence and tracking at 0.6. Tasks returns handedness classification confidence, not a landmark confidence score: the event confidence is this score, additionally gated at 0.6, and must not be interpreted as measured gesture accuracy.

The landmarker detects up to two hands. The selector follows the nearest wrist from frame to frame, so a changed detection order does not switch control to the other hand. A wrist jump above `--max-hand-jump` (default 0.30 normalized image distance) fails closed. After 15 missed frames, the old track is discarded; the controller still requires an open-hand clutch before sending again. Keep the intended control hand in view, and avoid crossing hands; two wrists that cross can still be ambiguous.

Exit metrics on stderr report actual elapsed runtime, emitted event count, average rate and minimum emission interval. `--dry-run` validates and prints JSON without UDP. No-hand frames emit nothing. Failure closes capture and socket; audio must retain its independent manual bypass. No camera frames or recordings are saved by this program.

## Demo-table calibration and setup

### 60-second rehearsal & calibration routine
Run through this quick 4-step sequence before each judge approaches:
1. **Frame check (15s)**: Sit with guitar. Check webcam angle: ensure your control hand has an unobstructed path from picking/belt height up to mid-chest. Verify no harsh backlight silhouettes the hand.
2. **Launch (10s)**: Start the demo vision process:
   ```bash
   python -m vision --model models/hand_landmarker.task --scene bloom
   ```
3. **Range tap (15s)**: If the player's natural height range is taller/shorter than the default $y \in [0.8, 0.2]$ normalized window, run with `--calibrate`: wrist at lowest rest position $\rightarrow$ press `l`, wrist at highest comfortable sweep $\rightarrow$ press `h`, press `s` to save `calibration.json`.
4. **Physical dry check (20s)**: Open hand (disarmed), pinch index+thumb (HUD turns green, engaged), sweep upward (filter opens, reverb blooms), open hand (disengages, scene holds). Strum a chord to verify StrumGuard suppresses accidental sweeps. You are ready to demo!

### Camera placement and lighting
- **Distance**: Place the webcam 2–3 feet (0.6–1.0 m) from the player, facing them directly.
- **Angle & height**: Position at laptop screen height tilted slightly upward (~10–15°), or on a small stand at chest height. Ensure the player's upper torso and free control hand are fully framed with ~1.5 ft of clear vertical travel.
- **Lighting**: Diffuse front or overhead room lighting is ideal. **Avoid strong backlighting** (such as bright windows, stage spots, or projector beams behind the player) which silhouetted hands drop MediaPipe landmark confidence below the 0.6 gate.
- **Framing hygiene**: Keep the control hand within the camera's central field of view. Avoid crossing the control hand over the fretting hand to ensure the nearest-wrist tracker remains locked onto the intended hand.

### The one command to run at the demo table
For the live 2-minute demonstration with Scene Morph (Clear to Cosmos blend) and live dashboard skeleton integration:

```bash
python -m vision --model models/hand_landmarker.task --scene bloom
```

This single command:
1. Opens the webcam and loads Google's pretrained MediaPipe Hand Landmarker.
2. Arms the open-then-pinch clutch for dual-parameter Scene Morphing (**Clear to Cosmos**: filter 1.0/reverb 0.0 → filter 0.4/reverb 0.75).
3. Publishes 21-point normalized landmark coordinates to `ws://127.0.0.1:47802` for the dashboard live HAND skeleton panel.
4. Sends schema-validated v1 JSON UDP datagrams to the engine on `127.0.0.1:47800` strictly bounded to $\le 20$ events/s.

*(Optional 10-second calibration)*: If the player's physical range differs from default $y \in [0.8, 0.2]$, run:
```bash
python -m vision --model models/hand_landmarker.task --calibrate
# Put wrist at lowest comfortable position -> press 'l'
# Put wrist at highest comfortable position -> press 'h'
# Press 's' to save local calibration.json, 'q' to quit
# Then launch: python -m vision --model models/hand_landmarker.task --scene bloom --calibration calibration.json
```

## Morning hardware checklist
Confirm each item in order before the judging window:
- [ ] **Model file present**: `models/hand_landmarker.task` exists locally and is readable.
- [ ] **Camera detection & dry-run**: `python -m vision --model models/hand_landmarker.task --dry-run` starts clean at $\ge 20$ FPS without OS permission errors or frame drops.
- [ ] **Clutch gating**:
  - Open hand in frame: HUD displays hand detected, clutch disarmed (no UDP events).
  - Pinch thumb + index: HUD displays engaged, wrist elevation smoothly sweeps parameter.
  - Release pinch / open hand: HUD returns to disengaged, last value holds rock steady.
  - Move hand out of frame: HUD clears gracefully, zero events transmitted.
- [ ] **Dashboard hand view**: Open `http://127.0.0.1:8080`. Verify the **HAND** panel renders 21 skeleton joints in real-time, highlights engagement on pinch, and clears to stale/neutral when hand leaves frame.
- [ ] **Audible sweep test**: With guitar playing through Solo, verify pinching and raising the hand produces an audible, click-free filter/reverb sweep without audio clicks or dropouts.
- [ ] **Subsystem isolation**: Kill vision (`Ctrl-C`) mid-riff; verify audio playback continues uninterrupted and dashboard marks vision offline.

## Validation status

Unit tests cover activation, loss/rearm, confidence rejection, rate limiting, deadband, smoothing and invalid calibration. Run `python -m unittest discover -s tests -p test_vision.py -v`.

Unit coverage includes reordered two-hand detections, implausible wrist jumps, track expiry, and clutch re-arm. Live webcam and audible integration still require validation on the target camera and audio hardware. Do not treat synthetic unit tests as a hardware acceptance check.

## Scene Morph: one gesture, two effects

`--scene bloom` turns wrist height into a continuous blend from **Clear to Cosmos**: bright/dry to darker/ambient. `--scene rise` blends **Underwater to Spotlight**: dark/wet to bright/drier. Open, pinch, then sweep upward; opening the hand holds the current scene. Hand loss emits no events. The same camera calibration applies. Single-effect and relative modes remain available separately.

```bash
python -m vision --model /path/to/hand_landmarker.task --scene bloom
python -m vision --model /path/to/hand_landmarker.task --scene rise
python -m vision.scene_demo --scene bloom --output recordings/bloom-synthetic.wav
```

The demo uses audio.fileio's existing synthetic chord and the real audio.Engine; it does not duplicate the virtual-guitar rig or demonstrate camera/hardware accuracy. Listen to 3 seconds of the starting sound, a 6-second morph, then 3 seconds at the destination. A sidecar JSON labels it synthetic and reports peak/clipping.

Customize with `--scene-file scene.json`:

```json
{"name":"My scene","from":{"filter":1,"reverb":0},"to":{"filter":0.4,"reverb":0.75}}
```

Values must be finite numbers between zero and one. Scene mode sends pairs of ordinary v1 filter/reverb messages with strictly increasing vision sequence numbers; default 10 pairs/second = 20 total messages/second. Pairs are not atomic over UDP. Smoothstep interpolation softens the blend endpoints; the gesture and audio smoothing remain active. The overlay names the scene, and existing dashboard filter/reverb cards follow both values. A separate scene badge would require dashboard-owner work. Do not run another vision producer at the same time.

These are expression presets, not loudness-matched patches. Reverb changes perceived loudness; check gain staging during the manual audible test.

## Live hand view for the dashboard

Vision starts an optional WebSocket feed on `ws://127.0.0.1:47802`; use `--no-hand-view` to disable it or `--hand-view-port` to isolate a test. It sends only the selected hand's 21 normalized x/y landmarks, timestamp, presence, engagement, confidence and current control/value. Scene mode uses `control: null` with the morph amount as value. No camera pixels are transmitted or stored. The dashboard implementation/schema belongs to SM.

A one-frame mailbox drops old frames. Each viewer receives at most 20 updates/s; slow sends time out independently. No client is required; port-bind failure reports a warning and gesture UDP output continues. Old snapshots are not repeatedly sent as new frames, so a stalled capture stream cannot keep a dashboard falsely fresh. The browser must clear stale/disconnected landmarks. Presence alone does not mean the clutch is armed.

## Gesture Takes: save a performance, replay the controls

Record the movements that sounded good without recording camera video:

```bash
mkdir -p recordings
python -m vision --model /path/to/hand_landmarker.task --scene bloom --record-take recordings/bloom-take.jsonl
# Stop vision, then replay the saved controls through the engine:
python -m engine --headless --no-keyboard --replay recordings/bloom-take.jsonl
```

The take contains the validated controls emitted by vision, including both Scene Morph parameters. Playback uses the engine's explicit REPLAY label. Headless mode processes silence; use the existing audio-device options for audible playback. This saves control automation, not audio, landmarks or video. The take records locally emitted events, not acknowledgments of UDP delivery. No-hand/released periods appear as timing gaps between events; leading silence before the first event is removed by engine replay.

Recording is opt-in and existing files are never overwritten. A bounded disk-writer queue keeps capture responsive. Recording stops with a warning if the writer falls behind, encounters a disk error, or reaches the replay loader's one-hour/10000-event limit. The saved prefix remains available; inspect warnings before using it as a backup. An empty take (no control events) cannot be replayed. Monotonic capture timing avoids backward timestamps if the system clock changes. `--dry-run --record-take` captures a rehearsal without UDP. Calibration emits no control events, so it produces an empty take.

The JSONL format is engine-replay compatible. Integration with the virtual-guitar CLI is coordinated separately with its owner; this feature adds no new virtual-guitar or DSP implementation.

## Tone Match: build a scene from audio

The offline [Tone Match tool](../tools/tone_match/README.md) fits existing
filter/reverb settings from paired, sample-aligned dry and processed recordings
of the same performance. It exports a ready-to-load `--scene-file`, a portable
audio comparison page, and a scripted morph audition/replay. Run
`python -m tools.tone_match.demo --output /tmp/tone-demo` for a clearly labeled
synthetic guitar demonstration without hardware. It does not clone amps or match
arbitrary song mixes; inspect the fit diagnostics and listen before performing.

## Performance setlists

Keep several scenes loaded for a set without restarting camera tracking:

```bash
python -m vision --model /path/to/hand_landmarker.task --setlist vision/setlist-demo.json
```

With the camera window focused, use **1–9** to select a slot, **n** for next,
**p** for previous, and **q** to quit. Next/previous wrap around. The overlay
shows the selected scene and slot. A setlist is a JSON object with a `scenes`
array of 1–9 ordinary scene definitions; copy a Tone Match `scene.json` object
into that array to include your fitted tone. Every entry is validated before
camera startup. The included three-scene example is an expression demo, not
a loudness-matched set of patches.

Build a custom setlist from named presets and exported scene files in the order
you want to perform them:

```bash
python -m vision.setlist bloom /tmp/velvet-space/scene.json rise --output my-show.json
python -m vision --model /path/to/hand_landmarker.task --setlist my-show.json
```

The builder needs no camera packages and refuses to overwrite an existing file.

Selection itself sends no controls: the engine holds its last settings. Open
your hand, then pinch again to start controlling the newly selected scene.
A held pinch cannot activate it accidentally. Selecting the current slot is
a no-op. The next engagement uses your calibrated absolute hand position, so
it can change the sound; engine smoothing applies, but this is not automatic
cross-scene pickup or a loudness-preserving transition. Stop/release and choose
your hand position deliberately before engaging.

Output sequence numbers stay increasing across switches, including when
revisiting an earlier scene, so UDP deduplication and Gesture Take replay keep
working. Takes record parameter events, not scene-name markers. Setlists need
the overlay keyboard and cannot be combined with `--no-overlay`, calibration,
relative mode, or another scene-selection option. No new dashboard or wire
protocol fields are introduced.

## StrumGuard & DualAxis 3D Spatial Control (python -m vision.spatial)

Spatial performance mode combines spatial protection (`StrumGuard`) with multi-dimensional hand control (`DualAxisController`) and an interactive terminal stage display (`StageHUD`).

### The one command to run
```bash
python -m vision.spatial --model models/hand_landmarker.task
```

### What judges see
1. **Live Terminal Stage HUD**: High-visibility ASCII meters displaying real-time Filter cutoff and Reverb depth bars, active FPS, clutch engagement state, and UDP emission metrics.
2. **StrumGuard Spatial Protection**:
   - Picking and strumming naturally inside the guitar body envelope is recognized as the **Guitar Strum Zone** (`y >= 0.55`).
   - The HUD displays `[STRUM GUARD: LOCKED]`; parameter sweeps are locked to protect the performance from accidental triggering while playing.
   - Rapid pick oscillations and reversal velocities are automatically rejected.
3. **Air Expression Zone & DualAxis 3D Control**:
   - Moving the hand upward into the expression zone (`y < 0.55`) and pinching thumb + index engages live 3D modulation.
   - **Hand elevation (Y-axis)** modulates the low-pass filter cutoff ($0.0 \rightarrow 1.0$).
   - **Knuckle roll tilt (3D roll angle)** modulates reverb depth: leveling the knuckles ($0^\circ$) gives a dry tone; rolling the knuckles outward ($0^\circ \rightarrow 60^\circ$) washes the guitar signal in spacious reverb.
   - Synchronized filter/reverb pairs are emitted at 10 pairs/s (strictly bounded to $\le 20$ events/s).
4. **Dashboard Hand View**: Normalized 21-point hand skeleton streams simultaneously to `ws://127.0.0.1:47802` for the dashboard live HAND panel.

