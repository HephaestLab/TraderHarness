# TraderHarness

A trading environment for autonomous agents.

## What This Is

LLM Agent 的交易环境。不限制交易方法论——纯主观、主观+技术、纯量化都在同一个环境里跑。Agent 通过 prompt 决定用什么方法交易，环境只负责提供市场、工具和账户。

与 backtrader/vnpy/qlib 的本质区别：策略不是代码，是 Agent。Agent 有自主性——能中途改策略、给自己写工具、跨天记忆、自主决定用什么方法。

## Design Principles

1. **回测期间零 I/O** — 所有数据启动时加载到内存，回测过程中只有 dict 查找
2. **单一下单路径** — `TradingBus.place_order()` 是唯一撮合入口
3. **严格日期隔离** — Agent 永远看不到当天及未来数据
4. **不复权价格** — 回测用真实价格，涨跌停/手续费/成交金额都基于原始价格
5. **环境确定性** — 同样的 action 序列，环境给出同样的结果
6. **Agent 不持有 Portfolio** — 环境持有，Agent 通过 PortfolioView 只读查看

## Architecture

```
TradingEnv.run(agent)
  → BacktestEngine.run()
    → MarketData.load_all()          # 全市场数据加载到内存
    → for each trading day:
        → TradingBus (per-agent)     # 纯内存，同步方法
        → agent.on_day(bus, date)    # Agent 通过 bus 查数据 + 下单
        → portfolio.record_equity()  # 日终记录权益
```

## 上下文管理 & Prompt Caching

每天上下文 reset，跨天靠记忆摘要延续。消息结构按缓存命中率优化：

```
[system] 角色设定 + 风控规则 + persona              ← 不变，可缓存
[system] 工具使用说明 + 环境规则 + 行业列表          ← 不变，可缓存
──────── 缓存边界 ────────
[system] 跨天记忆（追加模式，只在超限时压缩）        ← 前面的天可缓存
[user]   晨报                                     ← 每天变
... tool calls ...
```

设计要点：
- **不变前缀最大化**：system prompt 包含规则、工具说明、股票/行业列表等静态内容
- **记忆追加而非滚动**：Day N 的记忆 = Day 1~N-1 的摘要追加，前面的天命中缓存
- **显式缓存断点**：LLM 调用时标记 `cache_control`（Anthropic）或依赖前缀自动匹配（OpenAI）
- **超限才压缩**：只有总 token 接近上限时才对早期记忆做压缩，平时保持完整以利缓存

## 环境给 Agent 提供什么

三样东西：
1. **市场** — 真实历史行情 + 公告 + 政策快讯，按时间推送
2. **工具** — 查数据、分析、写代码、下单（19 个 tool）
3. **账户** — 资金、持仓、权益追踪

## 每日信息推送（三阶段）

### Phase 1：盘前分析（max 10 轮 tool call，不能下单）
- 总资产 / 累计收益率
- 持仓明细（数量、成本、昨日涨跌、浮盈）
- 全市场涨跌家数
- 板块涨幅前5 / 跌幅前5（同花顺 77 个一级行业）
- 自选股行情
- P0 公告：持仓 + 自选股相关公告
- P1 政策：国家级政策（央行/证监会/国务院/财政部）
- 时间窗口：昨日 15:00 ~ 今日 09:30（周一覆盖整个周末）

### Phase 2：开盘窗口（max 3 轮 tool call，可下单）
- 5 分钟 K 线 9:30~10:00（持仓股 + 自选股）
- 可交易价格列表
- 盘中快讯：09:30~10:00 期间的 P0/P1 消息（如有）

### Phase 3：尾盘窗口（max 3 轮 tool call，可下单 + finish_day）
- 5 分钟 K 线 14:30~15:00（持仓股 + 自选股）
- 收盘价列表
- 盘中快讯：10:00~14:30 期间的 P0/P1 消息（如有）

