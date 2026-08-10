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
from traderharness.tools.analysis import (
    GET_MARKET_OVERVIEW,
    GET_SECTOR_SUMMARY,
    SCREEN_BEHAVIORAL_CYCLE,
    SCREEN_STOCKS,
)
from traderharness.tools.business import GET_BUSINESS_SEGMENTS
from traderharness.tools.catalog import normalize_allowed_tools
from traderharness.tools.conditional_orders import (
    LIST_CONDITIONAL_ORDERS,
    MANAGE_CONDITIONAL_ORDER,
)
from traderharness.tools.control import FINISH_DAY
from traderharness.tools.fundamentals import GET_FUNDAMENTALS
from traderharness.tools.market import GET_KLINE, GET_STOCK_INFO, GET_STOCK_PRICE
from traderharness.tools.memory import GET_MEMORY, REMEMBER, SEARCH_MEMORY
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
    SCREEN_BEHAVIORAL_CYCLE,
    GET_SECTOR_SUMMARY,
    GET_PORTFOLIO,
    GET_POSITION,
    PLACE_ORDER,
    MANAGE_CONDITIONAL_ORDER,
    LIST_CONDITIONAL_ORDERS,
    GET_FUNDAMENTALS,
    GET_ANNOUNCEMENTS,
    GET_NEWS,
    ADD_WATCHLIST,
    REMOVE_WATCHLIST,
    GET_WATCHLIST,
    REMEMBER,
    SEARCH_MEMORY,
    GET_MEMORY,
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
| manage_conditional_order | 创建、上移/修改或取消环境托管条件单 |
| list_conditional_orders | 查看条件单状态、版本与触发失败记录 |
| add_watchlist | 加入自选股 |
| remove_watchlist | 移出自选股 |
| get_watchlist | 查看自选股 |
| remember | 保存结构化长期记忆或留痕替换旧版本 |
| search_memory | 按需检索未注入上下文的历史记忆 |
| get_memory | 按 ID 读取完整记忆记录 |
| execute_code | 执行Python代码（通过traderharness_api访问数据） |
| finish_day | 结束交易日并写总结 |

Specialized screen: `screen_behavioral_cycle` deterministically ranks point-in-time
accumulation/test/washout/markup evidence and returns structural invalidation levels.

### execute_code / traderharness_api 契约

沙箱内只能：`from traderharness_api import market, portfolio, news`，再配合 numpy/pandas。

**market 合法方法**（禁止臆造其它名字）：
`get_kline(code, days=60)`、`get_kline_5min(code)`、`get_stock_list()`、`get_all_stocks()`（=list 别名）、
`get_all_daily(days=20)`、`get_stock_price(code)`、`get_fundamentals(code)`、
`get_behavioral_features()`（无标签、无综合分、由 Agent 在沙盒中自行排序）、
`get_market_overview()`、`get_sector_summary(sector)`、`get_sector_stocks(sector)`、`screen_stocks(**筛选参数)`。

**get_all_daily 列名**：`stock_code, date, open, high, low, close, volume, change_pct`。
`date` 为相对整数偏移（开启日期遮罩时），不是日历字符串；只用参数 `days=`，不要传 `offset`/`date_offset`。
`date` 是日历日偏移，周末和休市日自然会形成跳号，不代表行情数据缺失。
缺少的涨跌幅用返回的 `change_pct` 或自行用 close 计算。

**get_kline 返回列名**：`date, open, high, low, close, volume`（部分数据另含 `amount`），
不含 `change_pct`；如需收益率请用 `close.pct_change()` 自行计算。

**get_behavioral_features 列名**：`stock_code, last_close, last_low, range_position_60,
drawdown_120_pct, change_20_pct, atr_20_pct, atr_5_to_20, volume_5_to_20,
up_down_volume_ratio, clv_5, clv_last, obv_flow_20, breakout_20d_pct,
support_20, resistance_20, earlier_resistance, observations, touched_support,
recently_broke_out, extended_20d, distribution_risk, zero_volume_baseline`。
该方法可能返回数千行；不要用 `dir()`、`columns` 或 `head()` 探查。
一次调用后直接在同一段代码内筛选、排序并只打印少量候选。

