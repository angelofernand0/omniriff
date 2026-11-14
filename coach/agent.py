"""Deep Agents guitar coach: Ears/Eyes, drills, memory, and approved rig tools."""
from __future__ import annotations

from pathlib import Path

from .tools import CoachTools, build_langchain_tools


COACH_PROMPT = """You are Riff, a kind guitar teacher who lives in the player's signal chain.
After each take, plan with write_todos: diagnose, choose a drill, set up the rig, check.
Ask the ears and eyes subagents for findings in parallel. Name one cause both reports support,
or only what timing shows if hand data is unavailable. Every claimed number must come from
a TakeReport or HandReport; never guess the chord name or what the player's hand did.
Open the matching drill skill, write a drill card, and say the cause and fix in at most two
sentences. Propose a rig change only through rig_control and wait for human approval.
After a drill take, compare it to the previous take and explain the actual numbers.
Update /memories/player.md with edit_file when you learn something worth carrying forward.
On a later session, start with a brief 'Last time…' reminder grounded in that memory.
Never use execute or shell commands; only the provided tools and virtual workspace files."""

EARS_PROMPT = """Read the requested TakeReport using get_take_report. Return at most five
short lines with measured times and milliseconds. Identify hesitations and uncertainty;
do not guess a chord, infer a hand movement, or give advice. Use compare_takes only when
asked to compare a before/after pair."""

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


def build_agent(service: CoachTools):
    """Build the pinned harness with read-only Ears/Eyes and approval-gated rig."""
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware
    from langchain.agents.middleware import TodoListMiddleware
    from langchain_anthropic import ChatAnthropic
    from langgraph.checkpoint.memory import MemorySaver

    workspace = prepare_workspace(service.workspace)
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    names = build_langchain_tools(service)
    main_model = ChatAnthropic(model="claude-sonnet-5-5", max_tokens=4096)
    fast_model = ChatAnthropic(model="claude-haiku-5-5", max_tokens=2048)
    ears = {
        "name": "ears", "description": "Reads a take's timing report and returns when and how the timing broke, in milliseconds.",
        "system_prompt": EARS_PROMPT,
        "tools": [names["get_take_report"], names["compare_takes"]], "model": fast_model,
        "middleware": [FilesystemMiddleware(backend=backend, tools=["ls", "read_file"])],
    }
    eyes = {
        "name": "eyes", "description": "Reads the strumming-hand report and returns measured hand stalls for a take.",
        "system_prompt": EYES_PROMPT, "tools": [names["get_hand_report"]], "model": fast_model,
        "middleware": [FilesystemMiddleware(backend=backend, tools=["ls", "read_file"])],
    }
    return create_deep_agent(
        model=main_model,
        tools=[names[key] for key in ("get_rig_state", "write_drill_card", "say", "rig_control", "compare_takes")],
        system_prompt=COACH_PROMPT,
        subagents=[ears, eyes],
        skills=["/skills/"],
        memory=["/AGENTS.md", "/memories/player.md"],
        backend=backend,
        middleware=[TodoListMiddleware(), FilesystemMiddleware(
            backend=backend, tools=["ls", "read_file", "write_file", "edit_file", "glob", "grep"]
        )],
        interrupt_on={"rig_control": {"allowed_decisions": ["approve", "reject"]}},
        checkpointer=MemorySaver(),
        name="omniriff-coach",
    )