### Agent 可主动查询（tool call）
- 任意股票 K 线 / 价格 / 基本面（历史对齐，只返回 pub_date <= current_date 的数据）
- 板块概览、选股筛选
- 公告/新闻详情

## Corporate Actions

- 分红/送股/转增：环境自动处理（除权日持仓数量变更、现金到账）
- 停牌：当天 place_order 拒绝（从 K 线缺失推断）

## 评估体系

回测完成后自动输出：
- 累计收益率、年化收益率
- 夏普 / 索提诺 / 卡玛比率
- 最大回撤、最大连续亏损天数
- 胜率、盈亏比
- 换手率、总交易次数
- vs 沪深300 基准对比

支持 action log 导出 + replay 模式（录制 LLM I/O，确定性重放）。

## 历史遮罩机制

所有数据访问都通过 `TradingBus._current_date` 过滤，Agent 无法获取当天及未来的任何信息：

| 数据类型 | 遮罩规则 |
|---------|---------|
| 日线 K 线 | `df["date"] < current_date` |
| 5 分钟线 | 只返回当天已发生的时段 |
| 公告 | `announcement_time < current_date 09:30` |
| 快讯 | `ctime` 按阶段窗口过滤（见每日信息推送） |
| 基本面 | `pub_date <= current_date` 取最新一条 |
| 分红除权 | `ex_date == current_date` 时触发 |
| 跨天记忆 | `memory.to_prompt_text(before_date=current_date)` |

Agent 只能通过 tool call 获取数据，每个 tool handler 内部都强制执行遮罩。

## Tool 设计

16 个工具分 6 类：

| 类别 | Tools | 说明 |
|------|-------|------|
| 市场数据 | get_kline, get_stock_price, get_stock_info | 量价 + 基本信息 |
| 分析 | get_market_overview, screen_stocks, get_sector_summary | 全市场/板块 |
| 持仓 | get_portfolio, get_position | 只读查看 |
| 交易 | place_order（仅开盘/尾盘窗口） | 唯一下单入口 |
| 自选股 | add_watchlist, remove_watchlist, get_watchlist | 跨天持久 |
| 沙箱 | execute_code | Python CLI 沙箱 |
| 控制 | finish_day | 结束当天 |

### Python 沙箱（execute_code）

Agent 可执行任意 Python 代码，高自由度探索。通过 `traderharness_api` 模块访问数据（内部强制遮罩）：

```python
from traderharness_api import market, portfolio, news

# 量价数据（自动遮罩到 current_date 之前）
df = market.get_kline("600519", days=120)       # 单只日线
df = market.get_kline_5min("600519")            # 单只当天5分钟线
codes = market.get_stock_list()                 # 全市场代码
df = market.get_all_daily(days=20)              # 全市场最近N天（向量化操作用）

# 基本面（按 pub_date 遮罩）
info = market.get_fundamentals("600519")

# 持仓（只读）
positions = portfolio.get_positions()
cash = portfolio.get_cash()

# 新闻公告
anns = news.get_announcements("600519", days=30)
policy = news.get_policy_news(days=7)
```

设计要点：
- **自由度高**：任意 import numpy/pandas/scipy/sklearn，自由读写工作目录
- **遮罩严格**：不能直接读 `~/.traderharness/dataset/`，数据只能通过 `traderharness_api`
- **性能优化**：`get_all_daily()` 返回全市场 DataFrame（内存 view，零拷贝），支持向量化
- **超时 60 秒**：硬上限，防死循环
- **去掉 read_file/write_file/list_files/run_script**：沙箱内可直接 open()/os.listdir()

### Tool 错误信息规范

所有 tool 失败时必须返回充分的错误信息，让 Agent 能自主修正：
- 区分"代码不存在" vs "日期前无数据" vs "已停牌"
- 参数被忽略时明确提示（如找不到指定板块）
- 空结果附带原因提示
- 涨停只拒绝买入、跌停只拒绝卖出（方向区分）

### 待新增 Tools（v0.1.0）

