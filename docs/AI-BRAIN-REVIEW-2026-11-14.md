# AI brain review — 14 November 2026

Reviewer: SM's Codex. Scope: Sol's R5–R8 implementation and the approved coach roadmap, with current board decisions. Reviewed against fetched main through `368154c`; the coach core files are identical to local `7d79dbf`. This is a review, not an implementation patch or a claim of live-model quality.

## Verdict

The Deep Agents foundation is real and worth keeping. It is not ready to sign off as the product's reliable teacher. The largest gaps are correct drill evaluation, state-aware rig actions, budget enforcement, and demonstrated model behavior. Adding more agents would not address them.

The roadmap supersedes the older README/architecture pitch: the teacher is the product. A convincing LangChain entry must show a complete measured lesson, with the harness doing useful work throughout. The team's roadmap quotes the sponsor requirement as “Build a deepagent”; the additional harness demonstration criteria are our product strategy, not independently verified judging rules.

## What was verified

- Read AGENTS.md, README.md, TEAM.md, ARCHITECTURE.md, ROADMAP.md, COACH.md, COACH-BUILD.md, coach implementation, skills, tests, the board issue and recent handoffs. Verified GitHub identity as `smcogburn`.
- Reviewed pinned installed versions: `deepagents 0.7.38`, `langchain 1.5.0`, `langchain-anthropic 1.7.10`, `langgraph 1.2.22`, including relevant installed harness implementation.
- All **27 existing coach tests passed** with localhost access and optional coach dependencies installed. The first sandboxed attempt could not open the localhost services and stalled; that specific process was stopped before reporting the successful rerun. The passing run emitted a socket ResourceWarning.
- Exercised the **actual compiled Deep Agents graph**, replacing only model responses with deterministic offline responses: parallel `task` calls to Ears/Eyes succeeded; the skill file was read; a drill card was persisted; `rig_control` interrupted before sending; approval executed one action; `edit_file` persisted player memory; final todos were available. No tool errors occurred in this path.
- Negative probes reproduced silence being scored as improvement, mutable measured reports, a turn exceeding the local budget estimate, a dry-check turning bypass off, and a loop command cancelling a just-started recording.
- No Anthropic or ElevenLabs requests, real webcam capture, or real rig control were made. The offline graph test proves wiring, not autonomous diagnosis or skill choice.

Reproduction script from this review: `/private/tmp/omniriff-ai-review.TPGoUc/audit.py`. Run using this checkout's `.venv/bin/python`. It uses disposable directories, scripted model responses, a fixture-only rig client and an in-memory audio engine. Temporary artifacts are not a permanent regression suite.

## Findings, in implementation order

### 1. P1 — The coach can celebrate silence as improvement

Locations: `coach/tools.py:23–27,65–81`; `coach/runner.py:224–237`.

An empty onset list becomes a zero worst gap. A before report with a 900 ms gap and one hesitation compared with silence produced `worst_gap_ms=[900,0]`, `hesitations=[1,0]`, `tempo_stability=[1,0]`, **`improved=true`**. The runner then forces `pleased/proud` and stores that comparison in memory.

The runner also compares every consecutive take without knowing whether the second belongs to the proposed drill, whether it covers the same passage, or whether the player changed tempo. `pass_rule` is display text, not an evaluated condition. The hand-moving skill's hand criterion is never part of the deterministic pass result.

Fix: require enough valid onsets and comparable coverage; retain an explicit baseline and active drill; evaluate the relevant timing excess/stability and hand evidence, with an insufficient-evidence outcome. Do not declare success merely because an absolute inter-strum gap shrank.

Status at publication: Angelo's Claude has merged additive TakeReport fields `judgeable` and `min_strums` in PR #97. The coach still ignores these fields, so the reproduced false success remains possible until the coach comparison gate uses them.

Acceptance: silence, a single strum, a shortened passage, a rejected drill and a faster but relatively worse performance cannot pass; a valid matched improvement can.

### 2. P1 — Approved rig actions can do the opposite of the lesson

Locations: `coach/workspace/skills/dry-check/SKILL.md:8`; `coach/tools.py:143–149`; `coach/rig.py:19–35,48–56`; `coach/runner.py:131–157`.

`bypass` and `loop` are **toggles**, but the tool description does not explain their state transitions and the dry-check skill unconditionally requests bypass. Reproduction with the real in-memory engine: an already-dry rig went from `bypass=true` to `false`.

Pedal approval is a transition into recording. If the pending approved action is `loop`, the coach then toggles the same loop again. Reproduction: `recording -> idle` when no audio had yet arrived; with recorded samples the same toggle finishes the take. The player's approval can therefore terminate the drill recording it just started.

