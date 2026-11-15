# Devpost Submission Form — Paste-Ready Fields

This document contains copy-and-paste text for every field of the Devpost submission form for **OmniRiff** at HackPrinceton Fall '26.

Submission deadline: **Sunday, Nov 15, 8:00 AM ET** (Target submission: **7:00 AM ET**).  
Submission portal: https://hackprinceton-fall-26.devpost.com/

---

## 1. Project Name

```text
OmniRiff
```

---

## 2. Tagline (≤ 60 characters)

**Character count: 49 / 60**
```text
A guitar teacher that lives in your signal chain.
```

*Alternative option (58 / 60 characters):*
```text
Never put the guitar down. A teacher in your signal chain.
```

---

## 3. Elevator Pitch / Short Description (≤ 200 characters)

**Character count: 178 / 200**
```text
OmniRiff is a guitar teacher that lives in your signal chain: it hears and sees you play, finds why you stumbled, and sets up the drill, without you ever putting the guitar down.
```

---

## 4. Built With (Tags)

Paste into the "Built with" tags field:
```text
python, numpy, scipy, sounddevice, portaudio, mediapipe, opencv, websockets, pyserial, jsonschema, javascript, html/css, arduino, focusrite-scarlett-solo, langchain deepagents, anthropic claude
```

---

## 5. Links & URLs

- **GitHub Repository (Public):**
  ```text
  https://github.com/angelofernand0/omniriff
  ```

- **Demo / Try It Out (Browser Simulator):**
  ```text
  https://omniriff.vercel.app
  ```
  *(Devpost label note: Browser simulator — synthetic guitar and hand controls. Tap Start simulator; no terminal required. The hosted simulator does not run the live AI coach. Real guitar/interface/camera operation still needs hardware verification.)*

- **Video Demo Link (≤ 2 minutes):**
  ```text
  [Paste demo video link here — unlisted YouTube, Vimeo, or Devpost direct upload]
  ```

---

## 6. Team & Discord Usernames

- **Team Members (Devpost invitations):**
  Angelo, SM, John, Aditya (Max 4 team members per HackPrinceton rules).

- **Discord Usernames (Required for winner contact; handles kept out of repo):**
  ```text
  Angelo: [Paste Discord handle]
  SM:     [Paste Discord handle]
  John:   [Paste Discord handle]
  Aditya: [Paste Discord handle]
  ```

---

## 7. Track Fit Statements (2–4 sentences each)

### Track 1: Entertainment & Media (Main Track)
*(Note: See SUBMISSION.md for Education track fallback condition if decided in person).*

```text
Practice becomes a live interactive duet with an AI teacher that lives inside your instrument chain. Rather than staring at a static tab or phone app, the system hears your audio through the interface, watches your hand kinematics with vision, and dynamically operates your looper, tone filters, and drills so you never put the guitar down. It transforms solo rehearsal into an engaging, responsive cyber-physical musical experience.
```

### Track 2: LangChain — Best use of deepagents
*(Special Sponsor Track)*

```text
Riff is built on the LangChain deepagents framework with an explicit planning graph and visible todo list on screen. The main deep agent orchestrates two dedicated subagents—Ears for acoustic transient onset analysis and Eyes for wrist kinematic tracking—while managing drills as discrete agent skills and persisting practice journals and player memory directly to the local filesystem. Every rig modification routes through a strict human-in-the-loop pause, requiring player approval (via pedal or dashboard) before the agent alters live sound settings.
```

### Track 3: Amazon — Best Practical AI
*(Special Sponsor Track)*

```text
OmniRiff delivers an agentic, adaptive practice assistant built for guitarists practising alone between lessons and players with limited dexterity for whom turning physical knobs or tapping tiny phone screens is a barrier. It minimizes friction during practice—clutched hand gestures shape tone, a voice goal uses push-to-talk, and player approval gates drills—while the agent adapts across takes and remembers your stumbling blocks in a persistent practice journal. The entire system is fully documented across modular runbooks and fails safe if external services drop out.
```

