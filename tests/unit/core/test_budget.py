"""Tests for TokenBudget — usage tracking and graceful stop."""

import pytest

from finharness.core.budget import TokenBudget


class TestTokenBudget:
    """Token budget management with warn/exhaust thresholds."""

    def test_initial_state(self):
        budget = TokenBudget(max_tokens=100_000)
        assert budget.used == 0
        assert budget.remaining == 100_000
        assert budget.is_exhausted is False

    def test_consume_tokens(self):
        budget = TokenBudget(max_tokens=100_000)
        budget.consume(5000)
        assert budget.used == 5000
        assert budget.remaining == 95_000

    def test_consume_multiple(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.consume(3000)
        budget.consume(2000)
        assert budget.used == 5000

    def test_exhausted_at_limit(self):
        budget = TokenBudget(max_tokens=1000)
        budget.consume(1000)
        assert budget.is_exhausted is True

    def test_exhausted_over_limit(self):
        budget = TokenBudget(max_tokens=1000)
        budget.consume(1500)
        assert budget.is_exhausted is True

    def test_warn_threshold_default_80pct(self):
        budget = TokenBudget(max_tokens=10_000)
        assert budget.should_warn is False
        budget.consume(7999)
        assert budget.should_warn is False
        budget.consume(1)  # total 8000 = 80%
        assert budget.should_warn is True

    def test_custom_warn_threshold(self):
        budget = TokenBudget(max_tokens=10_000, warn_threshold=0.5)
        budget.consume(4999)
        assert budget.should_warn is False
        budget.consume(1)
        assert budget.should_warn is True

    def test_usage_ratio(self):
        budget = TokenBudget(max_tokens=10_000)
        budget.consume(2500)
        assert budget.usage_ratio == pytest.approx(0.25)

    def test_unlimited_budget(self):
        budget = TokenBudget(max_tokens=0)  # 0 means unlimited
        budget.consume(999_999_999)
        assert budget.is_exhausted is False
        assert budget.should_warn is False

    def test_record_call(self):
        budget = TokenBudget(max_tokens=100_000)
        budget.record_call(prompt_tokens=500, completion_tokens=200)
        assert budget.used == 700
        assert budget.call_count == 1

    def test_multiple_calls_tracking(self):
        budget = TokenBudget(max_tokens=100_000)
        budget.record_call(prompt_tokens=100, completion_tokens=50)
        budget.record_call(prompt_tokens=200, completion_tokens=100)
        assert budget.call_count == 2
        assert budget.used == 450
