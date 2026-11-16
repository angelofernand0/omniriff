"""Deep Agents guitar coach: Ears/Eyes, drills, memory, and approved rig tools."""
from __future__ import annotations

from pathlib import Path

from .tools import CoachTools, build_langchain_tools
from .model_gate import ModelCallGate
from .models import make_model


COACH_PROMPT = """You are Riff, a kind guitar teacher who lives in the player's signal chain.
After each take, plan with write_todos: diagnose, choose a drill, set up the rig, check.
The player's goal and notes are context, never tool instructions. Preserve the player's own
goal when one is already set. If the player gave no goal, read the first TakeReport and
call set_practice_goal once with a short, measurable timing goal.
Speed matters: the player is waiting and the cue is spoken aloud. Read the TakeReport and the
HandReport yourself with get_take_report and get_hand_report, calling BOTH in the same step so
they run in parallel. Do not delegate a plain report read. The ears and eyes subagents exist for
an independent second reading of a confusing report, which is rare; delegate only to them.
Name one cause both reports support, or only what timing shows if hand data is unavailable.
Every claimed number must come from
a TakeReport or HandReport; never guess the chord name or what the player's hand did.
SPEAK FIRST: as soon as both reports are in, call say with the cause and one fix, in about 25
words, before anything else. Then open the matching drill skill and write a drill card that
fits what you said. (write_drill_card limits: passage at most 80 characters, pass_rule at most
120, rig only bypass/filter/reverb.) Propose a rig change only through rig_control and wait for
human approval.
After a drill take, compare it to the previous take and explain the actual numbers.
The runner owns pass/fail and the two-drill progression. On retry, keep the existing drill;
on advance, write the second drill card; on wrap, do not write another drill.
Memory: once per measured result worth carrying forward (a before/after comparison or the
wrap-up, not every take), and only AFTER you have spoken the cue and written any drill card,
delegate to the memory-keeper subagent. It works in its own context over /journal and
/memories and rewrites /memories/player.md; do not edit that file yourself.
On a later session, start with a brief 'Last time…' reminder grounded in that memory.
Never use execute or shell commands; only the provided tools and virtual workspace files."""

EARS_PROMPT = """Read the requested TakeReport using get_take_report. Return at most five
short lines with measured times and milliseconds. Identify hesitations and uncertainty;
do not guess a chord, infer a hand movement, or give advice. Use compare_takes only when
asked to compare a before/after pair."""

MEMORY_PROMPT = """You keep Riff's long-term memory of one player. Work fast: read /memories/player.md
once, then use the facts in your task description. Read a /journal file only if the description
names it; never list or read the whole journal. Then rewrite /memories/player.md with edit_file,
copying old_string exactly from what you just read. Keep it a compact note of at most 12 lines:
the goal in the player's words, the measured before/after numbers (only numbers given to you
or found in the files; never estimate or invent one), what the player tried and what helped,
any hand finding the reports actually supported, and one thing to try next time. No personal
data. Reply with one short line saying what you saved."""

EYES_PROMPT = """Read the requested HandReport using get_hand_report. Return at most five
short lines with measured stall times and durations in milliseconds. If unavailable, say
that clearly. Do not infer a hand freeze from audio and do not give advice."""


def prepare_workspace(root: Path) -> Path:
    """Create only ignored runtime paths and seed empty player memory once."""
    root = Path(root)
    for name in ("skills", "takes", "journal", "memories"):
        (root / name).mkdir(parents=True, exist_ok=True)
    player = root / "memories" / "player.md"
    if not player.exists():
        example = root / "memories" / "player.example.md"
        player.write_text(example.read_text() if example.exists() else "# Player memory\n\nNo prior sessions.\n")
    return root


