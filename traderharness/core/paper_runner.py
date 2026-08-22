"""Daily paper-trading runner driven by point-in-time minute snapshots."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from traderharness.core.engine import BacktestEngine, EngineConfig
from traderharness.core.live_feed import LiveFeed
from traderharness.data.market_data_manager import MarketDataManager

logger = logging.getLogger(__name__)

PHASE_CUTOFFS = {
    "open_1": time(9, 50),
    "open_2": time(10, 0),
    "close_1": time(14, 50),
    "close_2": time(15, 0),
}

PHASE_WINDOWS = {
    "open_1": (time(9, 30), time(9, 50)),
    "open_2": (time(9, 50), time(10, 0)),
    "close_1": (time(10, 0), time(14, 50)),
    "close_2": (time(14, 50), time(15, 0)),
}


class _AgentEventBus:
    """Inject Agent identity into loop/tool events before the shared live feed."""

    def __init__(self, target, *, agent_id: str, agent_name: str) -> None:
        self._target = target
        self._agent_id = agent_id
        self._agent_name = agent_name

    def emit(self, event: str, **kwargs: Any) -> None:
        payload = dict(kwargs)
        payload.setdefault("agent_id", self._agent_id)
        payload.setdefault("agent_name", self._agent_name)
        self._target.emit(event, **payload)


def build_market_pulse(
    frame: pd.DataFrame,
    *,
    cutoff: datetime,
    codes: list[str],
    names: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Summarize visible minute bars into a compact human-facing market pulse."""
    names = names or {}
    if frame.empty or "datetime" not in frame.columns:
        return {"advancers": 0, "decliners": 0, "unchanged": 0, "items": []}
    work = frame.copy()
    work["stock_code"] = work["stock_code"].astype(str).str.zfill(6)
    work["datetime"] = pd.to_datetime(work["datetime"], errors="coerce")
    work = work[
        work["stock_code"].isin({str(code).zfill(6) for code in codes})
        & (work["datetime"] <= pd.Timestamp(cutoff).tz_localize(None))
    ].sort_values(["stock_code", "datetime"])
    items: list[dict[str, Any]] = []
    for code, bars in work.groupby("stock_code", sort=True):
        bars = bars.dropna(subset=["open", "close"])
        if bars.empty:
            continue
        first_open = float(bars.iloc[0]["open"])
        last = bars.iloc[-1]
        last_price = float(last["close"])
        change_pct = (last_price / first_open - 1) * 100 if first_open else 0.0
        volumes = pd.to_numeric(bars.get("volume"), errors="coerce").fillna(0)
        baseline = float(volumes.iloc[:-1].tail(5).median()) if len(volumes) > 1 else 0.0
        volume_ratio = float(volumes.iloc[-1] / baseline) if baseline > 0 else 0.0
        importance = "high" if abs(change_pct) >= 3 or volume_ratio >= 3 else (
            "medium" if abs(change_pct) >= 1.5 or volume_ratio >= 1.8 else "normal"
        )
        items.append(
            {
                "stock_code": code,
                "stock_name": names.get(code, code),
                "last_price": round(last_price, 3),
                "change_pct": round(change_pct, 2),
                "volume_ratio": round(volume_ratio, 2),
                "importance": importance,
                "as_of": str(last["datetime"]),
            }
        )
    items.sort(
        key=lambda item: (
            item["importance"] == "high",
            abs(item["change_pct"]),
            item["volume_ratio"],
        ),
        reverse=True,
    )
    return {
        "advancers": sum(item["change_pct"] > 0 for item in items),
        "decliners": sum(item["change_pct"] < 0 for item in items),
        "unchanged": sum(item["change_pct"] == 0 for item in items),
        "items": items[:8],
    }