| Tool | 功能 | 数据源 |
|------|------|--------|
| get_fundamentals | 基本面查询（ROE/净利润/营收/EPS），按 pub_date 对齐 | fundamentals.parquet |
| get_announcements | 查某只股票的公告列表 | announcements.parquet |
| get_news | 查快讯/政策详情 | news_cls.parquet |
| execute_code | Python CLI 沙箱 + traderharness_api | 替代 run_script |

### 待修复（v0.1.0）

- get_stock_info: 接入 stock_registry 返回行业/名称
- get_market_overview / get_sector_summary: 接入行业分类
- screen_stocks: 增加涨跌幅、成交量、行业等筛选条件
- place_order 涨跌停: 涨停只拒绝买入、跌停只拒绝卖出
- 删除 read_file/write_file/list_files/run_script（被 execute_code 替代）

## Data Layer

```
~/.traderharness/dataset/
├── daily.parquet           # 全市场日线 5 年（OHLCV）
├── 5min_full.parquet       # 全市场 5 分钟线 5 年
├── announcements.parquet   # 全市场公告 5 年（标题+时间戳，秒级精度，巨潮）
├── news_cls.parquet        # 财联社快讯 5 年（秒级时间戳）
├── dividends.parquet       # 分红/送股/除权数据
├── fundamentals.parquet    # 基本面数据（含 pub_date 发布日期对齐）
└── metadata.json
```

数据来源：mootdx（日线/5分钟线）、BaoStock（历史回补 + 基本面）、巨潮 cninfo（公告）、财联社（快讯）、AKShare（分红除权）。

## Quick Reference

```bash
cd D:\traderharness
.venv\Scripts\python.exe -m pytest tests/ --no-header -q   # 168 tests

# 数据采集
python scripts/fetch_cninfo_announcements.py   # 公告
python scripts/fetch_cls_news.py               # 财联社快讯
python scripts/fetch_dividend_data.py          # 分红除权
python scripts/fetch_5min_backfill.py          # 5分钟线回补
python scripts/fetch_daily_backfill.py         # 日线回补
```

## Environment

```
Python 3.12 (.venv)
Key deps: pandas, numpy, pyarrow, httpx, click, jinja2, openai, mootdx, baostock, akshare
.env: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
```

## v0.1.0 Scope

### 要做的

| 模块 | 内容 |
|------|------|
| 数据层 | 5 年全量数据（日线/5分钟线/公告/快讯/分红/基本面） |
| 消息面推送 | P0 公告 + P1 政策，注入晨报/盘中窗口 |
| Corporate Actions | 分红送股自动处理 + 停牌拒绝交易 |
| 沙箱 | execute_code + traderharness_api 模块 |
| Tool 修复 | 行业接入、错误信息、涨跌停方向、screen_stocks 增强 |
| 新增 Tool | get_fundamentals, get_announcements, get_news |
| 上下文优化 | 缓存友好的消息结构 + 追加式记忆 |
| 评估输出 | vs 沪深300 基准 + Agent 行为分析指标 |
| 多 Agent 对比 | 多个 Agent 并行回测 + 横向对比表 + 排名 |
| 删除冗余 | read_file/write_file/list_files/run_script |
| README | 10K star 标准，漂亮、清晰、open-box usable |
| 打包 | PyPI 发布 + CI（GitHub Actions） |
| Web UI | Streamlit 实际可用（回测配置/运行/结果展示/多Agent对比） |

### 不在 v0.1.0

- Gym-style 接口（env.step/reset）— v0.2.0 学术场景
- 实时对战（Agent 之间互相影响市场价格）
- 公开排行榜 / 在线提交
- P3 行业关联智能推送

## Development Rules

1. **先讨论，后动手** — 任何功能先对齐方案，不自作主张
2. **不隐瞒问题** — 做得不到位直说，不等追问才暴露
3. **不编造概念** — 源项目没有的东西不发明
4. **质量标准：10K star** — 每个决定都问"这够不够好让人 star"
5. **大功能出设计文档** — 先写方案，确认后再实现
