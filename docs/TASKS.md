# First tasks

Owners are listed in [TEAM.md](../TEAM.md), and contracts are in [protocol/README.md](../protocol/README.md). Each task ends in a PR with its checks run and a completion post on issue #1. Prefer small PRs: get a thin working slice merged first, then iterate.

Python 3.12 is the default for host-side code. Each module adds its own dependencies under `<module>/requirements.txt` and documents how to run itself in `<module>/README.md`. Code that needs hardware must also have a mode that runs without it (simulated input, file or replay), so it can be tested on any laptop and in CI.

The audio host is a **Windows 11 laptop** with a **Scarlett Solo (3rd gen)**. Some agents work on macOS, so audio code must be cross-platform and avoid OS-specific APIs. The real latency test happens on the Windows laptop.

## Angelo's Claude — `audio/`

1. Build a streaming engine with explicit input/output device selection, an input gain, a hard output limiter and a manual bypass. It must also run from a WAV file to the speakers or to a file, without the Solo.
2. Add one effect: a smoothed low-pass sweep driven by `filter` in [0,1]. Add a placeholder `reverb` parameter, mapped but optional.
3. Add one reliable loop mode, toggled by the `loop` action (record → play → stop).
4. Expose a non-blocking `submit(event)` mailbox for `engine/`. The callback only reads the latest values. No allocation, logging or I/O inside the callback.
5. Track counters for xruns, input/output peak and current parameter values. `engine/` reads these through a snapshot function.

**Done when:** offline unit tests cover filter bounds, smoothing, loop state and bypass. A file-mode demo runs on macOS. A Windows run on the Solo is either recorded or listed as pending.

## Angelo's Codex — `engine/`

1. Write `protocol/state.schema.json` and post it on issue #1 first, because the dashboard depends on it.
2. Build the UDP listener on 47800: validate, drop stale and duplicate events, track sessions, and forward to `audio.submit`.
3. Build the serial adapter: wrap Arduino lines into full envelopes, handle resets and reconnects, and keep running with no device attached.
4. Build the WebSocket state publisher on 47801 at about 20 Hz.
5. Write a single launcher (`python -m engine`) that starts audio and the adapters. The audio must keep running if any adapter dies.
6. Add tests, including a scripted replay of `protocol/examples.json`-style events, with no hardware.

**Done when:** the replay test drives the audio engine's parameters end-to-end in CI, and killing any adapter leaves audio running.

## Sean's Claude — `vision/`

1. Track hand landmarks from the webcam with an off-the-shelf model (disclose which one). It must also run on a recorded video file.
2. Build one deliberate gesture → `filter` value, with a confidence gate, deadband, smoothing and a clutch (for example a pinch to engage), so the hand that strums can't sweep the filter by accident.
3. Emit valid v1 `parameter` events over UDP 47800 at a bounded rate, with no events when no hand is seen.
4. Write a calibration step and a debug overlay window.

**Done when:** schema-validated output from a recorded clip, tests for the gate, deadband and clutch logic, and a measured event rate (not an estimate).

## Sean's Codex — `dashboard/` and `tools/sim/`

1. Build `tools/sim/`: a CLI that sends scripted or keyboard-driven control events to UDP 47800, and a fake state publisher on 47801, so the dashboard and engine can each be built without the other.
2. Build `dashboard/`: a browser page showing bypass, loop state, filter/reverb, levels, xruns and source health from the WebSocket state, with buttons and sliders that send control events (`source: "dashboard"`).
3. Keep it optional: the instrument must work with the dashboard closed.

**Done when:** the dashboard works against the fake publisher, the sim has tests, and the dashboard switches to the real engine once `state.schema.json` lands.

## Aditya's Codex — `firmware/arduino/` and `docs/HARDWARE.md` (draft for Aditya)

1. Write a debounced footswitch sketch that sends the compact JSON lines from `protocol/README.md` at 115200 baud. Make the pins configurable, and include the button count and pin choices as TODOs for Aditya.
2. Compile the sketch with `arduino-cli` if available. Otherwise mark it as not compiled.
3. Write `docs/HARDWARE.md`, a wiring and mapping sheet for Aditya to fill in: the parts actually on hand, pins, which switch does loop vs bypass, and gesture notes for `vision/`.

**Done when:** a PR is open with the sketch, its compile status stated honestly, and the hardware sheet. Aditya flashes and tests it tomorrow night.

## Not in the MVP yet

SenseCAP panel, Raspberry Pi vision, environmental sensing, multitrack looping and custom model training. Aditya may pick up SenseCAP after the footswitch works.
