# Quickstart

## Install

=== "pip"

    ```bash
    pip install "traderharness[llm,data,ui]"
    ```

=== "source / Windows"

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

The download is checked against file sizes and SHA-256 hashes before an atomic install to `~/.traderharness/dataset`.

## Run the replay demo

```bash
traderharness demo
```

The cassette contains a real, masked model trajectory and needs no API key. The engine still evaluates it against real local market data.

## Open the web console

```bash
traderharness ui
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The server binds to loopback by default and refuses accidental public exposure unless explicitly enabled.

## Run a provider-backed agent

```powershell
$env:DEEPSEEK_API_KEY="..."
traderharness run `
  --agent trend-breakout `
  --start 2024-03-04 `
  --end 2024-03-29 `
  --mask-entities
```

`trend-breakout` is one of four bundled reference agent cards — alongside `quality-compounder`, `event-hawk`, and
`quant-researcher` — each with a distinct persona and `deepseek-v4-pro` (thinking mode) as the default executor
model. Compare all four head-to-head:

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

Use `--record-replay cassette.jsonl` to create a deterministic, leakage-audited recording.
