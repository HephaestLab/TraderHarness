"""Single source of truth for TraderHarness application directories.

All persistent state lives under one home directory:

    ~/.traderharness/
    ├── dataset/     # full-market parquet dataset
    ├── datasets/    # downloadable sample datasets
    ├── results/     # backtest results
    ├── agents/      # agent cards
    └── llm_cache/   # local LLM response cache

Override the location with the ``TRADERHARNESS_HOME`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_home() -> Path:
    env = os.environ.get("TRADERHARNESS_HOME")
    return Path(env) if env else Path.home() / ".traderharness"


def dataset_dir() -> Path:
    return get_home() / "dataset"


def datasets_dir() -> Path:
    return get_home() / "datasets"


def results_dir() -> Path:
    return get_home() / "results"


def agents_dir() -> Path:
    return get_home() / "agents"


def llm_cache_dir() -> Path:
    return get_home() / "llm_cache"


def prompt_audit_cache_dir() -> Path:
    return get_home() / "prompt_audit_cache"
