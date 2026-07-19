# 快速上手

## 安装

=== "pip"

    ```bash
    pip install "traderharness[llm,data,ui]"
    ```

=== "源码 / Windows"

    ```powershell
    git clone https://github.com/HephaestLab/TraderHarness
    cd TraderHarness
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -e ".[all]"
    ```

=== "Docker"

    ```bash
    docker compose up --build
    ```

## 安装行情数据

```bash
traderharness data download --full
```

下载完成后会按发布清单逐项校验文件大小与 SHA-256，再原子安装到 `~/.traderharness/dataset`。

## 跑免密回放演示

```bash
traderharness demo
```

盒带里是一段真实、经过掩码的模型轨迹，不需要 API key；引擎仍然会用本地真实行情对它进行评测。

## 打开 Web 控制台

```bash
traderharness ui
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。服务默认只绑定回环地址，除非显式开启，否则拒绝意外的公网暴露。

![回测控制室：像素办公室、实时净值与决策事件流](assets/live-control-room.png)

*回测控制室：左侧像素办公室里每个 Agent 各司其职，右侧实时净值曲线与决策事件流同步滚动。*

## 跑一个真实的模型 Agent

```powershell
$env:DEEPSEEK_API_KEY="..."
traderharness run `
  --agent trend-breakout `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities
```

`trend-breakout` 是内置的参考 Agent 卡片之一——与 `quality-compounder`、`event-hawk`、`quant-researcher` 并列，各自拥有独立人设，默认执行模型为 `deepseek-v4-pro`（thinking 深度推理模式）。把四位选手放进同一市场时钟正面对决：

```powershell
traderharness compare `
  --agent trend-breakout `
  --agent quality-compounder `
  --agent event-hawk `
  --agent quant-researcher `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities `
  --output showcase
```

加 `--record-replay cassette.jsonl` 可以把整段运行录成确定性的、可过泄漏审计的回放盒带。

![多 Agent 对比工作台](assets/compare-workbench.png)

*对比工作台：同一市场时钟下多个 Agent 的权益曲线、风险与行为指标横向排名。*
