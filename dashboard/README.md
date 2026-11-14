# Dashboard

Owner: SM's Claude. An optional browser page. It reads engine state (`protocol/state.schema.json`) from `ws://127.0.0.1:47801` and sends v1 control envelopes back on the same socket as `source: "dashboard"`. It processes no audio. The instrument works with this page closed.

Plain HTML/CSS/JS, no build step. The design language is in [DESIGN.md](DESIGN.md).

## Run

With the real engine:

```bash
python -m engine --headless --no-keyboard
```

```bash
python -m dashboard
```

Then open http://127.0.0.1:8080/. It has to be served from localhost, because the engine rejects `file://` pages. To point it at another state socket, add `?ws=ws://127.0.0.1:PORT`.

Without hardware, use the simulator. It runs the real engine with a synthetic guitar input and also serves the dashboard:

```bash
python -m tools.sim run --demo
```

## What it shows

- **Header:** connection (LIVE / STALE / OFFLINE), bypass, input meter in dB with peak hold and clip light, output meter.
- **Top third:** looper state (READY / REC / PLAY), loop length, and the loop waveform with playhead.
- **Bottom two thirds:** filter and reverb cards. When the hand camera is actively sending, the moving effect takes over the whole zone.
- **Side column:** hand cam and pedal status. "Manual controls" (loop, bypass, two sliders) is collapsed by default.
- **Footer:** xruns, clipped samples, event counters.

Sequence numbers start at the wall clock in ms, so a page reload never repeats one. Run one control dashboard at a time (see `engine/README.md`).
