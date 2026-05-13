"""Trajectory collector — dual-granularity (day + step level)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class StepRecord:
    """Fine-grained: each tool call + reasoning within a day."""

    date: date
    step: int
    type: str  # "llm_call", "tool_call", "tool_result"
    data: dict = field(default_factory=dict)


@dataclass
class DayRecord:
    """Coarse-grained: RL-style (obs, actions, reward, done)."""

    date: date
    observation: dict = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    reward: float = 0.0
    done: bool = False
    info: dict = field(default_factory=dict)


class TrajectoryCollector:
    """Collects both day-level and step-level trajectory data."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._day_records: list[DayRecord] = []
        self._step_records: list[StepRecord] = []
        self._current_step: int = 0

    def start_day(self, trade_date: date, observation: dict) -> None:
        self._current_step = 0
        self._day_records.append(DayRecord(date=trade_date, observation=observation))

    def record_step(self, trade_date: date, step_type: str, data: dict) -> None:
        self._step_records.append(StepRecord(
            date=trade_date,
            step=self._current_step,
            type=step_type,
            data=data,
        ))
        self._current_step += 1

    def end_day(self, actions: list[dict], reward: float, done: bool = False) -> None:
        if self._day_records:
            rec = self._day_records[-1]
            rec.actions = actions
            rec.reward = reward
            rec.done = done

    @property
    def day_records(self) -> list[DayRecord]:
        return list(self._day_records)

    @property
    def step_records(self) -> list[StepRecord]:
        return list(self._step_records)

    def to_day_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self._day_records:
            rows.append({
                "date": r.date,
                "observation": json.dumps(r.observation, default=str),
                "actions": json.dumps(r.actions, default=str),
                "reward": r.reward,
                "done": r.done,
            })
        return pd.DataFrame(rows)

    def to_step_dataframe(self) -> pd.DataFrame:
        rows = []
        for r in self._step_records:
            rows.append({
                "date": r.date,
                "step": r.step,
                "type": r.type,
                "data": json.dumps(r.data, default=str),
            })
        return pd.DataFrame(rows)

    def export_parquet(self, output_dir: str | Path) -> dict[str, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        day_path = out / f"{self.agent_id}_day_trajectory.parquet"
        step_path = out / f"{self.agent_id}_step_trajectory.parquet"

        day_df = self.to_day_dataframe()
        if not day_df.empty:
            day_df.to_parquet(day_path, index=False)

        step_df = self.to_step_dataframe()
        if not step_df.empty:
            step_df.to_parquet(step_path, index=False)

        return {"day": day_path, "step": step_path}
