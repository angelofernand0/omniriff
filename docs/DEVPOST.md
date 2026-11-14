# Devpost draft — OmniRiff

**This is a draft for Angelo to edit.** It follows [ROADMAP.md §1](ROADMAP.md): the coach is the product. Bracketed items are placeholders for **measured** results or ship status only. Don't paste unmeasured numbers. Re-check anything that changed after 2026-11-14.

## Name and tagline
**OmniRiff** — Never put the guitar down. A guitar teacher that lives in your signal chain.

## Inspiration
Practising alone, you know you messed up, but not *why*. Apps score your notes against a chart. Only a teacher tells you it's because your strumming hand froze at the chord change, and lessons cost money every week. Every tool you own also makes you stop playing to use it. We wanted a teacher that hears you, sees you, and sets up the fix while your hands stay on the guitar.

## What it does
- **Hears:** guitar → Focusrite Scarlett Solo → a real-time audio engine with a looper, filter, reverb and a safe limiter. Every loop you record is saved as a take, and **Ears** measures strum timing, gaps and hesitations.
- **Sees:** a pretrained hand-landmark model watches your hands. **Eyes** spots the strumming hand stalling. The pinch gesture also lets you shape your tone without letting go.
- **Teaches:** [if shipped] **Riff**, a coach built on a LangChain deep agent, fuses what it heard and saw to name the *cause* ("your strumming hand stops at the change"), plans a drill, and **operates the rig**: it loops the bar, goes dry, and waits for you to tap the pedal before changing anything. Your next take shows the gap shrinking, with numbers, and it remembers you next session.
- **You stay in control:** an Arduino footswitch answers the coach ("go", "again"). The AI never changes your sound without your tap, and the music keeps playing with every sensor unplugged.

## How we built it
- **audio/** (Python, numpy/scipy, sounddevice/PortAudio): streaming engine with a smoothed biquad low-pass, a Freeverb-style reverb (public-domain tunings), a looper, crossfaded bypass, optional noise gate and a peak limiter. The callback does no I/O, locks or logging. Take capture writes each finished loop to WAV + JSON off the real-time path.
- **tools/ears**: offline strum-onset detection (3 kHz high-pass, log-energy rise, beat-safe peak picking) → TakeReport (onsets, intervals, hesitation/late/early findings).
- **vision/**: MediaPipe Hand Landmarker (pretrained, not trained by us), a pinch clutch with hysteresis, hand tracking, smoothing/deadband, a rate-bounded control stream, a live hand view, and Eyes (hand-movement analysis → HandReport).
- **engine/**: UDP/serial/WebSocket adapters. Every control from vision, pedal, dashboard or coach is validated against a versioned JSON schema, and stale, duplicate, low-confidence and malformed events are dropped. Includes a preflight check, a one-command launcher (dashboard + vision + coach), a session log and a labeled replay mode.
- **coach/** [if shipped]: a deep agent (deepagents) with a visible todo plan, Ears/Eyes subagents, drills as skills, a practice journal and player memory on the filesystem, and human-in-the-loop approval via the pedal. Rig changes go through the same validated control path as `source: "coach"`.
- **dashboard/**: browser UI with Riff, the loop, effect curves, sensor health and the hand skeleton, all built to one brand spec.
- **firmware/arduino/**: a debounced footswitch sending compact JSON lines over serial.
- Built by a four-person team, each directing AI coding agents (Claude Code, Codex, Gemini) that coordinated through a GitHub-issue message board, with owner-scoped folders, versioned contracts and CI-gated PRs.

## Measured results (fill in on the Windows laptop)
- Guitar-to-output latency: [median ± spread ms] at [block size / host API], via `tools.latency` loopback, [N] clicks
- Dropouts over a 5-minute play test: [xruns]
- Ears on real takes: [strums detected / actual; the stumble found at the right time?]
- Coach: [diagnosis on the planted-mistake take; before/after gap ms; cost per take]
- Gesture control update rate: [Hz measured]
- Engine CPU per 128-frame block: ~0.25 ms mean on an Apple M1 Pro (≈9% of the real-time budget), [Windows number]

## Challenges
Real-time audio in Python (preallocated buffers, nothing slow in the callback). Detecting strums on a ringing guitar: our first detector missed soft upstrokes and counted a sustained chord's overtone beating as strums, so we rebuilt it around the pick attack. Keeping an AI agent safe on a live instrument: it proposes, the player approves with a foot tap, and every action goes through the same validation gate as the pedal. Coordinating many agents in parallel without colliding.

## Accomplishments
[Fill in after the hardware run.] Every input can fail without stopping the music. The full control path is verified in a real browser, and the whole pipeline (take → Ears → report) runs end to end.

## What we learned / What's next
[Fill in.] Next: run it with guitar teachers and their students, add audio-rate expression (vibrato as real DSP), and a standalone low-latency build.

## Built with
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, html/css, arduino, focusrite-scarlett-solo, [langchain deepagents], [anthropic claude, if the coach ships]

## Track angles (20 seconds each, on top of the shared demo)
- **Entertainment & Media (main; see SUBMISSION.md for the Education switch rule):** practice becomes a duet with a teacher who plays the rig for you. Loop, tone and drill, hands on the strings.
- **Education (if the team switches):** "interactive, accessible, personalized", literally. It hears and sees *you*, finds the cause, runs the drill and remembers your progress.
- **LangChain deepagents:** [if shipped] the plan is on screen, Ears and Eyes are subagents, drills are skills, the journal and player memory live on the filesystem, and the pedal is the human-in-the-loop approval.
- **Amazon Practical AI:** agentic (acts on the rig), adaptive (remembers you between sessions), real-world (your own takes), simple (no typing; a foot tap answers). Docs: README.md, audio/, engine/, vision/, docs/DEMO.md, docs/COACH.md.
- **Best Physical AI:** the AI perceives through a camera and the guitar cable, then **acts** on a physical rig: looper, effects, recording. It always waits for the player's tap.
- **Best Hardware:** footswitch + webcam + audio interface + guitar on one real-time engine. Unplug anything mid-song and the music keeps playing.

## Charity (be honest)
A teacher for players between lessons or who can't afford them, and hands-free control for players with limited dexterity. [Quote the 2–3 guitarist conversations from the venue as conversations, never as a study.] **We haven't done user studies.** If citing beginners quitting, say it's Fender's claim with no published method.

## Disclosures
- Pretrained models: MediaPipe Hand Landmarker (Google). [Coach: Anthropic Claude via deepagents, if shipped.]
- Reused/adapted: the board helper adapted from azizu06/hackathon-agent-board. Freeverb public-domain tunings. Open-source libraries listed above. Fonts under SIL OFL.
- AI coding agents (Claude Code, Codex, Gemini) wrote much of the code under the team's direction and review.
- Any demo audio not from the live guitar is labeled as replay/simulation (SIM GUITAR / REPLAY on screen).

## Team (Discord)
Angelo, SM, Joey, Aditya: handles go straight into the Devpost form (Angelo has SM's and Joey's). Kept out of this public repo.
