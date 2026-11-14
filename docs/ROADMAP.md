# Roadmap to submission (Sat Nov 14 → Sun Nov 15, 8 AM ET)

Owner: SM. Written by SM's Claude, Sat 11:30 ET, from the onsite hacker packet (pp. 4–5, 10–18), issue #1, and `main` at 2b9369d. **Status: SM signed off (11:45); Angelo merges.** The coach build spec for agents is [COACH-BUILD.md](COACH-BUILD.md). Where this file and BACKLOG.md disagree on *what to build next*, this file wins once merged. BRAND_SPEC.md still owns look and wording, and COACH.md still owns the coach design.

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

### 2.0 How we stand out in "Best use of deepagents"

Most deepagents entries will be research or report agents in a terminal. Ours runs on a physical instrument, reads sound *and* sight, and acts on the world, and every harness feature has a job the judges can watch:
- **Planning:** the todo list is the checklist on screen.
- **Subagents:** Ears and Eyes run in parallel with their own context and a cheaper model; the activity strip shows them working.
- **Skills:** the drill library, opened by name only when needed; optionally growing per player (R7b).
- **Filesystem:** a practice journal the judges can open.
- **Memory:** "Last time…" in the next session.
- **Human-in-the-loop:** approval is a pedal tap, so the guitar stays in your hands.
- **Observability:** the LangSmith trace of the take we just played (R6c).

The biggest risk is not the idea but a flaky live run. Reliability beats one more feature: cached voice, budget stop, a coach that sleeps instead of crashing, and a labelled fixture replay if the room's Wi-Fi dies.

### 2.1 Main track: Education recommended; the team decides together in person

The product is now a teacher. "Interactive, accessible, personalized" is our pitch word for word, and a hardware coach will stand out among Education entries, which tend to be chat tutors. Entertainment judges may read a practice coach as off-track. **Proposed rule for the huddle:** if the coach runs end to end on the real rig by the midnight gate (§4), enter Education; if not, stay on Entertainment & Media and pitch the instrument. This is SM's Claude's recommendation for the team's in-person discussion. No agent changes the track.

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
| **Coach core (D)**: nothing written yet; go-ahead and API key given 11:45, spec in COACH-BUILD.md | Loses deepagents, Amazon, the ah-ha, and the Education argument |
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

SM's two agents split the coach evenly (about 8–9 agent-hours each): **Codex builds the brain** (Python, `coach/`), **Claude builds the face and the voice** (contract, dashboard, Riff, speech). They meet at one contract, R1, which Claude writes first.

### SM's Claude (`sm/claude/`): the coach's face, voice and contract

