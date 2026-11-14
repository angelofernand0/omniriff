# Overnight backlog (2026-11-14)

This is the priority queue for when an agent finishes its current task. Angelo set it up for continuous overnight work while the humans sleep. Angelo's Claude keeps it current and merges green PRs under Angelo's overnight authorization.

**How to use it**
1. Take the first unclaimed item **in your own area** (see TEAM.md). Post `claiming B<n>` on issue #1 before starting.
2. One small PR per item. Run the tests, post the PR link and an honest summary of what's verified and what isn't.
3. Done, or blocked on hardware or a human? Post it and move to your next item. Don't sit idle waiting for replies.
4. If your area is empty, post `idle` on issue #1. Angelo's Claude will hand you something.
5. Don't touch the "Waiting on Angelo" list below, or another owner's files.

**Deadline shape:** all software plus most of the pitch done by **8 PM Saturday** (hardware bring-up starts when Aditya is back), then Devpost by 8 AM Sunday. Angelo approved entering every track we can credibly win: Entertainment & Media (main, final), Physical AI, Hardware, LangChain deepagents and Amazon Practical AI. See the table in docs/SUBMISSION.md.

## Demo-critical

| # | Area / owner | Task | Done when |
|---|---|---|---|
| ~~B1~~ ✅ #39 | engine/ — Angelo's Codex | **Preflight check**: `python -m engine --check`. List audio devices (flag the Focusrite and its input count), check ports 47800/47801/47802/8080 are free, list serial COM ports (flag the likely Arduino), check required packages, and print a pass/fail table with exact fix hints. No audio is opened. | Runs on macOS in CI-safe mode, unit tests for the checks, README section. Windows run unverified. |
| ~~B2~~ ✅ #42 | engine/ — Angelo's Codex | **One-command demo launcher**: `python -m engine.demo` starts the engine (live, or `--headless`/`--replay`), serves the dashboard and prints the URL. Optionally it starts vision as a child process (`--vision`), with clean shutdown of everything on Ctrl-C. Ports come from one place. | Headless smoke test passes, clean shutdown is tested, README. |
| B3 (draft merged #5; polarity + flash pending, Aditya 8 PM) | firmware/arduino/ — Aditya's Codex | **Grove variant**: MLH lends Grove Base Shields + Grove buttons. Grove Button modules are typically **active-HIGH** (the module pulls down; pressed = HIGH), but the sketch assumes active-LOW with INPUT_PULLUP. Add a compile-time polarity option (`kActiveLow`), document Grove D2/D3 wiring in docs/HARDWARE.md, and keep the serial format unchanged. Verify the polarity claim against the actual module's docs or label it as an assumption. | Sketch builds in both modes (or is marked not compiled), HARDWARE.md has both wirings. |
| ~~B4~~ ✅ #37 | audio/ — Angelo's Claude | **Level check for the Solo gain knob**: `python -m audio --level-check` listens to input 2 for ~10 s and reports the peak/RMS dBFS with advice (turn up / good / turn down; aim around −12 dBFS peak), without starting the full engine. | Unit-tested analysis function, README. Live run on the Solo pending. |
| ~~B5~~ ✅ #38 | docs/ — Angelo's Claude | **Demo runbook** `docs/DEMO.md`: a single morning sequence. Hardware checklist → `--check` → level check → latency loopback → engine/dashboard/vision commands → the 2-minute script → fallbacks (keyboard controls, `--replay`, virtual guitar). Links to MANUAL.md and SUBMISSION.md. | Merged. Each command checked to exist on main. |
| ~~B6~~ ✅ #38 | docs/ — Angelo's Claude | **Devpost draft** `docs/DEVPOST.md`: all the Devpost sections, built-with list, disclosures, and placeholders for measured numbers (no invented results). For Angelo to edit. | Merged as a draft. |
| ~~B7~~ ✅ #13/#46 | vision/ — Joey's Codex | **Merge-readiness for PR #13**: rebase on main, a short demo-table calibration section (camera placement, lighting, the one command to run), and a list of exactly what the morning hardware check must confirm. Then it's ready for Angelo's test. | PR #13 updated; checklist posted on issue #1. |
| ~~B8~~ ✅ #56/#60 | dashboard/ — SM's Claude | **Demo-table polish**: verify at the projector's likely resolution, add a visible 'SIMULATED'/'REPLAY' banner when the source isn't live hardware (whatever the state already exposes), and make sure a dashboard reload mid-demo is clean. No protocol change. | Screenshot check posted, PR merged. |
| ~~B9~~ ✅ #53 | tools/ — SM's Codex | **Playable demo** (in progress), then document how to use it as the **labeled** backup if the hardware fails at the table. | PR merged; DEMO.md fallback section links to it. |

## Pitch and tracks

| # | Area / owner | Task | Done when |
|---|---|---|---|
| B14 | coach/ — SM (Claude/Codex) | **Deepagents coach is approved.** Post the final split and contracts from docs/COACH.md §7 on issue #1, then build against tools/sim + virtual_guitar. The instrument never waits on it, and the coach is a separate process. Pieces that touch audio/ (take capture) or engine/ (a coach control source) are requested from those owners on the board, not edited directly. | Split posted; first coach PR. |
| ~~B15~~ ✅ #38 | docs/ — Angelo's Claude | Fold **track angles** into DEVPOST.md: a 20-second pitch each for Physical AI, Hardware, deepagents and Amazon Practical AI (accessibility use case + target user), plus the Amazon 'basic documentation' requirement (link the READMEs). | Merged. |
| B16 | tools/ — SM's Codex | **Labeled backup video plan**: a script that records the dashboard + processed audio from the virtual-guitar or replay demo into a clip, clearly marked SIMULATED, as a fallback for the optional ≤2-min Devpost video. The real hardware video gets recorded after 8 PM. | Script + README; sample clip not committed. |

## Next, if the above are done
- B10 (engine/): a structured JSONL session log (state snapshots + accepted controls, opt-in) so a demo run can be replayed or analyzed later. No audio samples.
- ~~B11~~ ✅ #41 noise gate.
- ~~B12~~ ✅ #32 StrumGuard/DualAxis.
- ~~B13~~ ✅ #36 manual checks.

## Coach pieces (docs/COACH.md §7) — status
| Piece | Owner | Status |
|---|---|---|
| A Take capture | Angelo's Claude | ✅ #47 (`--take-dir`, WAV + JSON sidecar) |
| B Ears analysis | John's Claude (SM's Codex was idle) | In progress: `tools/ears/`, TakeReport fields to be agreed with SM on issue #1 |
| C Eyes analysis | John's Claude | ✅ #40 (`vision/eyes.py`, HandReport; SM to confirm shape) |
| D Coach core, E coach feed | SM's Claude | Open: needs SM's go-ahead + a local Anthropic API key; feed socket proposed at 47803 |
| F Dashboard layer/avatar, H voice | SM | Riff design ✅ #56 (`OmniRiff.coach.set`); wiring open |
| G Live layer | First free agent after B + C | Open |
| I Coach control source (engine/ + protocol) | Angelo's Claude | ✅ #51 (`source: "coach"`, `sources.coach`) |

## engine/ follow-ups (Angelo's Codex)
- ~~B17~~ ✅ #50. `--headless` paced blocks with `stop.wait(block/sr)` and runs at ~55% of real time on macOS, so headless replays and takes stretch. Pace against a monotonic deadline instead. Live audio is unaffected.

## Waiting on Angelo (don't start)
- **Photon**: stretch only, and needs a human to sign up for the beta.
- Any change to protocol/ control or state schemas beyond what's already agreed on issue #1.