**portfolio**：`get_positions()`、`get_cash()`、`get_total_value()`。
**news**：`get_announcements(code, days=30)`、`get_policy_news(days=7)`。

禁止读取原始 dataset 路径、禁止 `import` 回测框架/`data_api`、禁止嵌套回测。
遇到 `AttributeError` 时改用上表方法，不得编造计算结果。

## 环境规则

- 分红/送股/转增由环境自动处理，到账时你会在晨报中看到提示
- 公告推送：持仓和自选股的重要公告会出现在晨报 P0 段
- 政策推送：央行/证监会/国务院等国家级政策出现在晨报 P1 段
- 每日总结写在 finish_day 中，这是你跨天记忆的来源
- 活动条件单由环境逐根检查后续5分钟bar收盘价并自动执行；它们不是提醒事项。
- 保护止损只能上移，修改后只对尚未揭示的bar生效。需要动态管理时调用 manage_conditional_order。
- 重要假设和复盘可写入 remember；系统只常驻精简长期记忆和近期日志，旧日志用 search_memory 检索。

## 你的交易风格

{persona}
"""

COMPACT_SYSTEM_PROMPT_TEMPLATE = """
You are an A-share trading agent in a historical simulation with {initial_cash} initial cash.

## Daily protocol

1. Pre-market research: research tools are available and orders are disabled.
2. Open window (09:30-10:00): orders are enabled under the environment's open execution rules.
3. Close window (14:30-15:00): orders are enabled under the environment's close execution rules.
4. Call finish_day when your work for the current phase is complete.

## Hard constraints

- Use only information returned by the supplied tools; never infer hidden dates or identities.
- T+1, lot size, price limits, suspensions, fees and execution rules are enforced by the environment.
- A security may be traded at most once per day.
- One position may not exceed {max_position_pct}% and at most {max_positions} positions may be held.
- Cash is valid. The environment owns portfolio state and TradingBus.place_order is the only order path.
{decision_recording_contract}
## Available tools

{allowed_tool_names}

Treat the supplied function schemas as authoritative. Do not invent tool names or parameters.

