"""One shared admission gate for every parent and specialist model call."""
from __future__ import annotations

from threading import Lock


class ModelCallGate:
    def __init__(self, guard):
        self.guard = guard
        self._lock = Lock()
        self._callback = None
        self._refused = False
        self._admitted = 0

    def bind(self, callback) -> None:
        """Use one invocation's cumulative, still-unrecorded usage."""
        with self._lock:
            self._callback = callback
            if callback is not None:
                self._refused = False
                self._admitted = 0

    @property
    def refused(self) -> bool:
        with self._lock:
            return self._refused

    @property
    def admitted_count(self) -> int:
        with self._lock:
            return self._admitted

    def usage(self) -> dict:
        with self._lock:
            callback = self._callback
        if callback is None:
            return {}
        # UsageMetadataCallbackHandler owns this lock while callbacks update totals.
        with callback._lock:
            return {model: dict(data) for model, data in callback.usage_metadata.items()}

    def call(self, handler):
        """The budget guard owns atomic in-flight reservations, including failures."""
        from .runner import BudgetExhausted

        if self.refused:
            raise BudgetExhausted("coach budget guard already refused this invocation")
        if not self.guard.before_model_call(self.usage()):
            with self._lock:
                self._refused = True
            raise BudgetExhausted("coach budget guard refused a model call")
        with self._lock:
            self._admitted += 1
        try:
            return handler()
        finally:
            self.guard.after_model_call(self.usage())
