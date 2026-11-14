"""Conservative local token-usage guard; not a provider billing statement."""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path


LIMIT_USD = 8.0
RUN_RESERVE_USD = 2.0
# Deliberately pessimistic safety rates, not a claim about current provider prices.
INPUT_USD_PER_M = 15.0
OUTPUT_USD_PER_M = 75.0


def _dollars(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("budget amounts must be finite nonnegative numbers")
    if not math.isfinite(value) or value < 0:
        raise ValueError("budget amounts must be finite nonnegative numbers")
    return value


def estimate_upper_bound_usd(usage_by_model: dict) -> float:
    """Charge every model at the same pessimistic upper-bound token rates."""
    if not isinstance(usage_by_model, dict):
        raise ValueError("usage must be a mapping of models to token counts")
    input_tokens = output_tokens = 0
    # The pinned usage callback replaces per-model records concurrently.
    # Snapshot the mapping before iterating while specialists finish.
    for data in usage_by_model.copy().values():
        if not isinstance(data, dict):
            raise ValueError("model usage must contain token counts")
        if any(key not in data for key in ("input_tokens", "output_tokens")):
            raise ValueError("model usage must include input and output token counts")
        counts = [data[key] for key in ("input_tokens", "output_tokens")]
        if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in counts):
            raise ValueError("token counts must be nonnegative integers")
        input_tokens += counts[0]
        output_tokens += counts[1]
    return round((input_tokens * INPUT_USD_PER_M + output_tokens * OUTPUT_USD_PER_M) / 1_000_000, 6)


class BudgetGuard:
    def __init__(self, path: Path, *, limit_usd: float = LIMIT_USD,
                 reserve_usd: float = RUN_RESERVE_USD):
        self.path = Path(path)
        self.limit_usd = _dollars(limit_usd)
        self.reserve_usd = _dollars(reserve_usd)
        self._lock = threading.RLock()
        self._in_flight = 0
        self._active_usd = 0.0

    def spent_usd(self) -> float:
        try:
            stream = self.path.open()
        except FileNotFoundError:
            return 0.0
        total = 0.0
        with stream:
            for line in stream:
                if line.strip():
                    total += _dollars(json.loads(line)["estimated_upper_bound_usd"])
        _dollars(total)
        return round(total, 6)

    def _observe_usage(self, usage_by_model: dict | None) -> None:
        if usage_by_model is not None:
            self._active_usd = max(self._active_usd, estimate_upper_bound_usd(usage_by_model))

    def _can_call(self, active_usd: float | None = None) -> bool:
        reserved = (self._in_flight + 1) * self.reserve_usd
        active = self._active_usd if active_usd is None else active_usd
        return round(self.spent_usd() + active + reserved, 6) < self.limit_usd

    def before_model_call(self, usage_by_model: dict | None = None) -> bool:
        """Atomically check and reserve one call for the runner's model hook.

        ``usage_by_model`` is cumulative usage for the active, UNRECORDED
        turn, including its specialists and approval resumes. Never pass
        usage already persisted with ``record`` or it will count twice.
        All parent/specialist calls in one turn must share this guard. Pair
        each True result with after_model_call(latest_usage) in a finally
        block, including model failures. A False result reserves nothing.
        Approval resumes must use the same turn's cumulative usage.

        Reserve headroom for this and all other in-flight calls in this
        process. Retain the cost high-water mark until record() so older
        concurrent snapshots cannot refund completed work. This is not a
        provider spending cap: a completed call can exceed its reservation.
        Refuse on unreadable/corrupt accounting rather than reset the budget.
        """
        with self._lock:
            try:
                active = self._active_usd
                if usage_by_model is not None:
                    active = max(active, estimate_upper_bound_usd(usage_by_model))
                if not self._can_call(active):
                    return False
                self._active_usd = active
                self._in_flight += 1
                return True
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                return False

    def after_model_call(self, usage_by_model: dict | None = None) -> None:
        """Observe shared cumulative usage and release one admitted call.

        The model wrapper must run this only for an admitted call, on both
        success and failure. Invalid usage raises and retains the reservation
        rather than make unknown usage look free.
        """
        with self._lock:
            if self._in_flight == 0:
                raise RuntimeError("no admitted model call to release")
            self._observe_usage(usage_by_model)
            self._in_flight -= 1

    def allow_new_run(self) -> bool:
        """Compatibility preflight; actual calls also need before_model_call."""
        with self._lock:
            try:
                return self._can_call()
            except (OSError, ValueError, TypeError, KeyError, OverflowError):
                return False

    def record(self, take_id: str, usage_by_model: dict, elapsed_s: float) -> dict:
        """Persist one finished turn, then reset its in-memory accounting.

        Call only after all admitted calls have left their finally blocks.
        The stored estimate never drops below usage already observed by hooks.
        """
        with self._lock:
            if self._in_flight:
                raise RuntimeError("cannot record a turn with model calls still in flight")
            self._observe_usage(usage_by_model)
            entry = {
                "timestamp_ms": int(time.time() * 1000), "take_id": take_id,
                "usage_by_model": usage_by_model,
                "estimated_upper_bound_usd": self._active_usd,
                "elapsed_s": round(elapsed_s, 2),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as stream:
                stream.write(json.dumps(entry, separators=(",", ":")) + "\n")
            self._active_usd = 0.0
            return entry
