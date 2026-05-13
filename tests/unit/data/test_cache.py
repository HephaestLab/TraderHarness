"""Tests for SQLite data cache."""

from datetime import date

import pandas as pd
import pytest

from finharness.data.cache import DataCache


@pytest.fixture
def cache(tmp_path):
    return DataCache(cache_path=tmp_path / "test.db")


class TestDataCache:
    def test_put_and_get(self, cache):
        df = pd.DataFrame({
            "date": [date(2024, 3, 4)],
            "close": [1800.0],
        })
        cache.put("600519", date(2024, 3, 4), date(2024, 3, 4), df)
        result = cache.get("600519", date(2024, 3, 4), date(2024, 3, 4))
        assert result is not None
        assert len(result) == 1

    def test_miss_returns_none(self, cache):
        result = cache.get("600519", date(2024, 3, 4), date(2024, 3, 4))
        assert result is None

    def test_clear(self, cache):
        df = pd.DataFrame({"date": [date(2024, 3, 4)], "close": [1800.0]})
        cache.put("600519", date(2024, 3, 4), date(2024, 3, 4), df)
        cache.clear()
        assert cache.get("600519", date(2024, 3, 4), date(2024, 3, 4)) is None
