# CLI 与本地 API 参考

## 核心 CLI

```text
traderharness run       运行单个 Agent
traderharness compare   在同一市场时钟下隔离运行多个 Agent
traderharness demo      免密回放内置的掩码运行
traderharness ui        启动本地 FastAPI + React 控制台
traderharness audit     扫描工件中的实体与日历泄漏
traderharness export    把轨迹转换为 SFT JSONL
traderharness data      下载、更新与检查数据集
```

各命令的具体参数以 `traderharness <command> --help` 为准。

## Agent 协议

自定义 Agent 实现 `traderharness.agents.protocol` 中的公开协议，分别在盘前、开盘窗口与尾盘窗口收到环境控制的上下文。只读顾问可以组合在单一执行者之后，详见[多角色委员会](design/multi-role-agent.md)。

## 本地 HTTP API

`traderharness ui` 提供：

- `GET /api/status` — 数据集、供应商与本地安全状态；
- `GET/POST /api/agents` — Agent 卡片集合；
- `GET/PUT/DELETE /api/agents/{id}` — 单张 Agent 卡片；
- `POST /api/runs` — 启动回测；
- `GET/DELETE /api/runs/{id}` — 查看或取消运行；
- `WS /api/runs/{id}/events` — 可重连的序号化事件日志；
- `GET /api/results` — 已落盘结果摘要；
- `GET /api/results/{file}` — 完整工件；
- `GET /api/results/{file}/analysis` — 归一化的 UI 研究档案；
- `POST /api/demo` — 启动内置回放；
- `GET /api/health` — 进程健康检查。

HTTP API 是本地工具，不是带鉴权的公共服务。请保持默认的 localhost 绑定。
