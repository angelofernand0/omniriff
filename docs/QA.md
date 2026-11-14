# Judge Q&A prep

Short, honest answers grounded in the repo. **Bracketed items must be filled with measured results on the Windows laptop, or said out loud as "not measured yet".** Never quote a target as a result.

## The instrument

**How much latency is there?**
[Measured with `python -m tools.latency` loopback: median ± spread ms at block size N / WASAPI.] The engine's own processing is about 0.25 ms per 128-sample block (~9% of the real-time budget, measured on an M1 Pro). Most of the delay is the audio driver's buffers, which is why we measure the whole loop through the interface instead of quoting buffer sizes.

**Why Python for real-time audio?**
The audio callback does only preallocated numpy work: no I/O, no logging, no locks. The camera, AI and network all run in other processes or threads and hand values over through a non-blocking mailbox. We measured the headroom instead of assuming it, and kept a hard rule that nothing slow ever runs in the callback. A native build is the obvious next step if we need lower latency.

**What happens if the camera / pedal / dashboard fails mid-song?**
The music keeps playing. Every input is a separate adapter that can die without touching audio (there are tests for adapter failure and USB disconnect). Bypass is always available from the keyboard. The dashboard shows the failed input as offline instead of pretending it's still live.

**Can strumming accidentally move the filter?**
Gesture control only acts while you pinch (a clutch with hysteresis), and it only arms after it has seen an open hand, so picking up the pick doesn't engage it (tested: 0 false events over 60 frames of strumming with a pick held). It rejects low-confidence frames, tracks one specific hand and fails closed on big jumps. On the engine side, stale, duplicate, malformed or low-confidence events are dropped before they reach audio.

Honest limit: if you show an open hand and *then* grab the pick and strum, the clutch is engaged and strumming moves the filter (a test reproduces it: 15 unintended moves in one second). StrumGuard, which mutes control inside the guitar zone, removes all of them in the tests. [Say whether StrumGuard is on in the demo path; today it's only in the experimental `python -m vision.spatial` mode.] On stage: release the pinch before you start strumming.

**What effects are there?**
A smoothed low-pass sweep, a Freeverb-style reverb, a 30-second looper, a click-free bypass, an optional noise gate and a peak limiter so loud stacks don't distort.

## The AI

**What does the AI actually do?**
A pretrained hand-landmark model (Google's MediaPipe Hand Landmarker) finds 21 hand points per frame. Our code turns them into a deliberate gesture: pinch to engage, then height controls the effect, and Scene Morph blends filter + reverb from one hand position. [Coach: a LangChain deep agent that analyzes takes between performances and runs drills, if shipped; otherwise say it's in progress.]

**Did you train the model?**
No. It's pretrained, and we say so. Our work is the real-time control system around it: clutching, confidence gating, smoothing, tracking the right hand, rate-limiting and safe failure.

**How accurate is the gesture tracking?**
[Measured FPS and control update rate from vision on the demo laptop.] We haven't measured landmark accuracy ourselves, and the confidence number we gate on is MediaPipe's handedness score, not an accuracy measure. In practice lighting matters most: light the hand from the front.

**Where's the "agent" in the coach?** *(deepagents track)*
[If shipped: the deep agent plans a drill, reads take timing ("Ears") and hand-movement reports ("Eyes"), and acts on the rig through the same validated control path as every other source (`source: "coach"`). The instrument never waits on it.] If not shipped, say what exists: take capture, hand-movement analysis and the coach control source are built and tested; the agent core is in progress.

## The coach

**What does a coaching session cost, and how slow is it?**
[Measured: $ per take and seconds from take end to diagnosis, from coach/workspace/usage.jsonl.] The budget is capped (it refuses new runs above $8 and says it's out of credit). The instrument never waits on it: the coach works between takes, not inside the audio path.

**What happens to my recordings?**
Takes and the practice journal stay on the laptop (`runs/takes`, `coach/workspace/`; both git-ignored). Only the coach's text analysis requests go to the model API; we don't upload video, and camera frames never leave the machine. [Confirm what the coach actually sends once it ships.]

**Can the AI mess up my sound mid-song?**
No. It proposes a change, and nothing happens until you tap the pedal or press Y. Its actions go through the same validation gate as every other control (stale, duplicate and malformed actions are dropped), and bypass is always yours.

**How do you know the diagnosis is right?**
Every claim comes from a measured number: Ears' gaps from the audio, Eyes' stalls from the hand. The coach shows before/after numbers from your own takes. [Report how it did on the planted-mistake take and on real takes.] No number, no claim.

What's tested so far, all on our synthetic guitar (the same model Ears was tuned on, so it says nothing yet about real takes): every strum and every planted pause found at 80, 120 and 160 strums a minute, within 15 ms. Two takes recorded through the real engine come out with the second pause smaller, as a before/after should. It still holds with mains hum, a -40 dBFS noise floor, clipping, DC offset, a dark pickup, and input as quiet as -30 dBFS. Known limits: a noise floor as loud as -30 dBFS halves strum recall, and an intended rest looks like a hesitation.

## Impact

**Who is this for?** *(Amazon / accessibility)*
Guitarists whose hands are busy, and especially players with limited mobility or dexterity, for whom small knobs or precise stomps are a barrier. Control moves to a hand gesture and a foot press.

**Have you tested with disabled players?**
No. We haven't done user studies, and we won't claim them. It's the clear next step.

**Why does this matter beyond guitar?**
The same safe pattern works for any instrument or creative tool where your hands are occupied: a perception model driving a real-time system with a clutch, confidence gates and a manual override.

## Process

**How did a team build this much in a weekend?**
Each of us directed AI coding agents (Claude Code, Codex, Gemini). They coordinated through a GitHub-issue message board, with owner-scoped folders, versioned JSON contracts and PRs merged only when CI passed. We disclose that on Devpost. The architecture, contracts and review were ours.

**What would you do with another week?**
Measure and cut latency (native audio path or ASIO), run user testing with players with limited mobility, add audio-rate modulation (vibrato/tremolo) as real DSP, and finish the coach.

**What's the biggest limitation right now?**
[Pick the honest one after the hardware run: e.g. latency on this laptop, tracking in poor light, or the coach being partial.]
