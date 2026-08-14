# TraderHarness 发布冲刺计划

> 目标：抢占"Trading Agent 规范化回测框架"的定位缺口，完成公开发布，并通过 SEO/GEO 快速积累影响力与 Star。
> 制定时间：2026-07-19 · 基于当日仓库实际盘点

---

## 0. 现状盘点：比预想更接近发布

### 已具备（不需要重做）

| 项 | 状态 |
|---|---|
| PyPI 包 `traderharness` | ✅ 已上线（pypi.org 200） |
| README.md（英文，344 行）+ README_zh.md | ✅ 结构完整，徽章/对比表/GIF 都有 |
| LICENSE(Apache-2.0) / CITATION.cff / CONTRIBUTING / SECURITY / CHANGELOG | ✅ 齐全 |
| 文档体系（mkdocs + docs/ 14 篇，含 comparison/contamination/training-data/faq） | ✅ 内容质量好 |
| CI / release.yml(PyPI) / docs.yml(Pages) / dataset-release.yml(HF) | ✅ 四个工作流都在 |
| HF 数据集脚本链（`build_hf_release.py` → `audit` → `upload_hf_release.py`） | ✅ 自动化已就绪 |
| 发布话术草稿（`docs/release-playbook.md`：Show HN、Reddit、topics、social preview） | ✅ 复制即用 |
| GEO 地基（llms.txt / llms-full.txt） | ✅ 已写 |
| Roadmap（`docs/roadmap.md`：v1.0 / paper trading / broker adapter / 非目标） | ✅ 只需小更新 |
| 本机 canonical 数据集（`~/.traderharness/dataset` 七项全部就绪） | ✅ 可立即打包 |

### 真实缺口（阻塞发布或影响传播）

| # | 缺口 | 影响 |
|---|---|---|
| G1 | **GitHub 仓库未公开**（匿名访问 404） | 一切传播的前提 |
| G2 | **文档站未部署**（hephaestlab.github.io 404，Pages 未开或未跑过 docs.yml） | SEO/GEO 主阵地缺失 |
| G3 | **全部 UI 素材过时**（demo GIF、3 张工作台截图、social-preview 均为 7/18 旧版，没有像素办公室、实时绩效面板、跨 run 对比等新门面） | 首屏传播力最大短板 |
| G4 | **README 首屏缺"三段式钩子"**（Agent 走入交易 → 无规范化回测框架 → 本项目=回测框架+数据合成器），"数据合成器"定位埋得太深 | 定位记忆点弱 |
| G5 | **HF 数据集未创建**（401）：需执行打包→audit→建仓→上传→完善 Dataset Card | 数据合成器故事的物证 |
| G6 | **工作区大量未提交改动**（UI 大修 + 新端点等），版本号与 CHANGELOG 未更新 | 工程收尾 |
| G7 | **数据再分发许可需确认**（A 股行情数据来自 mootdx/baostock，直接托管到 HF 前要核对 docs/data.md 的 licensing 结论；不行就改为"下载器+manifest 校验"模式） | 合规风险 |
| G8 | **分发渠道未执行**：awesome-* 列表 PR、中英文长文、视频、DeepWiki/Zread 收录、发布节奏 | 发布后冷启动 |

---

## 1. 阶段计划

### Phase 0 — 工程收尾（预计 0.5~1 天，全部可由 agent 完成）

| 任务 | 验收标准 |
|---|---|
| 0.1 提交全部改动，决定版本号（建议 `1.1.0`：研究台 2.0 + 像素办公室 + LiveRun 重构 + 结果管理），更新 CHANGELOG | git 干净、tag 就绪 |
| 0.2 全量验证：`pytest tests/`（含 integration）、`ruff`、webui `npm test` + `npm run build` + e2e | 全绿 |
| 0.3 真实回测验收跑（AGENTS.md 要求），`traderharness audit` 验收产物 | audit 通过 |
| 0.4 **重拍全部素材**：跑 `webui/scripts/capture-demo.mjs` 生成新 hero GIF；手动补拍像素办公室（闲聊/走风控台/Wall-Graph 活屏）、实时绩效面板、逐笔复盘、跨 run 对比 | `docs/assets/` 全部为新 UI |
| 0.5 重做 social-preview.png（1280×640，含像素办公室） | GitHub 分享卡片美观 |

### Phase 1 — README 钩子重写（预计 0.5 天，agent 主笔）

首屏新结构（英文为主，中文同步 README_zh.md）：

1. **钩子三段式**：LLM Agent 正在走入真实交易场景 → 但"跑个回测"至今没有规范化框架：数据泄漏（模型认得日期/公司/走势）、成交口径随意、结果不可复现 → TraderHarness = 抗污染回测执行环境 **+ LLM Trading 专项数据合成器**。
2. **双定位首屏**：左/上半屏讲回测框架（掩码、单一撮合、三阶段循环），右/下半屏讲数据合成（全保真轨迹 → replay cassette → SFT 导出，引用 `docs/training-data.md`）。
3. **新 hero GIF**（像素办公室直播 + 权益曲线 + 逐笔复盘的三连画面）。
4. 保留并后移：对比表、四智能体、架构、quickstart（60 秒无 key demo）。
5. 末尾：数据集 HF 链接、roadmap 链接、Star history 曲线徽章（利于社交证明）。