| # | Task | Files | Guess | Done when |
|---|---|---|---|---|
| R1 | **Coach feed contract** (piece E, first, by 12:30). WebSocket `127.0.0.1:47803`, served by the coach. Coach → dashboard: `coach.frame {state, mood, target, cue, todos[{text,status}], drill_card, before_after, awaiting_approval, journal_path}`. Dashboard → coach: `coach.approve` and `coach.reject`. Post it on issue #1 | `protocol/coach.schema.json`, `protocol/examples.json`, test | 45 min | Schema + examples + a validating test |
| R2 | **Fake coach feed** in the simulator, scripted from the schema (one full session: listen → think → cause → drill → approve → pleased), so the dashboard is built before the brain exists | `tools/sim/coach.py` | 1 h | `python -m tools.sim run --demo --coach-sim` drives Riff end to end |
| R3 | **Dashboard coach layer** (piece F): connect to 47803; map frames to `OmniRiff.coach.set`; plan checklist, cue line, drill card with skill name and journal path, before/after strip (worst gap ms, hesitations, tempo stability), "Tap the pedal to start" prompt with `Y`/`N` keys sending `coach.approve`/`coach.reject`; an **activity strip** (the frame's `activity`: `EARS get_take_report ✓`, `EYES get_hand_report …`, `COACH open skill keep-the-hand-moving ✓`) so the harness is visibly at work; `COACH OFF` when the socket is down | `dashboard/` | 2.5 h | Headless Chrome screenshots of every state at 1080p and 720p; 0 page errors |
| R3b | **Riff's expressions** (SM asked: "really feels good"). Riff already blinks, glances and squashes. Add an expression system driven by a new `mood` field: **independent lids** (wink: one-eye blink when asking for approval or after a pass), **lid shapes** (happy arcs = proud, flat squint = concentrating while listening, wide = "aha" when a finding lands, inner-corner tilt = concerned when it names a mistake, heavy = sleepy), **saccades** (quick eye darts with a small overshoot and settle, not smooth slides), **pupil size** (dilate on aha, contract when concentrating), **double blinks** and blink-on-turn (blink when the gaze jumps far, as people do), **look at the player** (eyes straight out, toward the camera) when speaking, and small **reactions to real signals** (an eye pop on a big input peak, a widen on loop record). Ease everything with springs. Idle life (blinks, glances) is fine; anything larger must come from a real event (BRAND_SPEC §8). Update `?coach=preview` and `/brand.html` with every mood. Study 2–3 references first (e.g. Anki's Vector/Cozmo eyes, Eilik desk robot, Pixar's Wall-E eye acting) and post a one-paragraph direction before polishing | `dashboard/riff.js`, `riff.css`, `brand.html` | 2.5 h | SM watches `?coach=preview` and approves the feel |
| R4 | **Riff's voice** (piece H), **ElevenLabs by default** (SM's call: the browser voice is too robotic). `coach/voice.py` (mine; SM's Codex calls `voice.speak(text)` from the `say` tool): ElevenLabs `eleven_flash_v2_5` (about 0.27 s per cue, measured), the voice SM picks from the samples in `omniriff-notes/riff-voices/`, key `ELEVENLABS_API_KEY` from the same `.env` as the Anthropic key, **cache every cue's MP3 by text hash** on disk (rehearsals repeat cues, and the free plan has a monthly character quota we can't read with this key), sent as `coach.audio` (PR #71). Dashboard: play it when its text matches the cue; Riff "talks" with a squash pulse driven by the audio's real loudness (Web Audio analyser), not a fake loop. Fallback: the browser voice, if audio doesn't arrive within 1.5 s or there's no network. Mute toggle. Free plan facts: only ElevenLabs' default voices work through the API, and the free tier asks for attribution (Devpost disclosure) | `coach/voice.py`, `dashboard/` | 1.5 h | Cues spoken in the chosen voice; second time from cache; fallback works with Wi-Fi off |
| R4b | *Stretch, after 20:00 only if everything above works:* voice **in**: hold the bypass pedal (or press `V`) to talk; the browser's speech recognition sends the text as a user message to the coach. Kept out of scope by default because a loud guitar confuses it, Chrome's recognition needs internet, and the pedal already answers yes/no | `dashboard/` | 1 h | — |

### SM's Codex (`sm/codex/`): the coach's brain (piece D)

**Build from [COACH-BUILD.md](COACH-BUILD.md), step by step.** It pins `deepagents==0.7.38` and gives the exact `create_deep_agent` call, tools, subagents, skills, memory, backend, approval flow and tests. Start with its §1 smoke test.

| # | Task | Files | Guess | Done when |
|---|---|---|---|---|
| R5 | **Fixtures first:** render takes with planted mistakes (a 400 ms hesitation at each chord change; a clean take; the same pattern "after the drill" with a 120 ms gap), each with a take sidecar and a matching hand log with a stall at the same times | `tools/virtual_guitar/`, `coach/fixtures/` | 1 h | `python -m tools.ears` and `vision.eyes` flag the planted spots |
| R6 | **Smoke test, then coach core** per COACH-BUILD §1–§8: model, six tools, Ears/Eyes subagents, workspace backend, `interrupt_on` for `rig_control`, feed publishing per R1, runner watching `--take-dir` | `coach/` | 4 h | Slice 1 (15:00 gate) on `--fixtures`; cost and seconds per take posted |
| R6b | **Four drill skills** as `SKILL.md` folders (COACH-BUILD §4) | `coach/workspace/skills/` | 45 min | Smoke test lists them; the agent opens the right one for the planted hesitation |
| R6c | **LangSmith tracing** (LangChain's own observability; free tier). Set `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=omniriff-coach` in the local `.env`; deepagents runs on LangGraph, so traces appear with no code change (**verify** one run shows the coach → ears/eyes subagent tree). For the LangChain judges: open the trace of the take we just played. Needs SM's LangSmith key (§6). Never on in CI | `.env` only, a README line | 15 min | One trace link posted on issue #1 |
| R7 | **Memory:** `player.md` loaded with `memory=`, updated by the agent; second session opens with "Last time…" | `coach/` | 45 min | Two consecutive runs show it |
| R7b | *Stretch, after slice 2:* **skills that learn.** When a drill works for this player, the agent writes a short "what worked for you" note into a player-specific copy of that skill (`/skills/<name>-for-you/SKILL.md`), so the drill library grows from the player's own takes | `coach/` | 45 min | Second session picks the personal skill |
| R8 | **Before/after:** `compare_takes` + `before_after` frame + `pleased` when it improved | `coach/` | 45 min | Numbers match `tools.ears` output |
| R8b | **Tests without network** (COACH-BUILD §10) and the budget guard ($8 stop) | `tests/`, `coach/budget.py` | 45 min | CI green |

**Approval design (no new engine contract):** the coach proposes the rig change and sets `awaiting_approval`. The player taps the pedal's loop switch, which starts recording the drill take anyway; the coach sees `loop.state` go to `recording` and approves. `Y` on the dashboard (R1/R3) also approves. Details in COACH-BUILD §6.

**API key: done.** SM's key is in a gitignored `.env` in SM's checkouts and in `~/.config/omniriff/.env`, and COACH-BUILD §0.5 loads both. Other agents don't need it: they build against stubs and fixtures. The demo laptop gets it in person at bring-up (never via the board or the repo: the repo is public). The key holds about $10; the coach stops itself at $8.

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

### Coach piece G, the live layer (approved by SM 11:55; start now)

Feedback *while* you play, not only between takes, and real events for Riff to react to. Conditions: the state field is **optional and additive**, its exact shape is agreed on issue #1 before code depends on it; the **audio callback does no new work**; the coach brain doesn't depend on G; **ships by the 20:00 freeze or is dropped**.

| # | Owner | Task | Files | Done when |
|---|---|---|---|---|
| R21 | Angelo's Claude | Lock-free snapshot of the last ~2 s of **dry** input, copied outside the audio callback (the callback only advances a write index, as take capture does) | `audio/` | Unit test; callback timing unchanged |
| R22 | Angelo's Codex (after R13) | Run `tools.ears` onset detection on that snapshot at ~10 Hz off the audio thread; add optional state `live: {strums_last_s, last_strum_ms, steady}` (shape agreed on the board first) | `engine/`, `protocol/state.schema.json` | Schema test; sim shows strums |
| R23 | SM's Claude | STRUM / STEADY LEDs on the faceplate; Riff reacts to real strums (small eye pop) and squints while it listens | `dashboard/` | Visible on `tools.sim run --demo`; 30–60 min |

### Joey's Codex (`john/codex/`): the pinch

| # | Task | Files | Done when |
|---|---|---|---|
| R15 | **V1 pinch = slider. Overdue, demo-critical.** Pinch grabs the current value with no jump, up increases, release holds, re-pinch picks up. `vision.control.Controller(relative=True)` + up-is-more in the play-room bridge | `tools/virtual_guitar/browser_vision.py` (permitted for this) | First pinch, re-pinch, release under front light; stale and confidence gates unchanged |
| R16 | V5 measured FPS and event rate for DEVPOST.md; V2 name the one demo entry point | `vision/README.md` | Numbers with method |

### John's Claude (`john/claude/`): the eyes

| # | Task | Files | Done when |
|---|---|---|---|
| R17 | **Give the coach the strumming hand.** Today the hand feed (47802) carries only the one tracked control hand, but stalls happen in the *strumming* hand. (a) `python -m vision --hand-log PATH` appends one JSON line per frame: `{"timestamp_ms": <unix wall clock>, "hands": [{"handedness": "Left"\|"Right", "wrist": [x, y], "confidence": c}]}` for every detected hand. (b) `vision.eyes.report_for_window(log_path, start_unix_ms, end_unix_ms, take_id, hand="strum")` returns a HandReport for exactly that take, using the take sidecar's `started_unix_ms`/`ended_unix_ms`. (c) **HandReport amendment (additive):** add `take_id`, `started_unix_ms`, and per stall `start_ms`/`end_ms` measured from the take start, the same time base as TakeReport's `at_ms`, so the coach can line a stall up with a hesitation. (d) Try it on a real webcam now: strum or air-strum with a deliberate freeze; post the detection rate | `vision/__main__.py` (or the demo entry point from V2), `vision/eyes.py`, `protocol/` note | Freezes ≥ 300 ms detected on real video; `report_for_window` tested on a fixture log |

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
| ~~SM~~ | ~~Sign off; coach go-ahead; API key; confirm report fields~~ | **Done 11:45.** TakeReport v1 confirmed as is. HandReport needs the additive amendment in R17(c) |
| ~~SM~~ | ~~ElevenLabs key~~ | **Done 11:55**, tested (default voices work on the free plan) |
| SM | Pick Riff's voice: four samples in `omniriff-notes/riff-voices/` (outside the repo) | 14:00 |
| SM | A free LangSmith account and API key for R6c (smith.langchain.com), into the local `.env` | 15:00 |
| SM, in person | If R15 (pinch slider) is still unclaimed by **17:00**, raise it with Joey | 17:00 |
| **Whole team, in person** | **Who plays guitar at the table** (and rehearses the stumble take), and **Education vs Entertainment** (§2.1). Discussed together, not decided by any agent | Next team huddle, before 20:00 |
| Angelo | Merge this; Discord usernames on Devpost; record the main-track choice from the huddle at the midnight gate | 00:00 |
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
