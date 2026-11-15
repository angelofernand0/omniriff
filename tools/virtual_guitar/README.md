# Virtual guitar test rig

This tool makes the real OmniRiff DSP audible and measurable without a guitar
or input interface. It is explicitly a **simulation**, not hardware validation.

## Play the full demo

```bash
python -m pip install -r tools/virtual_guitar/requirements.txt
# Place Google's Hand Landmarker model in models/hand_landmarker.task (link below)
python -m tools.virtual_guitar --live --open
```

Open **http://127.0.0.1:8080/** if it does not open automatically. You hear the
physical guitar model through your laptop output, processed continuously by the
real `audio.Engine`. The play room embeds the current dashboard without changing
its files. No microphone or input interface is opened. Start at low speaker volume;
the demo listening level defaults to 35% and can be muted independently of the DSP.

Try all of this:

1. Choose **Clean / dry**, **Dark / warm**, and **Wide / space**. Move Filter and
   Reverb; both the sound and the dashboard respond. Dashboard manual controls
   also operate the same engine.
2. Press **Record loop**, wait a few beats, then **Play loop**. **Pause guitar**
   stops the source with a short fade while the recorded loop and reverb keep
   playing. Shape the loop, then **Clear loop** and **Resume guitar**.
3. Press **Bypass FX** to compare with the dry source/loop mix; **Enable FX**
   restores the effects. **Mute** changes only listening volume. Dashboard
   output meters are before this listening attenuation.
4. Close/reopen the browser: audio continues and the dashboard reconnects.
   Ctrl-C in the terminal stops the audio and all demo servers. The page then
   shows OFFLINE. Restart the command to reconnect.

Space pauses/resumes the guitar, L cycles the looper, and B toggles bypass when
focus is on the play-room page (not in a slider/button or the embedded dashboard).
The source phrase repeats automatically; no scripted effects fight your controls.
The physical pedal stays offline until connected. For the real camera, download
Google's [Hand Landmarker model](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task)
to the ignored `models/hand_landmarker.task` path. Press **Start webcam** in the
play room in Chrome or another browser with camera permission and allow access
to `127.0.0.1`. (The Codex in-app browser may not complete camera permission.)
It shows a local webcam preview
and feeds frames in memory to John's real MediaPipe hand tracker, clutch/scene
controller and hand-view publisher. Open hand → pinch thumb and index → drag
up/down to move the filter; open again to hold. **Stop webcam**
ends capture while guitar playback and manual bypass keep working. No camera
frame or recording is saved. This is real webcam input with a simulated guitar.
The default is a **single filter slider**: open hand, pinch to grab the current
engine target, drag up to increase brightness or down to decrease it, then release
to hold. Re-pinching picks up the latest target, including manual changes between
gestures. At 100% the filter is fully open; move down first to hear a change.
Keep the hand lit from the front. Tracking loss/low confidence requires a fresh
open-hand arm. This does not change the camera model or make dim-light tracking
accurate. The play-room bridge follows the middle-finger palm joint for selection
and vertical drag, so a visible palm is not rejected merely because MediaPipe
projects the wrist below the camera frame. The camera status distinguishes no
hand, uncertain detection, ready-to-pinch and grabbed/dragging; `TRACKING` no
longer means only that frames are arriving. Keep the palm in view, and restart
the live launcher after updating code—reloading the page does not reload its
Python camera worker. Manual bypass remains independent.

Advanced, absolute Scene Morph remains opt-in with `--scene bloom` or
`--scene rise`; it is not the default pinch-slider demo. Set the model path with
`--model PATH`. Native webcam/physical Scarlett listening validation is separate
from deterministic control tests.

If another engine/simulator is already running (for example Claude's dashboard
preview), run alongside it without stopping that process:

```bash
python -m tools.virtual_guitar --live --http-port 8081 --ws-port 47911 --udp-port 47910 --hand-port 47912
```

Then open **http://127.0.0.1:8081/**. The embedded dashboard automatically uses
the matching WebSocket. A separate dashboard needs
`?ws=ws://127.0.0.1:47911&hand=ws://127.0.0.1:47912`.
The page's camera bridge targets the chosen UDP and hand-view ports. The default
ports 47800/47801/47802 follow the existing contracts without a change.
Occupied ports fail visibly; the launcher never silently attaches to an old engine.

`--input-wav clean-di.wav` loops your own PCM guitar recording instead of synthesis.
`--seconds`, `--bpm`, and `--seed` customize the precomputed source; `--out` and
`--hostapi` select an output device. `python -m audio --list-devices` lists devices.
Synthesis/file loading happen before audio starts. Source pause and listening gain
use 20 ms fades; phrase boundaries use 5 ms fades. Audio uses output-only playback
with conservative buffering, so this is for functional/audible testing, not a
low-latency input measurement. The browser sends up to 10 JPEG frames/s over
loopback only; no pixels are sent to a cloud service or stored on disk.

For CI or machines without output devices, use `--live --headless --duration 5`.
The UI labels this **HEADLESS · NO SPEAKER OUTPUT**. Offline rendering below remains
the repeatable path for gesture-take JSONL and signal comparisons.

## Render a repeatable audition

```bash
python -m pip install -r tools/virtual_guitar/requirements.txt
python -m tools.virtual_guitar --demo --output outputs/virtual-guitar.wav
```

The default input is a deterministic six-string physical model: Karplus–Strong
feedback strings in standard tuning, real Em–Cmaj7–G–Dsus2 fret voicings,
millisecond-staggered down/up strums, pick transients, string damping, clean
pickup bandwidth and restrained body resonances. It is still synthesis—not a
recording—but it is designed for audible effect tuning rather than merely
lighting up meters. The command runs it through `audio.Engine`, applies the
same validated control replay used by the backup demo, writes a processed
stereo WAV, and prints a JSON report with levels, spectral brightness,
limiter/clipping counters, control counts and render speed. Listen with any
player, or add `--play` to use the laptop's speakers/headphones after rendering.

For more realistic tuning, provide a clean guitar/DI PCM WAV:

```bash
python -m tools.virtual_guitar \
  --input-wav clean-guitar-di.wav \
  --demo \
  --output outputs/di-demo.wav \
  --report outputs/di-demo.json \
  --play
```

Use a constant setting for quick A/B renders:

```bash
python -m tools.virtual_guitar --seconds 6 --filter 1.0 --reverb 0.0 --output outputs/open-dry.wav
python -m tools.virtual_guitar --seconds 6 --filter 0.2 --reverb 0.6 --output outputs/dark-space.wav
```

`--controls PATH` accepts the replay JSONL format documented in
`engine/README.md`; timestamps become offsets from the start. This lets a
captured/synthetic gesture script drive the same audio engine reproducibly.

What this can validate:

- filter, reverb, loop, bypass, limiter and control timing through the real DSP;
- finite/bounded output, event acceptance and reproducible audio comparisons;
- future agent control plans without needing a live instrument.

What still requires hardware:

- Scarlett/driver behavior, guitar and interface gain staging, measured
  round-trip latency/xruns, feedback/noise, pedal wiring and final play feel.
