"""ToolAgent registry contract — the exact tool surface exposed to the LLM.

CLAUDE.md tool design: single sandbox entry (execute_code); no legacy
read_file/write_file/list_files/run_python; market overview registered.
"""

from decimal import Decimal

from traderharness.agents.tool_agent import ToolAgent

EXPECTED_TOOLS = {
    # market data
    "get_kline", "get_stock_price", "get_stock_info",
    # analysis
    "get_market_overview", "screen_stocks", "get_sector_summary",
    # fundamentals & news
    "get_fundamentals", "get_business_segments", "get_valuation",
    "get_announcements", "get_news",
    # portfolio & trading
    "get_portfolio", "get_position", "place_order",
    # watchlist
    "add_watchlist", "remove_watchlist", "get_watchlist",
    # sandbox & control
    "execute_code", "finish_day",
}

LEGACY_TOOLS = {"read_file", "write_file", "list_files", "run_python", "run_script"}


def _make_agent(tmp_path) -> ToolAgent:
    class _StubLLM:
        model = "stub"

    return ToolAgent(
        agent_id="registry_test",
        name="registry_test",
        llm_client=_StubLLM(),
        initial_cash=Decimal("1000000"),
        memory_dir=str(tmp_path),
    )


def test_registered_tool_surface(tmp_path):
    agent = _make_agent(tmp_path)
    registered = {
        s["function"]["name"] for s in agent._registry.get_openai_tools_schema()
    }
    assert registered == EXPECTED_TOOLS


def test_no_legacy_tools(tmp_path):
    agent = _make_agent(tmp_path)
    for name in LEGACY_TOOLS:
        assert name not in agent._registry, f"legacy tool {name} still registered"


def test_system_prompt_mentions_current_tools_only(tmp_path):
    agent = _make_agent(tmp_path)
    prompt = agent._system_prompt
    assert "execute_code" in prompt
    assert "get_market_overview" in prompt
    for name in LEGACY_TOOLS:
        assert name not in prompt, f"system prompt still mentions {name}"


def test_system_prompt_documents_sandbox_api_contract(tmp_path):
    agent = _make_agent(tmp_path)
    prompt = agent._system_prompt
    assert "traderharness_api" in prompt
    assert "get_all_daily" in prompt
    assert "change_pct" in prompt
    assert "get_sector_stocks" in prompt
    assert "offset" in prompt
