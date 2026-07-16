"""Sandbox filesystem isolation tests.

The sandbox MUST NOT let agent code read the raw dataset (or any file outside
the agent workspace), otherwise the date-masking / look-ahead protections are
trivially bypassed via ``pandas.read_parquet`` / ``open``.

``execute_code`` is the single sandbox entry point.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from traderharness.tools.registry import ToolContext
from traderharness.core.portfolio import Portfolio
from traderharness.tools.sandbox import handle_execute_code


def _make_ctx(workspace: Path) -> ToolContext:
    portfolio = Portfolio(Decimal("1000000"))
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
        portfolio=portfolio,
        initial_cash=Decimal("1000000"),
        preloaded_daily=preloaded,
        execution_price={"600519": Decimal("1805")},
        agent_id="test_agent",
        workspace_root=str(workspace),
    )


def _make_secret_parquet(outside_dir: Path) -> Path:
    """Simulate the raw dataset sitting outside the workspace (incl. future data)."""
    secret = outside_dir / "daily.parquet"
    pd.DataFrame({
        "date": [date(2099, 1, 1)],
        "close": [99999.0],
        "SECRET": ["FUTURE_DATA_LEAK"],
    }).to_parquet(secret)
    return secret


class TestExecuteCodeFilesystemIsolation:
    @pytest.mark.asyncio
    async def test_cannot_read_parquet_outside_workspace(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        secret = _make_secret_parquet(tmp_path)
        ctx = _make_ctx(ws)
        code = f"import pandas as pd\nresult = pd.read_parquet(r'{secret}').to_dict()"
        result = await handle_execute_code({"code": code}, ctx)
        assert "FUTURE_DATA_LEAK" not in str(result)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cannot_open_outside_workspace(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("FUTURE_DATA_LEAK")
        ctx = _make_ctx(ws)
        code = f"result = open(r'{secret}').read()"
        result = await handle_execute_code({"code": code}, ctx)
        assert "FUTURE_DATA_LEAK" not in str(result)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cannot_import_os(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        ctx = _make_ctx(ws)
        result = await handle_execute_code({"code": "import os\nresult = os.listdir('.')"}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cannot_import_pathlib(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        ctx = _make_ctx(ws)
        result = await handle_execute_code({"code": "import pathlib\nresult = 1"}, ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_blocks_backtest_frameworks(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        ctx = _make_ctx(ws)
        for mod in ("traderharness", "backtrader", "qlib"):
            result = await handle_execute_code({"code": f"import {mod}\nresult = 1"}, ctx)
            assert "error" in result, f"import {mod} should be blocked"

    @pytest.mark.asyncio
    async def test_can_read_workspace_parquet(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        pd.DataFrame({"a": [1, 2, 3]}).to_parquet(ws / "scratch.parquet")
        ctx = _make_ctx(ws)
        code = "import pandas as pd\nresult = int(pd.read_parquet('scratch.parquet')['a'].sum())"
        result = await handle_execute_code({"code": code}, ctx)
        assert result.get("result") == 6

    @pytest.mark.asyncio
    async def test_can_write_and_read_workspace_files(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        ctx = _make_ctx(ws)
        write = await handle_execute_code(
            {"code": "open('notes.txt', 'w').write('hello')\nresult = 'written'"}, ctx)
        assert write.get("result") == "written"
        read = await handle_execute_code(
            {"code": "result = open('notes.txt').read()"}, ctx)
        assert read.get("result") == "hello"

    @pytest.mark.asyncio
    async def test_numpy_pandas_still_work(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        ctx = _make_ctx(ws)
        code = "import numpy as np\nimport pandas as pd\nresult = float(np.mean([2, 4]))"
        result = await handle_execute_code({"code": code}, ctx)
        assert result.get("result") == 3.0