def select_news_broadcasts(
    news: pd.DataFrame,
    announcements: pd.DataFrame,
    *,
    target_codes: set[str],
    window_start: datetime,
    window_end: datetime,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Select related announcements and important flashes for the arena tape."""
    candidates: list[tuple[int, datetime, dict[str, Any]]] = []
    if not announcements.empty and {
        "stock_code",
        "title",
        "announcement_time",
    }.issubset(announcements.columns):
        times = pd.to_datetime(announcements["announcement_time"], errors="coerce")
        codes = announcements["stock_code"].astype(str).str.zfill(6)
        mask = codes.isin({str(code).zfill(6) for code in target_codes}) & times.between(
            window_start, window_end, inclusive="left"
        )
        for index, row in announcements[mask].iterrows():
            when = pd.Timestamp(times.loc[index]).to_pydatetime()
            code = str(row["stock_code"]).zfill(6)
            candidates.append(
                (
                    3,
                    when,
                    {
                        "source_id": f"announcement:{code}:{when.isoformat()}:{row['title']}",
                        "kind": "announcement",
                        "importance": "high",
                        "time": when.isoformat(),
                        "title": str(row["title"]),
                        "content": str(row["title"]),
                        "stock_code": code,
                        "tags": ["自选/持仓公告"],
                    },
                )
            )
    if not news.empty and {"display_time", "content"}.issubset(news.columns):
        times = pd.to_datetime(news["display_time"], errors="coerce")
        mask = times.between(window_start, window_end, inclusive="left")
        for index, row in news[mask].iterrows():
            when = pd.Timestamp(times.loc[index]).to_pydatetime()
            content = str(row.get("content") or row.get("title") or "").strip()
            if not content:
                continue
            level = str(row.get("level") or "").upper()
            policy = any(
                keyword in content
                for keyword in ("央行", "证监会", "国务院", "财政部", "发改委", "人民银行")
            )
            score = 2 if level in {"A", "B", "P0", "P1", "1", "2"} or policy else 1
            importance = "high" if score == 2 else "normal"
            source_id = str(row.get("id") or f"flash:{when.isoformat()}:{content[:40]}")
            tags = [tag for tag in str(row.get("tags") or "").split(",") if tag]
            candidates.append(
                (
                    score,
                    when,
                    {
                        "source_id": source_id,
                        "kind": "flash",
                        "importance": importance,
                        "time": when.isoformat(),
                        "title": str(row.get("title") or content[:46]),
                        "content": content[:240],
                        "stock_code": None,
                        "tags": tags[:4],
                    },
                )
            )
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item for _, _, item in candidates[:max_items]]


def aggregate_one_minute_to_five(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    """Aggregate only completed A-share five-minute buckets through ``cutoff``."""
    columns = [
        "stock_code",
        "date",
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    work = frame.copy()
    work["datetime"] = pd.to_datetime(work["datetime"])
    work = work[work["datetime"] <= pd.Timestamp(cutoff)]
    if work.empty:
        return pd.DataFrame(columns=columns)
    minute = work["datetime"].dt.hour * 60 + work["datetime"].dt.minute
    morning = minute.between(9 * 60 + 31, 11 * 60 + 30)
    afternoon = minute.between(13 * 60 + 1, 15 * 60)
    work = work[morning | afternoon].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)
    minute = work["datetime"].dt.hour * 60 + work["datetime"].dt.minute
    session_start = pd.Series(9 * 60 + 30, index=work.index)
    session_start.loc[minute >= 12 * 60] = 13 * 60
    bucket_end = session_start + ((minute - session_start + 4) // 5) * 5
    work["bucket_end"] = pd.to_datetime(work["datetime"].dt.date.astype(str)) + pd.to_timedelta(
        bucket_end, unit="m"
    )
    completed = work[work["bucket_end"] <= pd.Timestamp(cutoff)]
    if completed.empty:
        return pd.DataFrame(columns=columns)
    grouped = (
        completed.sort_values("datetime")
        .groupby(["stock_code", "bucket_end"], as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        )
        .rename(columns={"bucket_end": "datetime"})
    )
    grouped["date"] = grouped["datetime"].dt.date
    return grouped[columns].sort_values(["stock_code", "datetime"]).reset_index(drop=True)


@dataclass(frozen=True)
class PaperRunConfig:
    session_id: str
    agents: list[dict[str, Any]]
    session_date: date
    initial_cash: float = 1_000_000
    mode: str = "live"
    poll_seconds: int = 60
    max_attention_codes: int = 8
    dataset_root: Path | None = None
    artifact_root: Path | None = None


class PaperSnapshotProvider:
    """Load daily history only; intraday visibility is populated by barriers."""

    def __init__(self, root: Path) -> None:
        self.manager = MarketDataManager(root)

    async def load_market_snapshot(
        self, start: date, end: date
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        daily = await asyncio.to_thread(
            self.manager.load_daily,
            start_date=start,
            end_date=end,
        )
        return daily, pd.DataFrame()


class PaperTradingRunner:
    """Run one selected ToolAgent through a live or accelerated market day."""

    def __init__(self, config: PaperRunConfig, quote_provider: Any | None = None) -> None:
        from traderharness.paths import dataset_dir

        self.config = config
        self.dataset_root = Path(config.dataset_root or dataset_dir())
        self.feed = LiveFeed()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._error: Exception | None = None
        self._result = None
        self._quote_provider = quote_provider
        self._raw_minutes = pd.DataFrame()
        self._historical_five = pd.DataFrame()
        self._last_contexts: dict[str, Any] = {}
        self._last_source = "pending"
        self._last_missing: list[str] = []
        self._last_missing_by_agent: dict[str, list[str]] = {}
        self._seen_news: set[str] = set()
        self._raw_live_news = pd.DataFrame()
        self._news_provider = None
        self._last_news_poll: datetime | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def error(self) -> Exception | None:
        return self._error

    @property
    def result_path(self):
        return None

    def start(self) -> None:
        if self.running:
            return
        self._thread = threading.Thread(
            target=self._run,
            name=f"traderharness-paper-{self.config.session_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        try:
            self._result = asyncio.run(self._async_run())
        except Exception as exc:  # noqa: BLE001 - surfaced through session state
            if self._cancel.is_set():
                logger.info("Paper session %s cancelled safely", self.config.session_id)
                self.feed.push(
                    "paper_clock",
                    state="cancelled",
                    phase="cancelled",
                    session_date=self.config.session_date,
                    mode=self.config.mode,
                )
            else:
                self._error = exc
                logger.exception("Paper session %s failed", self.config.session_id)
                self.feed.push("error", message=str(exc), paper=True)
        finally:
            if not self.feed.done:
                self.feed.push(
                    "run_end",
                    trading_days=0 if self._error else 1,
                    cancelled=self._cancel.is_set(),
                    paper=True,
                )

    async def _async_run(self):
        agents = self._build_agents()
        provider = PaperSnapshotProvider(self.dataset_root)
        engine = BacktestEngine(
            config=EngineConfig(
                initial_cash=Decimal(str(self.config.initial_cash)),
                dataset_dir=str(self.dataset_root),
                mask_entities=False,
                cancel_check=self._cancel.is_set,
            ),
            data_provider=provider,
            event_bus=self.feed.event_bus,
        )
        self.feed.push(
            "paper_clock",
            state="starting",
            phase="pre_market",
            session_date=self.config.session_date,
            mode=self.config.mode,
        )
        result = await engine.run(
            agents=agents,
            start_date=self.config.session_date,
            end_date=self.config.session_date,
        )
        for agent_id, ctx in self._last_contexts.items():
            self._emit_snapshot(agent_id, ctx, "complete")
        return result

    def _build_agents(self):
        from traderharness.agents.llm_client import LLMClient
        from traderharness.agents.tool_agent import ToolAgent
        from traderharness.config.llm_settings import resolve_llm_credentials

        built = []
        live_file = (
            str(Path(self.config.artifact_root) / "trajectory.jsonl")
            if self.config.artifact_root is not None
            else None
        )
        for index, cfg in enumerate(self.config.agents):
            agent_id = cfg.get("id", f"paper-agent-{index + 1}")
            agent_name = cfg.get("name", f"Paper Agent {index + 1}")
            model = cfg.get("model") or "deepseek-chat"
            api_key, base_url = resolve_llm_credentials(model)
            client = LLMClient(
                model=model,
                api_key=api_key,
                base_url=base_url,
                cache_enabled=False,
            )
            agent = ToolAgent(
                agent_id=agent_id,
                name=agent_name,
                llm_client=client,
                persona=cfg.get("persona", "你是一位经验丰富的主观交易员。"),
                initial_cash=Decimal(str(self.config.initial_cash)),
                max_positions=cfg.get("max_positions", 4),
                max_position_pct=cfg.get("max_position_pct", 25.0),
                max_pre_iterations=cfg.get("max_pre_iterations", 10),
                max_window_iterations=cfg.get("max_window_iterations", 3),
                require_structured_plan=cfg.get("require_structured_plan", False),
                require_decision_card=cfg.get("require_decision_card", False),
                require_phase_completion=cfg.get("require_phase_completion", False),
                minimum_holding_days=cfg.get("minimum_holding_days", 0),
                research_interval_days=cfg.get("research_interval_days", 0),
                sandbox_pre_market_only=cfg.get("sandbox_pre_market_only", False),
                sandbox_max_calls_per_day=cfg.get("sandbox_max_calls_per_day", 0),
                watchlist_ttl_days=cfg.get("watchlist_ttl_days", 0),
                max_active_memories=cfg.get("max_active_memories", 0),
                max_daily_memories=cfg.get("max_daily_memories", 0),
                allowed_tools=cfg.get("allowed_tools"),
                event_bus=_AgentEventBus(
                    self.feed.event_bus,
                    agent_id=agent_id,
                    agent_name=agent_name,
                ),
                mask_dates=False,
                live_file=live_file,
                live_file_reset=index == 0,
            )
            agent.phase_barrier = self._barrier_for(agent.agent_id, agent.name)
            agent._loop.cancel_check = self._cancel.is_set
            built.append(agent)
        return built

    def _barrier_for(self, agent_id: str, agent_name: str):
        async def barrier(phase: str, ctx) -> None:
            await self._phase_barrier(agent_id, agent_name, phase, ctx)

        return barrier

    async def _phase_barrier(self, agent_id: str, agent_name: str, phase: str, ctx) -> None:
        if self._cancel.is_set():
            raise RuntimeError("模拟盘已取消")
        self._last_contexts[agent_id] = ctx
        cutoff = datetime.combine(self.config.session_date, PHASE_CUTOFFS[phase]).astimezone()
        self.feed.push(
            "paper_clock",
            agent_id=agent_id,
            agent_name=agent_name,
            state="waiting" if self.config.mode == "live" else "advancing",
            phase=phase,
            cutoff=cutoff.isoformat(),
            session_date=self.config.session_date,
            mode=self.config.mode,
        )
        if self.config.mode == "live":
            await self._collect_until(agent_id, agent_name, ctx, cutoff)
        else:
            await self._refresh_quotes(agent_id, ctx, cutoff)
        self._publish_market(ctx, cutoff)
        self._emit_market_pulse(agent_id, agent_name, ctx, cutoff)
        await self._emit_news(agent_id, agent_name, ctx, phase, cutoff)
        self._emit_snapshot(agent_id, ctx, phase)

    async def _collect_until(
        self,
        agent_id: str,
        agent_name: str,
        ctx,
        cutoff: datetime,
    ) -> None:
        last_poll: datetime | None = None
        while True:
            if self._cancel.is_set():
                raise RuntimeError("模拟盘已取消")
            now = datetime.now().astimezone()
            if now >= cutoff:
                await self._refresh_quotes(agent_id, ctx, cutoff)
                return
            market_open = datetime.combine(self.config.session_date, time(9, 30)).astimezone()
            if now >= market_open and self._market_is_collecting(now):
                if last_poll is None or (now - last_poll).total_seconds() >= self.config.poll_seconds:
                    await self._refresh_quotes(agent_id, ctx, now)
                    self._publish_market(ctx, now)
                    self._emit_market_pulse(agent_id, agent_name, ctx, now)
                    await self._emit_news(agent_id, agent_name, ctx, "collecting", now)
                    self._emit_snapshot(agent_id, ctx, "collecting")
                    last_poll = now
            remaining = max(0.1, min(1.0, (cutoff - now).total_seconds()))
            await asyncio.sleep(remaining)

    @staticmethod
    def _market_is_collecting(now: datetime) -> bool:
        clock = now.time()
        return time(9, 30) <= clock <= time(11, 30) or time(13, 0) <= clock <= time(15, 0)

    def _attention_codes(self, ctx) -> list[str]:
        watchlist = ctx.tool_call_cache.get("watchlist", {}) or {}
        codes = set(watchlist) | set(ctx.portfolio.positions)
        bus = ctx._bus
        if bus is not None and hasattr(bus, "list_conditional_orders"):
            codes.update(
                order["stock_code"]
                for order in bus.list_conditional_orders(status="active")
            )
        if not codes:
            candidates: list[tuple[float, str]] = []
            for code, frame in ctx.preloaded_daily.items():
                visible = frame[frame["date"] < ctx.current_date]
                if visible.empty:
                    continue
                row = visible.iloc[-1]
                activity = float(row.get("amount", row.get("volume", 0)) or 0)
                candidates.append((activity, code))
            codes.update(code for _, code in sorted(candidates, reverse=True)[:4])
        return sorted(codes)[: self.config.max_attention_codes]

    async def _refresh_quotes(self, agent_id: str, ctx, cutoff: datetime) -> None:
        codes = self._attention_codes(ctx)
        if not codes:
            raise RuntimeError("模拟盘关注池为空，无法取得可撮合行情")
        if self._quote_provider is not None:
            frame = await asyncio.to_thread(
                self._quote_provider.fetch_latest,
                codes,
                self.config.session_date,
            )
            provider_name = type(self._quote_provider).__name__
            self._last_source = str(
                getattr(self._quote_provider, "last_provider", None)
                or ("eastmoney_1m" if provider_name == "Eastmoney1MinProvider" else provider_name)
            )
        elif self.config.mode == "live":
            from traderharness.data.update_providers import (
                CascadingLiveMinuteProvider,
                Eastmoney1MinProvider,
                Sina1MinProvider,
            )

            self._quote_provider = CascadingLiveMinuteProvider(
                Eastmoney1MinProvider(workers=2, max_attempts=2, max_passes=1),
                Sina1MinProvider(workers=2),
            )
            frame = await asyncio.to_thread(
                self._quote_provider.fetch_latest,
                codes,
                self.config.session_date,
            )
            self._last_source = self._quote_provider.last_provider
        else:
            frame = await self._accelerated_snapshot(codes)
        if self._last_source != "canonical_5m":
            self._raw_minutes = self._merge_minutes(self._raw_minutes, frame)
        returned = set(frame.get("stock_code", pd.Series(dtype=str)).astype(str))
        self._last_missing = sorted(set(codes) - returned)
        self._last_missing_by_agent[agent_id] = self._last_missing
        held_missing = self._last_missing and set(self._last_missing) & set(ctx.portfolio.positions)
        if held_missing:
            raise RuntimeError(
                "持仓的一分钟行情缺失，已停止撮合以避免使用陈旧价格: "
                + ", ".join(sorted(held_missing))
            )
        gate = getattr(self._quote_provider, "request_gate", None)
        provider_metrics = getattr(self._quote_provider, "metrics", None)
        self.feed.push(
            "paper_quote",
            agent_id=agent_id,
            phase=getattr(ctx, "_current_sub_window", "pre_market"),
            source=self._last_source,
            attention_codes=codes,
            missing_codes=self._last_missing,
            one_minute_bars=len(self._raw_minutes),
            fetched_rows=len(frame),
            request_metrics=(
                dict(provider_metrics)
                if isinstance(provider_metrics, dict)
                else (dict(gate.stats) if gate is not None else {})
            ),
            as_of=cutoff.isoformat(),
        )

    def _emit_market_pulse(
        self,
        agent_id: str,
        agent_name: str,
        ctx,
        cutoff: datetime,
    ) -> None:
        codes = self._attention_codes(ctx)
        source = self._historical_five if self._last_source == "canonical_5m" else self._raw_minutes
        try:
            from traderharness.data.stock_registry_loader import get_stock_registry

            registry = get_stock_registry()
            names = {code: str(registry.get(code, {}).get("name") or code) for code in codes}
        except Exception:  # noqa: BLE001 - names are presentation metadata only
            names = {code: code for code in codes}
        pulse = build_market_pulse(
            source,
            cutoff=cutoff.replace(tzinfo=None),
            codes=codes,
            names=names,
        )
        if not pulse["items"]:
            return
        self.feed.push(
            "paper_market_pulse",
            agent_id=agent_id,
            agent_name=agent_name,
            source=self._last_source,
            phase=getattr(ctx, "_current_sub_window", "pre_market"),
            as_of=cutoff.isoformat(),
            **pulse,
        )

    async def _emit_news(
        self,
        agent_id: str,
        agent_name: str,
        ctx,
        phase: str,
        cutoff: datetime,
    ) -> None:
        start_clock = PHASE_WINDOWS.get(phase, (time(9, 30), cutoff.time()))[0]
        window_start = datetime.combine(self.config.session_date, start_clock)
        window_end = cutoff.replace(tzinfo=None)
        manager = getattr(ctx._bus, "_news_manager", None)
        if manager is None:
            return
        news = manager.news
        if self.config.mode == "live":
            now = datetime.now().astimezone()
            should_poll = (
                self._last_news_poll is None
                or (now - self._last_news_poll).total_seconds() >= self.config.poll_seconds
            )
            if should_poll:
                from traderharness.data.update_providers import ClsNewsProvider

                self._news_provider = self._news_provider or ClsNewsProvider()
                try:
                    latest = await asyncio.to_thread(
                        self._news_provider.fetch_latest,
                        window_start,
                        window_end,
                    )
                except Exception as exc:  # noqa: BLE001 - local point-in-time cache remains available
                    logger.warning("Live flash refresh failed; retaining local news cache: %s", exc)
                else:
                    if not latest.empty:
                        self._raw_live_news = pd.concat(
                            [self._raw_live_news, latest], ignore_index=True
                        ).drop_duplicates("id", keep="last")
                self._last_news_poll = now
            if not self._raw_live_news.empty:
                news = pd.concat([news, self._raw_live_news], ignore_index=True)
        items = select_news_broadcasts(
            news,
            manager.announcements,
            target_codes=set(self._attention_codes(ctx)),
            window_start=window_start,
            window_end=window_end + timedelta(microseconds=1),
        )
        fresh = [item for item in items if item["source_id"] not in self._seen_news]
        if not fresh:
            return
        self._seen_news.update(item["source_id"] for item in fresh)
        self.feed.push(
            "paper_news",
            agent_id=agent_id,
            agent_name=agent_name,
            phase=phase,
            as_of=cutoff.isoformat(),
            items=fresh,
        )

    async def _accelerated_snapshot(self, codes: list[str]) -> pd.DataFrame:
        if self._quote_provider is None:
            from traderharness.data.update_providers import Eastmoney1MinProvider

            provider = Eastmoney1MinProvider(workers=2, max_attempts=2, max_passes=1)
            try:
                frame = await asyncio.to_thread(
                    provider.fetch_latest,
                    codes,
                    self.config.session_date,
                )
            except Exception:  # noqa: BLE001 - canonical replay is the acceptance fallback
                logger.warning("Recent 1min snapshot unavailable; using canonical 5min replay")
            else:
                if not frame.empty:
                    self._quote_provider = provider
                    self._last_source = "eastmoney_1m_accelerated"
                    return frame
        if self._historical_five.empty:
            manager = MarketDataManager(self.dataset_root)
            self._historical_five = await asyncio.to_thread(
                manager.load_5min,
                start_date=self.config.session_date,
                end_date=self.config.session_date,
            )
        self._last_source = "canonical_5m"
        return self._historical_five[
            self._historical_five["stock_code"].astype(str).isin(codes)
        ].copy()

    @staticmethod
    def _merge_minutes(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
        if incoming.empty:
            return existing
        if existing.empty:
            merged = incoming.copy()
        else:
            merged = pd.concat([existing, incoming], ignore_index=True)
        return (
            merged.drop_duplicates(["stock_code", "datetime"], keep="last")
            .sort_values(["stock_code", "datetime"])
            .reset_index(drop=True)
        )

    def _publish_market(self, ctx, cutoff: datetime) -> None:
        if self._last_source == "canonical_5m":
            five = self._historical_five[
                pd.to_datetime(self._historical_five["datetime"]) <= pd.Timestamp(cutoff).tz_localize(None)
            ].copy()
        else:
            five = aggregate_one_minute_to_five(
                self._raw_minutes,
                cutoff.replace(tzinfo=None),
            )
        if five.empty:
            return
        for code, frame in five.groupby("stock_code"):
            normalized = frame.drop(columns=["stock_code"]).copy()
            normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
            normalized["datetime"] = pd.to_datetime(normalized["datetime"])
            ctx._bus.market.load_5min(str(code), normalized.reset_index(drop=True))

    def _emit_snapshot(self, agent_id: str, ctx, phase: str) -> None:
        prices: dict[str, Decimal] = {}
        positions = []
        for code, position in ctx.portfolio.positions.items():
            bars = ctx._bus.market.get_5min(code)
            if not bars.empty:
                price = Decimal(str(bars.iloc[-1]["close"]))
            else:
                visible = ctx.preloaded_daily[code]
                visible = visible[visible["date"] < ctx.current_date]
                price = Decimal(str(visible.iloc[-1]["close"])) if not visible.empty else position.avg_cost
            prices[code] = price
            market_value = float(price * position.quantity)
            cost_value = float(position.avg_cost * position.quantity)
            positions.append(
                {
                    "stock_code": code,
                    "quantity": position.quantity,
                    "available_quantity": position.sellable_quantity(ctx.current_date),
                    "avg_cost": float(position.avg_cost),
                    "last_price": float(price),
                    "market_value": market_value,
                    "unrealized_pnl": market_value - cost_value,
                }
            )
        equity = float(ctx.portfolio.total_value(prices))
        initial = float(self.config.initial_cash)
        self.feed.push(
            "paper_snapshot",
            agent_id=agent_id,
            phase=phase,
            account={
                "cash": float(ctx.portfolio.cash),
                "equity": equity,
                "return_pct": (equity - initial) / initial * 100 if initial else 0.0,
            },
            positions=positions,
            trades=list(ctx._bus.trade_history),
            quote_health={
                "source": self._last_source,
                "missing_codes": self._last_missing_by_agent.get(agent_id, self._last_missing),
                "granularity": "1m"
                if ("1m" in self._last_source.lower() or "1min" in self._last_source.lower())
                else "5m",
            },
            observed_at=datetime.now().astimezone().isoformat(),
        )
