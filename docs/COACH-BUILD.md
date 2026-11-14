# Coach build spec (piece D): for the agent writing `coach/`

Owner: SM. Builder: SM's Codex (roadmap R5–R8). Written by SM's Claude, Sat Nov 14, from the deepagents docs (docs.langchain.com/oss/python/deepagents, PyPI `deepagents` 0.7.38, released Nov 13 2026) and `main` at 2b9369d. Design and the "why" are in [COACH.md](COACH.md). This file is the "how". Follow it literally. Where it says **verify**, run the check before building on the assumption, and post on issue #1 if the check fails.

Goal: **"Best use of deepagents."** Judges should *see* every harness feature doing a real job: planning (todos), subagents, skills, filesystem, memory, and human-in-the-loop. Each one below has a job, and none is decoration.

---

## 0. Rules that don't bend

1. The coach is a **separate process**. If it crashes, hangs or loses Wi-Fi, the instrument doesn't notice. Never import `audio/` or `engine/` runtime code into it; talk over the existing sockets only.
2. It changes the rig **only** through `rig_control`, which sends normal control messages with `source: "coach"` over UDP, and only after approval (§6).
3. Every claim it makes comes from a number in a TakeReport or HandReport. No number, no claim. The system prompt says so.
4. Budget: the key has about $10. Log `usage` per take to `coach/workspace/usage.jsonl`. Refuse new runs above $8 total, publish `cue: "Coach is out of credit."` and go to sleep.
5. The key comes from the environment: load `.env` at the repo root, then `~/.config/omniriff/.env`, with `python-dotenv` (`load_dotenv(); load_dotenv(Path.home()/".config/omniriff/.env")`). Never print it, log it or commit it.

## 1. Install and verify first (30 minutes, before any feature code)

`coach/requirements.txt`:
```
deepagents==0.7.38
langchain-anthropic          # pin to whatever version this resolves to, then write that pin back
python-dotenv>=1.0
websockets>=14,<18
jsonschema>=4.23,<5
```
Needs Python ≥ 3.11.

Write `coach/smoke.py` and run it. It must:
1. Build the model (§3) and a `create_deep_agent(...)` with one dummy tool.
2. Print the agent's tool names. **Verify** `write_todos`, `ls`, `read_file`, `write_file`, `edit_file` and `task` are present. If `write_todos` is missing, add the todo middleware: try `from langchain.agents.middleware import TodoListMiddleware` and pass `middleware=[TodoListMiddleware()]`. If that import fails, search the installed package (`python -c "import deepagents, pkgutil; ..."`) and post what you found.
3. Invoke once: "List the files in /skills and read /memories/player.md". **Verify** the agent sees the files from §4. This settles how paths resolve under `FilesystemBackend(virtual_mode=True)`: leading slash, relative to `root_dir`.
4. Print `usage` and wall time.

Do not continue until all of this passes. Post the output summary on issue #1.

## 2. Files

```
coach/
  __init__.py
  __main__.py        # CLI: python -m coach [--sim] [--take-dir DIR] [--hand-log PATH] [--fixtures]
  agent.py           # build_agent(): model, tools, subagents, skills, memory, backend, interrupt_on
  tools.py           # the six tools (§5), plain functions with docstrings
  rig.py             # UDP control sender (source "coach") + engine state reader (ws 47801)
  feed.py            # coach feed WebSocket server on 127.0.0.1:47803 (schema: protocol/coach.schema.json, R1)
  runner.py          # session loop (§7): watch takes, build reports, run agent, handle approval
  budget.py          # usage log + $8 stop
  smoke.py
  requirements.txt
  fixtures/          # R5 rendered takes + hand logs with planted mistakes
  workspace/         # the agent's filesystem root (FilesystemBackend root_dir)
    AGENTS.md        # standing instructions loaded by memory= (short; see §4)
    memories/player.md   # player profile, seeded empty; the agent updates it (R7)
    skills/<4 drills>/SKILL.md
    takes/           # gitignored: per-take take.json + hand.json written by runner
    journal/         # gitignored: session notes + drill cards the agent writes
    usage.jsonl      # gitignored
tests/test_coach_*.py  # no network: tools, feed, runner with a fake agent
```
Add `coach/workspace/takes/`, `journal/`, `usage.jsonl` and `memories/player.md` to `.gitignore`. Commit a `memories/player.example.md` and copy it on first run.

## 3. Model

```python
from langchain_anthropic import ChatAnthropic
main_model = ChatAnthropic(model="claude-sonnet-5-5", max_tokens=4096)
fast_model = ChatAnthropic(model="claude-haiku-5-5", max_tokens=2048)
```
Claude 5.5 models reject things older examples do:
- **No `temperature`, `top_p` or `top_k`** (400). Don't pass them.
- **No forced tool choice** (`tool_choice` any/tool → 400). Don't use `with_structured_output` modes that force a tool. Steer with the prompt instead.
- **Thinking can't be turned off.** If LangChain exposes `effort`, use `"medium"` for main and `"low"` for subagents; if not, leave defaults.
- **Check `stop_reason == "refusal"`** if you ever read raw responses; treat it as "no finding", never crash.

