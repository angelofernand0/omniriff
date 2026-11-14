# Live Soundcheck

A guided **read-only** rehearsal of the pinch control path. It subscribes to the
existing engine state and hand-view WebSockets, displays a target, and checks
that the player reaches it, holds while pinching, then releases while the value
stays put. It never sends commands or changes effects. It is separate from the
coach, and is not a guitar-technique score or a camera accuracy benchmark.

## Run with the play room

Start the latest play room, open its printed URL and start the real webcam in
front lighting. Use the default filter-slider mode, **without `--scene`**:

```sh
python -m tools.virtual_guitar --live --model models/hand_landmarker.task
python -m vision.soundcheck --output /tmp/my-soundcheck
```

Open the second command's printed URL. Targets default to **25% → 75% → 50%**.
For each target: open the hand, pinch and move until the actual filter is within
5 percentage points; hold the pinch for one second; open the hand and hold the
value for half a second. Each target has a 20-second deadline, starting when the
soundcheck command runs, so start the camera first. At 100%, drag down first.

For a rig using separate ports:

```sh
python -m vision.soundcheck --engine-ws ws://127.0.0.1:47911 \
  --hand-ws ws://127.0.0.1:47912 --output /tmp/my-soundcheck
```

Use `--targets .2 .8 .5` or `--timeout 30` to change the exercise. Only localhost
WebSocket sources are accepted. The display binds to 127.0.0.1 on a free port;
`--http-port` chooses a fixed one. No cross-origin access is enabled. Commands
and POST requests are not supported by the display server.

## Honest evidence

- A hand must remain present with confidence ≥0.6 and identify `control: filter`.
  Scene Morph is not scored as a filter-slider exercise.
- Both feeds must be connected, received within 500 ms, and carry a timestamp
  within 500 ms of the local wall clock. Cached duplicate or reordered frames do
  not refresh the feed. A frozen or disconnected feed cannot pass a target.
- Losing the hand does **not** count as release. Loss during a hold resets it.
  An out-of-range value during release requires reaching/holding again.
- `report.json` and portable `index.html` are written to a new output folder.
  They include target results, elapsed times, tracking breaks and a bounded
  10 Hz control-value trace. No audio, camera images or landmarks are saved.
- Ctrl-C writes an incomplete report. An existing output folder is never replaced.
- This observes messages. It cannot prove that a hand feed came from a live
  camera, or distinguish a simultaneous manual slider adjustment from a gesture.
  Use `--source-label "SYNTHETIC TEST FEED"` for synthetic tests. Labels are
  operator-supplied and are not verification.
- Passing means the **control sequence** was observed. It says nothing about
  audible clipping, physical guitar/Scarlett latency, detector accuracy, or
  playing proficiency. Keep the physical manual acceptance check separate.

The tests use synthetic hand messages with the actual Runtime/HandView transport;
they verify that the observer sends no control commands. The committed package
has no synthetic-feed switch: tests and demos must supply their own labeled feed.
