# LangChain deepagents pitch (track-specific)

Use this in front of LangChain / deepagents judges, on top of the shared demo in [PITCH.md](PITCH.md).
Every claim below points at code that exists on this branch; the last section lists what **not** to say.
Written 2026-11-14 by SM's Claude from `coach/agent.py` and live runs. Re-check after any coach change.

## 20-second opener

"Riff is a deep agent that teaches guitar, and the guitar is real. After you play, it makes a plan you can
see on screen, reads what it heard and what the camera saw, picks a drill from its skills, remembers you
between sessions with a sub-agent that owns that memory, and when it wants to touch your rig it *stops and
waits* for you to hold the pedal. It's deepagents doing real work on a real instrument, not a chat window."

## 60-second beat sheet (what the judge sees, in order)

1. **Take ends, Riff answers at once.** A short cached spoken line ("Okay, let me listen back to that")
   covers the model's thinking time. *(coach/runner.py `_speak`)*
2. **The plan appears live.** The `write_todos` list streams to the dashboard as the agent writes it; items
   tick off. *(deepagents planning, streamed by the callback in `runner._invoke`)*
3. **Both reports in one parallel step.** The agent calls the timing report and the hand report together,
   then **speaks the cause and one fix first**; the drill card is written while you listen.
4. **A skill is opened.** The activity strip shows `open skill slow-then-speed-up`: progressive-disclosure
   skills (`coach/workspace/skills/*/SKILL.md`), read only when chosen.
5. **A sub-agent works in its own context.** `memory-keeper` reads the practice journal and the player's
   memory and rewrites `/memories/player.md`; the lead agent never loads those files. Shown as
   `subagent memory-keeper` running, then done.
6. **Human in the loop.** `rig_control` is an `interrupt_on` tool: the agent pauses and the dashboard asks
   for approve/reject; a pedal hold or Y approves. Reject and the rig is untouched.
7. **Next session:** "Last time..." comes from the memory file, not from a prompt we wrote.

## Feature to proof table

| deepagents feature | How Riff uses it | Where |
|---|---|---|
| Planning (`write_todos`) | The lesson plan is the dashboard's checklist, updated as the agent works | `coach/agent.py`, `coach/runner.py` |
| Virtual filesystem | Takes, reports, journal, drill cards and memory are files the agent reads and writes | `FilesystemBackend(virtual_mode=True)` |
| Skills | Four drill skills; the agent opens the one the evidence supports | `coach/workspace/skills/` |
| Long-term memory | `/memories/player.md` persists across sessions | `memory=[...]` + `memory-keeper` |
| Sub-agents | `memory-keeper` (context isolation over the journal); `ears` / `eyes` for an independent second reading | `subagents=[...]` |
| Human-in-the-loop | Rig changes require a physical pedal hold or Y | `interrupt_on={"rig_control": ...}` |
| Middleware | Budget gate on every model call, summarization, todo + filesystem middleware | `ModelCallGate`, `BudgetMiddleware` |
| Checkpointer | Session thread kept across takes | `MemorySaver()` |

## The engineering story (this one is true and worth telling)

"Our first version delegated every report read to an *ears* and an *eyes* sub-agent. We measured it: about
25 seconds per take, mostly two extra model round trips for what is one deterministic tool call each. We moved
plain reads to the lead agent in one parallel step (about 11 seconds on the same take) and kept sub-agents for
work that is actually isolated, like memory. A deep agent isn't more agents, it's the right structure."

Also true and good: the model's tool-validation errors are returned to it instead of crashing the run, there is
a hard budget gate around every call (real Sonnet 5.5 rates; a typical take is a few cents), and the agent's
plan/tools/skills/sub-agents are visible on screen rather than narrated.

## Prepared answers

- **"Why a deep agent and not a prompt?"** The lesson spans several takes, needs a plan, files, memory and a
  safety stop before a physical action. That is the deepagents shape.
- **"Where are the sub-agents?"** `memory-keeper` (own context, cheaper model) runs after the cue is spoken.
  `ears`/`eyes` stay available but the lead reads plain reports itself for latency; we measured the difference.
- **"Is it autonomous?"** It acts on a real rig only after a human approves with the pedal. That is the design.
- **"What does it cost?"** Our guard estimates under about $0.10 per take at list price (Sonnet 5.5 $2/$10 per M,
  Haiku 5.5 for the cheap steps). Say "our estimate", not "measured bill".
- **"What if it fails live?"** A recorded REPLAY of a real session (labelled) and the recorded backup video.

## Do not say / known limits (be honest if asked)

- Don't call the simulated-guitar runs "real guitar" runs. Say which input you used.
- Don't say the pedal-hold approval has been rehearsed on the real rig until someone has done it.
- Don't claim coaching quality is evaluated: we have live runs and offline tests, not an eval set
  (`docs/AI-BRAIN-REVIEW-2026-11-14.md` finding 4 is still open).
- Known false positive: a *repeating* rest in a strumming pattern (and the simulated guitar's built-in rest each bar)
  is flagged as a hesitation by `tools/ears`. Pick a take with no regular rests for the demo, or say so.
- The coach can currently edit its own evidence files inside the virtual filesystem (review finding 5, open).
- The Eyes check needs your strumming hand visible for at least half the take; otherwise Riff says timing-only.