### Track 4: Best Physical AI ($500)
*(Category Track)*

```text
OmniRiff perceives the physical world through two concurrent sensor streams—an acoustic guitar DI signal into a Focusrite Scarlett Solo interface and video frames into a hand-tracking camera—and directly acts upon a physical musical rig. It controls a real-time DSP looper, automated parameter crossfades, and practice drills, operating as a disciplined cyber-physical collaborator that gates rig changes behind player approval. Software contract tests ensure the audio stream continues running even during external sensor or network disconnection.
```

### Track 5: Best Hardware
*(Category Track)*

```text
The rig integrates an Arduino footswitch (debounced USB serial), USB webcam, Focusrite Scarlett Solo 3rd-gen interface, and electric guitar into a unified Python audio engine running with PortAudio and preallocated NumPy buffers. In software tests, the core audio callback remains isolated from external input failures (camera, pedal, dashboard or coach failures; not the audio interface itself), with hardware dropouts, real-take strum detection, and latency measured on the physical rig: [after the hardware run: Scarlett Solo latency median ± spread ms, xruns over a 5-minute sustained play test, real-take strum detection, and physical footswitch response].
```

---

## 8. Main Project Description / Story (Full Markdown for Devpost Text Field)

Copy the Markdown below directly into the Devpost rich text editor:

