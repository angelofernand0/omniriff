"""Verified practice memory, with synthetic replay isolated from real sessions."""
from __future__ import annotations

import math
import re
import shutil
from pathlib import Path


HISTORY = re.compile(
    r"^- Verified (recorded|synthetic) take: worst gap ([0-9]+(?:\.[0-9]+)?)"
    r" → ([0-9]+(?:\.[0-9]+)?) ms; hesitations ([0-9]+) → ([0-9]+)\.$"
)


def prepare_fixture_workspace(source: Path, target: Path) -> Path:
    """Copy instructions/skills, but never real player memory, into replay space."""
    from .agent import prepare_workspace

    source, target = Path(source), Path(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "AGENTS.md", target / "AGENTS.md")
    shutil.copytree(source / "skills", target / "skills", dirs_exist_ok=True)
    (target / "memories").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "memories" / "player.example.md", target / "memories" / "player.example.md")
    return prepare_workspace(target)


def _verified_numbers(comparison: dict) -> tuple[float, float, int, int]:
    before, after = comparison["worst_gap_ms"]
    bh, ah = comparison["hesitations"]
    if (not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
                for value in (before, after))
            or not all(isinstance(value, int) and value >= 0 for value in (bh, ah))):
        raise ValueError("comparison has invalid measured numbers")
    return float(before), float(after), bh, ah


def remember_comparison(workspace: Path, comparison: dict, *, synthetic: bool) -> str:
    """Append a factual, bounded-memory line derived only from TakeReports."""
    before, after, bh, ah = _verified_numbers(comparison)
    kind = "synthetic" if synthetic else "recorded"
    line = (f"- Verified {kind} take: worst gap {before:g} → {after:g} ms; "
            f"hesitations {bh} → {ah}.")
    path = Path(workspace) / "memories" / "player.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write("\n" + line + "\n")
    return line


def last_time_cue(workspace: Path) -> str | None:
    """A short opening cue from the last validated line, not free-form memory."""
    path = Path(workspace) / "memories" / "player.md"
    if not path.is_file():
        return None
    for line in reversed(path.read_text().splitlines()):
        match = HISTORY.fullmatch(line)
        if match:
            kind, before, after, bh, ah = match.groups()
            prefix = "Last time in synthetic replay" if kind == "synthetic" else "Last time"
            return (f"{prefix}, the worst gap went from {before} to {after} ms "
                    f"and hesitations from {bh} to {ah}.")
    return None
