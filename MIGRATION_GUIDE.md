# FinHarness 迁移指南 — 从股神竞技场提取核心引擎

> 本文档供新 session 的 Claude Code 使用，包含所有已实现的技术细节、数据层现状、已知坑点。
> 源代码位于 `D:\抖音股神竞技场`，目标位于 `D:\finharness`。

---

## 1. 源项目已完成的核心模块（已测试 178 tests, 81% coverage）

### 文件映射表

| 源文件 (D:\抖音股神竞技场) | → FinHarness 目标 | 行数 | 改动说明 |
|---------------------------|-------------------|------|----------|
| backend/arena/trading_bus.py | finharness/core/env.py + engine.py | 460 | 拆分+重命名+加PortfolioView |
| backend/arena/simulator.py | finharness/core/matching.py | 52 | +MarketProfile参数化 |
| backend/agents/portfolio.py | finharness/core/portfolio.py | ~80 | +PortfolioView只读代理 |
| backend/agents/agentic/tool_agent.py | finharness/agents/llm_agent.py | 332 | 重组 |
| backend/agents/agentic/agent_loop.py | finharness/agents/loop.py | 316 | 原样+渐进披露改进 |
| backend/agents/agentic/memory.py | finharness/agents/memory.py | 89 | 原样 |
| backend/agents/agentic/context_manager.py | finharness/agents/context.py | 99 | 原样 |
| backend/agents/agentic/sandbox.py | finharness/agents/sandbox/executor.py | 193 | 原样 |
| backend/agents/agentic/workspace.py | finharness/agents/sandbox/workspace.py | 80 | 原样 |
| backend/agents/agentic/tool_registry.py | finharness/tools/registry.py | 94 | 原样 |
| backend/agents/agentic/tools/market_tools.py | finharness/tools/market.py | 156 | 原样 |
| backend/agents/agentic/tools/portfolio_tools.py | finharness/tools/portfolio.py | 94 | 原样 |
| backend/agents/agentic/tools/trading_tools.py | finharness/tools/trading.py | 140 | 含风控硬检查 |
| backend/agents/agentic/tools/analysis_tools.py | finharness/tools/analysis.py | 225 | 原样 |
| backend/agents/agentic/tools/control_tools.py | finharness/tools/(合并到trading) | 30 | 原样 |
| backend/agents/agentic/tools/filesystem_tools.py | finharness/tools/filesystem.py + scripting.py | 174 | 拆分 |
| backend/arena/data_source.py | finharness/data/providers/*.py | 1023 | 拆分为多文件 |
| backend/arena/market_data.py | finharness/data/cache.py | 187 | 原样 |
| backend/arena/metrics.py | finharness/metrics/performance.py | 140 | 原样 |
| backend/arena/stock_info.py | finharness/data/registry.py | 95 | 原样 |
| backend/strategy/llm_client.py | finharness/agents/llm_client.py | 209 | +RateLimitError重试 |

---

## 2. 数据层技术细节

### 2.1 数据源现状

| 数据源 | 日K | 5分钟K | 股票列表 | 行业分类 | 实际可用性 |
|--------|-----|--------|----------|----------|-----------|
| **Mootdx** | ✅ | ✅ | ⚠️(via akshare) | ⚠️(需enrichment) | **主力源** |
| **Tencent** | ✅ | ❌ | ❌ | ❌ | 兜底 |
| **Akshare** | ✅(但SSL不稳定) | ❌ | ✅ | ✅(缓存) | 股票列表用 |
| **Tushare** | ✅ | ❌ | ✅ | ⚠️(需token) | 未配置 |

### 2.2 Mootdx 并发拉取（已实现）

`trading_bus.py` 中 `preload_all_market_data()` 方法：

```python
async def preload_all_market_data(self, codes: list[str], max_concurrency: int = 4) -> None:
    """批量预加载日K线数据（带并发限制）。"""
    sem = asyncio.Semaphore(max_concurrency)
    to_fetch = [c for c in codes if c not in self._daily_cache]

    async def _fetch_one(code: str) -> None:
        async with sem:
            try:
                start = self._current_date - timedelta(days=365)
                df = await self.market_data.get_daily_bars(code, start, self._current_date)
                if df is not None and not df.empty:
                    self._daily_cache[code] = df
            except Exception as e:
                logger.warning("bus.preload_fail: %s - %s", code, str(e))

    await asyncio.gather(*[_fetch_one(c) for c in to_fetch])
```

**关键参数**：
- `max_concurrency=4` — 经测试 8 并发有 30% 失败率，4 并发 100% 成功
- 每只股票 ~0.06s（mootdx TCP 协议）
- 全市场 5937 只约 5 分钟（4并发）
- 失败的股票跳过，不阻塞其他

### 2.3 板块/行业数据

**获取方式**（`data_source.py` 中 `HybridSource`）：
- 主路径：pywencai（同花顺问财）3级行业分类，5000+只股票
- 兜底：新浪财经行业分类
- 缓存7天（本地文件），超过30%股票缺失行业信息时自动刷新

**行业聚合统计**（`analysis_tools.py` + `agent_loop._build_morning_brief`）：
- 遍历 `preloaded_daily` 中所有股票
- 通过 `get_stock_info_quick(code)` 获取行业
- 按行业分组计算平均涨跌幅
- 排序输出 top/bottom 板块

**注意**：真实板块指数（880xxx）不可用！mootdx 返回的板块指数有 datetime bug + 数据滞后。
当前方案是用板块内个股聚合来替代板块指数。

### 2.4 SQLite 缓存

```
data/market/market_cache.db
表: daily_bars(stock_code TEXT, trade_date TEXT, data TEXT, cached_at TEXT)
TTL: 24 小时
```

### 2.5 股票注册表

```python
# backend/arena/stock_info.py
_registry: dict[str, dict] = {}  # code → {name, industry, market}

async def get_stock_registry() -> dict:
    """异步加载，有本地缓存文件 data/cache/stock_registry.json"""

def get_stock_info_quick(code: str) -> dict:
    """同步查询，只读内存/磁盘缓存"""
```

- 约 5937 只股票 + 282 个行业分类
- 缓存文件 `data/cache/stock_registry.json`
- 如果 > 1000 只才认为有效

### 2.6 已知不可用的数据源

| 尝试过的 | 为什么不行 |
|----------|-----------|
| akshare 东方财富日K | SSL/502 阻断 |
| akshare 同花顺板块历史K线 | 超时 |
| mootdx 板块指数 880xxx | datetime bug + 数据滞后 |
| mootdx 8并发 | 30% 失败率 |

---

## 3. TradingBus 核心引擎细节

### 3.1 交易日推进

```python
@staticmethod
def _get_trading_days(start: date, end: date) -> list[date]:
    """跳过周末（注意：暂未处理中国节假日！这是待实现项）"""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days
```

### 3.2 数据隔离（防未来函数）

所有数据查询强制 `date < current_date`：
```python
async def get_daily_bars(self, stock_code: str, days: int = 20) -> pd.DataFrame:
    df = await self._ensure_daily(stock_code)
    filtered = df[df["date"] < self._current_date]  # 严格小于
    return filtered.tail(days)
```

执行价是唯一使用当天数据的地方：
```python
async def get_execution_price(self, stock_code: str, window: str = "open") -> Decimal:
    today = df[df["date"] == self._current_date]  # 当天
    if window == "open":
        return Decimal(str(row["open"]))
    return Decimal(str(row["close"]))
```

### 3.3 订单撮合流程

`place_order()` 依次检查：
1. T+1 日内重复检查（同一 agent 同一天同一只只能交易一次）
2. 获取成交价（open/close 窗口）
3. 涨跌停检查（主板±10%，科创/创业±20%）
4. **风控硬检查**（新增）：
   - 单只仓位不超过 `max_position_pct`（默认25%）
   - 持仓只数不超过 `max_positions`（默认4只）
5. 执行买入/卖出（Portfolio.buy/sell）
6. 记录交易 + 更新 traded_today

### 3.4 手续费模型

```python
COMMISSION_RATE = Decimal("0.00025")  # 万2.5（买卖双向）
STAMP_TAX_RATE = Decimal("0.001")     # 千1（仅卖出）
MIN_COMMISSION = Decimal("5.00")       # 最低5元
```

### 3.5 多 Agent 并行

```python
tasks = [self._run_agent_day(agent, current_date) for agent in self._agents]
day_reports = await asyncio.gather(*tasks, return_exceptions=True)
```

每个 Agent 异常不影响其他，错误记入 DayReport.summary。

---

## 4. Agent 工具（16个）详细接口

### 4.1 市场数据工具

**get_kline**
```
输入: {stock_code: str, days: int(default=20, max=120)}
输出: {stock_code, count, data: [{date, open, high, low, close, volume}]}
隔离: 只返回 date < current_date 的数据
```

**get_stock_price**
```
输入: {stock_code: str}
输出: {stock_code, date, open, high, low, close, volume, change_pct}
返回: 前一个交易日的收盘价（不是当天！）
```

**get_stock_info**
```
输入: {stock_code: str}
输出: {code, name, industry, market, limit_pct}
来源: stock_registry + market_data.get_stock_info()
```

### 4.2 分析工具

**get_market_overview**
```
输入: {sector?: str}
输出: {date, top_sectors: [{sector, change_pct, rep}], bottom_sectors, total_sectors}
路径: 优先 bus.get_market_overview() → 兜底 preloaded_daily 聚合
```

**screen_stocks**
```
输入: {industries?: [str], price_min?: float, price_max?: float, max_results: int(default=10, max=20)}
输出: {stocks: [{code, name, industry, close, change_5d_pct, vol_ratio}], total_matched}
数据源: preloaded_daily 遍历筛选
```

**get_sector_summary**
```
输入: {sector: str}
输出: {sector, avg_change_pct, avg_vol_ratio, stocks: [...], top_gainers, top_losers}
```

### 4.3 持仓工具

**get_portfolio**
```
输入: {}
输出: {cash, total_value, return_pct, positions: [{code, name, qty, avg_cost, current_price, pnl_pct, market_value}], position_count}
价格来源: ctx.execution_price
```

**get_position**
```
输入: {stock_code: str}
输出: {stock_code, name, quantity, avg_cost, buy_date, current_price, pnl_pct, sellable_quantity, days_held}
T+1: sellable_quantity 通过 pos.sellable_quantity(current_date) 计算
```

### 4.4 交易工具

**place_order**
```
输入: {action: "buy"|"sell", stock_code: str, stock_name?: str, quantity: int, reasoning: str}
输出（成功）: {success: true, action, stock_code, price, quantity, total_cost/net_income, remaining_cash, portfolio_after: {cash, positions, position_count}}
输出（失败）: {success: false, error: "具体原因"}
限制: 盘前阶段不可调用（从 tools schema 中排除）
风控: max_position_pct + max_positions 硬检查
```

### 4.5 文件系统 + 沙箱

**read_file** / **write_file** / **list_files**
```
工作目录: data/agent_workspaces/{agent_id}/
子目录: scripts/, notes/, data/, journal/
限制: 8KB 读取上限, 100文件上限, 10MB总量上限
安全: 路径越界检查（不能逃逸出工作目录）
```

**run_script**
```
输入: {path: str, inject_data?: {变量名: 股票代码}}
执行: PythonSandbox 受限环境
允许: pandas, numpy, math, statistics, json, datetime, collections, re
禁止: os, sys, subprocess, socket, requests, exec, eval, __import__(受限)
超时: 10秒
输出上限: 8KB stdout
注入: inject_data 中指定的股票代码 → 对应的 DataFrame 作为变量名注入
```

### 4.6 控制工具

**finish_day**
```
输入: {summary: str}
输出: {status: "day_complete", summary_saved: true, trades_today: int}
作用: 标记当天结束，summary 存入跨天记忆
```

---

## 5. Agent Loop 三阶段上下文

### 5.1 Context 结构

每天的消息流：
```
[system] 交易员角色设定 + 规则 + 风控 + persona
[system] 最近5天交易记忆（JSONL → 格式化文本）
[user]   晨报（总资产/收益率/持仓涨跌/板块/可用工具）+ 回测进度
         → 盘前 tool calls (max 10轮, place_order 被排除)
[user]   开盘窗口（全市场概况 + 可交易价格）
         → 开盘 tool calls (max 3轮, 含 place_order)
[user]   尾盘窗口（收盘价 + 持仓）
         → 尾盘 tool calls (max 3轮, 含 place_order + finish_day)
```

### 5.2 晨报内容（已增强）

```
=== 市场晨报 ===

总资产: 1,043,635元 | 累计收益: +4.36%
持仓: 1只 | 可用资金: 600,000元
  600519 茅台: 100股, 成本436.35 昨日+1.2% 浮盈+1.8%

昨日板块涨跌:
  ▲ 白酒: +2.15%
  ▲ 新能源: +1.83%
  ---
  ▼ 地产: -1.45%

可用工具: get_kline(K线), get_stock_price(最新价), screen_stocks(选股)...
```

### 5.3 开盘窗口消息（待改进 → 渐进披露）

当前实现只列预加载的几只股票价格。
**FinHarness 中应改为**：给全市场开盘概况（涨跌家数、板块排名、持仓开盘价），Agent 自主探索。

### 5.4 Token 管理

- ContextManager 估算: `total_chars * 0.7`（中英混合粗估）
- 压缩阈值: 60000 tokens * 75% = 45000
- 压缩方式: 保留 system + 最近6条非system，中间压缩为摘要

### 5.5 跨天记忆

```json
// data/agent_workspaces/{agent_id}/journal/memory.jsonl
{"date": "2024-04-21", "summary": "买入宁德时代...", "trades_count": 1, "portfolio_value": 1050000}
```

注入方式：前 5 天的 summary 文本插入 system message。

---

## 6. LLM Client 细节

### 6.1 接口

```python
class OpenAICompatibleClient:
    async def chat_with_tools(self, messages, tools, temperature=0.3) -> Response
    # tools = OpenAI function calling format
```

### 6.2 缓存

- SHA256(messages_json + temperature) → 本地文件
- 命中时直接返回，0 网络开销

### 6.3 重试策略

当前只重试: `APIConnectionError`, `APITimeoutError`
**需要新增**: `RateLimitError`（429），指数退避

### 6.4 已知 Bug

- `json_repair` 依赖未在 requirements.txt 声明（import 时会崩）
- logger 使用 structlog kwargs 风格，标准 logging 不兼容（部分已修复）

---

## 7. 测试覆盖现状

| 模块 | 覆盖率 | 测试文件 |
|------|--------|---------|
| tool_registry | 100% | tests/unit/agentic/test_tool_registry.py |
| control_tools | 100% | tests/unit/agentic/tools/test_control_tools.py |
| portfolio_tools | 100% | tests/unit/agentic/tools/test_portfolio_tools.py |
| workspace | 98% | tests/unit/agentic/test_workspace.py |
| context_manager | 98% | tests/unit/agentic/test_context_manager.py |
| trading_tools | 97% | tests/unit/agentic/tools/test_trading_tools.py |
| market_tools | 95% | tests/unit/agentic/tools/test_market_tools.py |
| filesystem_tools | 92% | tests/unit/agentic/tools/test_filesystem_tools.py |
| memory | 92% | tests/unit/agentic/test_memory.py |
| sandbox | 91% | tests/unit/agentic/test_sandbox.py |
| analysis_tools | 90% | tests/unit/agentic/tools/test_analysis_tools.py |
| agent_loop | 79% | tests/unit/agentic/test_agent_loop.py |
| trading_bus | 100% (18 tests) | tests/unit/agentic/test_trading_bus.py |
| 集成测试(85天) | pass | tests/integration/test_bus_backtest.py |

---

## 8. 已修复的 Bug（迁移时注意保留修复）

| Bug | 文件 | 修复 |
|-----|------|------|
| sandbox `__import__` 缺失 | sandbox.py | 添加 safe `__import__` 到 builtins，带模块白名单 |
| logger kwargs 格式错误 | tool_registry.py, trading_bus.py | 改为 `%s` 格式化 |
| 涨跌停价格计算 | trading_tools.py | 用前一天收盘价计算 |

---

## 9. FinHarness 新增功能（迁移时需要实现）

| 功能 | 不在源码中，需新写 | 预计行数 |
|------|-------------------|----------|
| PortfolioView（只读代理） | 包装 Portfolio，隐藏 buy/sell | ~40 |
| MarketProfile（市场规则参数化） | T+N, lot_size, limit_pct 可配置 | ~40 |
| TokenBudget | 超限抛 BudgetExhaustedError | ~30 |
| EventBus | on/emit 事件系统 | ~60 |
| TrajectoryCollector | 双粒度记录（day + step） | ~120 |
| Replay 模式 | JSONL 录制/重放 LLM 调用 | ~100 |
| 中国交易日历 | 含春节/国庆/元旦等 | ~60 |
| Warmup 窗口 | 回测开始前预加载 N 天数据 | ~20 |
| CLI (click) | finharness run/data/benchmark/ui | ~100 |
| PromptAgent | YAML → LLM Agent 加载器 | ~50 |
| Baselines (3个) | BuyAndHold, Random, MACross | ~90 |
| HTML Report | Jinja2 模板 + plotly 图表 | ~100 |
| Benchmark 对比 | 自动跑 BuyAndHold + alpha 计算 | ~50 |
| Prompt 审核 | LLM 检测 persona 中的未来信息 | ~60 |
| 开盘窗口渐进披露 | 全市场概况→Agent自主探索 | ~40 |
| 断点模式 | breakpoints 参数 + pause/resume | ~50 |
| 多次运行统计 | --runs N + mean±std 输出 | ~40 |

---

## 10. 关键设计决策（必须遵守）

1. **Agent 不持有 Portfolio** — 环境持有，Agent 通过 PortfolioView 只读查看，通过 env.place_order() 下单
2. **环境不管阶段** — 环境只调 `agent.on_day(env, date)`，三阶段是 LLM Agent 内部的策略选择
3. **数据隔离绝对严格** — 所有查询 `date < current_date`，执行价用当天 open/close
4. **Token Budget 硬限制** — 超限优雅停止，不崩溃
5. **对外 API sync** — `env.run()` 是同步的，内部自动管 event loop
6. **API Key 从环境变量** — Agent YAML 只写 model name，不写 key
7. **结果存 ./runs/** — 每次运行一个目录，含所有产出物
8. **Prompt 每次审核** — 结果缓存，发现未来信息警告不阻止
9. **全市场渐进披露** — 开盘窗口给市场全貌，Agent 自主钻取

---

## 11. 运行命令参考

```bash
# 在源项目中运行现有测试
cd D:\抖音股神竞技场
python -m pytest tests/unit/agentic/ --cov=backend/agents/agentic --cov-report=term-missing

# 运行集成测试
python -m pytest tests/integration/test_bus_backtest.py -v

# 运行完整的 ToolAgent 回测（需要 LLM API key）
python scripts/run_tool_agent_backtest.py
```

---

## 12. .env 配置（源项目）

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
MARKET_DATA_SOURCE=mootdx
```
