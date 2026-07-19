"""ToolAgent — 完整的 Tool-Use Agentic Agent。

从源项目 backend/agents/agentic/tool_agent.py 迁移。
支持 TradingBus 模式：通过 on_day() 接入总线，Agent 自主查询一切数据。
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from traderharness.agents.llm_client import LLMClient
from traderharness.agents.loop import AgentLoop, DayResult
from traderharness.agents.memory import DailyMemory
from traderharness.core.events import EventBus
from traderharness.tools.analysis import GET_MARKET_OVERVIEW, GET_SECTOR_SUMMARY, SCREEN_STOCKS
from traderharness.tools.business import GET_BUSINESS_SEGMENTS
from traderharness.tools.catalog import normalize_allowed_tools
from traderharness.tools.control import FINISH_DAY
from traderharness.tools.fundamentals import GET_FUNDAMENTALS
from traderharness.tools.market import GET_KLINE, GET_STOCK_INFO, GET_STOCK_PRICE
from traderharness.tools.news import GET_ANNOUNCEMENTS, GET_NEWS
from traderharness.tools.portfolio import GET_PORTFOLIO, GET_POSITION
from traderharness.tools.registry import ToolContext, ToolRegistry
from traderharness.tools.sandbox import EXECUTE_CODE
from traderharness.tools.trading import PLACE_ORDER
from traderharness.tools.valuation import GET_VALUATION
from traderharness.tools.watchlist import ADD_WATCHLIST, GET_WATCHLIST, REMOVE_WATCHLIST

if TYPE_CHECKING:
    from traderharness.trajectory.collector import TrajectoryCollector

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = (
    GET_KLINE,
    GET_STOCK_PRICE,
    GET_STOCK_INFO,
    GET_MARKET_OVERVIEW,
    SCREEN_STOCKS,
    GET_SECTOR_SUMMARY,
    GET_PORTFOLIO,
    GET_POSITION,
    PLACE_ORDER,
    GET_FUNDAMENTALS,
    GET_ANNOUNCEMENTS,
    GET_NEWS,
    ADD_WATCHLIST,
    REMOVE_WATCHLIST,
    GET_WATCHLIST,
    EXECUTE_CODE,
    GET_BUSINESS_SEGMENTS,
    GET_VALUATION,
    FINISH_DAY,
)

DECISION_RECORDING_CONTRACT = """

## 决策记录要求

每次调用 place_order 前必须形成可审计的决策摘要，不要输出隐藏思维过程，只记录可验证依据。
reasoning 参数必须明确包含：交易信号、使用的数据或事件证据、主要风险与失效条件、仓位依据、退出计划。
不得只写“趋势较好”“看涨”或“止损”等无法复盘的短句。
"""

# Current contract version: DECISION_RECORDING_CONTRACT is injected into the
# system prompt. Cassettes/bundles recorded under this version include the
# contract text in every recorded prompt fingerprint.
CONTRACT_VERSION = "v2"
# Legacy version: no contract text was injected (pre-dates this feature, or a
# manifest/replay source explicitly says the recorded prompt lacked it).
LEGACY_CONTRACT_VERSION = "v1"


def resolve_decision_contract(
    llm_client: object,
    prompt_contract_version: str | None = None,
) -> tuple[str, str]:
    """Decide whether to inject `DECISION_RECORDING_CONTRACT` into the system
    prompt, and report which contract version that decision corresponds to.

    Returns `(contract_text, contract_version)`. `contract_text` is either
    `DECISION_RECORDING_CONTRACT` or a blank placeholder ("\\n") that keeps the
    template's line structure stable.

    Resolution order:
    1. If `prompt_contract_version` is given (typically read from a Replay
       Bundle manifest during replay, or explicitly set when recording), it
       is authoritative: `CONTRACT_VERSION` injects, anything else suppresses.
       This lets replay reproduce exactly whatever prompt was recorded,
       regardless of the current code's live-vs-replay state.
    2. Otherwise, fall back to the legacy heuristic: a replay player without
       manifest context means an old (pre-contract) v1 cassette, so the
       contract is suppressed to keep the request fingerprint stable; a live
       client (no player) injects the current contract.
    """
    if prompt_contract_version is not None:
        if prompt_contract_version == CONTRACT_VERSION:
            return DECISION_RECORDING_CONTRACT, CONTRACT_VERSION
        return "\n", LEGACY_CONTRACT_VERSION
    if getattr(llm_client, "_player", None) is not None:
        return "\n", LEGACY_CONTRACT_VERSION
    return DECISION_RECORDING_CONTRACT, CONTRACT_VERSION

SYSTEM_PROMPT_TEMPLATE = """
你是一位A股交易员，正在模拟交易环境中回测对战。初始资金{initial_cash}元。

