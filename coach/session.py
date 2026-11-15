"""Measured practice-session projection for the coach dashboard.

This is deliberately separate from the agent runner: only judgeable TakeReports
enter the history, while goals and targets are proposals from a drill plan.
"""
from __future__ import annotations

import math
import re


def late_ms(report: dict) -> float:
    """How late the worst strum came against the player's own beat (worst interval minus the median).

    Not the raw interval: at 120 bpm a 30 ms stumble is a 530 ms interval, which no drill target
    can sensibly be written against. Reports call this worst_gap_ms."""
    intervals = sorted(float(x) for x in report.get("intervals_ms") or [])
    if not intervals:
        return 0.0
    median = report.get("median_interval_ms")
    if not isinstance(median, (int, float)) or isinstance(median, bool) or not median > 0:
        mid = len(intervals) // 2
        median = intervals[mid] if len(intervals) % 2 else (intervals[mid - 1] + intervals[mid]) / 2
    return round(max(0.0, intervals[-1] - float(median)), 1)


GAP_TARGET = re.compile(r"^(?:worst|longest) gap (?:under|below|<) (\d+(?:\.\d+)?) ms$", re.I)


class PracticeSession:
    def __init__(self, *, last_time: str | None = None):
        if last_time is not None and (not isinstance(last_time, str) or len(last_time) > 120):
            raise ValueError("last_time must be at most 120 characters")
        self.goal: str | None = None
        self.mode = "practice"
        self.summary: str | None = None
        self.next_time: str | None = None
        self._plan_items: list[dict[str, str]] = []
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
        self._measured_gaps: dict[str, float] = {}

    def plan(self, *, goal: str, next_step: str | None = None,
             drill_step: int = 1, drill_count: int = 1,
             attempt_count: int | None = None,
             drill_titles: list[str] | None = None) -> None:
        """Set proposed plan fields; unknown values remain null, never invented."""
        if not isinstance(goal, str) or not 1 <= len(goal) <= 80:
            raise ValueError("goal must be 1–80 characters")
        if next_step is not None and (not isinstance(next_step, str) or len(next_step) > 80):
            raise ValueError("next step must be at most 80 characters")
        if not isinstance(drill_step, int) or not isinstance(drill_count, int) or not 1 <= drill_step <= drill_count <= 12:
            raise ValueError("invalid drill position")
        if attempt_count is not None and (not isinstance(attempt_count, int) or not 1 <= attempt_count <= 50):
            raise ValueError("invalid attempt count")
        if drill_titles is not None:
            if (not isinstance(drill_titles, list) or len(drill_titles) != drill_count
                    or drill_count > 5 or any(not isinstance(title, str) or not 1 <= len(title) <= 60
                                              for title in drill_titles)):
                raise ValueError("invalid drill titles")
            self._plan_items = [
                {"title": title, "status": "done" if i + 1 < drill_step else
                 "now" if i + 1 == drill_step else "next"}
                for i, title in enumerate(drill_titles)
            ]
        self.goal, self.next = goal, next_step
        self._explicit_goal = True
        self.mode = "practice"
        self.summary = None
        self.next_time = None
        self._drill_step, self._drill_count = drill_step, drill_count
        if self.drill:
            self.drill.update(step=drill_step, of=drill_count)
        if attempt_count is not None:
            self.attempt = {"n": 0, "of": attempt_count}

    def set_drill_card(self, card: dict) -> None:
        """Use the saved drill and a literal pass rule; never infer a target."""
        if self._plan_items and self.drill is not None and self.attempt and self.attempt["n"] > 0:
            raise ValueError("cannot replace a drill after judged attempts")
        self.drill = {"title": card["title"], "skill": card["skill"],
                      "step": self._drill_step, "of": self._drill_count}
        if self._plan_items and self._drill_step <= len(self._plan_items):
            self._plan_items[self._drill_step - 1]["title"] = card["title"]
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
        gap = late_ms(report)
        self.history = [*self.history, gap][-12:]
        self._seen_takes.add(take_id)
        self._measured_gaps[take_id] = gap
        if self.drill and self.attempt:
            self.attempt["n"] = min(self.attempt["n"] + 1, self.attempt["of"])
        return True

    def has_take(self, take_id: str) -> bool:
        """Whether a judgeable measured report was read for this take."""
        return take_id in self._seen_takes

    def assess_take(self, take_id: str) -> dict:
        """Evaluate a measured take against the literal card target, never a model guess."""
        if take_id not in self._measured_gaps:
            raise ValueError("take has no judgeable measured gap")
        return {"take_id": take_id, "gap_ms": self._measured_gaps[take_id],
                "target_ms": self.target,
                "passed": self._measured_gaps[take_id] < self.target if self.target is not None else None,
                "attempt": self.attempt.copy() if self.attempt else None}

    def next_action(self, take_id: str) -> dict:
        """Choose a session transition from evidence, never from a model assertion."""
        if self.mode == "play":
            return {"action": "ignore", "passed": None}
        if not self.has_take(take_id):
            raise ValueError("take has no judgeable measured gap")
        if not self._plan_items:
            return {"action": "diagnose", "passed": None}
        if self.drill is None:
            return {"action": "diagnose", "passed": None}
        assessment = self.assess_take(take_id)
        attempt = assessment["attempt"]
        if not attempt or attempt["n"] == 0:
            raise ValueError("take is not a drill attempt")
        passed = assessment["passed"]
        if passed is True or attempt["n"] >= 3:
            action = "wrap" if self._drill_step == len(self._plan_items) else "advance"
        else:
            action = "retry"
        return {"action": action, "passed": passed, "assessment": assessment}

    def advance_drill(self, *, passed: bool, next_step: str | None = None) -> None:
        """Move to the next drill only after a pass or the third judged attempt."""
        if self.mode != "practice" or not self._plan_items or self._drill_step >= len(self._plan_items):
            raise ValueError("no next drill")
        if not self.attempt or self.attempt["n"] == 0:
            raise ValueError("a judged drill attempt is required")
        if not passed and (not self.attempt or self.attempt["n"] < 3):
            raise ValueError("cannot skip before three judged attempts")
        self._plan_items[self._drill_step - 1]["status"] = "done" if passed else "skipped"
        self._drill_step += 1
        self._plan_items[self._drill_step - 1]["status"] = "now"
        self.next = next_step
        self.drill = None
        self.target = None
        self.attempt = {"n": 0, "of": 3}

    def finish(self, summary: str, *, passed: bool, next_time: str | None = None) -> None:
        """Publish a grounded wrap-up and return the coach to quiet PLAY mode."""
        if self.mode != "practice" or not self._plan_items or self._drill_step != len(self._plan_items):
            raise ValueError("session is not ready to finish")
        if not isinstance(summary, str) or not 1 <= len(summary) <= 200:
            raise ValueError("summary must be 1–200 characters")
        if next_time is not None and (not isinstance(next_time, str) or not 1 <= len(next_time) <= 80):
            raise ValueError("next_time must be 1–80 characters")
        if not self.attempt or self.attempt["n"] == 0:
            raise ValueError("a judged drill attempt is required")
        if not passed and (not self.attempt or self.attempt["n"] < 3):
            raise ValueError("cannot finish before three judged attempts")
        self._plan_items[-1]["status"] = "done" if passed else "skipped"
        self.mode = "play"
        self.summary = summary
        self.next_time = next_time
        self.next = None
        self.drill = None
        self.attempt = None

    def stop(self) -> None:
        """A player may leave practice without claiming a completed drill."""
        self.mode = "play"
        self.summary = None
        self.next_time = None
        self.next = None
        self.drill = None
        self.attempt = None

    def snapshot(self) -> dict:
        """Return a coach.schema.json session object with explicit nulls."""
        metric = None
        if self.target is not None:
            metric = {"name": "longest gap", "unit": "ms", "target": self.target,
                      "lower_is_better": True, "history": self.history.copy()}
        return {"mode": self.mode, "goal": self.goal,
                "plan": [item.copy() for item in self._plan_items],
                "summary": self.summary,
                "drill": self.drill.copy() if self.drill else None,
                "attempt": self.attempt.copy() if self.attempt else None,
                "metric": metric, "next": self.next, "last_time": self.last_time,
                "next_time": self.next_time}
