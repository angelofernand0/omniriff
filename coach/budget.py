"""Conservative local token-usage guard; not a provider billing statement."""
from __future__ import annotations

import json
import time
from pathlib import Path


LIMIT_USD = 8.0
RUN_RESERVE_USD = 2.0
# Deliberately pessimistic safety rates, not a claim about current provider prices.
INPUT_USD_PER_M = 15.0
OUTPUT_USD_PER_M = 75.0


def estimate_upper_bound_usd(usage_by_model: dict) -> float:
    """Charge every model at the same pessimistic upper-bound token rates."""
    input_tokens = sum(int(data.get("input_tokens", 0)) for data in usage_by_model.values())
    output_tokens = sum(int(data.get("output_tokens", 0)) for data in usage_by_model.values())
    return round((input_tokens * INPUT_USD_PER_M + output_tokens * OUTPUT_USD_PER_M) / 1_000_000, 6)


class BudgetGuard:
    def __init__(self, path: Path):
        self.path = Path(path)

    def spent_usd(self) -> float:
        if not self.path.is_file():
            return 0.0
        total = 0.0
        with self.path.open() as stream:
            for line in stream:
                if line.strip():
                    total += float(json.loads(line)["estimated_upper_bound_usd"])
        return round(total, 6)

    def allow_new_run(self) -> bool:
        """Reserve headroom before *each* model run, not only at session start."""
        return self.spent_usd() + RUN_RESERVE_USD < LIMIT_USD

    def record(self, take_id: str, usage_by_model: dict, elapsed_s: float) -> dict:
        entry = {
            "timestamp_ms": int(time.time() * 1000), "take_id": take_id,
            "usage_by_model": usage_by_model,
            "estimated_upper_bound_usd": estimate_upper_bound_usd(usage_by_model),
            "elapsed_s": round(elapsed_s, 2),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as stream:
            stream.write(json.dumps(entry, separators=(",", ":")) + "\n")
        return entry