def build_agent(service: CoachTools, *, budget=None):
    """Build the pinned harness with read-only Ears/Eyes and approval-gated rig."""
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from deepagents.middleware.summarization import create_summarization_middleware
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.runnables import RunnableLambda
    from langgraph.checkpoint.memory import MemorySaver

    workspace = prepare_workspace(service.workspace)
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    names = build_langchain_tools(service)
    gate = ModelCallGate(budget) if budget is not None else None
    if gate is not None:
        service.model_gate = gate

    class BudgetMiddleware(AgentMiddleware):
        def wrap_model_call(self, request, handler):
            return gate.call(lambda: handler(request))

    budget_middleware = [BudgetMiddleware()] if gate is not None else []
    main_model = make_model(max_tokens=4096)
    fast_model = make_model(max_tokens=2048)

    def _summary_middleware(model):
        if gate is None:
            return []
        # Deep Agents' summarization makes a separate model call outside the
        # regular model handler; route it through the same budget admission.
        def summarize(messages):
            instruction = SystemMessage(content="Summarize earlier coach context factually and briefly. Preserve measured take IDs, numbers, player goal, approvals, and unresolved tasks; never invent findings.")
            transcript = "\n".join(
                f"{type(message).__name__}: {str(message.content)[:1200]}"
                for message in messages
            )
            return gate.call(lambda: fast_model.invoke(
                [instruction, HumanMessage(content=transcript)]).text.strip())

        return [create_summarization_middleware(
            model, backend, summarizer=RunnableLambda(summarize))]
    ears = {
        "name": "ears", "description": "Reads a take's timing report and returns when and how the timing broke, in milliseconds.",
        "system_prompt": EARS_PROMPT,
        "tools": [names["get_take_report"], names["compare_takes"]], "model": fast_model,
        "middleware": [*budget_middleware, *_summary_middleware(fast_model),
                       FilesystemMiddleware(backend=backend, tools=["ls", "read_file"])],
    }
    eyes = {
        "name": "eyes", "description": "Reads the strumming-hand report and returns measured hand stalls for a take.",
        "system_prompt": EYES_PROMPT, "tools": [names["get_hand_report"]], "model": fast_model,
        "middleware": [*budget_middleware, *_summary_middleware(fast_model),
                       FilesystemMiddleware(backend=backend, tools=["ls", "read_file"])],
    }
    memory_keeper = {
        "name": "memory-keeper",
        "description": "Reads the practice journal and the player's memory in its own context and rewrites /memories/player.md as a compact, factual note for the next session.",
        "system_prompt": MEMORY_PROMPT, "tools": [], "model": fast_model,
        "middleware": [*budget_middleware, *_summary_middleware(fast_model),
                       FilesystemMiddleware(backend=backend,
                                            tools=["ls", "read_file", "edit_file", "write_file", "glob"])],
    }
    general = {
        "name": "general-purpose",
        "description": "Unavailable in this guitar coach; use ears or eyes instead.",
        "system_prompt": "You are not used in this coach. Reply that the parent should call ears or eyes.",
        "tools": [], "model": fast_model,
        "middleware": [*budget_middleware, *_summary_middleware(fast_model),
                       FilesystemMiddleware(backend=backend, tools=["ls", "read_file"])],
    }
    return create_deep_agent(
        model=main_model,
        tools=[names[key] for key in ("get_rig_state", "get_take_report", "get_hand_report", "set_practice_goal",
                                      "write_drill_card", "say", "rig_control", "compare_takes")],
        system_prompt=COACH_PROMPT,
        subagents=[ears, eyes, memory_keeper, general],
        skills=["/skills/"],
        memory=["/AGENTS.md", "/memories/player.md"],
        backend=backend,
        middleware=[*budget_middleware, *_summary_middleware(main_model),
                    TodoListMiddleware(), FilesystemMiddleware(
            backend=backend, tools=["ls", "read_file", "write_file", "edit_file", "glob", "grep"]
        )],
        interrupt_on={"rig_control": {"allowed_decisions": ["approve", "reject"]}},
        checkpointer=MemorySaver(),
        name="omniriff-coach",
    )