验收：首屏一屏内能看懂"是什么、为什么独特、30 秒怎么跑起来"；中英文一致。

### Phase 2 — HuggingFace 数据集（预计 0.5 天 + 用户账号操作）

| 步骤 | 负责 | 说明 |
|---|---|---|
| 2.1 确认再分发许可（读 docs/data.md licensing；必要时改"下载器+manifest"模式） | agent+用户决策 | **合规卡点，先做** |
| 2.2 本机执行 `python scripts/build_hf_release.py --output <dir>` | agent | staging |
| 2.3 `traderharness audit <dir>` | agent | 泄漏审计（发布铁律） |
| 2.4 创建 HF 数据集 repo（建议 `HephaestLab/traderharness-a-share`），配 `HF_TOKEN` secret | **用户** | 需要 HF 账号 |
| 2.5 上传（workflow_dispatch 或直接跑 upload 脚本） | agent | |
| 2.6 完善 Dataset Card：YAML 元数据、schema 表、许可、引用方式、与 GitHub/PyPI 互链；附 1~2 条示范 replay cassette 与 SFT 样例（"数据合成器"的物证） | agent | 卡片质量决定数据集页转化 |

### Phase 3 — 公开发布（预计 0.5 天，用户操作 + agent 核对）

1. 仓库转公开（用户）→ agent 逐项核对：description、topics（playbook 里现成 20 个）、social preview、默认分支保护。
2. 开 GitHub Pages、验证 docs.yml 部署成功、文档站 200 且互链正确。
3. 打 tag、release.yml 发 PyPI 1.1.0、GitHub Release 复制 CHANGELOG。
4. HF 数据集、PyPI、文档站、GitHub 四处链接交叉验证全部 200。

### Phase 4 — SEO/GEO 分发（发布后 1~2 周集中执行）

**英文线**
- Show HN：用 playbook 现成草稿，周二~周四 8-10am EST 发布；标题即"无污染回测"差异化。
- Reddit：r/algotrading（草稿已有）、r/LocalLLaMA（主打数据合成器+SFT）。
- 长文 1 篇（dev.to + Medium 双发）：角度建议《Your trading agent is probably cheating: contamination in LLM backtests》——问题导向最易被引用。
- X/Twitter 线程：3 张 GIF（办公室直播/掩码示意/SFT 导出）。
- awesome 系列 PR：`awesome-llm`、`awesome-ai-agents`、`awesome-quant`、`awesome-deepseek`、`awesome-finance-llm`（逐个按模板提 PR）。
- DeepWiki 收录申请 + README 加 badge。

**中文线**
- 知乎 + 掘金 + 思否长文各 1 篇（中文 SEO 主阵地，标题示例《LLM 炒股Agent遍地，却没有一个规范化的回测框架》）。
- B 站 3~5 分钟演示视频：像素办公室直播 → 逐笔复盘 → SFT 导出，比图文传播效率高一个量级。
- 即刻/小红书短内容；可选投稿量子位/机器之心。

**GEO（针对 AI 答案引擎）**
- 保持 llms.txt/llms-full.txt 与文档站同步（每次发版刷新）。
- docs 的 FAQ/comparison 页面标题改成问句式（"How to prevent data leakage in LLM trading backtests?"），AI 摘要友好。
- 数据集 HF 卡片、PyPI 描述、GitHub README 三处关键词统一：`backtesting LLM trading agents`、`trajectory SFT export`、`point-in-time masking`。
- 发布后 2 周抽查：问 ChatGPT/Kimi/Perplexity "有没有给 trading agent 做规范回测的框架"，看是否被提及，针对性补内容。

**节奏建议**：D0 仓库+文档站上线 → D1 中文长文+B站 → D2 Show HN+Reddit（工作日美东上午）→ D3~D7 awesome PR、X 线程、社群 → D14 GEO 抽查 + 复盘。

---

## 2. 需要用户决策/提供的清单

1. **数据再分发许可结论**（G7，合规决策）。
2. GitHub 仓库管理员操作：转公开、Pages 开启、secrets（HF_TOKEN、PYPI_TOKEN 确认）。
3. HuggingFace 账号与数据集 repo 命名确认。
4. 各分发平台账号（HN/Reddit/知乎/B站等，发布动作由用户账号发出）。
5. 版本号拍板：建议 1.1.0。

## 3. 建议执行顺序

**今天可立即开工（全部 agent 侧）**：Phase 0（提交+验证+重拍素材）→ Phase 1（README 重写）→ Phase 2.1~2.3（数据集 staging+audit）。
**等你账号操作**：Phase 2.4、Phase 3。
**发布后**：Phase 4 按节奏表执行，发布话术全部现成。
