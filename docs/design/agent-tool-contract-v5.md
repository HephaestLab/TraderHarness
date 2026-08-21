seo_title: TraderHarness Agent 工具 Schema、错误纠错与阶段执行合同 v5
description: TraderHarness 全部 30 个 Agent 工具的严格参数、统一错误、自纠错、沙箱超时和旧 replay 兼容设计。
lang: zh-CN
---

# Agent 工具合同 v5

本设计约束 TraderHarness 中全部 30 个 Agent 工具。目标是让模型在首次调用前看懂参数，
调用失败后能在同一市场阶段完成纠错，并让运行结果可以从 Schema、轨迹和 replay 三个层面审计。

## 合同边界

- v5 是新运行的默认合同；v1–v4 继续使用历史描述、Schema、消息顺序和序列化规则，保证旧 cassette 可回放。
- 每个 v5 输入对象都设置 `additionalProperties: false`，所有字段带说明，并声明枚举、范围、默认值和条件必填关系。
- 每个工具描述都包含可复制的 `arguments` 示例、成功结果摘要和统一失败合同。
- 本地验证先于实体反遮罩和 handler 执行。参数无效时不会进入工具实现，更不会进入撮合路径。
- DeepSeek 兼容端点并不统一支持供应商侧 strict mode，因此 v5 在本地执行确定性 Schema 校验；这不改变 API 供应商。

成功结果统一增加 `success: true`。失败结果统一为：

```json
{
  "success": false,
  "error": "给人和模型阅读的具体错误",
  "error_code": "稳定机器码",
  "retryable": true,
  "correction": {
    "tool": "工具名",
    "instruction": "同阶段如何修正",
    "valid_arguments_example": {},
    "received_arguments": {}
  }
}
```

`retryable: true` 的错误会保持为阶段内待办。Agent 必须让同一工具成功，或者在
`complete_phase` / `finish_day` 的 `abandon_error_codes` 中显式放弃并在摘要解释；否则市场时钟不推进。
结束工具本身也经过同一校验。收盘兜底最多进行三次可见纠错，失败会写入
`_finish_day_protocol_failure` 和轨迹，不再静默吞掉错误。

## 工具清单

| 类别 | 工具 | v5 重点 |
|---|---|---|
| 行情 | `get_kline` | 只返回 D-1 及更早日线；日内分钟线不混入 |
| 行情 | `get_stock_price` | 盘前为 D-1；盘中为当前已揭示 5 分钟收盘价，并返回来源、时点和可成交标记 |
| 行情 | `get_stock_info` | 代码、名称、行业和市场元数据 |
| 行情 | `get_market_overview` | 市场宽度和行业强弱 |
| 叙事 | `get_narrative_market_overview` | 多周期强度、扩散和高低切候选 |
| 筛选 | `screen_stocks` | 范围、排序和 1–30 条结果约束；价格上下界错误可纠正 |
| 筛选 | `screen_behavioral_cycle` | 点时行为量价特征，不输出买卖裁决 |
| 行业 | `get_sector_summary` | 行业平均表现与领涨/领跌成分 |
| 叙事 | `get_narrative_sector_summary` | 每日最多两个不同板块；预算耗尽为不可重试错误 |
| 基本面 | `get_fundamentals` | 财务指标附单位；比率统一为百分比 |
| 基本面 | `get_business_segments` | 收入字段为 `revenue_100m_cny`，明确单位为亿元人民币 |
| 基本面 | `get_valuation` | 估值与换手率附单位和数据日期 |
| 文本 | `get_announcements` | 同时返回点时时间、标题和公告类型 |
| 文本 | `get_announcement_evidence` | 返回可在决策卡中引用的 `evidence_id` |
| 文本 | `get_news` | 关键词按字面值匹配，返回时间、标题、正文和等级 |
| 文本 | `get_narrative_news` | 证据 ID、标签和关联股票；每日两次预算为明确错误 |
| 组合 | `get_portfolio` | 现金、净值、持仓与逐证券估值来源 |
| 组合 | `get_position` | 成本、可卖数量、计划、盈亏与当前价格来源 |
| 交易 | `place_order` | 买入手数、结构化计划和决策卡按上下文条件校验；唯一撮合入口不变 |
| 条件单 | `manage_conditional_order` | create/update/cancel 分支必填；使用相对字段 `expires_in_trading_days` |
| 条件单 | `list_conditional_orders` | 返回过滤状态、数量、版本和失败尝试 |
| 自选 | `add_watchlist` | 完整可见代码、理由和跨日有效期 |
| 自选 | `remove_watchlist` | 不存在条目为明确不可重试错误 |
| 自选 | `get_watchlist` | 盘中优先当前窗口价，并标注来源 |
| 记忆 | `remember` | 日限额不可重试；冲突/容量错误返回候选 ID 和可修正参数 |
| 记忆 | `search_memory` | 类型枚举和 1–20 条确定性检索 |
| 记忆 | `get_memory` | `memory_id` 必须从工具结果原样复制 |
| 沙箱 | `execute_code` | 代码长度限制、真实超时终止、traceback 行号和重试预算；可见 API 按工具权限收口 |
| 控制 | `complete_phase` | 只有成功调用且无未决可重试错误时才推进子阶段 |
| 控制 | `finish_day` | 摘要最多 500 字；失败自动纠错并留下协议失败审计 |

证券代码字段统一要求复制完整可见代码。开启实体遮罩时，例如 `SHM-000360` 必须保留板块前缀；
只提交六位后缀产生歧义时，错误会返回 `candidate_aliases` 和完整的 `retry_argument_choices`。

## 大结果与沙箱

超过 3000 字符的 v5 工具结果不再截断原始 JSON 字符串。系统会逐级压缩数组和长文本，返回仍可解析的
JSON，并附 `_truncation`、原长度和缩小查询范围的说明。v1–v4 保留旧序列化以兼容 replay。

沙箱仍遵守项目的进程内、只读市场视图边界。v5 为 Python 字节码安装 deadline trace；超时后确认工作线程
退出，并返回 `sandbox_timeout`。API 访问同时受 Agent 卡工具 allowlist 约束：例如全市场日线需要
`get_kline` 权限，行为特征需要 `screen_behavioral_cycle` 或 `get_kline` 权限。沙箱仍不能读取 canonical
dataset，也不能启动嵌套回测。

## 审计

自动合同测试遍历全部 30 个工具，验证工具目录、输入/输出合同、字段说明和调用示例一一对应；还覆盖：

- 无效类型、未知字段和缺失字段不会进入 handler；
- handler 的历史字符串错误会被规范化；
- 大结果压缩后仍是合法 JSON；
- 结束工具失败不能推进阶段；
- `finish_day` JSON 错误可自动重试；
- 沙箱真实死循环被终止；
- v2 内置真实数据 cassette 仍逐请求匹配。

验证命令：

```powershell
.venv\Scripts\python.exe -m ruff check traderharness tests
.venv\Scripts\python.exe -m pytest tests --no-header -q
traderharness audit <artifact>
```
