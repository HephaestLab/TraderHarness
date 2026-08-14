"""Point-in-time text tools return evidence that can be audited and linked."""

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from traderharness.core.entity_masking import EntityMasker
from traderharness.core.masking import DateMasker
from traderharness.core.portfolio import Portfolio
from traderharness.tools.news import (
    handle_get_announcement_evidence,
    handle_get_narrative_news,
)
from traderharness.tools.registry import ToolContext, ToolDefinition, ToolRegistry


def _ctx() -> ToolContext:
    current = date(2026, 3, 5)
    ctx = ToolContext(
        agent_id="behavioral-cycle",
        current_date=current,
        current_phase="pre_market",
        portfolio=Portfolio(Decimal("1000000")),
        initial_cash=Decimal("1000000"),
        preloaded_daily={"601012": pd.DataFrame({"date": [date(2026, 3, 4)]})},
        date_masker=DateMasker(anchor=current),
    )
    ctx.tool_call_cache["_news_data"] = pd.DataFrame(
        [
            {
                "id": 10,
                "title": "光伏行业出现新政策",
                "content": "政策支持光伏行业整合，隆基绿能受关注。",
                "display_time": pd.Timestamp("2026-03-04 10:00:00"),
                "level": "A",
                "tags": "光伏,政策",
                "stock_list": "隆基绿能",
            },
            {
                "id": 11,
                "title": "未来消息",
                "content": "这条消息在研究日之后。",
                "display_time": pd.Timestamp("2026-03-05 10:00:00"),
                "level": "A",
                "tags": "",
                "stock_list": "",
            },
        ]
    )
    ctx.tool_call_cache["_announcements_data"] = pd.DataFrame(
        [
            {
                "stock_code": "601012",
                "title": "关于行业整合的公告",
                "announcement_time": pd.Timestamp("2026-03-03 18:00:00"),
                "ann_type": "临时公告",
            }
        ]
    )
    return ctx


@pytest.mark.asyncio
async def test_news_returns_timestamped_linkable_evidence_and_excludes_future(monkeypatch):
    monkeypatch.setattr("traderharness.tools.news.get_stock_name", lambda code: "隆基绿能")
    ctx = _ctx()
    result = await handle_get_narrative_news(
        {
            "days": 3,
            "stock_code": "601012",
            "market_relevant_only": True,
            "max_results": 10,
        },
        ctx,
    )

    assert result["count"] == 1
    evidence = result["news"][0]
    assert evidence["evidence_id"] == "news:10"
    assert evidence["time"] == "D-1 10:00"
    assert evidence["title"] == "光伏行业出现新政策"
    assert evidence["tags"] == "光伏,政策"
    assert evidence["linked_stocks"] == "隆基绿能"
    assert "未来消息" not in str(result)
    assert ctx.tool_call_cache["_visible_text_evidence_ids"] == {"news:10"}


@pytest.mark.asyncio
async def test_announcements_return_timestamped_evidence():
    ctx = _ctx()
    result = await handle_get_announcement_evidence(
        {"stock_code": "601012", "days": 30},
        ctx,
    )

    assert result["count"] == 1
    assert result["announcements"][0] == {
        "evidence_id": "announcement:601012:0",
        "time": "D-2 18:00",
        "title": "关于行业整合的公告",
        "type": "临时公告",
    }
    assert ctx.tool_call_cache["_visible_text_evidence_ids"] == {
        "announcement:601012:0"
    }


@pytest.mark.asyncio
async def test_registry_masks_in_universe_and_external_company_names_in_text():
    ctx = _ctx()
    ctx.tool_call_cache["_news_data"].loc[0, "content"] += " 中国平安也被提及。"
    ctx.entity_masker = EntityMasker(
        ["601012", "600000"],
        names={"601012": "隆基绿能", "600000": "浦发银行"},
        sanitize_aliases={"601318": ["中国平安"]},
        seed=1,
    )
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_narrative_news",
            description="test",
            parameters={"type": "object", "properties": {}},
            handler=handle_get_narrative_news,
        )
    )

    result = await registry.execute(
        "get_narrative_news",
        {"days": 3, "stock_code": ctx.entity_masker.mask_code("601012")},
        ctx,
    )

    rendered = str(result)
    assert "隆基绿能" not in rendered
    assert "中国平安" not in rendered
    assert "601012" not in rendered
    assert "外部公司" in rendered
