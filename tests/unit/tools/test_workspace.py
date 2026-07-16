"""TDD tests for workspace tools — read_file, write_file, list_files, run_python.

Tests the new sandbox design:
- Agent has a persistent workspace directory
- Can read/write files within workspace only
- run_python injects traderharness_api, blocks dangerous imports
- Cannot escape workspace or import backtest modules
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from traderharness.tools.registry import ToolContext
from traderharness.core.portfolio import Portfolio


def _make_ctx(tmp_path: Path) -> ToolContext:
    portfolio = Portfolio(Decimal("1000000"))
    preloaded = {"600519": pd.DataFrame({
        "date": [date(2024, 3, d) for d in range(1, 6)],
        "open": [1800 + i for i in range(5)],
        "high": [1810 + i for i in range(5)],
        "low": [1790 + i for i in range(5)],
        "close": [1805 + i for i in range(5)],
        "volume": [10000] * 5,
    })}
    ctx = ToolContext(
        current_date=date(2024, 3, 5),
        current_phase="pre_market",
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        preloaded_daily=preloaded,
        execution_price={"600519": Decimal("1805")},
        agent_id="test_agent",
        workspace_root=str(tmp_path),
    )
    return ctx


class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_creates_file(self, tmp_path):
        from traderharness.tools.workspace import handle_write_file
        ctx = _make_ctx(tmp_path)
        result = await handle_write_file({"path": "notes/day1.md", "content": "hello world"}, ctx)
        assert result.get("success") is True
        assert (tmp_path / "notes" / "day1.md").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_rejects_path_escape(self, tmp_path):
        from traderharness.tools.workspace import handle_write_file
        ctx = _make_ctx(tmp_path)
        result = await handle_write_file({"path": "../../etc/passwd", "content": "hack"}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_write_rejects_absolute_path(self, tmp_path):
        from traderharness.tools.workspace import handle_write_file
        ctx = _make_ctx(tmp_path)
        result = await handle_write_file({"path": "/tmp/evil.py", "content": "hack"}, ctx)
        assert "error" in result


class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        from traderharness.tools.workspace import handle_read_file
        (tmp_path / "test.txt").write_text("content here")
        ctx = _make_ctx(tmp_path)
        result = await handle_read_file({"path": "test.txt"}, ctx)
        assert result.get("content") == "content here"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_path):
        from traderharness.tools.workspace import handle_read_file
        ctx = _make_ctx(tmp_path)
        result = await handle_read_file({"path": "missing.txt"}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_read_rejects_path_escape(self, tmp_path):
        from traderharness.tools.workspace import handle_read_file
        ctx = _make_ctx(tmp_path)
        result = await handle_read_file({"path": "../../../etc/passwd"}, ctx)
        assert "error" in result


class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_root(self, tmp_path):
        from traderharness.tools.workspace import handle_list_files
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "c.md").write_text("c")
        ctx = _make_ctx(tmp_path)
        result = await handle_list_files({"path": "."}, ctx)
        assert "a.txt" in result.get("files", [])
        assert "b.py" in result.get("files", [])
        assert "subdir/" in result.get("files", []) or "subdir" in result.get("files", [])

    @pytest.mark.asyncio
    async def test_list_subdir(self, tmp_path):
        from traderharness.tools.workspace import handle_list_files
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "x.py").write_text("x")
        ctx = _make_ctx(tmp_path)
        result = await handle_list_files({"path": "sub"}, ctx)
        assert "x.py" in result.get("files", [])

    @pytest.mark.asyncio
    async def test_list_rejects_escape(self, tmp_path):
        from traderharness.tools.workspace import handle_list_files
        ctx = _make_ctx(tmp_path)
        result = await handle_list_files({"path": "../../"}, ctx)
        assert "error" in result


class TestRunPython:
    @pytest.mark.asyncio
    async def test_basic_execution(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        result = await handle_run_python({"code": "result = 1 + 1"}, ctx)
        assert result.get("result") == 2

    @pytest.mark.asyncio
    async def test_traderharness_api_available(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "from traderharness_api import market\nresult = len(market.get_stock_list())"
        result = await handle_run_python({"code": code}, ctx)
        assert result.get("result") == 1  # only 600519 in test data

    @pytest.mark.asyncio
    async def test_blocks_traderharness_import(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "from traderharness.core.engine import BacktestEngine"
        result = await handle_run_python({"code": code}, ctx)
        assert "error" in result
        assert "禁止" in result["error"] or "blocked" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_blocks_backtrader_import(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "import backtrader"
        result = await handle_run_python({"code": code}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_can_read_workspace_files(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        (tmp_path / "data.txt").write_text("hello from file")
        ctx = _make_ctx(tmp_path)
        code = "result = open('data.txt').read()"
        result = await handle_run_python({"code": code}, ctx)
        assert result.get("result") == "hello from file"

    @pytest.mark.asyncio
    async def test_can_write_workspace_files(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "open('output.txt', 'w').write('written by agent')\nresult = 'ok'"
        result = await handle_run_python({"code": code}, ctx)
        assert result.get("result") == "ok"
        assert (tmp_path / "output.txt").read_text() == "written by agent"

    @pytest.mark.asyncio
    async def test_cannot_read_outside_workspace(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "result = open('/etc/passwd').read()"
        result = await handle_run_python({"code": code}, ctx)
        # Should either error or be blocked
        assert "error" in result or result.get("result") is None

    @pytest.mark.asyncio
    async def test_numpy_pandas_available(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = "import numpy as np; import pandas as pd; result = float(np.mean([1,2,3]))"
        result = await handle_run_python({"code": code}, ctx)
        assert result.get("result") == 2.0

    @pytest.mark.asyncio
    async def test_date_masking(self, tmp_path):
        from traderharness.tools.workspace import handle_run_python
        ctx = _make_ctx(tmp_path)
        code = """
from traderharness_api import market
df = market.get_kline('600519', days=120)
result = str(df['date'].max())
"""
        result = await handle_run_python({"code": code}, ctx)
        # current_date is 2024-03-05, should not include it
        assert "2024-03-05" not in str(result.get("result", ""))
