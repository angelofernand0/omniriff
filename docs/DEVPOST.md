# Devpost draft — OmniRiff

**This is a draft for Angelo to edit.** Bracketed items are placeholders to fill with **measured** results only. Don't paste unmeasured numbers. Facts are from the repo as of 2026-11-14; re-check anything that changed.

## Name and tagline
**OmniRiff** — Never put the guitar down. Shape your sound with a pinch and a tap, while your hands stay on the strings.

## Inspiration
Every guitar effect asks you to take a hand off the strings or look down at a pedalboard. For players with limited mobility or dexterity, a small knob or a precise stomp can be the barrier between practicing and not. We wanted the instrument to listen to the player's body instead.

## What it does
- Guitar → Focusrite Scarlett Solo → laptop audio engine, with a low-pass sweep, reverb, a looper and click-free bypass, safely limited.
- **Gesture control:** a pretrained hand-landmark model watches one hand. Pinch to engage, and hand height sweeps the filter (or morphs filter + reverb between scenes). Strumming without the clutch does nothing.
- **Foot control:** an Arduino footswitch toggles the loop and bypass.
- **Live dashboard:** levels, loop state, effect curves, sensor health and a live hand skeleton, so you can see what the rig hears and sees.
- [**Practice coach** (if shipped): a LangChain deep agent works between takes, explains what went wrong from what the rig heard and saw, and runs the next drill.]

## How we built it
- **audio/** (Python, numpy/scipy, sounddevice/PortAudio): streaming engine with a smoothed biquad low-pass, a Freeverb-style reverb (public-domain tunings), a looper, a crossfaded bypass and a peak limiter. The audio callback does no I/O, logging or blocking. Controls arrive through a non-blocking mailbox.
- **engine/**: UDP control input, serial (Arduino) input and a WebSocket state feed. It validates every control against a versioned JSON schema and drops stale, duplicate, low-confidence and malformed events before they reach audio. The audio keeps running if any input dies. Labeled replay mode for backups.
- **vision/**: MediaPipe Hand Landmarker (pretrained, not trained by us), a pinch clutch with hysteresis, two-hand tracking, smoothing/deadband and a rate-bounded event stream. [Scene Morph, setlists, StrumGuard/DualAxis if merged.]
- **dashboard/**: a browser UI on WebSocket state, with STALE/OFFLINE handling and the hand view.
- **firmware/arduino/**: a debounced footswitch sending compact JSON lines over serial.
- **tools/**: a simulator, a virtual guitar (Karplus-Strong physical model), latency measurement, an acceptance test suite and [Tone Match].
- Built by a four-person team, each directing AI coding agents (Claude Code, Codex, Gemini) that coordinated through a GitHub-issue message board, with owner-scoped branches and PR review.

## Measured results (fill in on the Windows laptop)
- Guitar-to-output latency: [median ± spread ms] at [block size / host API], via `tools.latency` loopback, [N] clicks
- Dropouts over a 5-minute play test: [xruns]
- Gesture control update rate: [Hz measured]
- Engine CPU per 128-frame block: ~0.25 ms mean on an Apple M1 Pro (≈9% of the real-time budget), [Windows number]

## Challenges
Keeping audio real-time in Python (preallocated buffers, no work in the callback). Making gesture control safe: the strumming hand must never sweep the filter, so we added a clutch, confidence gating and stale-event rejection. Coordinating many agents in parallel without colliding.

## Accomplishments
[Fill in after the hardware run.] The whole control path is verified in a real browser: gesture/pedal/dashboard controls → engine → audio state → dashboard. Every input can fail without stopping the music.

## What we learned / What's next
[Fill in.] Next: more expressive gestures mapped to real DSP (e.g. an audio-rate LFO for vibrato rather than control-rate wobble), user studies with players with limited mobility, and a standalone low-latency build.

## Built with
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, html/css, arduino, focusrite-scarlett-solo, [langchain deepagents], [model provider if the coach ships]

## Track angles (20 seconds each, on top of the shared demo)
- **Entertainment & Media (main):** a new way to *perform* — the body becomes part of the instrument, live, with a loop and gesture-shaped effects.
- **Best Physical AI:** a pretrained hand-landmark model in a real-time physical control loop with a guitar rig. AI perception drives sound safely (clutch, confidence gate, staleness rejection, manual override). The camera is the sensor, the guitar rig is the actuator.
- **Best Hardware:** an Arduino footswitch, webcam and audio interface integrated with a real-time engine. Unplug any device mid-song and the music keeps playing.
- **LangChain deepagents:** [if shipped] the coach is a deep agent with tools over the rig: it plans a drill, triggers loops/effects through the same validated control path, and reasons from take data. The instrument never waits on it.
- **Amazon Practical AI:** an accessibility tool using gesture + vision. **Target user:** guitarists with limited mobility or dexterity, and any player whose hands are busy. **Use case:** control effects and looping without knobs or precise stomps. Docs: README.md, audio/README.md, engine/README.md, vision/README.md, docs/DEMO.md. **We haven't done user studies; don't claim them.**

## Disclosures
- Pretrained models: MediaPipe Hand Landmarker (Google). [Coach model/provider if used.]
- Reused/adapted: the board helper adapted from azizu06/hackathon-agent-board. Freeverb public-domain tunings. Open-source libraries listed above.
- AI coding agents (Claude Code, Codex, Gemini) wrote much of the code under the team's direction and review.
- Any demo audio not from the live guitar is labeled as replay/synthesis.

## Team (Discord)
Angelo, SM, Joey, Aditya: handles go straight into the Devpost form (Angelo has SM's and Joey's). Kept out of this public repo.
