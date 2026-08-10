"""Parsing and signing contracts for production incremental providers."""

from datetime import date

import pandas as pd
import pytest

import traderharness.data.update_providers as update_providers
from traderharness.data.update_providers import (
    BaostockProvider,
    CninfoAnnouncementsProvider,
    Eastmoney5MinProvider,
    baostock_code,
    cls_sign,
    parse_baostock_rows,
    parse_baostock_valuation_rows,
    parse_cninfo_announcement,
    parse_eastmoney_5min_klines,
    retry_failed_batches,
)


def test_baostock_exchange_code_mapping():
    assert baostock_code("600519") == "sh.600519"
    assert baostock_code("300750") == "sz.300750"


def test_parse_baostock_daily_and_minute_rows():
    daily = parse_baostock_rows(
        "600519",
        [["2024-03-01", "sh.600519", "1", "2", "0.5", "1.5", "100", "150"]],
        frequency="d",
    )
    minute = parse_baostock_rows(
        "600519",
        [["20240301093500000", "sh.600519", "1", "2", "0.5", "1.5", "100", "150"]],
        frequency="5",
    )

    assert daily.iloc[0]["close"] == 1.5
    assert str(daily.iloc[0]["date"].date()) == "2024-03-01"
    assert str(minute.iloc[0]["datetime"]) == "2024-03-01 09:35:00"


def test_parse_baostock_valuation_rows():
    frame = parse_baostock_valuation_rows(
        "600519",
        [["2024-03-01", "sh.600519", "1.2", "20.5", "8.1", "15.2", "0"]],
    )

    assert frame.to_dict("records") == [
        {
            "stock_code": "600519",
            "date": pd.Timestamp("2024-03-01"),
            "turn": 1.2,
            "pe_ttm": 20.5,
            "pb_mrq": 8.1,
            "ps_ttm": 15.2,
            "is_st": False,
        }
    ]


def test_parse_eastmoney_5min_converts_lots_to_canonical_shares():
    frame = parse_eastmoney_5min_klines(
        "600519",
        [
            "2026-07-07 10:00,1193.65,1194.00,1194.99,1192.24,488,58256908.00,0.23,0.01,0.10,0.00"
        ],
    )

    assert frame.to_dict("records") == [
        {
            "stock_code": "600519",
            "date": pd.Timestamp("2026-07-07"),
            "datetime": pd.Timestamp("2026-07-07 10:00"),
            "open": 1193.65,
            "high": 1194.99,
            "low": 1192.24,
            "close": 1194.0,
            "volume": 48800,
            "amount": 58256908.0,
        }
    ]


def test_cls_signature_is_order_independent():
    assert cls_sign({"b": "2", "a": "1"}) == cls_sign({"a": "1", "b": "2"})


def test_parse_cninfo_record():
    parsed = parse_cninfo_announcement(
        {
            "secCode": "600519",
            "secName": "贵州茅台",
            "announcementTitle": "年度报告",
            "announcementTime": 1709251200000,
            "adjunctUrl": "x.pdf",
            "announcementTypeName": "年度报告",
        }
    )

    assert parsed["stock_code"] == "600519"
    assert parsed["stock_name"] == "贵州茅台"
    assert parsed["title"] == "年度报告"


def test_parse_cninfo_preserves_non_a_share_code_width_for_filtering():
    parsed = parse_cninfo_announcement(
        {
            "secCode": "02513",
            "secName": "智谱",
            "announcementTime": 1709251200000,
        }
    )

    assert parsed["stock_code"] == "02513"
    assert CninfoAnnouncementsProvider._parse_items(
        [
            {
                "secCode": "02513",
                "secName": "智谱",
                "announcementTime": 1709251200000,
            }
        ]
    ) == []


def test_retry_failed_batches_only_resubmits_failed_codes():
    calls = []

    def fetch_once(codes):
        calls.append(list(codes))
        if len(calls) == 1:
            return ["first-frame"], ["600000"]
        return ["retry-frame"], []

    frames, failed = retry_failed_batches(
        ["600519", "600000"],
        fetch_once,
        max_attempts=3,
        retry_delay=0,
    )

    assert calls == [["600519", "600000"], ["600000"]]
    assert frames == ["first-frame", "retry-frame"]
    assert failed == []