```markdown
## Inspiration
Practising alone, you know you messed up, but not *why*. Apps score your notes against a chart. Only a teacher tells you it's because your strumming hand froze at the chord change, and lessons cost money every week. Every tool you own also makes you stop playing to use it. We wanted a teacher that hears you, sees you, and sets up the fix while your hands stay on the guitar.

## What it does
- **Hears:** guitar → Focusrite Scarlett Solo → a real-time audio engine with a looper, filter, reverb and a safe limiter. Every loop you record is saved as a take, and **Ears** measures strum timing, gaps and hesitations.
- **Sees:** a pretrained hand-landmark model watches your hands. **Eyes** spots the strumming hand stalling. The pinch gesture also lets you shape your tone without letting go.
- **Teaches:** **Riff**, a coach built on a LangChain deep agent, fuses what it heard and saw to name the *cause* ("your strumming hand stops at the change"), plans a drill, and **operates the rig**: it plays your take back so you can hear the stumble, goes dry, and waits for you to hold the pedal (or press Y) before changing anything. You record a fresh drill take, it shows the gap shrinking, with numbers, and it remembers you next session.
- **You stay in control:** an Arduino footswitch: tap to loop, hold to start practice or approve what Riff proposes. The AI never changes your sound without that hold (or Y on the keyboard), and the music keeps playing if the camera, pedal, dashboard or coach drops out (the audio interface itself is the one part the sound needs).

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
- **Real-time audio in Python:** Preallocated NumPy buffers and a design rule of no locks, network I/O, file I/O or logging inside the real-time audio callback.
- **Acoustic transient perception:** Detecting strums on a ringing guitar is deceptively difficult. Our initial energy detector was fooled by ringing string overtones and overtone beating, while completely missing soft upstrokes. We had to rebuild Ears around pick-attack physics (a 3 kHz high-pass filter, log-energy rise, and dynamic thresholding).
- **Safe cyber-physical agency:** An AI agent controlling live audio parameters cannot act unguided. The agent proposes changes, the player approves by holding a physical footswitch (or pressing Y), and every single action routes through the exact same schema-validation gate as the pedal.
- **Concurrent multi-agent orchestration:** Coordinating four humans and their autonomous coding agents across well over a hundred pull requests: owner-scoped folders, versioned contracts agreed on the board, and CI-gated PRs kept conflicts rare and caught them before main.

## Accomplishments
- **One complete cyber-physical teaching loop:** The full journey runs end to end (verified in simulation; real-rig run: [after the hardware run]): you play a phrase; the looper records the take; **Ears** measures strum timing and pauses while **Eyes** tracks hand kinematics; **Riff** diagnoses the root cause ("your strumming hand stopped at the chord change"), plans a drill, plays your take back, and waits for a physical pedal hold before altering your sound; a fresh drill take then shows whether the measured gap shrank, and the result is recorded to your practice journal.
- **Every input fails safe without stopping the music:** The audio callback is strictly isolated from the rest of the system: covered by software tests, the audio keeps running when external inputs fail (camera/vision, pedal serial, dashboard WebSocket or coach failures, including the coach running out of budget; unplugging the audio interface itself does stop the sound), with hardware dropouts measured in the 5-minute soak: [xruns]. Parameters are smoothed, bypass uses a 5 ms linear crossfade, vision output is rate-limited, and the router drops stale, duplicate, and low-confidence events.
- **Rigorous multi-agent engineering with contract enforcement:** Four teammates directed autonomous coding agents through more than a hundred CI-gated pull requests on a shared GitHub message board. By enforcing owner-scoped directories, versioned, additive-only schema changes agreed on the board, and automated contract tests run in CI on every pull request, we developed real-time DSP, computer vision, LangChain deep agents, and firmware simultaneously, keeping branch conflicts rare and catching them before main.
- **Hardware-ready physical prototype:** [after the hardware run: latency median ± spread; xruns over a 5-minute play test; real-take strum detection; footswitch check].

## What we learned
- **Acoustic transient physics beat raw energy:** Detecting strums on a ringing electric guitar required looking at the high-frequency pick attack rather than raw audio power. Sustained open chords produce overtone beating that mimics rhythms, but the sharp pick strike creates an unmistakable high-frequency burst (>3 kHz) with an immediate rise time.
- **Physical instruments require human-in-the-loop agency:** An AI agent on a live instrument must be a disciplined collaborator, not an unpredictable autonomous actor. Gating every rig adjustment behind a physical pedal hold and subjecting the AI to the exact same parameter clamp and rate limits as manual controls creates immediate trust.
- **Multi-agent teams need clear modular boundaries:** When multiple autonomous coding agents work in parallel, shared files create instant collisions. Splitting the project into owner-scoped packages (`audio/`, `engine/`, `vision/`, `coach/`, `firmware/`) with versioned, additive-only protocol schemas agreed on the board kept conflicts rare and caught issues in CI before merge.

## What's next for OmniRiff
- **Field testing with guitar teachers and students:** Put OmniRiff into the hands of music educators and beginner guitarists to evaluate how longitudinal practice memory and instant cause-and-effect drills impact deliberate practice between lessons.
- **Continuous audio-rate optical modulation:** Expand vision gestures beyond control-rate filtering into continuous audio-rate modulation (e.g. optical vibrato, tremolo, and morphing multi-FX spaces) using direct DSP buffers.
- **Embedded C++ / Faust hardware pedal:** Port the core audio callback and parameter router to a dedicated embedded C++/Faust engine running on a bare-metal microcontroller or Raspberry Pi for a standalone physical pedal enclosure.
- **Polyphonic chord voicing transcription:** Extend Ears from strum timing to polyphonic chord voicing transcription, identifying missed fretboard fingerings and buzzing strings alongside rhythmic timing.

## Charity (be honest)
A teacher for players between lessons or who can't afford them, and hands-free control for players with limited dexterity. [Quote the 2–3 guitarist conversations from the venue as conversations, never as a study.] **We haven't done user studies.** If citing beginners quitting, say it's Fender's claim with no published method.

## Disclosures
- Pretrained models: MediaPipe Hand Landmarker (Google). Coach: Anthropic Claude (claude-sonnet-5-5 / claude-haiku-5-5) via deepagents.
- Reused/adapted: the board helper adapted from azizu06/hackathon-agent-board. Freeverb public-domain tunings. Open-source libraries listed above. Fonts under SIL OFL.
- AI coding agents (Claude Code, Codex, Gemini) wrote much of the code under the team's direction and review.
- Any demo audio not from the live guitar is labeled as replay/simulation (SIM GUITAR / REPLAY on screen).
```
