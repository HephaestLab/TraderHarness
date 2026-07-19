"""FastAPI application factory for the local TraderHarness UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from traderharness.agents.agent_card import (
    BUILTIN_STORAGE_DIR,
    AgentCard,
    list_cards,
    load_card,
    save_card,
)
from traderharness.paths import agents_dir, dataset_dir, results_dir
from traderharness.result_analysis import (
    MarketDatasetBarSource,
    build_comparison,
    build_result_analysis,
)
from traderharness.tools.catalog import normalize_allowed_tools, tool_catalog_payload


class RunManagerProtocol(Protocol):
    def start(self, request: RunRequest) -> dict[str, Any]: ...

    def get(self, run_id: str) -> dict[str, Any] | None: ...

    def cancel(self, run_id: str) -> bool: ...

    def events(self, run_id: str): ...


class AgentCardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    persona: str = Field(min_length=1, max_length=20_000)
    strategy_tags: list[str] = Field(default_factory=list, max_length=8)
    risk_profile: Literal["conservative", "balanced", "aggressive"] = "balanced"
    holding_period: str = Field(default="3-10 trading days", max_length=100)
    allowed_tools: list[str] | None = None
    model: str = Field(min_length=1, max_length=100)
    initial_cash: int = Field(gt=0)
    max_positions: int = Field(ge=1, le=20)
    max_position_pct: float = Field(gt=0, le=100)

    @field_validator("allowed_tools")
    @classmethod
    def valid_tools(cls, value: list[str] | None) -> list[str]:
        return normalize_allowed_tools(value)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[str] = Field(min_length=1, max_length=8)
    start_date: str
    end_date: str
    initial_cash: int = Field(default=1_000_000, gt=0)
    mask_entities: bool = True
    entity_mask_seed: int = 0
    replay: bool = False

    @field_validator("start_date", "end_date")
    @classmethod
    def valid_iso_date(cls, value: str) -> str:
        from datetime import date

        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def valid_range(self) -> RunRequest:
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


def _result_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary: dict[str, Any] = {
        "file": path.name,
        "status": data.get("status", "done"),
        "start_date": data.get("start_date") or data.get("config", {}).get("start_date"),
        "end_date": data.get("end_date") or data.get("config", {}).get("end_date"),
        "trading_days": data.get("trading_days", 0),
    }
    agent_data = data.get("agent_data") or {}
    summary["agent_count"] = len(agent_data)
    if len(agent_data) == 1:
        # Single agent: the metrics ARE the run's metrics, no ranking needed.
        summary["metrics"] = next(iter(agent_data.values())).get("metrics") or {}
    elif len(agent_data) > 1:
        # Multiple agents: showing only the first agent's metrics would
        # misrepresent the run. Surface a ranked summary instead.
        comparison = build_comparison(agent_data)
        if comparison:
            summary["agents"] = comparison["agents"]
            summary["best_agent_id"] = comparison["best_agent_id"]
            summary["best_return"] = comparison["agents"][0]["total_return_pct"]
    return summary


def _evaluation_bar_provider(data_root: Path) -> MarketDatasetBarSource | None:
    """Wire the default evaluation-only K-line backfill source, if the dataset exists.

    Returns ``None`` when there is no local dataset to read from (e.g. a
    fresh install, or a unit test with an injected fake dataset root) so
    trade reviews simply keep whatever bars the agent's own tool calls
    produced.
    """
    from traderharness.data.market_data_manager import MarketDataManager

    manager = MarketDataManager(data_root)
    if not manager.has_daily_cache():
        return None
    return MarketDatasetBarSource(manager)


def create_app(
    *,
    run_manager: RunManagerProtocol | None = None,
    dataset_path: Path | None = None,
    results_path: Path | None = None,
    agents_path: Path | None = None,
) -> FastAPI:
    """Create an app with injectable storage and runner dependencies."""
    if run_manager is None:
        from traderharness.server.run_manager import RunManager

        run_manager = RunManager()
    data_root = Path(dataset_path or dataset_dir())
    result_root = Path(results_path or results_dir())
    agent_root = Path(agents_path or agents_dir())
    use_builtin_agents = agents_path is None
    result_root.mkdir(parents=True, exist_ok=True)
    agent_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="TraderHarness API",
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Result artifacts are immutable once written (rewrites bump mtime), so
    # (size, mtime_ns)-keyed caches avoid re-parsing potentially huge JSON
    # files on every library/dossier request. Analysis payloads are large,
    # so that cache is kept small; summaries are tiny and kept per file.
    summary_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    analysis_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    analysis_cache_max_entries = 4

    def _file_stamp(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return (stat.st_size, stat.st_mtime_ns)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "traderharness"}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            "dataset": {
                "daily": (data_root / "daily.parquet").is_file(),
                "five_minute": (data_root / "5min_clean").is_dir(),
                "announcements": (data_root / "announcements.parquet").is_file(),
                "news": (data_root / "news_cls.parquet").is_file(),
                "fundamentals": (data_root / "fundamentals.parquet").is_file(),
                "valuation": (data_root / "valuation.parquet").is_file(),
                "benchmark": (data_root / "index_300.parquet").is_file(),
            },
            "providers": {
                "deepseek_configured": bool(os.environ.get("DEEPSEEK_API_KEY")),
            },
            "security": {
                "scope": "local-only",
                "public_exposure_supported": False,
            },
        }

    @app.get("/api/agents")
    def get_agents() -> list[dict[str, Any]]:
        cards = list_cards() if use_builtin_agents else list_cards(agent_root)
        payload = []
        for card in cards:
            item = card.to_dict()
            item["builtin"] = (
                use_builtin_agents
                and (BUILTIN_STORAGE_DIR / f"{card.id}.json").is_file()
                and not (agent_root / f"{card.id}.json").is_file()
            )
            payload.append(item)
        return payload

    @app.get("/api/tools")
    def get_tools() -> list[dict[str, Any]]:
        return tool_catalog_payload()

    @app.post("/api/agents", status_code=201)
    def create_agent(payload: AgentCardPayload) -> dict[str, Any]:
        existing = (
            load_card(payload.id) if use_builtin_agents else load_card(payload.id, agent_root)
        )
        if existing is not None:
            raise HTTPException(409, "智能体 ID 已存在")
        card = AgentCard.from_dict(payload.model_dump())
        save_card(card, agent_root)
        return card.to_dict()

    @app.put("/api/agents/{agent_id}")
    def update_agent(agent_id: str, payload: AgentCardPayload) -> dict[str, Any]:
        if payload.id != agent_id:
            raise HTTPException(400, "智能体 ID 不可修改")
        existing = load_card(agent_id) if use_builtin_agents else load_card(agent_id, agent_root)
        if existing is None:
            raise HTTPException(404, "未找到智能体")
        card = AgentCard.from_dict(payload.model_dump())
        save_card(card, agent_root)
        return card.to_dict()

    @app.delete("/api/agents/{agent_id}", status_code=204)
    def delete_agent(agent_id: str) -> Response:
        card = load_card(agent_id) if use_builtin_agents else load_card(agent_id, agent_root)
        if card is None:
            raise HTTPException(404, "未找到智能体")
        user_path = agent_root / f"{agent_id}.json"
        if not user_path.is_file():
            raise HTTPException(403, "不能删除内置智能体")
        user_path.unlink()
        return Response(status_code=204)

    @app.get("/api/results")
    def get_results() -> list[dict[str, Any]]:
        summaries = []
        seen: set[str] = set()
        for path in sorted(result_root.glob("*_result.json"), reverse=True):
            try:
                stamp = _file_stamp(path)
                cached = summary_cache.get(path.name)
                if cached is not None and cached[0] == stamp:
                    summary = cached[1]
                else:
                    summary = _result_summary(path)
                    summary_cache[path.name] = (stamp, summary)
                seen.add(path.name)
                summaries.append(summary)
            except (OSError, json.JSONDecodeError):
                continue
        for stale in set(summary_cache) - seen:
            summary_cache.pop(stale, None)
        return summaries

    @app.get("/api/results/{filename}/analysis")
    def get_result_analysis(filename: str) -> dict[str, Any]:
        if Path(filename).name != filename or not filename.endswith("_result.json"):
            raise HTTPException(400, "结果文件名无效")
        path = result_root / filename
        if not path.is_file():
            raise HTTPException(404, "未找到回测结果")
        stamp = _file_stamp(path)
        cached = analysis_cache.get(filename)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        document = json.loads(path.read_text(encoding="utf-8"))
        evaluation_bars = _evaluation_bar_provider(data_root)
        analysis = build_result_analysis(document, evaluation_bars=evaluation_bars)
        analysis_cache[filename] = (stamp, analysis)
        while len(analysis_cache) > analysis_cache_max_entries:
            analysis_cache.pop(next(iter(analysis_cache)))
        return analysis

    @app.get("/api/results/{filename:path}")
    def get_result(filename: str) -> dict[str, Any]:
        if Path(filename).name != filename or not filename.endswith("_result.json"):
            raise HTTPException(400, "结果文件名无效")
        path = result_root / filename
        if not path.is_file():
            raise HTTPException(404, "未找到回测结果")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.delete("/api/results/{filename:path}", status_code=204)
    def delete_result(filename: str) -> Response:
        if Path(filename).name != filename or not filename.endswith("_result.json"):
            raise HTTPException(400, "结果文件名无效")
        path = result_root / filename
        if not path.is_file():
            raise HTTPException(404, "未找到回测结果")
        path.unlink()
        # Both caches key on the bare filename (path.name), so drop any stale
        # entries alongside the artifact itself.
        summary_cache.pop(filename, None)
        analysis_cache.pop(filename, None)
        return Response(status_code=204)

    @app.post("/api/runs", status_code=202)
    def start_run(request: RunRequest) -> dict[str, Any]:
        return run_manager.start(request)

    @app.post("/api/demo", status_code=202)
    def start_demo() -> dict[str, Any]:
        return run_manager.start(
            RunRequest(
                agents=["momentum-dragon"],
                start_date="2024-03-14",
                end_date="2024-03-14",
                initial_cash=1_000_000,
                mask_entities=True,
                entity_mask_seed=42,
                replay=True,
            )
        )

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return run_manager.list()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        state = run_manager.get(run_id)
        if state is None:
            raise HTTPException(404, "未找到回测运行")
        return state

    @app.delete("/api/runs/{run_id}", status_code=202)
    def cancel_run(run_id: str) -> dict[str, str]:
        if not run_manager.cancel(run_id):
            raise HTTPException(404, "未找到回测运行，或该运行已经结束")
        return {"id": run_id, "status": "cancelling"}

    @app.websocket("/api/runs/{run_id}/events")
    async def run_events(websocket: WebSocket, run_id: str) -> None:
        if run_manager.get(run_id) is None:
            await websocket.close(code=4404, reason="Run not found")
            return
        await websocket.accept()
        try:
            async for event in run_manager.events(run_id):
                await websocket.send_json(event)
        except WebSocketDisconnect:
            return

    static_root = Path(__file__).resolve().parents[1] / "ui" / "static"
    if (static_root / "index.html").is_file():
        assets_root = static_root / "assets"
        if assets_root.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_root), name="web-assets")

        @app.get("/", include_in_schema=False)
        @app.get("/{spa_path:path}", include_in_schema=False)
        def web_app(spa_path: str = "") -> FileResponse:
            if spa_path.startswith("api/"):
                raise HTTPException(404, "未找到 API 端点")
            return FileResponse(static_root / "index.html")

    return app