def test_baostock_provider_isolates_residual_failures_into_single_code_batches(
    monkeypatch,
):
    provider = BaostockProvider(
        frequency="d",
        batch_size=10,
        max_attempts=1,
        retry_delay=0,
    )
    calls = []

    def fake_fetch_once(codes, start, end):
        calls.append((list(codes), provider.batch_size))
        if provider.batch_size > 1:
            return [], list(codes)
        return [pd.DataFrame({"stock_code": codes})], []

    monkeypatch.setattr(provider, "_fetch_once", fake_fetch_once)

    result = provider.fetch(
        ["300997", "603880"],
        date(2026, 7, 1),
        date(2026, 7, 2),
    )

    assert calls == [
        (["300997", "603880"], 10),
        (["300997", "603880"], 1),
    ]
    assert result["stock_code"].tolist() == ["300997", "603880"]
    assert provider.batch_size == 10


def test_baostock_provider_retries_batches_when_process_pool_stalls(monkeypatch):
    submitted = []
    shutdown_calls = []

    class FakeFuture:
        def __init__(self, job):
            self.job = job

    class FakeExecutor:
        _processes = {}

        def __init__(self, *, max_workers):
            assert max_workers == 2

        def submit(self, function, job):
            future = FakeFuture(job)
            submitted.append(future)
            return future

        def shutdown(self, *, wait=True, cancel_futures=False):
            shutdown_calls.append((wait, cancel_futures))

    monkeypatch.setattr(update_providers, "ProcessPoolExecutor", FakeExecutor)
    monkeypatch.setattr(
        update_providers,
        "wait",
        lambda pending, **kwargs: (set(), set(pending)),
    )
    provider = BaostockProvider(
        frequency="5",
        workers=2,
        batch_size=1,
        stall_timeout=0.01,
        max_attempts=1,
    )

    frames, failed = provider._fetch_once(
        ["600519", "300750"],
        date(2026, 7, 1),
        date(2026, 7, 2),
    )

    assert frames == []
    assert failed == ["600519", "300750"]
    assert len(submitted) == 2
    assert shutdown_calls == [(False, True)]


def test_eastmoney_5min_provider_resumes_from_per_code_cache(tmp_path, monkeypatch):
    provider = Eastmoney5MinProvider(
        cache_dir=tmp_path,
        workers=1,
        max_attempts=1,
        retry_delay=0,
        max_passes=1,
        pass_delay=0,
    )
    calls = []
    fail_once = {"000001"}

    def fake_fetch_one(client, code, start, end):
        calls.append(code)
        if code in fail_once:
            fail_once.remove(code)
            raise RuntimeError("temporary failure")
        return parse_eastmoney_5min_klines(
            code,
            ["2026-07-08 09:35,10,10.1,10.2,9.9,100,100000,0,0,0,0"],
        )

    monkeypatch.setattr(provider, "_fetch_one", fake_fetch_one)

    with pytest.raises(RuntimeError, match="Completed code caches are preserved"):
        provider.fetch(
            ["600519", "000001"],
            date(2026, 7, 8),
            date(2026, 7, 8),
        )

    result = provider.fetch(
        ["600519", "000001"],
        date(2026, 7, 8),
        date(2026, 7, 8),
    )

    assert calls == ["600519", "000001", "000001"]
    assert sorted(result["stock_code"].tolist()) == ["000001", "600519"]


def test_eastmoney_5min_provider_retries_failed_codes_in_a_fresh_pass(tmp_path, monkeypatch):
    provider = Eastmoney5MinProvider(
        cache_dir=tmp_path,
        workers=1,
        max_attempts=1,
        retry_delay=0,
        max_passes=2,
        pass_delay=0,
    )
    calls = []

    def fake_fetch_one(client, code, start, end):
        calls.append(code)
        if len(calls) == 1:
            raise RuntimeError("temporary failure")
        return parse_eastmoney_5min_klines(
            code,
            ["2026-07-08 09:35,10,10.1,10.2,9.9,100,100000,0,0,0,0"],
        )

    monkeypatch.setattr(provider, "_fetch_one", fake_fetch_one)

    result = provider.fetch(
        ["600519"],
        date(2026, 7, 8),
        date(2026, 7, 8),
    )

    assert calls == ["600519", "600519"]
    assert result["stock_code"].tolist() == ["600519"]
    assert provider.last_failed == []
