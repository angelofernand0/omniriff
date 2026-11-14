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

Exit metrics on stderr report actual elapsed runtime, emitted event count, average rate and minimum emission interval. `--dry-run` validates and prints JSON without UDP. No-hand frames emit nothing. Failure closes capture and socket; audio must retain its independent manual bypass. No camera frames or recordings are saved by this program.

## Validation status

Unit tests cover activation, loss/rearm, confidence rejection, rate limiting, deadband, smoothing and invalid calibration. Run `python -m unittest discover -s tests -p test_vision.py -v`.

Real webcam operation, recorded hand-video schema output, measured live event rate, and audible integration remain unverified until a task model, dependencies and a recording/device are available. Do not treat synthetic unit tests as recorded-video or hardware acceptance. A one-hand model may switch between visible hands; keep only the control hand in view during the MVP demo. Sudden hand replacement without a detection gap remains a live-validation risk.
