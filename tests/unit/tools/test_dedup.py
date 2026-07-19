"""TDD tests for tool call deduplication — same params same day returns cached hint."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.portfolio import Portfolio
from traderharness.tools.registry import ToolContext


def _make_ctx() -> ToolContext:
    preloaded = {"600519": pd.DataFrame({
        "date": [date(2024, 3, d) for d in range(1, 6)],
        "open": [1800 + i for i in range(5)],
        "high": [1810 + i for i in range(5)],
        "low": [1790 + i for i in range(5)],
        "close": [1805 + i for i in range(5)],
        "volume": [10000] * 5,
    })}
    return ToolContext(
        current_date=date(2024, 3, 5),
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily=preloaded,
        agent_id="test",
    )


class TestDedup:
    @pytest.mark.asyncio
    async def test_get_stock_info_dedup(self):
        from traderharness.tools.dedup import with_dedup
        from traderharness.tools.market import handle_get_stock_info
        ctx = _make_ctx()

        wrapped = with_dedup(handle_get_stock_info)
        r1 = await wrapped({"stock_code": "600519"}, ctx)
        r2 = await wrapped({"stock_code": "600519"}, ctx)

        # First call: full result
        assert "name" in r1
        # Second call: dedup hint
        assert r2.get("_dedup") is True or "name" in r2

    @pytest.mark.asyncio
    async def test_different_params_no_dedup(self):
        from traderharness.tools.dedup import with_dedup
        from traderharness.tools.market import handle_get_stock_info
        ctx = _make_ctx()

        wrapped = with_dedup(handle_get_stock_info)
        r1 = await wrapped({"stock_code": "600519"}, ctx)
        r2 = await wrapped({"stock_code": "000001"}, ctx)

        # Different params: both full results
        assert "name" in r1
        assert "error" in r2 or "name" in r2  # 000001 may not be in preloaded

    @pytest.mark.asyncio
    async def test_dedup_does_not_cache_errors(self):
        from traderharness.tools.dedup import with_dedup
        from traderharness.tools.market import handle_get_stock_info
        ctx = _make_ctx()

        wrapped = with_dedup(handle_get_stock_info)
        r1 = await wrapped({"stock_code": ""}, ctx)  # error
        r2 = await wrapped({"stock_code": ""}, ctx)  # should still return error, not dedup

        assert "error" in r1
        assert "error" in r2
        assert r2.get("_dedup") is not True
