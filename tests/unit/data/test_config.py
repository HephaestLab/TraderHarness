"""Tests for YAML config loading."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from traderharness.config.env_config import EnvYAMLConfig, AgentYAMLConfig


@pytest.fixture
def env_yaml(tmp_path):
    content = """
backtest:
  start: "2024-03-01"
  end: "2024-06-30"
  initial_cash: 500000
  warmup_days: 60
  dataset: "a50-2024"
data_dir: "./data"
cache_enabled: true
log_level: "DEBUG"
"""
    p = tmp_path / "env.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def agent_yaml(tmp_path):
    content = """
name: "value_investor"
model: "deepseek-chat"
persona: "You are a value investor focusing on fundamentals."
tools:
  - get_kline
  - get_financials
  - buy
  - sell
temperature: 0.3
max_tokens_per_day: 50000
"""
    p = tmp_path / "agent.yaml"
    p.write_text(content)
    return p


class TestEnvYAMLConfig:
    def test_load(self, env_yaml):
        cfg = EnvYAMLConfig.from_yaml(env_yaml)
        assert cfg.backtest.start == date(2024, 3, 1)
        assert cfg.backtest.end == date(2024, 6, 30)
        assert cfg.backtest.initial_cash == Decimal("500000")
        assert cfg.backtest.warmup_days == 60
        assert cfg.data_dir == "./data"
        assert cfg.log_level == "DEBUG"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            EnvYAMLConfig.from_yaml("/nonexistent.yaml")


class TestAgentYAMLConfig:
    def test_load(self, agent_yaml):
        cfg = AgentYAMLConfig.from_yaml(agent_yaml)
        assert cfg.name == "value_investor"
        assert cfg.model == "deepseek-chat"
        assert "get_kline" in cfg.tools
        assert cfg.temperature == 0.3
        assert cfg.max_tokens_per_day == 50000

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            AgentYAMLConfig.from_yaml("/nonexistent.yaml")
