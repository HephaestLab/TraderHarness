# 扩展 TraderHarness

TraderHarness 的设计允许在不削弱核心不变量的前提下扩展：回测期零 I/O、唯一下单路径、严格时点可见性、确定性执行、环境托管账户（见[核心架构](architecture.md)与
[`AGENTS.md`](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md)）。本页是几个常见扩展点的简要契约。大型改动前请先开 issue；流程见
[`CONTRIBUTING.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CONTRIBUTING.md)。

## 数据源适配器

新市场，或现有 A 股数据集的新供应商，都应产出符合[数据与许可](data.md)中规范 schema 的数据。

契约：

- 在 `traderharness/data/providers/` 下实现 provider；不得绕过 `traderharness/data/datasets.py`，也不得直接写入正在运行的回测的内存表。
- 保持时点完整性：每条记录需要稳定的自然键；非价格类记录还需要可供掩码层过滤的发布时间戳（`pub_date` 式列）。
- 为新表添加或扩展数据医生检查（`scripts/data_doctor.py`）：必需列、日期覆盖与重复键不变量。
- 在 `tests/fixtures/` 提供小体量真实数据夹具与加载测试；验收验证不得用合成价格顶替（见真实数据工作区规则）。

## 工具

面向 Agent 的工具位于 `traderharness/tools/`，通过 `traderharness/tools/registry.py` 注册。

契约：

- 工具处理器接收本次运行的掩码上下文；它绝不能越过上下文读取规范数据集或其他 Agent 的状态。
- 每条失败路径都返回结构化、可行动的错误，区分"代码不存在""该日期前无数据""停牌""参数被忽略"——笼统异常不可接受。
- 新工具需要 JSON-schema 参数校验、每种失败模式一个单元测试；若内置 Agent 应使用它，还要加入相应 Agent 卡片的 `allowed_tools`。
- 工具不得新增第二条下单路径。交易始终走 `TradingBus.place_order()`。

## 沙箱后端

`execute_code` 工具与 `traderharness_api` 模块是 Agent 对掩码数据运行任意分析代码的受认可方式（见[防数据泄漏](contamination.md#egress-coverage)）。

契约：

- 沙箱后端必须执行同样的路径防护，阻断直接读取数据集（`sandbox/guard.py`），并使用同样的 wall-clock 超时。
- `traderharness_api` 的新增能力必须经由现有掩码访问器解析；不得添加返回未掩码 DataFrame 或真实实体代码的代码路径。
- 任何沙箱后端都不得启动嵌套回测，也不得回调引擎的下单路径。
- 沙箱隔离的演进方向见[路线图](roadmap.md#hardened-sandbox)；缩小可信面的贡献尤其受欢迎。

## 评估指标

绩效与行为指标位于 `traderharness/metrics/`。

契约：

- 新指标是对已完成运行的每日净值、成交与决策的纯函数——不得要求重跑回测或调用供应商 API。
- 在 docstring 中写清公式与边界情况（空成交历史、单交易日、缺基准数据），并添加报告/JSON 导出测试。
- Agent 间比较类指标（如排名）属于 `traderharness/metrics/comparison.py`，不属于单 Agent 报告。

## 券商适配器

v1.0 没有实盘券商适配器，见[路线图](roadmap.md#live-broker-adapter)。欢迎以 issue 形式讨论设计与原型，但券商集成不应接进回测用
`TradingBus`——历史模拟与实盘下单是不同的信任边界，必须保持分离。

## 前端（webui）

研究控制台是 `webui/` 下的纯本地 React 应用。

契约：

- 新视图从现有 REST/WebSocket API（`traderharness/server/app.py`）取数；不得在客户端用原始字段重新推导掩码数据。
- 中文文案统一走 `webui/src/locale.ts`，不要在组件里硬编码字面量。
- 新组件配 Vitest 单元测试；新页面或新流程配 `webui/tests/e2e` 下的 Playwright 场景（若应出现在 README GIF 中，同步扩展 `webui/scripts/capture-demo.mjs`）。

## 提交 PR 之前

1. 先写一个能证明新契约的失败测试。
2. 实现时不得削弱
   [`AGENTS.md`](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#non-negotiable-invariants) 中任何不变量。
3. 跑聚焦测试套件，再跑全量（`pytest tests/ --no-header -q`、`ruff check`；涉及引擎/掩码/工具/数据/沙箱的改动还需一次真实回放或回测并检查轨迹）。
4. 如实声明做过哪些真实数据运行、哪些没做。
