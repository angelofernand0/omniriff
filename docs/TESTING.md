# Testing every way to run OmniRiff

One launcher, the same on macOS, Windows and Linux. **Windows and Linux are untested**: the launcher is plain
Python (`os.name` checks only), but nobody has run it there yet. Please try it and paste `check` on the board.

```
python -m tools.launch            # a menu
python -m tools.launch check      # what this machine has: paste this output on the board when you report
python -m tools.launch setup      # first time on macOS/Linux; on Windows: scripts\windows\setup.ps1 -Coach
```

On a fresh clone the launcher itself needs only Python (any 3.x); it finds the right environment (`.venv`, a
sibling checkout's venv, or PATH) and tells you what is missing. Windows: `py -3.12 -m tools.launch ...` or
`.venv\Scripts\python -m tools.launch ...`. macOS camera: run from **Terminal.app** (macOS only grants the camera to
Terminal-launched processes).

## The modes

| Run | What it is | Needs | Costs | Look for on screen |
|---|---|---|---|---|
| `demo` | Simulated guitar through the real engine + hand tracking + the **LIVE** AI coach | `.env` with `ANTHROPIC_API_KEY` (`ELEVENLABS_API_KEY` for Riff's voice), camera | API credit while you practice (a take is a few cents) | coach light **LIVE**, pill says **SIM GUITAR** |
| `rig` | A real guitar/interface + hand tracking + the **LIVE** coach | same + an interface (Windows defaults to a Focusrite on WASAPI ch. 2; override with `--audio "..."`) | same | coach light **LIVE**, no SIM label |
| `fallback` | Simulated guitar + the **SCRIPTED** coach (canned, follows the live flow) | nothing | free | coach light and pill say **SCRIPTED** |
| `replay [file]` | Simulated guitar + a recorded **real** coach session played back | a recording in `dashboard/replays/` (or pass a file) | free | banner **REPLAY · a recorded session, not live**, pill says **REPLAY COACH** |
| `quiet` | Just the instrument | nothing | free | coach column off |

Overrides: `--source hardware|virtual|silent`, `--coach live|scripted|replay|off`, `--vision auto|on|off`,
`--camera N`, `--audio "<engine audio args>"`, `--serial COM3`, `--no-open`, `--dry-run` (prints what would run).

### Switching modes is a restart, on purpose
Press Ctrl-C and start another preset (`python -m tools.launch fallback`). There is no hot-swap because the LIVE
coach costs money and can ask to change the rig: it is never run alongside the others, so a tester looking at the
scripted coach can't wake it with a pedal press. Every mode says what it is on screen; if the screen and the
command disagree, that is a bug, report it.

## The hosted browser simulator (Vercel)
A zero-install page for anyone: a simulated guitar and hand in the browser, no keys, no coach. It is the
try-it-now proof, **not** the AI demo: no Riff coaching, no Deep Agents (see [BROWSER.md](BROWSER.md)). Its link
is whatever the board says the production URL is; check the board before sharing one, because the project and
root directory were still being changed when this was written. Use `?source=live` for browser mic + camera.

## What to check, per mode
- **Starts without edits** on a clean machine (note anything you had to install).
- **The screen says what it is** (table above). A simulated guitar must show SIM GUITAR; a recording must show REPLAY.
- **Hand tracking:** the hand panel shows your hand; pinch to move the filter. Note camera index and any dropouts.
- **Coach (live):** press **Y** (or hold the pedal) to start practice, loop 10+ seconds, listen for the spoken
  acknowledgement, the cue, the plan and skill steps. Click the page once first so the browser allows sound.
- **Real guitar (`rig`):** input level moves, no clipping, loop records and plays back, latency feels playable.

## Reporting
Post on the board: your OS, `python -m tools.launch check` output, the mode you ran, what you saw, what broke
(last 30 terminal lines). The coach's own terminal lines (`coach tool -> ...`, `coach voice: ...`) are the first
thing to look at when Riff is quiet or slow.