`RigStateReader` also retains its last frame indefinitely across disconnects, and sending UDP is reported as success without observing the resulting state.

Fix: expose explicit intent and prerequisites to the model; check fresh state again at execution; account for the action already performed by the approval pedal; verify the resulting state. Preserve the existing engine contract unless its owner agrees to an extension.

Acceptance: repeated “go dry” is harmless, pedal approval does not stop recording, disconnected/stale state cannot be mistaken for current state, and a dropped/rejected control is not reported as applied.

### 3. P1 — The budget guard is not an in-run limit

Locations: `coach/runner.py:167–194`; `coach/budget.py:37–50`; `coach/agent.py:55–56`.

The ledger is checked once before a whole coaching turn and updated only in `finally`. That turn can contain many parent calls, specialist calls and approval resumes. No check stops these calls as spending accumulates. The $2 reserve is not an enforced maximum turn cost.

The real graph test used eight scripted parent responses with synthetic usage metadata. It completed and logged **$12** against an $8 limit. This is a deterministic accounting reproduction, not actual spending or a provider price estimate.

Fix: enforce a shared call/token budget around every parent and specialist model invocation and resume, reserve in-flight calls, record usage incrementally, and bound request time/retries. Keep the ledger outside model-writable storage. A provider account limit remains separate from the application's estimate.

Acceptance: a sequence that crosses the allowed budget stops before another call, including parallel specialists and post-approval resumes; restart cannot erase already-accounted use.

### 4. P1 — The current evidence does not establish autonomous coaching quality

Locations: `tests/test_coach_core.py:145–169,174–196`; `.github/workflows/checks.yml`; `requirements-dev.txt`.

The end-to-end tests prescribe the answer in `FakeAgent`: it chooses the skill, manufactures the interrupt and invokes the rig directly. They do not test whether the actual model delegates correctly, reads the right skill, grounds its diagnosis, honors rejection, or adapts the next lesson. CI installs requirements-dev.txt, not coach/requirements.txt, so the harness/runner tests guarded by `find_spec` are skipped in that job.

The new offline graph probe fills part of this gap: the real harness can perform the intended operations when supplied appropriate model outputs. It does not establish that Sonnet/Haiku will choose those outputs. The board's earlier smoke test only verified basic tools, file access and planning. The full live coaching fixture run was not completed.

Fix: add a dedicated optional-dependency CI job running the real graph with deterministic model outputs. Separately run a bounded live-model evaluation set with machine-checkable evidence and tool outcomes. Retain selected tool inputs/outputs and timing/usage as evaluation artifacts; do not substitute polished scripted dialogue for these results.

Acceptance: planted hesitation plus aligned stall; timing issue without camera; hand stall outside the audio gap; intentional rest/ambiguous evidence; clean take; insufficient data; reject/timeout; state change during approval; improved matched take; restart with remembered progress. Measure diagnosis support, skill suitability, tool correctness, approval behavior, completion time and actual reported token use. Repeat the primary demo case to expose variability.

### 5. P2 — Measured evidence is writable by the coach

Location: `coach/agent.py:52–78`.

The main agent has unrestricted write/edit access inside the same filesystem that holds reports, instructions, skills and, in real mode, usage.jsonl. Virtual mode confines paths but does not make evidence immutable. An actual graph `edit_file` call changed the stored measured interval from 900 ms to 100 ms successfully. Subsequent report tools trust those files.

Fix: make take/hand reports, standing instructions, skills and accounting read-only to model tools; allow controlled writes to journal and player memory. LangChain supports filesystem permissions and separable backends. Specialist filesystem tools are already restricted appropriately.

Acceptance: model attempts to rewrite evidence, policy, a skill or the ledger fail; journal and approved memory writes continue to work.

### 6. P2 — Restart reprocesses historical takes

Locations: `coach/runner.py:129,246–262`.

Processed paths are kept only in a new in-memory set. Restarting the coach with an existing take directory analyzes and pays to coach every historical take again, potentially proposing rig changes while the player is doing something else. A file is also marked seen before processing succeeds, so a transient failure is not retried during that process.

Fix: persist a processed-take identity/cursor, define explicit replay behavior, and distinguish retryable failure from completed evaluation.

Acceptance: restart processes only new takes; deliberate replay is labeled; transient failures can be retried without duplicate rig effects.

### 7. P2 — Real AI on synthetic input is mislabeled “NOT AI”

Locations: `coach/__main__.py:49`; `dashboard/coach.js` scripted-label rendering; `coach/README.md`.

