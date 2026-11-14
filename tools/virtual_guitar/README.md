# Virtual guitar test rig

This tool makes the real OmniRiff DSP audible and measurable without a guitar
or input interface. It is explicitly a **simulation**, not hardware validation.

## Play the full demo

```bash
python -m pip install -r tools/virtual_guitar/requirements.txt
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
Camera/pedal status remains offline until a real sender connects. This demo does
not simulate hand tracking or prove gesture recognition.

If another engine/simulator is already running (for example Claude's dashboard
preview), run alongside it without stopping that process:

```bash
python -m tools.virtual_guitar --live --http-port 8081 --ws-port 47811 --udp-port 47810
```

Then open **http://127.0.0.1:8081/**. The embedded dashboard automatically uses
the matching WebSocket. A separate dashboard needs `?ws=ws://127.0.0.1:47811`.
External gesture senders must target the chosen UDP port. The default ports
47800/47801 work with the existing vision/control tools without a contract change.
Occupied ports fail visibly; the launcher never silently attaches to an old engine.

`--input-wav clean-di.wav` loops your own PCM guitar recording instead of synthesis.
`--seconds`, `--bpm`, and `--seed` customize the precomputed source; `--out` and
`--hostapi` select an output device. `python -m audio --list-devices` lists devices.
Synthesis/file loading happen before audio starts. Source pause and listening gain
use 20 ms fades; phrase boundaries use 5 ms fades. Audio uses output-only playback
with conservative buffering, so this is for functional/audible testing, not a
low-latency input measurement. No files are recorded in live mode.

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
