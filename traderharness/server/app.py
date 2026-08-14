"""FastAPI application factory for the local TraderHarness UI."""

from __future__ import annotations

import asyncio
import copy
import json
import os
from datetime import date, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from traderharness import __version__
from traderharness.agents.agent_card import (
    BUILTIN_STORAGE_DIR,
    AgentCard,
    list_cards,
    load_card,
    save_card,
)
from traderharness.config.llm_settings import (
    clear_llm_settings,
    llm_config_status,
    resolve_llm_credentials,
    save_llm_settings,
)
from traderharness.paths import agents_dir, dataset_dir, results_dir
from traderharness.result_analysis import (
    MarketDatasetBarSource,
    build_result_analysis,
)
from traderharness.results import (
    compact_result_analysis,
    ensure_result_summary,
    read_result_analysis_summary,
    result_analysis_summary_path,
    result_summary_path,
    write_result_analysis_summary,
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
    mask_dates: bool = True
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


def _validate_http_url(value: str | None) -> str | None:
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("请求地址必须以 http:// 或 https:// 开头")
    return value


class LLMConfigPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)
    clear: bool = False

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value)


class LLMTestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=100)

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str | None) -> str | None:
        return _validate_http_url(value)


def _result_summary(path: Path) -> dict[str, Any]:
    return ensure_result_summary(path)


def _compact_result_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    return compact_result_analysis(analysis)


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