## 每天流程

**盘前分析**：你会收到市场晨报（包含持仓、板块、公告、政策快讯）。可以自由使用工具研究市场（最多10轮），但不能下单。
**开盘窗口 (9:30-10:00)**：可以下单（最多3轮），成交价为开盘价。
**尾盘窗口 (14:30-15:00)**：可以下单（最多3轮），成交价为收盘价。
完成后调用 finish_day 写下今日总结（含持仓理由、市场判断、下一步计划）。

## 交易规则

1. T+1：今天买入的股票明天才能卖
2. 同一只股票一天只能操作一次（买或卖）
3. 买入数量必须是100的整数倍（1手=100股）
4. 涨跌停限制：主板±10%，创业板(300/301)±20%，科创板(688)±20%
5. 停牌股无法交易（环境自动拒绝）
6. 手续费：买入佣金0.025%（最低5元），卖出佣金0.025%+印花税0.1%
7. 你不知道未来会发生什么，只能基于已有信息判断

## 风控约束

- 单只股票仓位不超过总资产的{max_position_pct}%
- 最多同时持有{max_positions}只股票
- 空仓也是策略，不必强制交易
- 注意控制回撤，亏损达10%时应认真复盘
{decision_recording_contract}## 工具说明

| 工具 | 用途 |
|------|------|
| get_kline | 查K线（最多120天） |
| get_stock_price | 查最新价和涨跌幅 |
| get_stock_info | 查股票基本信息（名称/行业/板块） |
| get_fundamentals | 查财务指标（ROE/净利润/营收/EPS） |
| get_business_segments | 查主营业务构成（产品/地区营收占比+毛利率） |
| get_valuation | 查估值（PE/PB/PS/换手率/是否ST） |
| get_market_overview | 全市场概览（涨跌家数、板块涨幅/跌幅前5） |
| get_sector_summary | 板块涨跌排名 |
| screen_stocks | 条件选股 |
| get_announcements | 查个股公告 |
| get_news | 查财经快讯（可按关键词过滤） |
| get_portfolio | 查持仓全貌 |
| get_position | 查单只股票持仓详情 |
| place_order | 下单买入/卖出（仅开盘/尾盘窗口可用） |
| add_watchlist | 加入自选股 |
| remove_watchlist | 移出自选股 |
| get_watchlist | 查看自选股 |
| execute_code | 执行Python代码（通过traderharness_api访问数据） |
| finish_day | 结束交易日并写总结 |

### execute_code / traderharness_api 契约

沙箱内只能：`from traderharness_api import market, portfolio, news`，再配合 numpy/pandas。

**market 合法方法**（禁止臆造其它名字）：
`get_kline(code, days=60)`、`get_kline_5min(code)`、`get_stock_list()`、`get_all_stocks()`（=list 别名）、
`get_all_daily(days=20)`、`get_stock_price(code)`、`get_fundamentals(code)`、
`get_market_overview()`、`get_sector_summary(sector)`、`get_sector_stocks(sector)`、`screen_stocks(**筛选参数)`。

