# TraderHarness compared with adjacent projects

TraderHarness is an environment and evidence harness. It can host different agent architectures, but it does not
prescribe their investment methodology.

| Project | Primary responsibility | Native decision unit | What an integration still needs |
|---|---|---|---|
| **TraderHarness** | Historically valid market, execution, portfolio, evaluation, replay, and training trajectories | Autonomous agent, isolated comparison, or one-executor committee | An agent persona or external framework |
| **TradingAgents** | Multi-role analyst, debate, risk, and trader workflow | Prescribed role graph | A strict market simulator and order contract for benchmark use |
| **StockBench** | Standardized stock-reasoning benchmark tasks | Benchmark task/prediction | A persistent portfolio environment for autonomous tool use |
| **Qlib** | Quantitative data, model, experiment, and strategy research | ML model or coded strategy | An LLM-native tool loop and contamination-resistant language egress |
| **Backtrader / vn.py** | Strategy execution and trading infrastructure | Coded strategy | The autonomous LLM research loop, masking, and trajectory contract |

## Independent agents versus a committee

`traderharness compare` is a race: every agent has its own cash, positions, memory, and portfolio. All agents see the
same market clock and are scored independently.

A committee is one contestant: read-only advisors may research concurrently, but one Trader is the only role that
receives order tools. This produces one accountable action path and one portfolio. See
[Multi-role committees](design/multi-role-agent.md).

## Bring your own framework

An external LangGraph, TradingAgents, or custom orchestrator should return its final decision through the public agent
protocol. Market reads and orders still pass through `TradingBus`, so the framework inherits the same temporal mask,
entity/date anonymization, progressive intraday visibility, and matching rules.
