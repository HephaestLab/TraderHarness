"""Offline company-name templating for distributable text datasets."""

import pandas as pd

from traderharness.data.entity_templates import (
    EntityTemplateMap,
    build_alias_map,
    filter_a_share_announcements,
)


def test_longest_alias_wins_and_special_characters_are_literal():
    templates = EntityTemplateMap(
        {
            "600519": {"长江", "长江电力", "长电(集团)"},
            "600000": {"浦发银行"},
        }
    )

    text = templates.template_text("长江电力和长电(集团)公告，长江上涨")

    assert text == "{{C600519}}和{{C600519}}公告，{{C600519}}上涨"


def test_templates_company_names_when_immediately_followed_by_board_count():
    templates = EntityTemplateMap(
        {
            "605298": {"必得科技"},
            "603261": {"立航科技"},
        }
    )

    text = templates.template_text("必得科技3连板、立航科技6板")

    assert text == "{{C605298}}3连板、{{C603261}}6板"


def test_template_frame_does_not_mutate_input():
    templates = EntityTemplateMap({"600519": {"贵州茅台", "茅台"}})
    frame = pd.DataFrame(
        {
            "title": ["贵州茅台年度报告"],
            "content": ["茅台发布分红方案"],
            "value": [1],
        }
    )

    result = templates.template_frame(frame, ["title", "content"])

    assert frame.iloc[0]["title"] == "贵州茅台年度报告"
    assert result.iloc[0]["title"] == "{{C600519}}年度报告"
    assert result.iloc[0]["content"] == "{{C600519}}发布分红方案"
    assert result.iloc[0]["value"] == 1


def test_build_alias_map_combines_registry_and_announcement_names():
    registry = {
        "600519": {"name": "贵州茅台"},
        "600000": {"name": "浦发银行"},
        "002513": {"name": "蓝丰生化"},
    }
    announcements = pd.DataFrame(
        {
            "stock_code": ["600519", "600519", "930651", "02513", "002513"],
            "stock_name": [
                "茅台",
                "贵州茅台股份有限公司",
                "银行",
                "智谱",
                "蓝丰旧名",
            ],
        }
    )

    aliases = build_alias_map(registry, announcements)

    assert aliases["600519"] == {"贵州茅台", "茅台", "贵州茅台股份有限公司"}
    assert aliases["600000"] == {"浦发银行"}
    assert aliases["002513"] == {"蓝丰生化", "蓝丰旧名"}
    assert "930651" not in aliases


def test_filter_a_share_announcements_rejects_short_hk_codes_without_zfill():
    frame = pd.DataFrame(
        {
            "stock_code": ["600519", "02513", "510300", "301001"],
            "stock_name": ["贵州茅台", "智谱", "沪深300ETF", "联合精密"],
        }
    )

    filtered = filter_a_share_announcements(frame)

    assert filtered["stock_code"].tolist() == ["600519", "301001"]