If `ChatAnthropic` rejects one of these on the first smoke run, fix the constructor and record what worked here.

## 4. Backend, skills, memory

One real directory, so everything the agent writes is inspectable on disk (good for judges and for debugging):
```python
from deepagents.backends import FilesystemBackend
backend = FilesystemBackend(root_dir="coach/workspace", virtual_mode=True)   # virtual_mode sandboxes paths
```
- **Skills** (`skills=["/skills/"]`, path per smoke test): four folders. Each `SKILL.md` starts with frontmatter `name:` (equal to the folder name, lowercase-hyphen) and `description:` (when to use it, under 1,024 characters), then the drill: what to play, how many times, what counts as a pass, which rig settings, and what to say. The agent sees only names and descriptions until it opens one, which is progressive disclosure, a point worth saying to the LangChain judges.
  - `isolate-the-change`: play only the two bars around the flagged change, 4 times.
  - `slow-then-speed-up`: same passage at about 70% tempo, then back up.
  - `dry-check`: effects off (bypass) so the player hears the timing.
  - `keep-the-hand-moving`: strumming hand keeps swinging through the change (pendulum), ghost strums allowed.
- **Memory** (`memory=["/AGENTS.md", "/memories/player.md"]`): loaded at startup. `AGENTS.md` holds standing rules (§0.3, keep cues to two sentences). `player.md` is the profile. The system prompt tells the agent to update `player.md` with `edit_file` at the end of each drill ("G→C change: hand stalls ~400 ms; keep-the-hand-moving cut it to 120 ms"). The next session starts with "Last time…". That's R7, and it's what Amazon's "adaptive, learns from the user" asks for.
- **Journal:** the agent writes `/journal/<session>/<take_id>.md` (diagnosis) and the drill card JSON via the `write_drill_card` tool.

## 5. Tools (`coach/tools.py`)

Plain Python functions with type hints and a clear docstring (the docstring is what the model reads). Each one that the dashboard should show **publishes a coach frame itself** through `feed.publish(...)`. Don't rely on event streaming for the dashboard: tool-side publishing is deterministic.

| Tool | Signature | Does | Publishes |
|---|---|---|---|
| `get_rig_state` | `() -> dict` | Latest engine state frame from ws 47801: loop state, bypass, filter, reverb, sources | — |
| `get_take_report` | `(take_id: str) -> dict` | Reads `/takes/<id>/take.json` (TakeReport v1 from `tools.ears`) | `state:"thinking", target:"loop"` |
| `get_hand_report` | `(take_id: str) -> dict` | Reads `/takes/<id>/hand.json` (HandReport for that take window). Returns `{"available": false}` if there's no camera data, and the agent must then diagnose from timing only | `state:"thinking", target:"hand"` |
| `compare_takes` | `(before_id: str, after_id: str) -> dict` | Deterministic diff: hesitation count, worst gap ms, median interval, tempo_stability, before vs after | `before_after` |
| `write_drill_card` | `(skill: str, passage: str, reps: int, pass_rule: str, rig: dict) -> str` | Validates and saves the drill card; returns its path | `drill_card` |
| `say` | `(text: str) -> str` | One cue, max two sentences: the cause, then the fix | `state:"speaking", cue:text` |
| `rig_control` | `(control: "bypass"\|"filter"\|"reverb"\|"loop", value: float \| None = None) -> str` | **Interrupted for approval** (§6). On approve: sends one control message (`version 1, source "coach", seq, timestamp_ms, type, control, value, confidence 1.0`) to UDP 127.0.0.1:47800 | `state:"pointing", target:control` |

Validate every outgoing control against `protocol/control.schema.json` before sending.

## 6. Human-in-the-loop (approval without letting go of the guitar)

```python
from langgraph.checkpoint.memory import MemorySaver
agent = create_deep_agent(..., interrupt_on={"rig_control": {"allowed_decisions": ["approve", "reject"]}},
                          checkpointer=MemorySaver())
config = {"configurable": {"thread_id": session_id}}
result = agent.invoke({"messages": [...]}, config=config)
if result.get("__interrupt__"):
    pending = result["__interrupt__"][0].value["action_requests"]   # list of {name, args}
    # publish awaiting_approval with a human sentence describing `pending`
    # then wait for approval (below), then:
    from langgraph.types import Command
    result = agent.invoke(Command(resume={"decisions": [{"type": "approve"}] * len(pending)}), config=config)
```
One decision per pending action, in order. A reject is `{"type": "reject", "message": "Player declined."}`.

**What counts as approval**, whichever comes first:
1. The player starts recording with the pedal: the engine state shows `loop.state` changing to `recording`. That's the natural "go": they're already starting the drill take.
2. A `coach.approve` message from the dashboard on the 47803 socket (key `Y` or a button, R3).
3. Timeout after 60 s → reject, `say("No problem, I'll leave your sound as it is.")`.

