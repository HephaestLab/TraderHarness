---
seo_title: TraderHarness Quickstart — Replay an LLM Trading Agent in Three Steps
description: Install TraderHarness, download five years of China A-share data, run a no-key replay, open the local console, and compare isolated LLM trading agents.
lang: en
---

# Quickstart

## Install

=== "pip"

    ```bash
    pip install "traderharness[llm,data,ui]"
    ```

=== "Source / Windows"

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

## Install market data

```bash
traderharness data download --full
```

The installer verifies file size and SHA-256 against the release manifest before atomically replacing `~/.traderharness/dataset`.

## Run the no-key replay

```bash
traderharness demo
```

The cassette contains a recorded masked LLM trajectory. No API key is required; the engine still re-evaluates it against local canonical market data.

## Open the research console

```bash
traderharness ui
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The service binds to loopback by default and rejects accidental public exposure unless explicitly enabled.

![TraderHarness live control room](https://hephaestlab.github.io/TraderHarness/assets/live-control-room.png)

## Run a fresh model agent

```powershell
$env:DEEPSEEK_API_KEY="..."
traderharness run `
  --agent trend-breakout `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities
```

Compare the four built-in reference cards under one market clock and isolated portfolios:

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

Add `--record-replay cassette.jsonl` to save a deterministic, leakage-auditable replay cassette.
