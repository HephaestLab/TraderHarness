# FinHarness

A realistic LLM-native harness for building, testing, and benchmarking autonomous trading agents.

## Install

```bash
pip install finharness
```

## Quick Start

```python
from finharness import TradingEnv

env = TradingEnv(dataset="a50-2024")
result = env.run(agent)
print(result.metrics)
```