## 7. Session loop (`coach/runner.py`)

```
start: load .env, check budget, start feed server (47803), connect to engine state (47801, read-only),
       publish {state:"idle", cue:"Play me something. Tap the pedal to record."}
loop:
  wait for a new take-*.json sidecar in --take-dir (poll every 0.5 s; ignore files you've seen)
  take = tools.ears.analyze_take(wav, sidecar)                     -> workspace/takes/<id>/take.json
  hand = vision.eyes.report_for_window(hand_log, started_unix_ms, ended_unix_ms, take_id)   (R17; if missing → {"available": false})
                                                                   -> workspace/takes/<id>/hand.json
  publish {state:"listening" → "thinking"}
  invoke agent: "New take <id>. Diagnose it, choose one drill, set up the rig." (same thread_id all session)
  handle interrupt (§6), loop until no interrupt
  if this take was a drill take: compare_takes(previous, this) is called by the agent; if better → state "pleased"
on any exception: log it, publish {state:"asleep", cue:"Coach hit a problem; the rig is fine."}, keep the loop alive
```
`--fixtures` replays `coach/fixtures/` takes through the same loop with no engine (rig_control logs instead of sending). `--sim` assumes `python -m tools.sim run --demo --take-dir ...` is running.

## 8. The agent itself (`coach/agent.py`)

```python
from deepagents import create_deep_agent

EARS = {"name": "ears", "description": "Reads a take's timing report and returns where and how the timing broke, in milliseconds.",
        "system_prompt": EARS_PROMPT, "tools": [get_take_report, compare_takes], "model": fast_model}
EYES = {"name": "eyes", "description": "Reads the strumming-hand report for a take and returns when the hand stalled.",
        "system_prompt": EYES_PROMPT, "tools": [get_hand_report], "model": fast_model}

agent = create_deep_agent(
    model=main_model,
    tools=[get_rig_state, write_drill_card, say, rig_control, compare_takes],
    system_prompt=COACH_PROMPT,
    subagents=[EARS, EYES],
    skills=["/skills/"],
    memory=["/AGENTS.md", "/memories/player.md"],
    backend=backend,
    interrupt_on={"rig_control": {"allowed_decisions": ["approve", "reject"]}},
    checkpointer=MemorySaver(),
    name="omniriff-coach",
)
```
`COACH_PROMPT` (keep it short and plain; Claude 5.5 does better with intent than rules):
> You are Riff, a guitar teacher who lives in the player's signal chain. After each take: plan with write_todos (diagnose, choose a drill, set up the rig, check). Ask the ears and eyes subagents for findings, in parallel. Name **one** cause that both reports support, or say only what timing shows if the hand report isn't available. Open the matching skill, write a drill card, say the cause and the fix in at most two sentences, then set up the rig with rig_control. After a drill take, compare it with the take before and tell the player what changed, in numbers. Update /memories/player.md when you learn something that should carry to next time. Never claim anything a report doesn't show.

Subagent prompts: return at most 5 lines, each with a time in ms and a number. No advice; that's the coach's job.

## 9. Showing the harness (what the dashboard gets)

| Harness feature | Shown as | Source |
|---|---|---|
| `write_todos` plan | Checklist in 04 COACH | After each `invoke`, read `result.get("todos")` and publish them; **verify** the key name in the smoke test |
| Subagents | Riff `thinking`, looking at LOOP (ears) or HAND (eyes) | Tool-side publishes in §5 |
| Skills | Drill card title = skill name | `write_drill_card` |
| Filesystem | Journal path shown under the drill card | `write_drill_card` return value |
| Memory | First cue of a session: "Last time…" | Prompt + `player.md` |
| Human-in-the-loop | "Tap the pedal to start" prompt; Riff waits | `awaiting_approval` |

Optional, only after all of the above works: use `agent.stream_events(..., version="v3")` and `stream.subagents[*].status` for live subagent status.

## 10. Tests (no network, in CI)

- `tools.py`: each tool against fixture JSON; `rig_control` builds schema-valid messages; `compare_takes` numbers.
- `feed.py`: frames validate against `protocol/coach.schema.json`.
- `runner.py`: with a fake agent object whose `invoke` returns a canned `__interrupt__` and then a final state, check that approval by `loop.state → recording` resumes with `{"type": "approve"}`.
- Live LLM runs (`python -m coach --fixtures`) are manual, cost money, and are **not** in CI. Post their cost and time on issue #1.

## 11. Done means

1. `python -m coach --fixtures` on the planted-hesitation take prints a plan, finds the hesitation at the right ms, names the cause, writes a drill card and asks to set up the rig; approve → controls logged; the drill take shows a smaller gap in `compare_takes`.
2. The same thing with `tools.sim` + the dashboard, with Riff moving (slice 2, 18:00 gate).
3. Two sessions in a row: the second opens with "Last time…".
4. Kill the coach mid-drill: audio keeps playing, the dashboard shows `COACH OFF`.
