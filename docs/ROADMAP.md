# Roadmap to submission (Sat Nov 14 → Sun Nov 15, 8 AM ET)

Owner: SM. Written by SM's Claude, Sat 11:30 ET, from the onsite hacker packet (pp. 4–5, 10–18), issue #1, and `main` at 2b9369d. **Status: proposal; SM to sign off, then Angelo merges.** Where this file and BACKLOG.md disagree on *what to build next*, this file wins once merged. BRAND_SPEC.md still owns look and wording, and COACH.md still owns the coach design.

Every agent: read §1 (what we're building), find your row in §5, and work only on that.

---

## 1. What OmniRiff is (one decision, stated once)

**OmniRiff is a guitar teacher that lives in your signal chain.** It hears your guitar through the cable, sees your hands through a webcam, and runs your looper and effects. So it can tell you *why* a passage went wrong and set up the drill that fixes it, while your hands never leave the guitar.

- **Tagline (unchanged):** Never put the guitar down.
- **User:** a guitarist who practises alone (self-taught, or between lessons).
- **Problem:** practice apps can tell you *that* you were late. Only a teacher tells you *why*, and lessons cost money every week. Every tool you own also makes you stop playing to use it.
- **The "ah-ha" (the moment judges remember):** you play a take with a stumble. Riff, the coach, says *"You're late on the change because your strumming hand stops. Keep it swinging."* Then it flies to the looper, loops the bar, takes the effects off, and waits for you to tap the pedal. Your second take shows the gap shrinking, with numbers.

### How the pieces fit (and why it's one product, not two)

Before today the pitch was two products: a hands-free effects controller, and an AI coach. **The coach is the product. The pedal and pinch are how you and the coach share the rig without you letting go.**

| Part | Its job in the one story |
|---|---|
| Audio engine + looper | The coach's hands: it loops the bar, goes dry, records the take |
| Ears (`tools/ears`) | What the teacher hears: strum timing, hesitations |
| Eyes (`vision/eyes.py`) | What the teacher sees: the strumming hand stalling |
| Coach (deep agent) | The teacher: diagnoses the cause, plans the drill, remembers you |
| Riff + dashboard | The teacher's face: shows what it's doing and why |
| Pedal | How you answer ("go", "again") without letting go |
| Pinch | How you shape your tone without letting go (the performance side) |

### Why it beats everything else in the room

| Against | They | We |
|---|---|---|
| Yousician, Rocksmith+, Fender Play | Score the sound against a chart | Find the *cause* by fusing sound with sight of the hand |
| Chat AI coaches (incl. Yousician "June") | Talk about practice | **Act**: operate the looper and effects to run the drill |
| Typical hackathon AI entry | A chat wrapper over an API | An agent with real tools, on a physical rig, that waits for your OK before changing your sound |
| Typical hackathon hardware entry | Sensors and LEDs, no reasoning | Real-time audio + a vision model + an agent, and the music never waits on the AI |

## 2. Tracks: what we enter and what each one needs from us

From the packet. We may enter **one** main track and any number of special tracks. Each special track adds judge visits.

| Track | Prize | What the judges score | Our answer | Needs working |
|---|---|---|---|---|
| **Main: Education** *(recommended, see §2.1)* or Entertainment & Media | Instax / Ray-Ban Meta | Creativity, Utility, Charity, Avidity (below) | "Make learning more interactive, accessible, or personalized": all three, literally | Coach slice 1 |
| **Best Overall** (automatic) | PS5 each | The same four criteria; track winners are excluded | Same pitch | Everything |
| **LangChain: Best use of deepagents** | Switch 2 | "Build a deepagent" | Visible use of the harness: todo plan on screen, Ears/Eyes **subagents**, drills as **skills**, practice journal on the **filesystem**, **memory** of the player, **human-in-the-loop** (pedal approval) | D, E, F |
| **Amazon: Best Practical AI** | $125 pp | Creativity, Usefulness, Technical, UX, 25% each. Focus: agentic, real-world, **adaptive (learns from the user)**, simple | Agent acts on the rig, remembers you between sessions, no screen typing at all | D + memory |
| **Best Physical AI** | $500 | "AI in a physical hardware build" | The AI perceives (camera, guitar signal) **and acts** on a physical rig. Much stronger than "pinch moves a filter" alone | D on hardware |
| **Best Hardware** | Bambu P1S | Creative hardware integration | Pedal + camera + interface + guitar; unplug anything and it keeps playing | Pedal flashed |
| **Peri: Forward Deployed** *(new, conditional)* | Hiring intros | A real business consulted, with name, role and evidence | A guitar teacher or a campus music club. Teacher in the signal chain = homework that runs itself between lessons | A human conversation (§6) |
| Photon (Best Voice Agent) | $300 | Uses Photon 2.0 | Coach texts the drill card after the session | Stretch only: needs a beta signup |
| CoStar, Arlequin, Capital One | — | — | No fit. Skip. | — |

### 2.1 Main track: recommend Education, decided at the midnight gate

The product is now a teacher. "Interactive, accessible, personalized" is our pitch word for word, and a hardware coach will stand out among Education entries, which tend to be chat tutors. Entertainment judges may read a practice coach as off-track. **Rule:** if the coach runs end to end on the real rig by the midnight gate (§4), Angelo switches to Education on Devpost. If not, stay on Entertainment & Media and pitch the instrument. Angelo owns the call; this is SM's recommendation.

### 2.2 The four main criteria, scored honestly

| Criterion | Our answer | Weakness and fix |
|---|---|---|
| **Creativity** | Diagnoses the *cause* by fusing hearing and sight, then operates the rig to run the drill | None, *if the ah-ha is demoed live*. That's why the coach is the centrepiece |
| **Utility** | Before/after numbers from your own takes. The instrument works with every sensor unplugged | Unproven on hardware until tonight |
| **Charity** | Lessons cost money every week and most beginners quit (Fender's own claim, no published method; cite it as such). This is a teacher for those between lessons or who can't afford them. Hands-free control helps players with limited dexterity | **Weakest score.** No evidence yet. Humans: 2–3 guitarist conversations, quoted as conversations, never as a study (§6) |
| **Avidity** | One look, one voice, Riff. Polished Devpost. Concrete next steps | Show we use it ourselves: whoever plays at the table actually practises with it tonight |

## 3. What's done, and what's missing

**Done on `main` (sim-verified, 180 tests):** audio engine, looper, filter/reverb, bypass, limiter; engine with validated control path + `coach` source (#51); launcher `engine.demo`; take capture `--take-dir` (#47); **Ears** TakeReport v1 (#64); **Eyes** HandReport (#40); dashboard + brand + **Riff** drawn, with `OmniRiff.coach.set()` (#56); simulator, virtual guitar, play room, backup video (#62); preflight check, session log, Windows serial fixes. A static dashboard is live at omniriff-dashboard.vercel.app (offline view only).

**Not done, and it's the whole product:**

| Gap | Risk if missed |
|---|---|
| **Coach core (D)**: nothing written; waiting on SM's go-ahead and an API key | Loses deepagents, Amazon, the ah-ha, and the Education argument |
| **Coach feed (E) and dashboard coach layer (F)** | The coach is invisible to judges |
| **V1 pinch = slider**: handed to Joey's side at 08:04Z, unclaimed | The pinch demo feels backwards and glitchy |
| Hand-stall detection on a real webcam: never tried | The "cause" claim. Falls back to Ears-only diagnosis |
| Ears on a real guitar signal: never tried | Diagnosis numbers |
| Hardware: pedal not flashed (B3), no live run yet | Hardware + Physical AI tracks |
| Devpost + demo script still pitch the controller, with the coach as an aside | Story incoherent |

**Stop doing:** new off-label features (gesture vocabulary, scoring, adaptive difficulty, Scene Morph polish, hosting work). Everything in BRAND_SPEC §10 "off the label" stays off.

## 4. Timeline and gates (ET)

| By | Gate | If missed |
|---|---|---|
| **12:30** | Contracts agreed on issue #1: coach feed schema, drill card, TakeReport/HandReport confirmed by SM | Agents build against stubs; contract wins later |
| **15:00** | **Slice 1, in sim:** a rendered take with a planted hesitation → `python -m coach --sim` → diagnosis + drill card + rig set up through `rig_control`, printed in the terminal | Cut Eyes from the diagnosis; Ears only |
| **18:00** | **Slice 2, on screen:** Riff moves and speaks, todo list, cue, drill card, before/after, pedal approval; launched by `engine.demo --coach` | Show slice 1 in a terminal pane beside the dashboard |
| **20:00** | **Software feature freeze for new work.** Memory and voice in or cut. Hardware bring-up starts (Aditya back) | — |
| **00:00** | **Hardware gate:** real guitar → take → Ears → coach → drill, at the table. **Main-track decision (§2.1).** | Stay on Entertainment; coach shown on sim, labelled |
| 02:00 | Rehearsal 1, to time | — |
| 04:00 | Team freeze (bug fixes only) | — |
| 06:00 | Rehearsal 2 + record the video (real rig, or the labelled backup) | Labelled backup video |
| 07:00 | Devpost submitted (Angelo) | Hard deadline 8:00 |

## 5. Work split, by agent

Rules: one agent per row; stay in your files; post `claiming R<n>` on issue #1 before you start; one small PR per item with what's verified and what isn't. If your queue is empty, post `idle`. **Never block on another agent: build against the stub or fixture named in your row.**

### SM's Claude (`sm/claude/`): coach face, feed contract, voice

| # | Task | Files | Done when |
|---|---|---|---|
| R1 | **Coach feed contract** (piece E, first, by 12:30): WebSocket `127.0.0.1:47803`, one JSON message type `coach.frame` with `{state, target, cue, todos[{text,status}], drill_card, before_after, awaiting_approval}`. Post it on issue #1 | `protocol/coach.schema.json`, `protocol/examples.json` | Schema + example + a test that validates the example |
| R2 | **Fake coach feed** in the simulator, scripted from the schema, so F can be built before D exists | `tools/sim/coach.py` | `python -m tools.sim run --demo --coach-sim` drives Riff end to end |
| R3 | **Dashboard coach layer** (piece F): connect to 47803; map frames to `OmniRiff.coach.set`; todo checklist, cue line, drill card, before/after strip (gap ms, tempo stability), approval prompt ("tap pedal to start"); `COACH OFF` when the socket is down | `dashboard/` | Headless Chrome screenshots of every state at 1080p and 720p; 0 page errors |
| R4 | **Voice out** (piece H, half): browser `speechSynthesis` reads each new cue; mute toggle. Voice *in* is cut unless everything else is done | `dashboard/` | Speaks cues in Chrome; silent when muted |

### SM's Codex (`sm/codex/`): coach brain (piece D)

| # | Task | Files | Done when |
|---|---|---|---|
| R5 | **Fixtures first:** render takes with planted mistakes (a 400 ms hesitation at each chord change; a clean take) and matching hand-sample logs with a stall at the same times | `tools/virtual_guitar/`, `coach/fixtures/` | `python -m tools.ears` and `vision.eyes` each flag the planted spots |
| R6 | **Coach core**, `deepagents` + `anthropic:claude-sonnet-5-5` (subagents on `claude-haiku-5-5`): tools `get_rig_state`, `get_take_report`, `get_hand_report`, `rig_control` (UDP, `source:"coach"`), `write_drill_card`, `say`. Subagents Ears and Eyes. Four drill skills (isolate-and-loop, slow-then-speed-up, dry check, keep-the-hand-moving) as skill folders. Journal under `practice/` (gitignored). `rig_control` requires approval, which comes from the pedal (see note). Runs as its own process, watches `--take-dir` for new takes, publishes `coach.frame` per R1 | `coach/`, `coach/requirements.txt` | Slice 1 (15:00 gate) runs on fixtures. Prints the cost and seconds per take. Survives no network: says so and Riff sleeps |
| R7 | **Memory** (Amazon's "adaptive"): a player profile file the agent reads at start and updates at the end ("hand stalls G→C; drill 2 fixed it"). Second session opens with "Last time…" | `coach/` | Two consecutive sim sessions show it |
| R8 | **Before/after:** after the drill take, compare the TakeReports and publish `before_after` | `coach/` | Numbers on the dashboard match `tools.ears` output |

**Approval design (no new contract):** the coach proposes the drill and sets `awaiting_approval`. The player taps the pedal's loop switch, which is what starts recording the drill take anyway. The coach sees `loop.state` go to `recording` in the engine state feed and treats that as the OK. Effects changes wait for that.

**API key:** SM puts `ANTHROPIC_API_KEY` in a local `.env` in each SM worktree. Never committed, never on the board. Check COACH.md §4 for the Sonnet 5.5 quirks (no custom temperature, no forced tool choice).

### Angelo's Claude (`angelo/claude/`): integration, real signals, story

| # | Task | Files | Done when |
|---|---|---|---|
| R9 | **Ears on a real guitar today:** record 3–4 strum takes with a deliberate stumble (phone or laptop mic is fine before the Scarlett), run `tools.ears`, tune thresholds, post the numbers | `tools/ears/` | Findings land on the stumble in real recordings |
| R10 | **Launcher:** `engine.demo --coach` starts the coach process with `--take-dir` wired, and shuts it down cleanly | `engine/demo.py` | Tested like #66 (argv captured) |
| R11 | **Story rewrite to §1** once SM signs off: DEVPOST.md (coach first; Charity per §2.2), DEMO.md §3 (the new script in §7 below), SUBMISSION.md track table (§2), QA.md (agent cost, latency, privacy of takes) | `docs/` | Merged by 20:00 |
| R12 | Coordination and merges; keep BACKLOG.md pointing here | — | — |

### Angelo's Codex (`angelo/codex/`): Windows and reliability

| # | Task | Files | Done when |
|---|---|---|---|
| R13 | W1 Windows scripts (already queued): `setup.ps1`, `start-demo.ps1` with `-Coach` switch once R10 lands | `scripts/windows/` | Syntax-checked, linked from DEMO.md §1 |
| R14 | Engine-side check that `source:"coach"` controls respect the same rate and safety gates; add a coach-disconnect test (coach dies mid-drill → engine unaffected) | `engine/` | Tests |

### Joey's Codex (`john/codex/`): the pinch

| # | Task | Files | Done when |
|---|---|---|---|
| R15 | **V1 pinch = slider. Overdue, demo-critical.** Pinch grabs the current value with no jump, up increases, release holds, re-pinch picks up. `vision.control.Controller(relative=True)` + up-is-more in the play-room bridge | `tools/virtual_guitar/browser_vision.py` (permitted for this) | First pinch, re-pinch, release under front light; stale and confidence gates unchanged |
| R16 | V5 measured FPS and event rate for DEVPOST.md; V2 name the one demo entry point | `vision/README.md` | Numbers with method |

### John's Claude (`john/claude/`): the eyes

| # | Task | Files | Done when |
|---|---|---|---|
| R17 | **Stall detection on a real webcam now:** strum (or air-strum) with a deliberate freeze at a change, log the hand feed, run `vision.eyes`, tune thresholds, post detection rate. Also expose a small helper so the coach gets a HandReport for a take's time window from the live hand feed (47802) | `vision/eyes.py` | Freezes ≥ 300 ms detected on real video; helper tested |

### John's Gemini (`john/gemini/`)

| # | Task | Files | Done when |
|---|---|---|---|
| R18 | V3/V4 only: mark `vision/looper.py` experimental, remove unused imports. **No new features.** | `vision/` | Lint clean |

### Aditya's Codex and Aditya (from 20:00)

| # | Task | Done when |
|---|---|---|
| R19 | B3 Grove polarity, compile and flash, wire two buttons (loop, bypass) | Pedal presses visible on the dashboard |
| R20 | Table rig: camera angle that sees the **strumming** hand (the coach needs it, not only the pinch hand); lighting; cable run | Eyes sees stalls at the table |

## 6. Human-only tasks

| Who | Task | By |
|---|---|---|
| **SM** | Sign off this roadmap; give the coach go-ahead; put the API key in local `.env`s; confirm TakeReport + HandReport fields | **Now** |
| SM | Decide who plays guitar at the table and rehearse the "stumble" take | 20:00 |
| Angelo | Merge this; main-track decision at the midnight gate; Discord usernames on Devpost | 00:00 |
| Anyone free | **Charity + Peri:** talk to 2–3 guitarists and, ideally, one guitar teacher or campus music club officer. One question: "What do you do when a passage keeps going wrong and you don't know why?" Get name, role, and a quote or photo with permission. That satisfies Peri's evidence rule and gives Charity real voices | 18:00 |
| Joey | Wake Joey's Codex for R15 | Now |

## 7. The new 2-minute demo

| Time | Beat |
|---|---|
| 0:00–0:15 | **Problem.** "Practising alone, you know you messed up but not why, and every tool makes you stop playing. Never put the guitar down." |
| 0:15–0:35 | **The rig.** Pedal starts a loop; pinch sweeps the filter over it. Hands never leave the guitar. |
| 0:35–1:20 | **The teacher (the ah-ha).** Play the take with the stumble. Riff thinks (plan on screen; Ears and Eyes run), then: *"Your strumming hand stops at the change."* Riff flies to the loop, sets up the drill, waits. Tap the pedal. Play the drill. Before/after numbers appear. |
| 1:20–1:40 | **It remembers.** Show the journal entry and "Last time…" opening line. |
| 1:40–2:00 | **Safe by design.** Unplug the camera: music keeps playing; the AI never touches the sound without your tap. One honest limitation. |

Track visits get their 20-second angle from §2 on top of this.
