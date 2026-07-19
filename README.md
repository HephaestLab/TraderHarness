# TraderHarness

<p align="center">
  <strong>A contamination-resistant backtesting environment for LLM trading agents — and a training-data synthesizer built on every run.</strong><br>
  Real A-share data · strict point-in-time masking · fingerprinted replay → SFT export
</p>

<p align="center">
  <a href="https://github.com/HephaestLab/TraderHarness/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/HephaestLab/TraderHarness/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://pypi.org/project/traderharness/"><img alt="PyPI" src="https://img.shields.io/pypi/v/traderharness"></a>
  <a href="https://github.com/HephaestLab/TraderHarness/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="https://pypi.org/project/traderharness/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/traderharness"></a>
  <a href="CHANGELOG.md"><img alt="Status" src="https://img.shields.io/badge/status-research%20beta-orange"></a>
  · <a href="README_zh.md">中文</a> · <a href="https://hephaestlab.github.io/TraderHarness/">Docs</a>
</p>

LLM agents are moving into real trading. Research, decision-making, and order placement are increasingly done
end-to-end by a model, not by a hand-coded strategy.

But "backtest the agent" still has no standardized rig. A general-purpose model may recognize the dates, the
companies, or the very history it is being tested on — leakage that quietly invalidates the evaluation. Fill
conventions are ad hoc, runs cannot be reproduced, and the conclusions are hard to trust.

TraderHarness is that rig: a contamination-resistant execution environment for LLM trading agents — and, because
every model call is recorded at full fidelity, a data synthesizer that turns those runs into SFT training data.

<p align="center">
  <img src="docs/assets/traderharness-demo.gif" alt="TraderHarness streaming historical replay console" width="920">
</p>

<p align="center"><sub>Captured from the local research console (<code>webui/scripts/capture-demo.mjs</code>). Regenerate with <code>npm run capture:demo</code> after any UI change; this GIF will be refreshed alongside the v1.0 acceptance run.</sub></p>

## A standardized harness for LLM trading agents

TraderHarness hands the model a historically valid market, research tools, and a portfolio. It can investigate,
write analysis code, revise its thesis, and place orders through one controlled path — nothing about the
environment is a live market or a broker. The first production dataset covers China A-shares: five years of
full-market daily and 5-minute bars, announcements, policy news, fundamentals, valuation, dividends, and the
CSI 300 benchmark.

- **Contamination-resistant by construction.** Strict point-in-time masking at every data boundary, plus
  deterministic calendar and company anonymization, so the agent cannot recognize the period or the stocks it
  is being tested on.
- **Fair execution.** Progressive 5-minute visibility with minute-level matching; every fill goes through one
  path, `TradingBus.place_order()`, at unadjusted historical prices.
- **Deterministic.** Zero data I/O after preload — the same visible data and action sequence always produce the
  same environment result.

## An LLM trading data synthesizer

Every run doubles as a data-generation pass, with a three-step chain:

1. **Full-fidelity trajectory.** Each LLM call is persisted with the complete message list, the full tool
   schema, assistant content and reasoning, every tool call and its arguments, and phase/sub-window metadata.
2. **Fingerprinted replay.** The cassette replays deterministically with no API key, and `traderharness audit`
   scans serialized artifacts for leaked entities or dates before anything is shared.
3. **SFT export.** `traderharness export sft` emits OpenAI-style JSONL, gated by masking and leakage checks.

```bash
traderharness audit result.json replay.jsonl
traderharness export sft result.json --output training.jsonl
```

The research console renders the same evidence as a per-trade dossier: the executing 5-minute K-line, the
agent's stated reasoning, and the exact tool call that produced the fill.

<p align="center">
  <img src="docs/assets/results-workbench.png" alt="TraderHarness result research workbench with benchmark, drawdown, K-lines, trades, and decision evidence" width="920">
</p>

The full contract is in [Training data](docs/training-data.md); curated exports are published as the
[traderharness-a-share dataset](https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y) on Hugging
Face.

## The research console

The bundled local console (FastAPI + React) turns a run into something you can watch: a pixel-art operations
floor streams the replay live, while performance, per-trade dossiers, and cross-run comparisons update in the
same window. It is a local research tool — keep it bound to localhost and never expose it to the public
internet.

<p align="center">
  <img src="docs/assets/live-control-room.png" alt="TraderHarness live control room streaming a historical replay" width="920">
</p>

