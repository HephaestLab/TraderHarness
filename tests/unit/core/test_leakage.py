"""Static leakage audit for masked prompts and trajectories."""

from traderharness.core.leakage import EntityLeakDetector


def test_detects_real_aliases_dates_and_unresolved_templates():
    detector = EntityLeakDetector(
        {
            "600519": {"贵州茅台", "茅台"},
            "600000": {"浦发银行"},
        }
    )

    findings = detector.scan_text(
        "贵州茅台在2024-03-04发布公告，另见{{C600000}}。",
        location="step-1",
    )

    assert {item.kind for item in findings} == {"entity_alias", "calendar_date", "template"}
    assert any(item.value == "贵州茅台" for item in findings)
    assert all(item.location == "step-1" for item in findings)


def test_neutral_labels_and_relative_dates_are_clean():
    detector = EntityLeakDetector({"600519": {"贵州茅台", "茅台"}})

    findings = detector.scan_text("公司-600000在D-1上涨，今日继续观察。")

    assert findings == []


def test_detects_chinese_month_day_without_year():
    detector = EntityLeakDetector({})

    findings = detector.scan_text("财联社3月4日电。")

    assert [(item.kind, item.value) for item in findings] == [
        ("calendar_date", "3月4日")
    ]


def test_amount_with_year_is_not_a_calendar_date():
    detector = EntityLeakDetector({})

    findings = detector.scan_text("宣布2023年1万亿元增发国债项目全部下达完毕")

    assert findings == []


def test_detects_chinese_year_month_with_month_marker():
    detector = EntityLeakDetector({})

    findings = detector.scan_text("政策始于2023年1月。")

    assert [(item.kind, item.value) for item in findings] == [
        ("calendar_date", "2023年1月")
    ]
