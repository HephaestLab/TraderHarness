# 抖音图文发布清单

## 定位

- 主线：交易 Agent 缺少一套规范、完整的回测框架。
- 核心叙事：回测不是“问一次买不买，再画净值曲线”，而是市场时钟、数据边界、事件、撮合、账户和证据的统一环境。
- 遮罩、时点安全与回放审计是框架细节，不占据封面主叙事。

## 图片顺序

1. `douyin/01-cover.png`：封面用 Result 的逐笔成交与 K 线做主视觉，再用大字号串起决策理由、`place_order` 与执行回执。
2. `douyin/02-problem.png`：解释为什么只有收益曲线不构成回测框架。
3. `douyin/03-market-clock.png`：盘前研究、开盘窗口、尾盘窗口的三阶段市场时钟。
4. `douyin/04-event-bus.png`：EventBus、WebSocket 日志与实时消息推送。
5. `douyin/05-execution-path.png`：只读组合、唯一下单入口和环境持仓。
6. `douyin/06-pit-safety.png`：遮罩、时点安全、指纹回放作为防污染细节。
7. `douyin/07-cta.png`：把整套能力收束为交易 Agent 的标准实验室。

全部图片为 1080×1920 的 9:16 竖图。

## 发布操作

- 标题使用 `douyin-title.txt`，正文使用 `douyin-body.md`。
- 置顶 `douyin-pinned-comment.md`，给技术读者明确入口。
- CTA 统一写“GitHub 搜 TraderHarness”。
- 话题控制在 5–6 个，优先技术标签。
