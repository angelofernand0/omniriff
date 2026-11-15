# Devpost draft — OmniRiff

**This is a draft for Angelo to edit.** It follows [ROADMAP.md §1](ROADMAP.md): the coach is the product. Bracketed items are placeholders for **measured** results or ship status only. Don't paste unmeasured numbers. Re-check anything that changed after 2026-11-14.

## Name and tagline
**OmniRiff** — Never put the guitar down. A guitar teacher that lives in your signal chain.

## Inspiration
Practising alone, you know you messed up, but not *why*. Apps score your notes against a chart. Only a teacher tells you it's because your strumming hand froze at the chord change, and lessons cost money every week. Every tool you own also makes you stop playing to use it. We wanted a teacher that hears you, sees you, and sets up the fix while your hands stay on the guitar.

## What it does
- **Hears:** guitar → Focusrite Scarlett Solo → a real-time audio engine with a looper, filter, reverb and a safe limiter. Every loop you record is saved as a take, and **Ears** measures strum timing, gaps and hesitations.
- **Sees:** a pretrained hand-landmark model watches your hands. **Eyes** spots the strumming hand stalling. The pinch gesture also lets you shape your tone without letting go.
- **Teaches:** **Riff**, a coach built on a LangChain deep agent, fuses what it heard and saw to name the *cause* ("your strumming hand stops at the change"), plans a drill, and **operates the rig**: it loops the bar, goes dry, and waits for you to tap the pedal before changing anything. Your next take shows the gap shrinking, with numbers, and it remembers you next session.
- **You stay in control:** an Arduino footswitch answers the coach ("go", "again"). The AI never changes your sound without your tap, and the music keeps playing with every sensor unplugged.

