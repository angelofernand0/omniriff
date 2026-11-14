"""One-call verification of the pinned Deep Agents harness and workspace paths.

This intentionally uses a disposable workspace. It never reads player data or
modifies the rig. The only network call is the explicit Anthropic model invoke.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import time

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"write_todos", "ls", "read_file", "write_file", "edit_file", "task"}
MARKER = "SMOKE_PLAYER_MARKER_2026"


def load_key() -> None:
    """Load either ignored key location without printing its contents."""
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(Path.home() / ".config" / "omniriff" / ".env", override=False)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is missing from the local environment")


def make_workspace(root: Path) -> None:
    skill = root / "skills" / "smoke-read"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: smoke-read\ndescription: Only for verifying workspace access.\n---\n"
        "Read a synthetic marker, and never change the rig.\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("Smoke test: use only these synthetic files.\n", encoding="utf-8")
    memory = root / "memories"
    memory.mkdir()
    (memory / "player.md").write_text(f"Synthetic player marker: {MARKER}\n", encoding="utf-8")


def make_agent(root: Path):
    """Build the specified model and expose the full default harness."""
    dummy = StructuredTool.from_function(
        func=lambda: "pong", name="smoke_ping", description="Return pong for a harness smoke test.")
    model = ChatAnthropic(model="claude-sonnet-5-5", max_tokens=4096, timeout=40, max_retries=0)
    return create_deep_agent(
        model=model,
        tools=[dummy],
        backend=FilesystemBackend(root_dir=root, virtual_mode=True),
        skills=["/skills/"],
        memory=["/AGENTS.md", "/memories/player.md"],
        middleware=[TodoListMiddleware()],
        name="omniriff-coach-smoke",
    )


def tool_names(agent) -> set[str]:
    return set(agent.nodes["tools"].bound.tools_by_name)


def usage(result: dict) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for message in result.get("messages", []):
        info = getattr(message, "usage_metadata", None) or {}
        for field in total:
            total[field] += int(info.get(field, 0))
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Deep Agents tools and virtual workspace with one paid model call")
    parser.add_argument("--tools-only", action="store_true", help="inspect harness without a model call or key")
    args = parser.parse_args(argv)
    if not args.tools_only:
        load_key()
    with tempfile.TemporaryDirectory(prefix="omniriff-coach-smoke-") as folder:
        make_workspace(Path(folder))
        agent = make_agent(Path(folder))
        names = tool_names(agent)
        print("tools:", ", ".join(sorted(names)))
        missing = EXPECTED - names
        if missing:
            raise RuntimeError(f"harness tools missing: {', '.join(sorted(missing))}")
        if args.tools_only:
            return 0
        start = time.monotonic()
        result = agent.invoke(
            {"messages": [("user", "Make a brief todo, then list /skills and read /memories/player.md. "
                           "Reply with the skill folder name and the exact synthetic player marker.")]},
            config={"recursion_limit": 16},
        )
        elapsed = time.monotonic() - start
        answer = str(result["messages"][-1].content)
        if "smoke-read" not in answer or MARKER not in answer:
            raise RuntimeError("agent did not report the skill folder and synthetic memory marker")
        print("workspace paths: verified /skills and /memories/player.md")
        print("todos key:", "present" if "todos" in result else "absent")
        print("usage:", usage(result))
        print(f"wall_seconds: {elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
