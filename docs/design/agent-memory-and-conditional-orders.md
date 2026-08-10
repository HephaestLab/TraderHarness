# Agent 分层记忆与条件单执行

本文记录 TraderHarness 的 Agent 记忆和环境托管条件单设计。目标是让研究结论可复用、执行状态不依赖 LLM 记忆，同时保持点时安全、确定性和完整审计。

## 设计来源

本实现借鉴而非复制下列开源设计：

- [OpenClaw Memory](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)：精简长期记忆、逐日日志、按需检索，以及上下文压缩前的 memory flush。
- [Letta Memory Blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks)：始终可见、带类型和容量边界的结构化记忆。
- [OpenHands Context Condenser](https://docs.openhands.dev/sdk/guides/context-condenser)：保留近期事件并把早期上下文压缩成可追溯摘要。
- [LangGraph Checkpoints](https://langchain-ai.github.io/langgraph/reference/checkpoints/)：把线程短期状态与跨线程长期存储分开。

TraderHarness 没有引入这些框架或远程 embedding 服务。核心回测必须确定性复现，因此使用本地 JSONL 事件日志和确定性词法检索。

## 记忆层级

1. **硬状态**：持仓、冻结持仓计划、活动条件单由环境拥有。压缩前自动 flush 成版本化 `runtime_state`，但真实执行始终以环境状态为准。
2. **长期记忆**：假设、风控规则和复盘教训带有 `memory_id`、类型、标签、重要度、来源和状态，精简后常驻每日初始上下文。
3. **逐日日志**：`finish_day` 总结和成交按日追加。最近五日注入完整内容，更早内容只提示已归档。
4. **按需检索**：`search_memory` 以确定性词法重合排序；`get_memory` 按 ID 读取完整记录。
5. **版本链**：`remember(..., supersedes_id=...)` 先追加 supersede 事件，再创建新记录。旧记录不删除，审计时能恢复完整演变。

持久化文件仍为 `<memory_dir>/<agent_id>_memory.jsonl`。回测默认只在当前 Agent 实例内跨日共享；若显式提供 `memory_dir`，调用方必须使用 run-scoped 目录，避免后一次历史回测读到前一次更晚日期的经验。

## 条件单状态机

```text
create -> active -> triggered
                 -> cancelled
                 -> expired
          \-> trigger_failed -> active (后续窗口继续尝试)
```

`manage_conditional_order` 支持 `create`、`update`、`cancel`；`list_conditional_orders` 查询状态、修改版本和失败尝试。比较器为：

- `price_lte`：5 分钟 bar 收盘价小于等于触发价；
- `price_gte`：5 分钟 bar 收盘价大于等于触发价。

创建或修改后只扫描尚未揭示的 bar，绝不追溯触发。活动订单按时间、再按 `order_id` 确定性排序。每次实际成交仍调用 `TradingBus.place_order()`，因此继续受到以下规则约束：

- T+1；
- 涨跌停；
- 100 股整数手；
- 现金余额；
- 单股每日只能交易一次；
- 条件买入在触发时重新检查 Agent 的持仓只数和单股仓位约束。

满足价格不等于保证成交。若 T+1、跌停、现金或当日已交易等检查失败，订单保留为 `active`，记录 `trigger_failed`，后续新窗口继续尝试。

## 结构化持仓计划联动

要求结构化计划的 Agent 在首次 `place_order(buy)` 成功后，环境自动创建：

```text
side=sell
quantity=0                 # 触发时全部可卖
comparator=price_lte
trigger_price=original_structural_stop
protective=true
```

A 股 T+1 下，该保护单从下一交易日开始有效。多头保护价只能上移，不能下调；修改只对后续 bar 生效。若保护价被上移到原始止损之上，最短持有期约束仍由环境执行。全部退出后，同一股票的其它活动卖出条件单自动取消。

## 为什么只用 bar close

单根 OHLC 无法说明价格先触及 high 还是先触及 low。若直接用 high/low 触发，会在同一根 bar 内虚构一条未知价格路径。当前实现逐根使用真实 5 分钟收盘价，并以该收盘价成交，牺牲部分灵敏度来换取无歧义和可复现。未来接入逐笔或盘口流时，可以保持同一状态机，只替换价格事件粒度。

## 结果审计

每个 Agent 结果新增：

- `conditional_orders`：所有条件单最终状态；
- `conditional_order_events`：创建、修改、失败、触发、取消和过期事件；
- `memory_events`：日记、记忆、替换和运行状态 flush 的追加日志；
- 条件成交在普通 `trades` 中带 `conditional_order_id` 和 `execution_time`。

这些字段随正常结果文件保存，可由 `traderharness audit <artifact>` 一并审计。
