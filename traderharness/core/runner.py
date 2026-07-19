"""Backtest runner — launches backtest in a background thread with live event feed.

Usage from Streamlit:
    from traderharness.core.runner import BacktestRunner

    runner = BacktestRunner(config)
    runner.start()

    # In render loop:
    for event in runner.feed:
        st.write(event)
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from traderharness.core.engine import BacktestEngine, EngineConfig, EngineResult
from traderharness.core.live_feed import LiveFeed


@dataclass
class RunConfig:
    start_date: date
    end_date: date
    initial_cash: float = 1_000_000
    agents: list[dict[str, Any]] | None = None
    mask_entities: bool = True
    entity_mask_seed: int = 0
    replay_path: Path | None = None


class BacktestRunner:
    """Wraps BacktestEngine in a background thread with LiveFeed for UI consumption."""

    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._feed = LiveFeed()
        self._thread: threading.Thread | None = None
        self._result: EngineResult | None = None
        self._error: Exception | None = None
        self._cancel_event = threading.Event()
        self._result_path = None
        self._replay_player = None
        self._replay_bundle_player = None
        from traderharness.results import generate_result_filename

        self._result_filename = generate_result_filename()

    @property
    def feed(self) -> LiveFeed:
        return self._feed

    @property
    def result(self) -> EngineResult | None:
        return self._result

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def result_path(self):
        return self._result_path

    def start(self) -> None:
        if self.running:
            return
        from traderharness.results import save_pending

        save_pending(self._result_filename, self._persisted_config())
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request cooperative cancellation after the current trading day."""
        self._cancel_event.set()

    def _run(self) -> None:
        try:
            self._result = asyncio.run(self._async_run())
        except Exception as e:
            self._error = e
            from traderharness.results import save_failed

            self._result_path = save_failed(
                self._result_filename,
                str(e),
                self._persisted_config(),
            )
            self._feed.push("error", message=str(e))
        finally:
            if not self._feed.done:
                self._feed.push("run_end", trading_days=0)

    async def _async_run(self) -> EngineResult:
        engine_config = EngineConfig(
            initial_cash=Decimal(str(self._config.initial_cash)),
            mask_entities=self._config.mask_entities,
            entity_mask_seed=self._config.entity_mask_seed,
            cancel_check=self._cancel_event.is_set,
        )
        engine = BacktestEngine(config=engine_config, event_bus=self._feed.event_bus)

        agents = self._build_agents()
        self._feed.push("loading_data", message="Loading market data...")

        result = await engine.run(
            agents=agents,
            start_date=self._config.start_date,
            end_date=self._config.end_date,
        )
        if self._replay_player is not None:
            self._replay_player.assert_consumed()
        if self._replay_bundle_player is not None:
            self._replay_bundle_player.assert_all_consumed()
        from traderharness.metrics.benchmark import load_csi300_curve
        from traderharness.results import save_complete
        from traderharness.run_results import build_result_document

        initial_cash = Decimal(str(self._config.initial_cash))
        benchmark = load_csi300_curve(
            self._config.start_date,
            self._config.end_date,
            initial_cash,
        )
        document = build_result_document(
            result,
            initial_cash=initial_cash,
            config=self._persisted_config(),
            benchmark_curve=benchmark,
            entity_masker=engine._entity_masker,
        )
        status = "cancelled" if self._cancel_event.is_set() else "done"
        self._result_path = save_complete(
            self._result_filename,
            document,
            status=status,
        )
        return result

    def _build_agents(self) -> list:
        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent
        from traderharness.trajectory.bundle import ScopedReplayPlayer, is_bundle_path
        from traderharness.trajectory.replay import ReplayPlayer

        agent_configs = self._config.agents or [{"id": "default", "name": "Default Agent"}]
        replay_path = self._config.replay_path

        replay_player: ReplayPlayer | None = None
        bundle_player: ScopedReplayPlayer | None = None
        prompt_contract_version: str | None = None
        if replay_path is not None:
            if is_bundle_path(replay_path):
                # A Replay Bundle scopes one cassette per agent id, so any
                # number of agents may be replayed concurrently.
                bundle_player = ScopedReplayPlayer(replay_path)
                prompt_contract_version = bundle_player.manifest.prompt_contract_version
            else:
                # A v1 single-file cassette has no scoping, so it can only
                # stand in for exactly one executor agent's call sequence.
                if len(agent_configs) != 1:
                    raise ValueError("Replay mode supports exactly one executor agent")
                replay_player = ReplayPlayer(replay_path)
                # Replay must rebuild the exact system prompt that was
                # recorded, so the cassette's contract version wins over the
                # legacy player-presence heuristic (see resolve_decision_contract).
                prompt_contract_version = replay_player.prompt_contract_version
        self._replay_player = replay_player
        self._replay_bundle_player = bundle_player
        agents = []

        for cfg in agent_configs:
            agent_id = cfg.get("id", "agent_0")
            player = bundle_player.scope(agent_id) if bundle_player is not None else replay_player
            llm_client = LLMClient(
                model=cfg.get("model") or "deepseek-chat",
                api_key="replay" if player is not None else None,
                cache_enabled=False,
                replay_player=player,
            )
            agent = ToolAgent(
                agent_id=agent_id,
                name=cfg.get("name", "Agent"),
                llm_client=llm_client,
                persona=cfg.get("persona", "你是一位经验丰富的主观交易员。"),
                initial_cash=Decimal(str(self._config.initial_cash)),
                max_positions=cfg.get("max_positions", 4),
                max_position_pct=cfg.get("max_position_pct", 25.0),
                allowed_tools=cfg.get("allowed_tools"),
                event_bus=self._feed.event_bus,
                prompt_contract_version=prompt_contract_version,
            )
            agents.append(agent)

        return agents

    def _persisted_config(self) -> dict[str, Any]:
        return {
            "start_date": str(self._config.start_date),
            "end_date": str(self._config.end_date),
            "initial_cash": self._config.initial_cash,
            "agents": [config.get("id") for config in (self._config.agents or [])],
            "mask_entities": self._config.mask_entities,
            "entity_mask_seed": self._config.entity_mask_seed,
            "replay": self._config.replay_path is not None,
        }
