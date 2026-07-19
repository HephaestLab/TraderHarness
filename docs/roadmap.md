# 路线图

本页记录 TraderHarness 已经交付了什么、计划做什么，方便集成方做"自建还是等待"的决策，而不必从 issue 列表里猜。以下内容均不构成日期承诺。

## ✅ v1.0 已交付

- 五年全市场 A 股数据集（日线、5 分钟、公告、政策新闻、基本面、估值、分红、沪深 300），带原子增量更新与完整性检查。
- 预加载后回测期零行情 I/O；`TradingBus.place_order()` 唯一下单路径。
- 日线、盘中、新闻、公告、基本面与沙箱出口的严格时点掩码。
- 确定性日历（`D+0`、`D-1`……）与保留板块语义的公司实体匿名化。
- 盘前 / 开盘窗口 / 尾盘窗口三阶段 Agent 循环，盘中渐进可见。
- 独立多 Agent 对比（`traderharness compare`），以及单执行者多角色委员会参考实现（顾问只读；唯一 Trader 持有下单工具）。
- 全保真 LLM 交互轨迹、失败即报错的指纹回放、OpenAI 风格轨迹导出。
- 序列化工件泄漏审计（`traderharness audit`）。
- 本地 FastAPI + React 研究控制台、非特权 Docker 镜像、PyPI 打包与 CI。

逐项发布说明见 [`CHANGELOG.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CHANGELOG.md)。

## 🚧 下一步：模拟实盘（paper trading）

一种模拟的实时前推模式：复用现有引擎、掩码与工具契约，但数据源从全量预加载改为流式推送，从而无需改动代码就能对一张 Agent 卡片做面向未来的评估。该功能在设计中，**目前不可用**，仓库中任何内容都不应被解读为相反 claim。

从回测引擎继承的约束：

- 同样的 `TradingBus.place_order()` 路径与风控检查；
- 任何面向 Agent 的出口都遵守同样的掩码契约；
- 不存在让沙箱或工具看到模拟时钟之后数据的捷径。

## 📋 规划：实盘券商适配器 {#live-broker-adapter}

一个适配器边界，让模拟实盘或研究 Agent 可以对接真实券商 API。它依赖模拟实盘先落地，并需要与项目整体安全姿态相匹配的凭据与下单授权威胁模型（见
[`SECURITY.md`](https://github.com/HephaestLab/TraderHarness/blob/main/SECURITY.md)）。目前没有任何券商集成。

## 📋 规划：沙箱加固 {#hardened-sandbox}

当前 Python 沙箱（`execute_code` + `traderharness_api`）的定位是防止单一可信研究者意外读取规范数据集或启动嵌套回测——见
[本地服务器安全](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#local-server-security)。未来版本计划的加固：

- 适合运行不可信或第三方 Agent 卡片的资源与 wall-clock 隔离；
- 更窄的默认 `traderharness_api` 面，按工具做能力域划分；
- 与现有轨迹记录并列的结构化沙箱审计日志。

## ❌ 非目标

- **公开排行榜或托管多租户服务。** TraderHarness 是本地研究基础设施；见[本地服务器安全](https://github.com/HephaestLab/TraderHarness/blob/main/AGENTS.md#local-server-security)。
- **市场冲击建模。** 历史成交使用不复权价格，不模拟 Agent 自己的订单对市场的推动。
- **规定交易方法论。** 环境保持 Agent 架构中立；见[项目对比](comparison.md)。
- **Agent 之间实时互动、互相影响成交。** 每个 Agent（或委员会）都在自己的隔离账户中对同一历史时钟交易。

## 如何参与

上述路线图条目是最可能被快速接受的贡献方向。贡献契约见[扩展开发](extensions.md)，流程见
[`CONTRIBUTING.md`](https://github.com/HephaestLab/TraderHarness/blob/main/CONTRIBUTING.md)。
