# 各渠道发布文案

## 1. B站（视频发布，素材用 promo/out/traderharness-promo-v4.mp4）

**标题（三选一，推荐第一个）：**
- 我们让 4 个 AI 在 A 股暴跌月实盘对打，结果出乎预料
- AI 炒股回测都是作弊的？我做了个防作弊考场
- 【开源】给 LLM 交易 Agent 做的规范化回测框架，附像素办公室直播

**简介：**
> LLM 炒股 Agent 越来越多，但回测时模型可能认得历史行情——收益再高也可能是"背"出来的。
> TraderHarness 是一个抗污染的 LLM 交易 Agent 回测环境：日期与实体双重遮罩、严格时点安全、
> 唯一撮合路径、指纹回放可复现，每次回测还能一键导出轨迹训练数据。
> 实测：2026.6.20-7.20 沪深300 暴跌 -9.12% 的窗口里，Claude/Kimi/Qwen/DeepSeek
> 四个模型独立跑完 21 个交易日，全部大幅跑赢指数，但"交易性格"天差地别。
>
> GitHub: https://github.com/HephaestLab/TraderHarness
> 文档: https://hephaestlab.github.io/TraderHarness/
> 数据集: https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y

**标签：** 量化交易, LLM, AI Agent, 大模型, 回测, 开源, Python, 人工智能, A股, 深度学习

**置顶评论：**
> 时间轴：00:00 问题：AI 回测为什么可能是作弊 → 00:45 双重遮罩 → 01:30 像素办公室直播
> → 02:30 四模型魔鬼行情对决 → 03:30 轨迹数据导出。项目完全开源（Apache-2.0），
> pip install 三行命令就能跑，demo 不需要 API Key。

---

## 2. V2EX（「分享创造」节点）

**标题：** [开源] TraderHarness：给 LLM 交易 Agent 做的抗污染回测环境——让 4 个模型在 A 股暴跌月实盘对打

**正文：**
> 各位好，分享一个做了很久的项目。
>
> 背景：现在 LLM 炒股 Agent 很火，但我看了一圈发现个尴尬的事——大多数项目的回测里，
> 模型是知道真实日期和公司名的。通用大模型大概率"背过"那段历史行情，回测收益再漂亮，
> 也分不清是交易能力还是记忆力。
>
> TraderHarness 的做法：
> - 日期+实体双重遮罩：模型看到的是 D-1 和伪代码，不知道自己在哪段历史里
> - 所有数据出口强制时点过滤，没有未来函数
> - 唯一撮合路径 + 预载内存数据，同样输入必然同样结果
> - 每次 LLM 调用记录指纹，回放盒带无需 API Key 即可逐位复现
>
> 实测：6.20-7.20 沪深300 跌 -9.12%，同一张趋势交易卡跑 4 个模型，
> Claude +1.45%（6 笔，回撤 0.76%）、Kimi +0.34%（全月 2 笔）、Qwen -1.64%（12 笔全亏）、
> DeepSeek -2.69%。全部跑赢指数，但风格差异巨大，挺有意思。
>
> 另外每次回测自动沉淀全保真轨迹，可导出 SFT/RL 训练数据，5 年 A 股数据集已放 HuggingFace。
>
> GitHub: https://github.com/HephaestLab/TraderHarness
> 本地控制台有个像素办公室可以围观 Agent 上班，demo 不需要 API Key，欢迎体验拍砖。

---

## 3. 开源中国（开源软件收录申请）

- **软件名称：** TraderHarness
- **所属分类：** 程序开发 → 测试工具 / 人工智能
- **授权协议：** Apache-2.0
- **开发语言：** Python / TypeScript
- **一句话简介：** 面向 LLM 交易 Agent 的抗污染回测环境与轨迹数据合成器
- **软件介绍：**（用 article-main.md 第 2-4 节，去掉第一人称，改陈述句）
- **亮点：** 日期与实体双重遮罩防数据泄漏；时点安全的数据出口；唯一撮合路径保证成交口径一致；
  指纹回放确定性复现；回测轨迹一键导出训练数据；内置像素风可视化控制台。

---

## 4. HelloGitHub 投稿（GitHub issue，我可直接用 gh 提交）

**标题：** 【项目推荐】TraderHarness：面向 LLM 交易 Agent 的抗污染回测环境

**正文：**
> - 项目地址：https://github.com/HephaestLab/TraderHarness
> - 类别：Python / 人工智能 / 金融
> - 项目标题：面向 LLM 交易 Agent 的抗污染回测环境与轨迹数据合成器
> - 项目描述：LLM 交易 Agent 的回测长期没有规范：模型认得真实日期与公司名导致数据泄漏、
>   成交口径混乱、结果无法复现。TraderHarness 通过日期与实体双重遮罩、时点安全的数据出口、
>   唯一撮合路径与指纹回放，让"AI 炒股"第一次可复现、可审计；每次回测同时沉淀全保真轨迹，
>   一键导出 SFT/RL 训练数据。附带 5 年 A 股全市场数据集（已发布 HuggingFace）与
>   像素风可视化控制台。
> - 亮点：抗污染评测 / 确定性回放 / 轨迹数据合成 / 中文文档完善 / 60 秒上手 demo 无需 Key
> - 截图：（附 docs/assets/traderharness-demo.gif、results-workbench.png、像素办公室图）

---

## 5. 小红书（图文笔记，成稿见 final/xhs-title.txt + final/xhs-body.md）

**标题：** Agent炒股 连个回测框架都没有？（18字，限20）

**定位：** 面向小红书技术人群，口吻与掘金/聚宽稿一致（技术长文收敛版），不用网感话术、不堆 emoji

**平台约束与注意：**
- 正文 855 字（限 1000），已含 8 个话题标签，发布时在编辑器里把 # 标签逐个点选成蓝色话题（#LLM 若匹配不到站内话题，换 #大模型应用）
- 不放任何外链/二维码（导流敏感），CTA 只写 "GitHub 搜 TraderHarness"
- 金融内容审核严：已用"技术实验"定位 + 文末免责声明，不出现"教你炒股/收益保证"话术
- 国产模型（Qwen/DeepSeek）战绩垫底可能引战，属预期内讨论流量，免责声明已在
- 图文笔记不支持 GIF；如发视频笔记用 promo/out/traderharness-promo-v4.mp4

**配图顺序：**
1. final/xhs-cover.png（封面，3:4 带标题字，由 build_xhs_cover.py 生成）
2. docs/assets/office-live.png（像素办公室全图）
3. docs/assets/results-workbench.png（净值/回撤工作台）
4. docs/assets/run-compare.png（四模型对比）
5. docs/assets/trade-review.png（K线逐笔复盘）

**发布时间建议：** 工作日 12:00-14:00 或 19:00-22:00（小红书流量高峰）

---

## 6. 公众号投稿邮件（HelloGitHub 月刊 / 开源中国）

> 主题：项目自荐 | TraderHarness——给 LLM 交易 Agent 一个不作弊的考场
>
> 编辑老师好，自荐一个开源项目：LLM 炒股 Agent 今年爆发，但回测普遍存在数据泄漏
> （模型认得历史行情）。TraderHarness 用双重遮罩+时点安全+指纹回放做了套"防作弊考场"，
> 并实测 4 个主流模型在沪深300 暴跌 -9.12% 的月份全部跑赢指数。
> 项目：github.com/HephaestLab/TraderHarness（Apache-2.0，中文文档，demo 无需 Key）。
> 详细介绍长文见附件/链接，如需配图和视频素材可随时提供。
