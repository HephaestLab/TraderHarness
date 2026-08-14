### 项目地址

https://github.com/HephaestLab/TraderHarness

### 类别

人工智能

### 项目标题

给 LLM 交易 Agent 一个不作弊的考场

### 项目描述

LLM 炒股 Agent 越来越多，但回测环节几乎没有规范：模型在训练语料里"背过"历史行情，回测成了开卷考试；各家成交口径不一，收益无法复现。这个项目为 A 股场景做了一套抗污染评测环境：日期与实体双重遮罩让模型认不出考题，公告严格按披露时点落地，同一份输入重放结果逐位一致。每次回测还会沉淀全保真决策轨迹，可导出为 SFT/RL 训练数据，适合研究 LLM 交易能力、或者正在为交易类 Agent 攒训练语料的同学。

### 亮点

- **抗污染是底层设计，不是补丁**：不只屏蔽未来数据，连真实日期、公司名都会替换成代号——模型就算在语料里背过这段历史，也对不上号。
- **确定性回放**：同样的可见数据 + 同样的动作序列，环境结果完全一致（含订单号）。Agent 实验第一次有了可靠的对照组，收益差异终于可以归因到模型本身。
- **回测即数据采集**：每一天的决策上下文（看到什么、怎么推理、怎么下单）全程录制，一键导出 SFT/RL 训练样本，相当于一台交易方向的训练数据合成器。
- **数字克制透明**：README 公开了 4 个主流模型在沪深 300 单月 -9.12% 行情下的完整成绩与 token 成本测算，不吹年化翻倍。
- **上手友好**：中文 README、Apache-2.0，附像素风可视化控制台，60 秒跑通 demo，无需 API Key。

### 示例代码

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

### 截图或演示视频

![研究控制台演示](https://hephaestlab.github.io/TraderHarness/assets/traderharness-demo.gif)

![回测结果工作台](https://hephaestlab.github.io/TraderHarness/assets/results-workbench.png)

![像素办公室](https://hephaestlab.github.io/TraderHarness/assets/office-live.png)

文档站：https://hephaestlab.github.io/TraderHarness/
