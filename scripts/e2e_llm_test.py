"""
Real LLM E2E test — 3 trading days with DeepSeek.
Logs every phase, every tool call, every response.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from traderharness.core.engine import BacktestEngine, EngineConfig
from traderharness.core.events import EventBus
from traderharness.agents.tool_agent import ToolAgent
from traderharness.agents.llm_client import LLMClient
from traderharness.metrics.performance import calculate_metrics

# Setup logging
LOG_PATH = Path(__file__).parent.parent / "e2e_llm_test.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("e2e_test")

# Patch the loop to log phases
original_run_phase = None


def patch_agent_loop():
    """Monkey-patch AgentLoop to log all tool calls and responses."""
    from traderharness.agents.loop import AgentLoop
    from traderharness.tools.registry import ToolRegistry

    original_execute = ToolRegistry.execute

    async def logged_execute(self, name, arguments, ctx):
        logger.info("TOOL_CALL: %s | args: %s", name, json.dumps(arguments, ensure_ascii=False, default=str)[:500])
        result = await original_execute(self, name, arguments, ctx)
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > 1000:
            result_str = result_str[:1000] + "..."
        logger.info("TOOL_RESULT: %s | %s", name, result_str)
        return result

    ToolRegistry.execute = logged_execute

    # Log phase transitions
    original_run_day = AgentLoop.run_day

    async def logged_run_day(self, current_date, ctx):
        logger.info("=" * 60)
        logger.info("DAY START: %s", current_date)
        logger.info("  Cash: %.2f | Positions: %s", float(ctx.portfolio.cash),
                    list(ctx.portfolio.positions.keys()))

        # Log P0/P1
        p0 = ctx.tool_call_cache.get("_p0_announcements", [])
        p1 = ctx.tool_call_cache.get("_p1_policy", [])
        corp = ctx.tool_call_cache.get("_corporate_actions", [])
        if p0:
            logger.info("  P0 announcements: %d items", len(p0))
        if p1:
            logger.info("  P1 policy: %d items", len(p1))
        if corp:
            logger.info("  Corporate actions: %s", corp)

        result = await original_run_day(self, current_date, ctx)

        logger.info("DAY END: %s | trades=%d | summary=%s",
                    current_date, len(result.trades),
                    result.summary[:200] if result.summary else "(none)")
        logger.info("=" * 60)
        return result

    AgentLoop.run_day = logged_run_day


async def main():
    patch_agent_loop()

    logger.info("Starting 3-day LLM E2E test")
    logger.info("Model: deepseek-chat")
    logger.info("Period: 2024-06-03 ~ 2024-06-05")

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL")

    llm = LLMClient(
        model="deepseek-chat",
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
        cache_enabled=False,
    )

    agent = ToolAgent(
        agent_id="e2e_test_agent",
        name="E2E Test Agent",
        llm_client=llm,
        persona="你是一位谨慎的价值投资者。偏好大盘蓝筹股，注重安全边际。不急于交易，宁可错过也不犯错。",
        initial_cash=Decimal("1000000"),
        max_positions=3,
        max_position_pct=30.0,
    )

    config = EngineConfig(initial_cash=Decimal("1000000"))
    event_bus = EventBus()
    engine = BacktestEngine(config=config, event_bus=event_bus)

    try:
        result = await engine.run(
            agents=[agent],
            start_date=date(2024, 6, 3),
            end_date=date(2024, 6, 5),
        )
    except Exception as e:
        logger.error("ENGINE CRASHED: %s", e, exc_info=True)
        return

    # Results
    data = result.agent_data["e2e_test_agent"]
    curve = data["equity_curve"]
    trades = data["trades"]

    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("  Trading days: %d", result.trading_days)
    logger.info("  Trades: %d", len(trades))
    for t in trades:
        logger.info("    %s %s %s x%d @%.2f", t.get("date"), t.get("action"),
                    t.get("stock_code"), t.get("quantity", 0), float(t.get("price", 0)))
    logger.info("  Equity curve:")
    for d, v in curve:
        logger.info("    %s: %.2f", d, float(v))

    metrics = calculate_metrics(curve, Decimal("1000000"), trades)
    logger.info("  Return: %.2f%%", metrics.total_return_pct)
    logger.info("  Token usage: %d", llm.total_tokens_used)
    logger.info("DONE")


if __name__ == "__main__":
    asyncio.run(main())