`--fixtures` invokes the real model but passes `scripted=true`; the dashboard renders “SCRIPTED · NOT AI.” The code deliberately conflates synthetic sensor input with scripted reasoning. That would misdescribe the hardware-free LangChain demo.

Fix with SM's Claude: distinguish input provenance from agent provenance. A real model using synthetic takes should say “AI coach · synthetic input”; the canned fallback should stay clearly scripted. Any feed schema change needs coordination.

### 8. P2 — The plan is not shown while the agent plans

Location: `coach/runner.py:176–181`.

Todos are published only after `invoke` returns or interrupts. During the diagnosis and skill-selection work, the dashboard cannot show the actual evolving plan. Activity entries are generated by report tools and often marked done before specialist interpretation finishes, so they are not a complete agent execution trace.

Fix: publish relevant plan/tool lifecycle updates from graph streaming or middleware, retaining the agreed full-frame UI contract. Show observed actions and outcomes, not generated pretend progress.

## Cross-owner integration gaps

**R17 remains absent from reviewed main.** `vision.eyes.report_for_window` does not exist, and the vision CLI rejects `--hand-log`. I verified argument rejection before any camera/model access. The coach's graceful unavailable fallback is appropriate, but real webcam/audio fusion is not functional yet. The documented `engine.demo --coach --vision --hand-log ...` path passes an unsupported flag to the vision child. This is the existing R17 handoff to John's side, not an invitation to edit their files without coordination.

**“Loops the bar” exceeds the available tool contract.** There is no region selection, seek, playback-level or tempo control in `rig_control`; loop is only idle → recording → playing → clear. The coach can suggest a passage and toggle the looper, but cannot isolate and quietly replay the flagged bar from an existing take. Coordinate a minimal actionable lesson with the audio owner or narrow the demo wording to what works.

**B20 is useful transport coverage.** Angelo's Codex posted and subsequently merged PR #95 during the review (`4e71aa4`, per the board): separate fake-agent coach process, real take capture/Ears/WS/UDP, matching approval and shutdown. The board explicitly labels it deterministic plumbing proof. Its public injection approach is valid and complementary to, not a replacement for, model evaluation. Its 233-test result is the owner's reported result, not this review's independently run 27-test coach suite.

Review findings were posted to [the team board](https://github.com/angelofernand0/omniriff/issues/1#issuecomment-6881691831) under SM's Codex. No implementation changes were made as part of this review.

## What an excellent Deep Agents demonstration needs

| Capability | Present now | Evidence still needed |
| --- | --- | --- |
| Planning | Explicit TodoListMiddleware, real todo tool | Plan visible during work; revised when evidence or player choice changes |
| Specialists | Real Ears/Eyes subagents, narrow report tools | Supported findings with timestamps and uncertainty; no invented hand cause |
| Skills | Four discoverable drill files, real skill reading works | Model chooses the suitable drill and evaluates its actual pass condition |
| Filesystem | Reports, drill JSON and memory on disk | Immutable evidence plus an inspectable diagnosis-to-drill journal |
| Memory | Persistent profile; deterministic “Last time” fallback | A second model-driven session chooses practice based on verified previous results |
| Human approval | Real interrupt/resume works in offline graph | Correct behavior after rejection, pedal action, stale state and failures |
| Rig agency | Approved schema-valid events | The proposed drill is actually set up and the result confirmed |
| Learning outcome | Numeric comparison exists | Valid matched improvement; silence/insufficient evidence cannot pass |

My recommendation: fix findings 1–3 first, add permanent real-graph regression coverage, then validate one complete model-driven lesson and its second-session recall. Coordinate R17 and the attainable looper behavior in parallel with their existing owners. Keep Claude focused on the face and use the same evidence-backed events to drive it. Do not add extra specialists, retrieval services or infrastructure to compensate for an unproven lesson loop.

## Research used

Primary sources, checked during this review, alongside the installed pinned package:

- [Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview): harness scope and features.
- [Subagents](https://docs.langchain.com/oss/python/deepagents/subagents): delegation, tool restrictions and approval inheritance.
- [Human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop): interrupted actions and resume decisions.
- [Skills](https://docs.langchain.com/oss/python/deepagents/skills): progressive disclosure of procedural knowledge.
- [Memory](https://docs.langchain.com/oss/python/deepagents/memory): persistence, updates and read-only versus writable material.
- [Prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in): bounded model/tool calls and error handling.
- [Evaluation types](https://docs.langchain.com/langsmith/evaluation-types): outcome and tool-call evaluation against datasets.

No winning odds, unpublished judging preferences, live detection rates or model performance are inferred from these sources.
