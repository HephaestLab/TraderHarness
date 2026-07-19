"""Parsing and signing contracts for production incremental providers."""

from datetime import date

import pandas as pd

from traderharness.data.update_providers import (
    BaostockProvider,
    CninfoAnnouncementsProvider,
    baostock_code,
    cls_sign,
    parse_baostock_rows,
    parse_baostock_valuation_rows,
    parse_cninfo_announcement,
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