## Trading style

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
            max_pre_iterations=card.max_pre_iterations,
            max_window_iterations=card.max_window_iterations,
            require_structured_plan=card.require_structured_plan,
            minimum_holding_days=card.minimum_holding_days,
            research_interval_days=card.research_interval_days,
            sandbox_pre_market_only=card.sandbox_pre_market_only,
            sandbox_max_calls_per_day=card.sandbox_max_calls_per_day,
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
        max_pre_iterations: int = 10,
        max_window_iterations: int = 3,
        require_structured_plan: bool = False,
        minimum_holding_days: int = 0,
        research_interval_days: int = 0,
        sandbox_pre_market_only: bool = False,
        sandbox_max_calls_per_day: int = 0,
        allowed_tools: list[str] | None = None,
        memory_dir: str | None = None,
        workspace_root: str | None = None,
        live_file: str | None = None,
        event_bus: EventBus | None = None,
        mask_dates: bool = True,
        committee=None,
        prompt_contract_version: str | None = None,
        compact_prompt: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.llm_client = llm_client
        self.persona = persona
        self.initial_cash = initial_cash
        self.max_positions = max_positions
        self.max_position_pct = max_position_pct
        self.require_structured_plan = require_structured_plan
        self.minimum_holding_days = max(0, int(minimum_holding_days))
        self.research_interval_days = max(0, int(research_interval_days))
        self.sandbox_pre_market_only = bool(sandbox_pre_market_only)
        self.sandbox_max_calls_per_day = max(0, int(sandbox_max_calls_per_day))
        self.mask_dates = mask_dates
        self.allowed_tools = normalize_allowed_tools(allowed_tools)
        self.workspace_root = workspace_root or agent_id

        contract_text, self.prompt_contract_version = resolve_decision_contract(
            llm_client, prompt_contract_version
        )
        prompt_template = COMPACT_SYSTEM_PROMPT_TEMPLATE if compact_prompt else SYSTEM_PROMPT_TEMPLATE
        self._system_prompt = prompt_template.format(
            initial_cash=f"{float(initial_cash):,.0f}",
            max_position_pct=f"{max_position_pct:.0f}",
            max_positions=max_positions,
            persona=persona,
            decision_recording_contract=contract_text,
            allowed_tool_names=", ".join(self.allowed_tools),
        )
        if not compact_prompt:
            import re

            allowed = set(self.allowed_tools)
            prompt_lines = []
            for line in self._system_prompt.splitlines():
                first_column = line.split("|", 2)[1].strip() if line.startswith("|") else ""
                if re.fullmatch(r"[a-z][a-z0-9_]*", first_column) and first_column not in allowed:
                    continue
                prompt_lines.append(line)
            self._system_prompt = "\n".join(prompt_lines)
            if "execute_code" not in allowed:
                self._system_prompt = re.sub(
                    r"\n### execute_code / traderharness_api .*?(?=\n## )",
                    "",
                    self._system_prompt,
                    flags=re.DOTALL,
                )
            if "screen_behavioral_cycle" not in allowed:
                self._system_prompt = re.sub(
                    r"\nSpecialized screen: `screen_behavioral_cycle`.*?levels\.\n",
                    "\n",
                    self._system_prompt,
                    flags=re.DOTALL,
                )
            if not ({"get_news", "get_announcements"} & allowed):
                self._system_prompt = re.sub(r"\n\*\*news\*\*：.*?。\n", "\n", self._system_prompt)

        if self.sandbox_pre_market_only:
            self._system_prompt += (
                "\n\n## 本 Agent 的研究执行约束\n"
                "execute_code 仅在盘前可用。研究日盘前最多调用两次：第一次完成机械筛选，"
                "第二次只复核最终候选的 K 线；不得在沙盒里查询新闻、公告、政策、估值或基本面。"
                "之后停止代码研究，使用普通行情工具把候选缩减到最多3只；离开盘前前必须调用 "
                "add_watchlist 登记最终候选，否则窗口没有这些股票的分钟行情，不得开仓。\n"
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
            max_pre_iterations=max_pre_iterations,
            max_window_iterations=max_window_iterations,
            event_bus=event_bus,
            committee=committee,
        )
        self._loop.trajectory = self._trajectory

        # 自选股（Agent 通过 add_watchlist 工具动态管理，跨天持久）
        self._watchlist_codes: set[str] = set()
        self._position_plans: dict[str, dict] = {}

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

        preloaded_daily = {code: bus.market.get(code) for code in bus.market.all_codes()}

        # Day-start window/execution snapshots stay empty. AgentLoop rebuilds
        # them from the live watchlist ∪ positions when entering open/close.
        # Pre-market valuation uses previous close, never today's fill prices.
        ctx = ToolContext(
            agent_id=self.agent_id,
            current_date=current_date,
            current_phase="pre_market",
            portfolio=portfolio,
            initial_cash=self.initial_cash,
            preloaded_daily=preloaded_daily,
            window_minutes={},
            execution_price={},
            close_prices={},
            workspace_root=self.workspace_root,
            max_position_pct=self.max_position_pct,
            max_positions=self.max_positions,
            require_structured_plan=self.require_structured_plan,
            minimum_holding_days=self.minimum_holding_days,
            day_index=bus._day_index,
            research_interval_days=self.research_interval_days,
            sandbox_pre_market_only=self.sandbox_pre_market_only,
            allowed_tools=frozenset(self.allowed_tools),
            sandbox_max_calls_per_day=self.sandbox_max_calls_per_day,
            _bus=bus,
        )
        # Seed persisted watchlist so morning brief / tools see yesterday's set,
        # and so an emptied watchlist can be written back at day end.
        ctx.tool_call_cache["watchlist"] = {code: "" for code in sorted(self._watchlist_codes)}
        self._position_plans = {
            code: plan
            for code, plan in self._position_plans.items()
            if code in portfolio.positions
        }
        ctx.tool_call_cache["_position_plans"] = self._position_plans
        ctx.tool_call_cache["_memory"] = self._memory

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
