"""TokenBudget — track LLM token usage with warn/exhaust thresholds."""

from __future__ import annotations


class TokenBudget:
    """Tracks token consumption and signals when budget is near or exceeded."""

    def __init__(self, max_tokens: int, warn_threshold: float = 0.8) -> None:
        self._max_tokens = max_tokens
        self._warn_threshold = warn_threshold
        self._used: int = 0
        self._call_count: int = 0

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        if self._max_tokens == 0:
            return 999_999_999
        return max(0, self._max_tokens - self._used)

    @property
    def is_exhausted(self) -> bool:
        if self._max_tokens == 0:
            return False
        return self._used >= self._max_tokens

    @property
    def should_warn(self) -> bool:
        if self._max_tokens == 0:
            return False
        return self._used >= self._max_tokens * self._warn_threshold

    @property
    def usage_ratio(self) -> float:
        if self._max_tokens == 0:
            return 0.0
        return self._used / self._max_tokens

    @property
    def call_count(self) -> int:
        return self._call_count

    def consume(self, tokens: int) -> None:
        self._used += tokens

    def record_call(self, prompt_tokens: int, completion_tokens: int) -> None:
        self._used += prompt_tokens + completion_tokens
        self._call_count += 1