def _build_result_entity_revealer(document: dict[str, Any], data_root: Path):
    """Reconstruct the run-scoped entity permutation from local canonical data."""
    from traderharness.core.entity_masking import EntityMasker
    from traderharness.data.market_data_manager import MarketDataManager
    from traderharness.data.stock_registry_loader import get_stock_registry

    config = document.get("config") or {}
    if not config.get("mask_entities"):
        return None
    start_text = config.get("start_date") or document.get("start_date")
    end_text = config.get("end_date") or document.get("end_date")
    try:
        start_date = date.fromisoformat(str(start_text))
        end_date = date.fromisoformat(str(end_text))
    except (TypeError, ValueError):
        return None

    manager = MarketDataManager(data_root)
    if not manager.has_daily_cache():
        return None
    daily = manager.load_daily(
        start_date=start_date - timedelta(days=180),
        end_date=end_date,
    )
    if daily.empty or "stock_code" not in daily.columns:
        return None
    codes = sorted({str(code).zfill(6) for code in daily["stock_code"].dropna().unique()})
    registry = get_stock_registry()
    names = {code: registry.get(code, {}).get("name", code) for code in codes}
    return EntityMasker(
        codes,
        names=names,
        seed=config.get("entity_mask_seed", 0),
        style=config.get("entity_mask_style", "permutation"),
    )


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    if host == "testclient":
        return
    try:
        is_loopback = ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(403, "解除实体遮罩仅允许从本机访问")


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
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    # Result artifacts are immutable once written (rewrites bump mtime), so
    # (size, mtime_ns)-keyed caches avoid re-parsing potentially huge JSON
    # files on every library/dossier request. Analysis payloads are large,
    # so that cache is kept small; summaries are tiny and kept per file.
    summary_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    analysis_cache: dict[
        tuple[str, bool, str], tuple[tuple[int, int], dict[str, Any]]
    ] = {}
    entity_revealer_cache: dict[str, tuple[tuple[int, int], Any]] = {}
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
                "llm_source": llm_config_status()["source"],
            },
            "security": {
                "scope": "local-only",
                "public_exposure_supported": False,
            },
        }

    @app.get("/api/showcase/masking-ab")
    def masking_ab_showcase() -> dict[str, Any]:
        """Return the credential-free, precomputed masking experiment summary."""
        from importlib.resources import files

        resource = files("traderharness.demo").joinpath("masking_ab_showcase.json")
        candidate = Path(str(resource))
        source_candidate = (
            Path(__file__).resolve().parents[2]
            / "traderharness"
            / "demo"
            / "masking_ab_showcase.json"
        )
        selected = candidate if candidate.is_file() else source_candidate
        if not selected.is_file():
            raise HTTPException(404, "Masking A/B showcase artifact is missing")
        try:
            payload = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "Masking A/B showcase artifact is invalid") from exc
        if not isinstance(payload, dict):
            raise HTTPException(500, "Masking A/B showcase artifact is invalid")
        return payload

    @app.get("/api/config/llm")
    def get_llm_config() -> dict[str, Any]:
        """Effective LLM credentials status. Never returns the full API key."""
        return llm_config_status()

    @app.put("/api/config/llm")
    def put_llm_config(payload: LLMConfigPayload) -> dict[str, Any]:
        if payload.clear:
            clear_llm_settings()
        else:
            save_llm_settings(api_key=payload.api_key, base_url=payload.base_url)
        return llm_config_status()

    @app.post("/api/config/llm/test")
    async def test_llm_config(payload: LLMTestPayload) -> dict[str, Any]:
        """Connectivity check: one minimal chat call with a 20s overall timeout."""
        from traderharness.agents.llm_client import LLMClient

        model = payload.model or "deepseek-chat"
        saved_key, saved_url = resolve_llm_credentials(model)
        api_key = payload.api_key or saved_key
        base_url = payload.base_url or saved_url
        if not api_key:
            return {"ok": False, "detail": "未配置 API Key", "model": model}

        client = LLMClient(
            model=model,
            api_key=api_key,
            base_url=base_url,
            cache_enabled=False,
            max_retries=1,
        )
        try:
            await asyncio.wait_for(
                client.chat([{"role": "user", "content": "ping"}], max_tokens=1),
                timeout=20,
            )
        except asyncio.TimeoutError:
            return {"ok": False, "detail": "连接超时（20 秒）", "model": model}
        except Exception as e:  # noqa: BLE001 — surface any provider/network error
            detail = str(e) or type(e).__name__
            # Provider errors may echo request details; never leak the key.
            detail = detail.replace(api_key, "***")
            return {"ok": False, "detail": detail[:300], "model": model}
        return {"ok": True, "detail": "连接成功", "model": model}

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
    def get_result_analysis(
        filename: str,
        request: Request,
        reveal_entities: bool = False,
        detail: Literal["summary", "full"] = "full",
    ) -> dict[str, Any]:
        if Path(filename).name != filename or not filename.endswith("_result.json"):
            raise HTTPException(400, "结果文件名无效")
        path = result_root / filename
        if not path.is_file():
            raise HTTPException(404, "未找到回测结果")
        stamp = _file_stamp(path)
        cache_key = (filename, reveal_entities, detail)
        cached = analysis_cache.get(cache_key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        summary_payload = (
            read_result_analysis_summary(path) if detail == "summary" else None
        )
        if summary_payload is not None:
            document = summary_payload.get("document") or {}
            analysis = copy.deepcopy(summary_payload["analysis"])
        else:
            document = json.loads(path.read_text(encoding="utf-8"))
        # Persisted masked trades carry pseudocodes. Evaluation-only chart
        # backfill must query the canonical code, otherwise the masked page
        # silently displays a different company's price history.
        # A precomputed masked summary is already self-contained. Rebuilding
        # the full-universe entity permutation here used to add seconds to
        # every first page load even though no entity was being revealed.
        revealer = None
        if reveal_entities or summary_payload is None:
            cached_revealer = entity_revealer_cache.get(filename)
            if cached_revealer is not None and cached_revealer[0] == stamp:
                revealer = cached_revealer[1]
            else:
                revealer = _build_result_entity_revealer(document, data_root)
                entity_revealer_cache[filename] = (stamp, revealer)
        if summary_payload is None:
            evaluation_bars = _evaluation_bar_provider(data_root)
            if evaluation_bars is not None and revealer is not None:
                canonical_evaluation_bars = evaluation_bars

                def evaluation_bars(code: str, trade_date: str) -> list[dict[str, Any]]:
                    return canonical_evaluation_bars(revealer.unmask_code(code), trade_date)

            analysis = build_result_analysis(document, evaluation_bars=evaluation_bars)
        reveal_available = bool(
            (document.get("config") or {}).get("mask_entities")
            and (data_root / "daily.parquet").is_file()
        )
        if reveal_entities:
            _require_loopback(request)
            if revealer is None:
                raise HTTPException(409, "无法从本地数据重建该次运行的实体映射")
            analysis = revealer.reveal_obj(analysis)
            analysis["entity_view"] = {"available": True, "mode": "original"}
        else:
            analysis["entity_view"] = {
                "available": reveal_available,
                "mode": "masked",
            }
        if detail == "summary":
            analysis = _compact_result_analysis(analysis)
            if summary_payload is None and not reveal_entities:
                # Legacy artifacts pay the parse cost once; subsequent page
                # loads use the stamp-validated compact sidecar.
                write_result_analysis_summary(path, document, copy.deepcopy(analysis))
        else:
            analysis["detail"] = "full"
        analysis_cache[cache_key] = (stamp, analysis)
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
        sidecar = result_summary_path(path)
        if sidecar.is_file():
            sidecar.unlink()
        analysis_sidecar = result_analysis_summary_path(path)
        if analysis_sidecar.is_file():
            analysis_sidecar.unlink()
        # Both caches key on the bare filename (path.name), so drop any stale
        # entries alongside the artifact itself.
        summary_cache.pop(filename, None)
        entity_revealer_cache.pop(filename, None)
        for cache_key in [key for key in analysis_cache if key[0] == filename]:
            analysis_cache.pop(cache_key, None)
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
                mask_dates=True,
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
