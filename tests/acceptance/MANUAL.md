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
