# FinHarness

LLM-native trading agent backtesting harness for Chinese A-shares.

## Quick Reference

```bash
cd D:\finharness
.venv\Scripts\python.exe -m pytest tests/ --no-header -q  # 168 tests, ~60s
```

## Architecture

```
TradingEnv.run(agent)
  → BacktestEngine.run()
    → MarketData.load_all()          # 一次性加载全市场到内存（单文件 parquet）
    → for each trading day:
        → TradingBus (per-agent)     # 纯内存，同步方法，零 I/O
        → agent.on_day(bus, date)    # Agent 通过 bus 查数据 + 下单
        → portfolio.record_equity()  # 日终收盘价记录权益
```

## Key Design Rules

1. **回测期间零 I/O** — 所有数据在启动时加载到内存（MarketData dict），回测过程中只有 dict 查找
2. **单一下单路径** — `TradingBus.place_order()` 是唯一撮合入口，tool handler 只做前置检查然后委托
3. **严格日期隔离** — `df[df["date"] < current_date]` 用 bisect 做，Agent 永远看不到当天及未来数据
4. **不复权价格** — 回测用真实价格，涨跌停/手续费/成交金额都基于原始价格
5. **Agent 不持有 Portfolio** — 环境持有，Agent 通过 PortfolioView 只读查看

## Data Layer

```
~/.finharness/dataset/
├── daily.parquet    # 全市场日线（stock_code, date, OHLCV），47 MB
├── 5min.parquet     # 全市场5分钟线（stock_code, date, datetime, OHLCV），614 MB
└── metadata.json

首次运行自动从 mootdx 拉取（MarketDataManager），后续读缓存。
测试用 tests/fixtures/market_data/（5090 个单文件 parquet，兼容旧模式）。
```

## Agent 上下文（每天注入）

```
[system] 角色设定 + 规则 + 风控 + persona
[system] 跨天记忆（最近5天 JSONL）
[user]   晨报：总资产/收益/持仓涨跌/板块涨跌前5后5/自选股/工具列表/回测进度
         → 盘前 tool calls (max 10轮, place_order 被排除)
[user]   开盘窗口（5分钟K线或成交价列表）
         → 开盘 tool calls (max 3轮)
[user]   尾盘窗口（收盘价）
         → 尾盘 tool calls (max 3轮) + finish_day
```

## Tool 列表（19个）

| 类别 | Tools |
|------|-------|
| 市场数据 | get_kline, get_stock_price, get_stock_info |
| 分析 | get_market_overview, screen_stocks, get_sector_summary |
| 持仓 | get_portfolio, get_position |
| 交易 | place_order（仅开盘/尾盘窗口可用） |
| 自选股 | add_watchlist, remove_watchlist, get_watchlist |
| 文件 | read_file, write_file, list_files, run_script |
| 控制 | finish_day |

## Common Tasks

### 跑回测（无 LLM）
```python
from finharness.core.env import TradingEnv, EnvConfig
from finharness.data.providers.parquet import ParquetProvider

env = TradingEnv(config=EnvConfig(start_date=date(2024,3,1), end_date=date(2024,6,30)),
                 data_provider=ParquetProvider('tests/fixtures/market_data'))
result = env.run(my_agent)
```

### 跑 LLM Agent 回测
```python
from finharness.agents.tool_agent import ToolAgent
from finharness.agents.llm_client import LLMClient

llm = LLMClient(model='deepseek-chat', api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com')
agent = ToolAgent(agent_id='test', name='Test', llm_client=llm, persona='你是趋势交易者。')
result = env.run(agent)  # 每天 ~45s（LLM 调用）
```

### 拉取全市场数据
```bash
python scripts/fetch_5year_data.py  # BaoStock 全市场 5 年日线+5分钟线
```

## File Map

```
finharness/
├── core/engine.py          # BacktestEngine + TradingBus + MarketData（核心）
├── core/portfolio.py       # Portfolio + PortfolioView
├── core/env.py             # TradingEnv（用户入口）
├── agents/tool_agent.py    # ToolAgent（LLM Agent 组装）
├── agents/loop.py          # AgentLoop（三阶段循环）
├── agents/llm_client.py    # LLMClient（OpenAI-compatible）
├── tools/trading.py        # place_order（薄包装 → bus）
├── tools/registry.py       # ToolContext + ToolRegistry
├── data/market_data_manager.py  # 首次拉取 + 缓存管理
└── data/stock_registry_loader.py  # 行业分类（282个行业）
```

## Testing

```bash
# 全部测试（含真实数据集成测试）
.venv/Scripts/python.exe -m pytest tests/ -q

# 只跑单元测试（快）
.venv/Scripts/python.exe -m pytest tests/unit/ -q

# 跑带 LLM 的集成测试（需要 DEEPSEEK_API_KEY）
.venv/Scripts/python.exe -m pytest tests/integration/test_real_backtest.py -v
```

## Known Issues / Tech Debt

- BaoStock 5年数据脚本因服务端限流暂时不可用（IP 需恢复）
- mootdx 5分钟线数据只有 ~3 个月（翻页有效范围受限）
- Streamlit UI 是空壳页面
- CLI `finharness run` 不真的跑回测（只 print）
- 没有 README / PyPI 打包 / CI

## Environment

```
Python 3.12 (.venv)
Key deps: pandas, numpy, pyarrow, httpx, click, jinja2, openai, mootdx, baostock
.env: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
```
