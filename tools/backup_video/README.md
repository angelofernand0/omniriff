# Labelled backup video (B16)

This is a last-resort, hardware-free clip for the optional Devpost video or a
demo-table failure. It records the **real dashboard** while the production
`audio.Engine` processes a **synthetic guitar** and the validated
`engine/demo-controls.jsonl` script. Its sound is the processed output of that
same run, not microphone or interface audio. The dashboard shows `SIM GUITAR`
and `REPLAY`; a permanent badge says **SIMULATED GUITAR + SCRIPTED CONTROLS /
NO HARDWARE**. Do not present this as a live gesture, pedal, guitar or hardware
test. Record the real rig separately after hardware bring-up.

## One command

Install the normal repo dependencies (`requirements-dev.txt`), then install
Playwright into the same Python environment and put `ffmpeg` on `PATH` (or
install `imageio-ffmpeg` into that environment). Google
Chrome is used by default; for another Chromium executable use
`--browser-executable PATH`. On a machine without Chrome, install Playwright's
Chromium and supply its executable path. The recorder makes no cloud calls.

```bash
python -m pip install playwright imageio-ffmpeg
python -m tools.backup_video
```

The default clip is `recordings/backup-simulated.mp4` (an ignored local path),
10 seconds at 1280×720. `--seconds` accepts 7.5–120 seconds;
the lower bound keeps the last scripted control in the clip, while 120 seconds is
the optional Devpost video limit. An existing output file is **never**
overwritten. The MP4 is local and should be reviewed for readable labels,
audible output and alignment before submission. It is not committed to Git.
Browser capture starts before the audio/replay; the script trims the labelled
pre-roll when muxing, so this is a fallback presentation clip, not a latency
measurement or frame-accurate synchronization record.

The tool does not start a camera, microphone, audio device, serial port or
physical pedal. It binds temporary dashboard/state servers to loopback with
ephemeral ports, then shuts them down. If Playwright, Chrome or ffmpeg is
missing, it exits with an installation hint and leaves the requested MP4 alone.