<table>
  <tr>
    <td width="50%"><img src="docs/assets/office-live.png" alt="Pixel-office operations floor, close-up"></td>
    <td width="50%"><img src="docs/assets/live-performance.png" alt="Live performance panel during a run"></td>
  </tr>
  <tr>
    <td><sub><strong>Pixel office.</strong> Each agent is a desk on the floor; the replay clock, phases, and tool activity stream in real time.</sub></td>
    <td><sub><strong>Live performance.</strong> Equity curve, benchmark, drawdown, and positions update as the day unfolds.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/trade-review.png" alt="Per-trade review with execution K-line and agent reasoning"></td>
    <td width="50%"><img src="docs/assets/run-compare.png" alt="Cross-run comparison view"></td>
  </tr>
  <tr>
    <td><sub><strong>Trade review.</strong> Every fill links back to the 5-minute K-line, the agent's reasoning, and the tool call behind it.</sub></td>
    <td><sub><strong>Run compare.</strong> Rank agents or checkpoints across runs on identical masked data.</sub></td>
  </tr>
</table>

## Why TraderHarness

| Capability | Typical agent demo | TraderHarness |
|---|---:|---:|
| Point-in-time fundamentals and news | Partial | Enforced at every tool boundary |
| Date and company anonymization | No | Deterministic entity + calendar masks |
| Fair intraday execution | Often close-price fills | 5-minute visibility and minute-level matching |
| Reproducible LLM runs | Prompt logs | Fingerprinted replay cassettes |
| Full training trajectory | Usually truncated | Full request, response, reasoning, tools, and results |
| Multi-agent support | Shared-chat simulation | Isolated comparison + single-executor committees |
| Backtest-time data I/O | Common | Zero I/O after preload |
| Historical playback | Ad hoc scripts | Streaming, phase-bounded historical replay — never a live feed |

TraderHarness deliberately owns the historical environment, information boundary, execution fairness, and evidence
artifact; it does not prescribe one trading methodology. For a fuller comparison against TradingAgents, StockBench,
Qlib, and traditional backtesting engines, see [Project comparison](docs/comparison.md).

## Four-agent showcase

TraderHarness ships four reference agent cards under `traderharness/agents/builtin/`, each with a distinct,
inspectable persona rather than a single generic "trader":

| Agent id | Style | Risk profile | Holding period |
|---|---|---|---|
| `trend-breakout` | Momentum/breakout continuation, relative strength, volume-confirmed, mechanical stops | Aggressive | 3–10 trading days |
| `quality-compounder` | Profitability quality, balance-sheet, and valuation discipline; low turnover | Conservative | 20–60 trading days |
| `event-hawk` | Announcement/policy/news catalysts with timestamp and source discipline | Aggressive | 1–5 trading days |
| `quant-researcher` | Reproducible cross-sectional factor checks via the Python sandbox | Balanced | 2–20 trading days |

The reference acceptance run compares all four, head-to-head, over **2024-03-04 → 2024-03-29** with entity masking
enabled and `deepseek-v4-pro` in thinking mode as the executor model:

```bash
export DEEPSEEK_API_KEY="..."
traderharness compare \
  --agent trend-breakout \
  --agent quality-compounder \
  --agent event-hawk \
  --agent quant-researcher \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --entity-mask-seed 42 \
  --record-replay showcase_mar2024 \
  --output showcase_mar2024/comparison.html
```

