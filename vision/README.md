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
Keep the model outside tracked source; supply its path explicitly.

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