**get_all_daily 列名**：`stock_code, date, open, high, low, close, volume, change_pct`。
`date` 为相对整数偏移（开启日期遮罩时），不是日历字符串；只用参数 `days=`，不要传 `offset`/`date_offset`。
缺少的涨跌幅用返回的 `change_pct` 或自行用 close 计算。

**portfolio**：`get_positions()`、`get_cash()`、`get_total_value()`。
**news**：`get_announcements(code, days=30)`、`get_policy_news(days=7)`。

禁止读取原始 dataset 路径、禁止 `import` 回测框架/`data_api`、禁止嵌套回测。
遇到 `AttributeError` 时改用上表方法，不得编造计算结果。

## 环境规则

- 分红/送股/转增由环境自动处理，到账时你会在晨报中看到提示
- 公告推送：持仓和自选股的重要公告会出现在晨报 P0 段
- 政策推送：央行/证监会/国务院等国家级政策出现在晨报 P1 段
- 每日总结写在 finish_day 中，这是你跨天记忆的来源

## 你的交易风格

{persona}
"""


class ToolAgent:
    """Tool-Use Agentic Agent — 通过 function calling 自主研究和交易。"""

    @classmethod
    def from_card(cls, card_id: str, llm_client: LLMClient | None = None) -> ToolAgent:
        from traderharness.agents.agent_card import load_card

        card = load_card(card_id)
        if card is None:
            raise FileNotFoundError(f"Agent card not found: {card_id}")

        if llm_client is None:
            llm_client = LLMClient(model=card.model)

        return cls(
            agent_id=card.id,
            name=card.name,
            llm_client=llm_client,
            persona=card.persona,
            initial_cash=Decimal(str(card.initial_cash)),
            max_positions=card.max_positions,
            max_position_pct=card.max_position_pct,
            allowed_tools=card.allowed_tools,
        )

    def __init__(
        self,
        agent_id: str,
        name: str,
        llm_client: LLMClient,
        persona: str = "你是一位经验丰富的主观交易员。",
        initial_cash: Decimal = Decimal("1000000"),
        max_positions: int = 4,
        max_position_pct: float = 25.0,
        allowed_tools: list[str] | None = None,
        memory_dir: str | None = None,
        live_file: str | None = None,
        event_bus: EventBus | None = None,
        mask_dates: bool = True,
        committee=None,
        prompt_contract_version: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.llm_client = llm_client
        self.persona = persona
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self.mask_dates = mask_dates
        self.allowed_tools = normalize_allowed_tools(allowed_tools)

        contract_text, self.prompt_contract_version = resolve_decision_contract(
            llm_client, prompt_contract_version
        )
        self._system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            initial_cash=f"{float(initial_cash):,.0f}",
            max_position_pct=f"{max_position_pct:.0f}",
            max_positions=max_positions,
            persona=persona,
            decision_recording_contract=contract_text,
        )

        self._registry = ToolRegistry()
        for tool in TOOL_DEFINITIONS:
            if tool.name in self.allowed_tools:
                self._registry.register(tool)

        self._memory = DailyMemory(agent_id=agent_id, storage_dir=memory_dir)

        from traderharness.trajectory.collector import TrajectoryCollector

        self._trajectory = TrajectoryCollector(agent_id=agent_id, live_file=live_file)

        self._loop = AgentLoop(
            llm_client=llm_client,
            tool_registry=self._registry,
            system_prompt=self._system_prompt,
            memory=self._memory,
            event_bus=event_bus,
            committee=committee,
        )
        self._loop.trajectory = self._trajectory

        # 自选股（Agent 通过 add_watchlist 工具动态管理，跨天持久）
        self._watchlist_codes: set[str] = set()

        self.day_results: list[DayResult] = []

    @property
    def trajectory(self) -> TrajectoryCollector:
        return self._trajectory

    async def on_day(self, bus, current_date: date) -> None:
        """TradingBus 模式：总线通知新交易日。

        数据已在回测启动时全量加载到 bus.market (MarketData)。
        这里只构建 ToolContext 视图，不做任何 I/O。
        """
        from datetime import datetime, timedelta

        portfolio = bus._portfolio

        initial = portfolio.cash + sum(
            p.avg_cost * p.quantity for p in portfolio.positions.values()
        )

        preloaded_daily = {code: bus.market.get(code) for code in bus.market.all_codes()}

        # Day-start window/execution snapshots stay empty. AgentLoop rebuilds
        # them from the live watchlist ∪ positions when entering open/close.
        # Pre-market valuation uses previous close, never today's fill prices.
        ctx = ToolContext(
            agent_id=self.agent_id,
            current_date=current_date,
            current_phase="pre_market",
            portfolio=portfolio,
            initial_cash=initial,
            preloaded_daily=preloaded_daily,
            window_minutes={},
            execution_price={},
            close_prices={},
            workspace_root=self.agent_id,
            max_position_pct=self.max_position_pct,
            max_positions=self.max_positions,
            _bus=bus,
        )
        # Seed persisted watchlist so morning brief / tools see yesterday's set,
        # and so an emptied watchlist can be written back at day end.
        ctx.tool_call_cache["watchlist"] = {code: "" for code in sorted(self._watchlist_codes)}

        from traderharness.core.masking import DateMasker

        ctx.date_masker = DateMasker(anchor=current_date, enabled=self.mask_dates)
        ctx.entity_masker = getattr(bus, "_entity_masker", None)

        # Inject news data for tool handlers
        news_mgr = getattr(bus, "_news_manager", None)
        if news_mgr is not None:
            ctx.tool_call_cache["_announcements_data"] = news_mgr.announcements
            ctx.tool_call_cache["_news_data"] = news_mgr.news

        # Inject fundamentals data
        fundamentals_df = getattr(bus, "_fundamentals_df", None)
        if fundamentals_df is not None and not fundamentals_df.empty:
            ctx.tool_call_cache["_fundamentals_data"] = fundamentals_df

        # Inject business segments data
        segments_df = getattr(bus, "_business_segments_df", None)
        if segments_df is not None and not segments_df.empty:
            ctx.tool_call_cache["_business_segments_data"] = segments_df

        # Inject valuation data (PE/PB/turnover/isST)
        valuation_df = getattr(bus, "_valuation_df", None)
        if valuation_df is not None and not valuation_df.empty:
            ctx.tool_call_cache["_valuation_data"] = valuation_df

        # P0 + P1 for morning brief
        if news_mgr is not None:
            target_codes = set(portfolio.positions.keys()) | self._watchlist_codes
            prev_close = datetime.combine(
                current_date - timedelta(days=1), datetime.min.time()
            ).replace(hour=15, minute=0)
            today_open = datetime.combine(current_date, datetime.min.time()).replace(
                hour=9, minute=30
            )
            ctx.tool_call_cache["_p0_announcements"] = news_mgr.get_p0_announcements(
                target_codes, prev_close, today_open
            )
            ctx.tool_call_cache["_p1_policy"] = news_mgr.get_p1_policy_news(prev_close, today_open)

        # Corporate actions today
        corporate_actions = getattr(bus, "_corporate_actions_today", [])
        if corporate_actions:
            ctx.tool_call_cache["_corporate_actions"] = corporate_actions

        # 回测进度
        self._loop.remaining_trading_days = bus._total_days - bus._day_index - 1
        self._loop.total_trading_days = bus._total_days

        result = await self._loop.run_day(current_date, ctx)
        self.day_results.append(result)

        # 持久化自选股（含清空：键存在即回写，允许空集）
        if "watchlist" in ctx.tool_call_cache:
            watchlist_from_ctx = ctx.tool_call_cache.get("watchlist") or {}
            self._watchlist_codes = set(watchlist_from_ctx.keys())