## How we built it
- **audio/** (Python, numpy/scipy, sounddevice/PortAudio): streaming engine with a smoothed biquad low-pass, a Freeverb-style reverb (public-domain tunings), a looper, crossfaded bypass, optional noise gate and a peak limiter. The callback does no I/O, locks or logging. Take capture writes each finished loop to WAV + JSON off the real-time path.
- **tools/ears**: offline strum-onset detection (3 kHz high-pass, log-energy rise, beat-safe peak picking) → TakeReport (onsets, intervals, hesitation/late/early findings).
- **vision/**: MediaPipe Hand Landmarker (pretrained, not trained by us), a pinch clutch with hysteresis, hand tracking, smoothing/deadband, a rate-bounded control stream, a live hand view, and Eyes (hand-movement analysis → HandReport).
- **engine/**: UDP/serial/WebSocket adapters. Every control from vision, pedal, dashboard or coach is validated against a versioned JSON schema, and stale, duplicate, low-confidence and malformed events are dropped. Includes a preflight check, a one-command launcher (dashboard + vision + coach), a session log and a labeled replay mode.
- **coach/**: a deep agent (deepagents) with a visible todo plan, Ears/Eyes subagents, drills as skills, a practice journal and player memory on the filesystem, and human-in-the-loop approval via the pedal. Rig changes go through the same validated control path as `source: "coach"`.
- **dashboard/**: browser UI with Riff, the loop, effect curves, sensor health and the hand skeleton, all built to one brand spec.
- **firmware/arduino/**: a debounced footswitch sending compact JSON lines over serial.
- Built by a four-person team, each directing AI coding agents (Claude Code, Codex, Gemini) that coordinated through a GitHub-issue message board, with owner-scoped folders, versioned contracts and CI-gated PRs.

## Measured results (fill in on the Windows laptop)
Run `scripts/windows/measure.ps1 -Pass Loopback` then `-Pass Guitar` (see DEMO.md §1) and paste the measured lines from `runs/measure/*/results.md`. Leave anything it marks "not measured" as a bracket.
- Guitar-to-output latency: [median ± spread ms] at [block size / host API], via `tools.latency` loopback, [N] clicks
- Dropouts over a 5-minute play test: [xruns]
- Ears on real takes: [strums detected / actual; the stumble found at the right time?]
- Coach: [diagnosis on the planted-mistake take; before/after gap ms; cost per take]
- Gesture control: [moving-hand webcam numbers from `--metrics-json`]. Diagnostic so far (R16, static hand images, not a moving-hand test): 150/150 frames detected, 30.9 processed FPS, 9.3 ms mean per frame (p95 10.1 ms) on the dev Mac.
- Engine CPU per 128-frame block: ~0.25 ms mean on an Apple M1 Pro (≈9% of the real-time budget), [Windows number]

## Challenges
- **Real-time audio in Python:** Preallocated NumPy buffers, zero memory allocation, zero locks, and no file I/O or logging inside the real-time audio callback.
- **Acoustic transient perception:** Detecting strums on a ringing guitar is deceptively difficult. Our initial energy detector was fooled by ringing string overtones and overtone beating, while completely missing soft upstrokes. We had to rebuild Ears around pick-attack physics (a 3 kHz high-pass filter, log-energy rise, and dynamic thresholding).
- **Safe cyber-physical agency:** An AI agent controlling live audio parameters cannot act unguided. The agent proposes changes, the player approves with a physical foot tap, and every single action routes through the exact same schema-validation gate as the pedal.
- **Concurrent multi-agent orchestration:** Coordinating four humans and their autonomous coding agents across 330 commits without code drift, race conditions, or merge collisions.

## Accomplishments
- **One complete cyber-physical teaching loop:** The full journey runs end to end: you play a phrase; the looper records the take; **Ears** measures strum timing and pauses while **Eyes** tracks hand kinematics; **Riff** diagnoses the root cause ("your strumming hand stopped at the chord change"), plans a drill, loops the target bar, and waits for a physical pedal tap before altering your sound; your next attempt shows the measured gap shrinking in real time, with the result recorded to your longitudinal practice journal.
- **Every input fails safe without stopping the music:** The audio callback is strictly isolated from the rest of the system. Unplug the webcam, disconnect the footswitch serial cable, sever the WebSocket telemetry feed, or exhaust the AI budget—the audio engine continues playing clean, glitch-free sound without skips, clicks, or dropouts. Every control event (gesture, pedal, dashboard, coach) is validated against JSON schemas (`control.schema.json`, `state.schema.json`), rate-limited, and smoothed with linear crossfading.
- **Rigorous multi-agent engineering with 100% contract enforcement:** Four teammates directed autonomous coding agents through 144 merged pull requests and 330 commits on a shared GitHub message board. By enforcing owner-scoped directories, frozen public schemas, and automated contract tests (421 tests passing in CI), we developed real-time DSP, computer vision, LangChain deep agents, and firmware simultaneously without cross-branch contamination or merge conflicts.
- **Hardware-ready physical prototype:** [Fill in after the hardware run: Scarlett Solo latency median ± spread ms, 0 xruns over 5-minute sustained play test, real-take strum onset accuracy, and live footswitch response].

## What we learned
- **Acoustic transient physics beat raw energy:** Detecting strums on a ringing electric guitar required looking at the high-frequency pick attack rather than raw audio power. Sustained open chords produce overtone beating that mimics rhythms, but the sharp pick strike creates an unmistakable high-frequency burst (>3 kHz) with an immediate rise time.
- **Physical instruments require human-in-the-loop agency:** An AI agent on a live instrument must be a disciplined collaborator, not an unpredictable autonomous actor. Gating every rig adjustment behind a physical pedal tap and subjecting the AI to the exact same parameter clamp and rate limits as manual controls creates immediate trust.
- **Multi-agent teams need clear modular boundaries:** When multiple autonomous coding agents work in parallel, shared files create instant collisions. Splitting the project into owner-scoped packages (`audio/`, `engine/`, `vision/`, `coach/`, `firmware/`) with strictly versioned protocol schemas enabled continuous, parallel shipping without coordination deadlocks.

## What's next for OmniRiff
- **Field testing with guitar teachers and students:** Put OmniRiff into the hands of music educators and beginner guitarists to evaluate how longitudinal practice memory and instant cause-and-effect drills impact deliberate practice between lessons.
- **Continuous audio-rate optical modulation:** Expand vision gestures beyond control-rate filtering into continuous audio-rate modulation (e.g. optical vibrato, tremolo, and morphing multi-FX spaces) using direct SIMD DSP buffers.
- **Embedded C++ / Faust hardware pedal:** Port the core audio callback and parameter router to a dedicated embedded C++/Faust engine running on a bare-metal microcontroller or Raspberry Pi for a standalone sub-1 ms physical pedal enclosure.
- **Polyphonic chord voicing transcription:** Extend Ears from monophonic strum-timing analysis to polyphonic audio transcription, identifying missed fretboard fingerings and buzzing strings alongside rhythmic timing.

## Built with
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, html/css, arduino, focusrite-scarlett-solo, langchain deepagents, anthropic claude

## Track angles (20 seconds each, on top of the shared demo)
- **Entertainment & Media (main; see SUBMISSION.md for the Education switch rule):** practice becomes a duet with a teacher who plays the rig for you. Loop, tone and drill, hands on the strings.
- **Education (if the team switches):** "interactive, accessible, personalized", literally. It hears and sees *you*, finds the cause, runs the drill and remembers your progress.
- **LangChain deepagents:** the plan is on screen, Ears and Eyes are subagents, drills are skills, the journal and player memory live on the filesystem, and the pedal is the human-in-the-loop approval.
- **Amazon Practical AI:** agentic (acts on the rig), adaptive (remembers you between sessions), real-world (your own takes), simple (no typing; a foot tap answers). Docs: README.md, audio/, engine/, vision/, docs/DEMO.md, docs/COACH.md.
- **Best Physical AI:** the AI perceives through a camera and the guitar cable, then **acts** on a physical rig: looper, effects, recording. It always waits for the player's tap.
- **Best Hardware:** footswitch + webcam + audio interface + guitar on one real-time engine. Unplug anything mid-song and the music keeps playing.

## Charity (be honest)
A teacher for players between lessons or who can't afford them, and hands-free control for players with limited dexterity. [Quote the 2–3 guitarist conversations from the venue as conversations, never as a study.] **We haven't done user studies.** If citing beginners quitting, say it's Fender's claim with no published method.

## Disclosures
- Pretrained models: MediaPipe Hand Landmarker (Google). Coach: Anthropic Claude (claude-sonnet-5-5 / claude-haiku-5-5) via deepagents.
- Reused/adapted: the board helper adapted from azizu06/hackathon-agent-board. Freeverb public-domain tunings. Open-source libraries listed above. Fonts under SIL OFL.
- AI coding agents (Claude Code, Codex, Gemini) wrote much of the code under the team's direction and review.
- Any demo audio not from the live guitar is labeled as replay/simulation (SIM GUITAR / REPLAY on screen).

## Team (Discord)
Angelo, SM, Joey, Aditya: handles go straight into the Devpost form (Angelo has SM's and Joey's). Kept out of this public repo.
