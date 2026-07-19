# 多角色 Agent 适配器

## 目标

在不改变 TraderHarness 的市场、账户、撮合、掩码与回放语义的前提下，支持 TradingAgents 风格的委员会。委员会是被评估的一个 Agent、一个账户。专家角色只提供建议；唯一执行者才能调用
`place_order`。

这与 `traderharness compare` 不同：后者中独立 Agent 各自持有账户并相互排名。

## 模型

```text
BacktestEngine（共享不可变市场快照）
  └─ CommitteeAgent（一个 Portfolio + 一个 TradingBus）
       ├─ 基本面顾问 ───────┐
       ├─ 技术面顾问 ───────┼─> 阶段备忘录
       ├─ 新闻顾问 ─────────┤
       ├─ 多头研究员 ───────┤
       ├─ 空头研究员 ───────┘
       └─ trader/执行者 -> 现有 AgentLoop -> TradingBus.place_order()
```

多个独立委员会之间仍可由引擎并行：

```text
委员会 A + 账户 A ────┐
委员会 B + 账户 B ────┼─ 每个交易日 asyncio.gather
单 Agent + 账户 C ────┘
```

## 不变量

1. 顾问只收到已经掩码的 Agent 可见消息。
2. 顾问没有下单工具。只读工具访问是后续扩展。
3. 执行者使用现有 `ToolRegistry`；`TradingBus.place_order()` 仍是唯一撮合路径。
4. 委员会调用对回放是确定的：角色、阶段、提示词、响应、模型与顺序都是轨迹记录。
5. 一个运行级的 `EntityMasker` 由所有顾问与执行者共享。
6. 顾问失败在备忘录与轨迹中显式可见；不做静默兜底。

## 扩展面

```python
class Advisor(Protocol):
    role: str
    async def advise(self, messages: list[dict], phase: str) -> str: ...

class CommitteeCoordinator:
    async def build_memo(
        self,
        messages: list[dict],
        phase: str,
        sub_window: str | None,
    ) -> CommitteeMemo: ...
```

`AgentLoop._run_phase()` 在每个 `(day, phase, sub_window)` 的首次执行者调用前请求一份备忘录。顾问通过
`asyncio.gather` 并发执行；产出作为带标签的系统消息注入。执行者可以接受或否决每一条建议。

## TradingAgents 适配器

适配器把外部图节点映射为 `Advisor` 实现：

- 市场/新闻/基本面分析师 -> 专家顾问
- 多/空研究员 -> 对抗顾问
- 研究经理/风险经理 -> 综合顾问
- Trader -> TraderHarness 执行者

外部工具与账户对象不会被引入，取而代之的是 TraderHarness 的掩码观测与单一账户/下单路径。这样既保留外部推理拓扑，又保证回测公平性。

## 配置

加载器（`PromptAgent`）通过顶层 `advisors:` 列表识别委员会——不存在嵌套的 `committee:`
或 `executor:` 块。`id`、`name` 与执行者自己的 `model`/`persona` 都在顶层，与单 Agent 卡片完全一致：

```yaml
id: tradingagents-reference
name: TradingAgents Reference Committee
model: deepseek-chat
persona: ...
advisors:
  - role: fundamentals
    model: deepseek-chat
    prompt: ...
  - role: technical
    model: deepseek-chat
    prompt: ...
  - role: bull
    model: deepseek-chat
    prompt: ...
  - role: bear
    model: deepseek-chat
    prompt: ...
```

完整可加载的参考委员会见
[`examples/tradingagents_committee.yaml`](https://github.com/HephaestLab/TraderHarness/blob/main/examples/tradingagents_committee.yaml)。

## 验收标准

- 单元测试证明顾问永远不会拿到 `place_order`。
- 单元测试证明所有顾问被并发调度。
- 集成测试证明恰好只有一个执行者能下单。
- 回放能复现同样的备忘录与执行者动作序列。
- 真实一日、三日与一个月运行通过泄漏审计。
- `compare` 能在相同数据、现金、掩码种子与基准下，把委员会与普通 Agent 一起排名。

## 暂缓项

- 按顾问划分的只读工具预算。
- 任意环形图与 Agent 间消息总线。
- 多执行者共享账户（有意排除——它会让订单归属与回放变得含糊）。
