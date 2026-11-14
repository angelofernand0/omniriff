# Dashboard

Owner: SM's Claude. An optional browser page. It reads engine state (`protocol/state.schema.json`) from `ws://127.0.0.1:47801` and sends v1 control envelopes back on the same socket as `source: "dashboard"`. It processes no audio. The instrument works with this page closed.

Plain HTML/CSS/JS, no build step, no network requests (fonts are local). The brand rules are in [BRAND_SPEC.md](../BRAND_SPEC.md), the page design in [DESIGN.md](DESIGN.md), and the built brand sheet at `/brand.html`.

## Run

With the real engine:

```bash
python -m engine --headless --no-keyboard
```

```bash
python -m dashboard
```

Then open http://127.0.0.1:8080/. It has to be served from localhost, because the engine rejects `file://` pages. To point it at another state socket, add `?ws=ws://127.0.0.1:PORT`.

`?sim=...` puts an amber `SIMULATED` chip on the faceplate (`?sim=guitar` reads `SIM GUITAR`). The simulator's server adds it for you and the play room passes it to its embedded dashboard, so a synthetic guitar is always named on screen. The real engine never sets it, and it is not part of the state protocol.

Without hardware, use the simulator. It runs the real engine with a synthetic guitar input and also serves the dashboard:

```bash
python -m tools.sim run --demo
```

## What it shows

- **Faceplate:** logo, one LED each for ENGINE (LIVE / STALE / OFFLINE), CAM, PEDAL and COACH, the SIMULATED, REPLAY and BYPASS chips, and the meter bridge (input over output, dB, peak hold, clip light).
- **01 LOOP:** state (READY / REC / PLAY), loop length, one hint, and the loop waveform with a playhead and a tick per second.
- **02 TONE:** filter and reverb cards with each effect's curve. When the hand camera is actively sending, the moving effect takes over the whole zone.
- **03 HAND:** the tracked hand's 21 joints from vision's optional feed (`ws://127.0.0.1:47802`, `protocol/hand.schema.json`), mirrored and zoomed to follow the hand. Pink with the pinch boxed and a value rail while the clutch is engaged; `SEEN` otherwise (not "armed": vision may be waiting for an open-hand re-arm); `NO HAND` / `NO CAMERA`. Frames are aged by browser receive time and cleared after 500 ms or on disconnect. `?hand=off` disables it, `?hand=ws://...` overrides it.
- **04 COACH:** the dock for Riff, the coach character. **Design only: there is no AI behind it yet**, so it reads `COACH OFF` with Riff asleep. `?coach=preview` plays a scripted tour of the character's states, labelled `SCRIPTED PREVIEW` on screen. `?coach=off` hides it.
- **05 MANUAL:** loop and bypass keys and two faders, closed by default.
- **Footer:** xruns, clipped samples, event counters, and the keys `F` fullscreen / `L` loop / `B` bypass.
- **Feedback** (`juice.js`): loop stamps, live filter/reverb graphs, the offline screen. Display only. `?juice=off` disables it. Details in [DESIGN.md](DESIGN.md#feedback-layer-juicejs).

Sequence numbers start at the wall clock in ms, so a page reload never repeats one. Run one control dashboard at a time (see `engine/README.md`).

## Layout: Spotlight (index.html, stage.css, stage.js)

While you play it is a guitar app: LOOP is the hero, TONE below with FX POWER, the hand view appears only while the camera sees a hand, and Riff sits small on the loop's top edge. When Riff has something for you (a cue, a question for your pedal, a result) it steps forward: the instrument dims except the control it is operating, Riff grows to centre stage, and the line prints at subtitle size so it reads from the floor. When it changes your rig it walks to the control, points, and presses it in time with the real change. Engineering readouts (LEDs, meters, dB, xruns, manual faders, keys) live in the rig drawer: `D` or the RIG button. One status pill says what is true (LIVE, SIMULATED, REPLAY, SCRIPTED COACH).

## Coach layer (coach.js)

Connects to the coach feed `ws://127.0.0.1:47803` (`protocol/coach.schema.json`; override with `?coachws=`), drives Riff and fills the spotlight: the line, the pedal prompt (`Y`/`N` also answer), the drill, big before/after numbers, and one quiet line by Riff's perch saying what the coach and its Ears/Eyes subagents are doing. Voice: the coach's ElevenLabs audio, queued so Riff never cuts itself off; the browser voice only when the coach sends none. `M` mutes. A scripted session always shows SCRIPTED · NOT AI.
