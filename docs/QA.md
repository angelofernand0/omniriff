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
Gesture control only acts while you pinch (a clutch with hysteresis). It rejects low-confidence frames, tracks one specific hand, fails closed on big jumps, and StrumGuard mutes control inside the guitar zone. On the engine side, stale, duplicate, malformed or low-confidence events are dropped before they reach audio.

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
