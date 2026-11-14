"""Measured practice-session projection for the coach dashboard.

This is deliberately separate from the agent runner: only judgeable TakeReports
enter the history, while goals and targets are proposals from a drill plan.
"""
from __future__ import annotations

import math
import re


GAP_TARGET = re.compile(r"^(?:worst|longest) gap (?:under|below|<) (\d+(?:\.\d+)?) ms$", re.I)


class PracticeSession:
    def __init__(self, *, last_time: str | None = None):
        if last_time is not None and (not isinstance(last_time, str) or len(last_time) > 120):
            raise ValueError("last_time must be at most 120 characters")
        self.goal: str | None = None
        self._explicit_goal = False
        self.next: str | None = None
        self.last_time = last_time
        self._drill_step = 1
        self._drill_count = 1
        self.drill: dict | None = None
        self.attempt: dict | None = None
        self.target: float | None = None
        self.history: list[float] = []
        self._seen_takes: set[str] = set()

    def plan(self, *, goal: str, next_step: str | None = None,
             drill_step: int = 1, drill_count: int = 1,
             attempt_count: int | None = None) -> None:
        """Set proposed plan fields; unknown values remain null, never invented."""
        if not isinstance(goal, str) or not 1 <= len(goal) <= 80:
            raise ValueError("goal must be 1–80 characters")
        if next_step is not None and (not isinstance(next_step, str) or len(next_step) > 80):
            raise ValueError("next step must be at most 80 characters")
        if not isinstance(drill_step, int) or not isinstance(drill_count, int) or not 1 <= drill_step <= drill_count <= 12:
            raise ValueError("invalid drill position")
        if attempt_count is not None and (not isinstance(attempt_count, int) or not 1 <= attempt_count <= 50):
            raise ValueError("invalid attempt count")
        self.goal, self.next = goal, next_step
        self._explicit_goal = True
        self._drill_step, self._drill_count = drill_step, drill_count
        if self.drill:
            self.drill.update(step=drill_step, of=drill_count)
        if attempt_count is not None:
            self.attempt = {"n": 0, "of": attempt_count}

    def set_drill_card(self, card: dict) -> None:
        """Use the saved drill and a literal pass rule; never infer a target."""
        self.drill = {"title": card["title"], "skill": card["skill"],
                      "step": self._drill_step, "of": self._drill_count}
        if not self._explicit_goal:
            self.goal = card["pass_rule"][:80]
        if self.attempt:
            self.attempt["n"] = 0
        match = GAP_TARGET.fullmatch(card["pass_rule"].strip())
        self.target = float(match.group(1)) if match else None
        if self.target is not None and not math.isfinite(self.target):
            self.target = None

    def record_take(self, report: dict) -> bool:
        """Add exactly one measured value for a judgeable take, oldest first."""
        if report.get("judgeable") is not True:
            return False
        take_id = report.get("take_id")
        if not isinstance(take_id, str) or not take_id or take_id in self._seen_takes:
            return False
        intervals = report.get("intervals_ms")
        if not isinstance(intervals, list) or not intervals:
            return False
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   and math.isfinite(x) and x >= 0 for x in intervals):
            return False
        self.history = [*self.history, float(max(intervals))][-12:]
        self._seen_takes.add(take_id)
        if self.drill and self.attempt:
            self.attempt["n"] = min(self.attempt["n"] + 1, self.attempt["of"])
        return True

    def snapshot(self) -> dict:
        """Return a coach.schema.json session object with explicit nulls."""
        metric = None
        if self.target is not None:
            metric = {"name": "longest gap", "unit": "ms", "target": self.target,
                      "lower_is_better": True, "history": self.history.copy()}
        return {"goal": self.goal, "drill": self.drill.copy() if self.drill else None,
                "attempt": self.attempt.copy() if self.attempt else None,
                "metric": metric, "next": self.next, "last_time": self.last_time}
