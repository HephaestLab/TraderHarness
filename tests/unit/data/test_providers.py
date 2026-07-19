"""Tests for data providers."""

from datetime import date

import pandas as pd
import pytest

from traderharness.data.providers.parquet import ParquetProvider


@pytest.fixture
def sample_parquet(tmp_path):
    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-03-04", "2024-03-05", "2024-03-06"]),
        "open": [1800.0, 1810.0, 1820.0],
        "high": [1850.0, 1860.0, 1870.0],
        "low": [1790.0, 1800.0, 1810.0],
        "close": [1810.0, 1820.0, 1830.0],
        "volume": [10000, 12000, 11000],
    })
    df.to_parquet(tmp_path / "600519.parquet")
    return tmp_path


class TestParquetProvider:
    @pytest.mark.asyncio
    async def test_get_daily_bars(self, sample_parquet):
        p = ParquetProvider(sample_parquet)
        df = await p.get_daily_bars("600519", date(2024, 3, 4), date(2024, 3, 6))
        assert len(df) == 3
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]

    @pytest.mark.asyncio
    async def test_date_filtering(self, sample_parquet):
        p = ParquetProvider(sample_parquet)
        df = await p.get_daily_bars("600519", date(2024, 3, 5), date(2024, 3, 5))
        assert len(df) == 1

    @pytest.mark.asyncio
    async def test_missing_stock(self, sample_parquet):
        p = ParquetProvider(sample_parquet)
        df = await p.get_daily_bars("000001", date(2024, 3, 4), date(2024, 3, 6))
        assert df.empty

    @pytest.mark.asyncio
    async def test_get_stock_list(self, sample_parquet):
        p = ParquetProvider(sample_parquet)
        stocks = await p.get_stock_list()
        assert len(stocks) == 1
        assert stocks[0]["code"] == "600519"