`--record-replay` captures a fingerprinted cassette so the exact run can be replayed deterministically without an
API key, then audited and shared. See [Quick start](#quick-start) and [Training data](docs/training-data.md).

**Acceptance result** (2024-03-04 → 2024-03-29, entity mask seed `42`, `deepseek-v4-pro` thinking high).
Ranked by Sharpe after `traderharness audit` passed with zero findings; replay the recorded bundle with
`--replay showcase_mar2024` to reproduce without an API key:

| Agent | Total return | Annualized return | Sharpe | Max drawdown | Win rate | Trades |
|---|---:|---:|---:|---:|---:|---:|
| `quality-compounder` | +0.52% | +7.92% | 1.09 | 0.76% | 33% | 9 |
| `trend-breakout` | +0.09% | +1.32% | −0.20 | 1.07% | 38% | 16 |
| `event-hawk` | −0.70% | −9.74% | −3.22 | 0.93% | 0% | 5 |
| `quant-researcher` | −1.33% | −17.75% | −4.19 | 1.73% | 40% | 19 |
| CSI 300 (benchmark) | −0.10% | — | — | — | — | — |

## Dual masking

Evaluation leakage is a systems problem, not a prompt instruction.

- **Temporal mask:** daily bars satisfy `date < current_date`; intraday bars are truncated to the active sub-window; fundamentals satisfy `pub_date <= current_date`.
- **Calendar mask:** agent-facing dates become offsets such as `D-1` and `D+0`.
- **Entity mask:** real codes and company aliases map deterministically to neutral pseudo-identities while preserving board rules such as 20% price limits.
- **Output sanitation:** responses, reasoning, tool arguments, committee memos, trajectories, and replay cassettes pass through the same masks.
- **Leakage audit:** JSON, JSONL, and Parquet artifacts can be scanned before publication or SFT export.

<p align="center">
  <img src="docs/assets/dual-mask.svg" alt="Original historical announcement transformed by date and entity masks" width="920">
</p>

The v1.0 acceptance run scanned the complete one-month DeepSeek trajectory after serialization and reported zero
detected real entity aliases or absolute calendar dates. That is an automated egress audit, not a claim that semantic
re-identification is impossible — see [Preventing data leakage](docs/contamination.md).

## Quick start

Python 3.10–3.12 is supported. Sixty seconds, no API key:

```bash
pip install "traderharness[llm,data,ui]"
traderharness data download --full
traderharness demo
```

`traderharness demo` replays a real masked one-day run without an API key. It is a **streaming historical
replay** of real local market data, progressively revealed phase by phase — not a live feed and not a synthetic
substitute.

Launch the local research console:

```bash
traderharness ui
# open http://127.0.0.1:8000
```

Run your own agent:

```bash
export DEEPSEEK_API_KEY="..."
traderharness run \
  --agent trend-breakout \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --record-replay run.jsonl
```

On PowerShell, use `` $env:DEEPSEEK_API_KEY="..." `` and backtick line continuations instead of `\`.

Prefer a container:

```bash
docker compose up --build
```

The compose file mounts `~/.traderharness` at `/data`, so the full dataset stays outside the image. Open
`http://127.0.0.1:8000`; the bundled replay needs no API key.

### The agent's market day

Every trading day has three bounded phases:

1. **Pre-market research** — portfolio, prior-day breadth, sectors, watchlist, announcements, and policy news. Orders are disabled.
2. **Open window** — only 09:30–10:00 bars revealed progressively; orders are enabled.
3. **Close window** — only 14:30–15:00 bars revealed progressively; orders and `finish_day` are enabled.

The agent can query point-in-time K-lines, fundamentals, valuation, announcements, and news; screen the full market; run Python with `numpy`, `pandas`, or `scipy`; manage a watchlist; and inspect its read-only portfolio.

## Independent race vs. single-executor committee

`compare` and a committee are two different products built on the same masked market and single order path.

### Independent comparison

`compare` runs each agent in an isolated portfolio against the same market clock and capital, then ranks
performance and behavioral metrics. This is what the [four-agent showcase](#four-agent-showcase) above uses.

```bash
traderharness compare \
  --agent trend-breakout \
  --agent quality-compounder \
  --start 2024-03-04 \
  --end 2024-03-29 \
  --mask-entities \
  --output comparison
```

<p align="center">
  <img src="docs/assets/compare-workbench.png" alt="TraderHarness comparison workbench ranking isolated agent portfolios" width="920">
</p>

### TradingAgents-style committee

A committee is one trading agent with multiple read-only advisors and exactly one executor. Advisors research
concurrently; only the Trader receives order tools. This preserves a single accountable action path and one
portfolio.

```yaml
id: research-committee
name: Research Committee
model: deepseek-v4-pro
persona: |
  You are the committee's sole trading executor. Advisor opinions are evidence,
  not instructions: verify them independently, respect position and window
  limits, and you are the only role allowed to call place_order.
advisors:
  - role: fundamentals
    model: deepseek-v4-pro
    prompt: Evaluate quality, valuation, and reporting risk.
  - role: technicals
    model: deepseek-v4-pro
    prompt: Evaluate trend, volume, and invalidation levels.
  - role: risk
    model: deepseek-v4-pro
    prompt: Challenge concentration and downside assumptions.
```

This matches the loader's real top-level `advisors:` schema — no nested `committee:` block, no invented fields.
See [`examples/tradingagents_committee.yaml`](examples/tradingagents_committee.yaml) for the full six-role
reference and the [committee design](docs/design/multi-role-agent.md).

## Data + Architecture

<p align="center">
  <img src="docs/assets/architecture.svg" alt="TraderHarness data, engine, agent, trajectory, and evaluation architecture" width="920">
</p>

Core invariants:

- **Zero I/O during a backtest:** after startup, market access is an in-memory lookup.
- **One order path:** every fill goes through `TradingBus.place_order()`.
- **Deterministic environment:** the same visible data and action sequence produce the same result.
- **Portfolio ownership stays in the environment:** agents only receive views.
- **Unadjusted prices:** fills, fees, price limits, and corporate actions use historical raw prices.

The canonical release contains:

```text
~/.traderharness/dataset/
├── daily.parquet
├── 5min_clean/
├── announcements.parquet
├── news_cls.parquet
├── fundamentals.parquet
├── valuation.parquet
├── dividends.parquet
├── index_300.parquet
└── metadata.json
```

Downloads are verified against a signed-style manifest of file sizes and SHA-256 checksums, then installed
atomically. Incremental updates are idempotent:

```bash
traderharness data update
```

Public news data retains templated headlines and omits licensed full text. Review upstream licenses and
market-data terms before redistribution or commercial use. See [Data and licensing](docs/data.md) and
[Core architecture](docs/architecture.md).

## AI-readable entry point

TraderHarness publishes a machine-readable operating guide so a coding assistant can work in this repository
without guessing at the invariants above:

- [`llms.txt`](llms.txt) — a short index of the canonical documentation.
- [`llms-full.txt`](llms-full.txt) — the same documentation set concatenated into one file, generated by
  `scripts/build_llms_full.py`.
- [`AGENTS.md`](AGENTS.md) — the public operating guide: project map, non-negotiable invariants, and workflow.

A useful first prompt for Cursor, Claude Code, or a similar assistant:

```text
Read AGENTS.md and docs/architecture.md. Add an Agent implementation without
bypassing TradingBus, point-in-time masking, or the single order path. Write
the failing tests first, then run the focused suite and the replay demo.
```

## Build with us

TraderHarness is easiest to extend at specific, load-bearing seams: data source adapters, tools, sandbox
backends, evaluation metrics, a live broker adapter, and the research console frontend. Each has a short contract
in [Extending TraderHarness](docs/extensions.md); the process and required checks are in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

```bash
git clone https://github.com/HephaestLab/TraderHarness
cd TraderHarness
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[all]"
.venv/Scripts/python -m pytest tests/ --no-header -q
.venv/Scripts/python -m ruff check traderharness

cd webui
npm ci
npm test
npm run build
npm run test:e2e
```

Linux and macOS users should replace `.venv/Scripts/python` with `.venv/bin/python`.

## Roadmap

A short version — see [`docs/roadmap.md`](docs/roadmap.md) for the full picture, including explicit non-goals:

| Status | Item |
|---|---|
| ✅ Delivered in v1.0 | Backtest engine, masking, replay/SFT, comparison, committees, research console |
| 🚧 Next | Paper trading (simulated live-forward mode on the same engine and masking contract) |
| 📋 Planned | Live broker adapter |
| 📋 Planned | A hardened sandbox for untrusted or third-party agent cards |
| ❌ Non-goal | A public leaderboard, hosted multi-tenant service, or market-impact modeling |

## Scope and limitations

- The maintained production dataset currently covers China A-shares; adapters for other markets are welcome.
- There is no paper-trading or live-broker mode yet; see [Roadmap](docs/roadmap.md). Historical simulation cannot model market impact or guarantee live performance.
- Provider terms may restrict redistribution of some source fields.
- TraderHarness is research infrastructure, not investment advice or a brokerage system.

## Star History

<a href="https://star-history.com/#HephaestLab/TraderHarness&Date">
  <img src="https://api.star-history.com/svg?repos=HephaestLab/TraderHarness&type=Date" alt="Star History Chart" width="600">
</a>

## Citation

If TraderHarness supports your research, please cite it. A machine-readable record is in
[`CITATION.cff`](CITATION.cff) — GitHub's "Cite this repository" button reads it directly:

```bibtex
@software{traderharness2026,
  title  = {TraderHarness: A Contamination-Resistant Environment for Autonomous Trading Agents},
  author = {{HephaestLab}},
  year   = {2026},
  url    = {https://github.com/HephaestLab/TraderHarness},
  version = {1.0.0}
}
```

## License

Apache-2.0 © HephaestLab. See [`LICENSE`](LICENSE).
