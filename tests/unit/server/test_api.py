import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi.testclient import TestClient

from traderharness.server.app import create_app


class FakeRunManager:
    def __init__(self):
        self.started = []
        self.cancelled = []

    def start(self, request):
        self.started.append(request)
        return {
            "id": "run-1",
            "status": "running",
            "created_at": "2026-07-17T00:00:00Z",
        }

    def get(self, run_id):
        if run_id != "run-1":
            return None
        return {
            "id": run_id,
            "status": "running",
            "created_at": "2026-07-17T00:00:00Z",
        }

    def list(self):
        return [self.get("run-1")]

    def cancel(self, run_id):
        if run_id != "run-1":
            return False
        self.cancelled.append(run_id)
        return True

    async def events(self, run_id) -> AsyncIterator[dict]:
        if run_id != "run-1":
            return
        yield {"sequence": 1, "type": "phase_change", "data": {"phase": "pre_market"}}
        yield {"sequence": 2, "type": "run_end", "data": {"trading_days": 1}}


def _client(tmp_path: Path) -> TestClient:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "daily.parquet").write_bytes(b"present")
    results = tmp_path / "results"
    results.mkdir()
    agents = tmp_path / "agents"
    return TestClient(
        create_app(
            run_manager=FakeRunManager(),
            dataset_path=dataset,
            results_path=results,
            agents_path=agents,
        )
    )


def test_health_and_runtime_status_do_not_expose_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret-value")
    with _client(tmp_path) as client:
        assert client.get("/api/health").json() == {
            "status": "ok",
            "service": "traderharness",
        }
        status = client.get("/api/status").json()

    assert status["dataset"]["daily"] is True
    assert status["providers"]["deepseek_configured"] is True
    assert "secret-value" not in json.dumps(status)


def test_compiled_react_app_and_spa_routes_are_served(tmp_path):
    with _client(tmp_path) as client:
        root = client.get("/")
        nested = client.get("/results")
        missing_api = client.get("/api/not-a-route")

    assert root.status_code == 200
    assert nested.status_code == 200
    assert "<title>TraderHarness 交易智能体研究台</title>" in root.text
    assert missing_api.status_code == 404


def test_agent_card_crud(tmp_path):
    with _client(tmp_path) as client:
        created = client.post(
            "/api/agents",
            json={
                "id": "trend-agent",
                "name": "Trend Agent",
                "persona": "只做确认趋势",
                "model": "deepseek-chat",
                "initial_cash": 1000000,
                "max_positions": 4,
                "max_position_pct": 25,
            },
        )
        assert created.status_code == 201
        assert client.get("/api/agents").json()[0]["id"] == "trend-agent"

        updated = client.put(
            "/api/agents/trend-agent",
            json={
                "id": "trend-agent",
                "name": "Trend Agent v2",
                "persona": "等待量价确认",
                "model": "deepseek-chat",
                "initial_cash": 1000000,
                "max_positions": 3,
                "max_position_pct": 20,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Trend Agent v2"
        assert client.delete("/api/agents/trend-agent").status_code == 204
        assert client.get("/api/agents").json() == []


def test_agent_tool_catalog_and_protected_allowlist(tmp_path):
    with _client(tmp_path) as client:
        catalog = client.get("/api/tools")
        created = client.post(
            "/api/agents",
            json={
                "id": "focused-agent",
                "name": "Focused Agent",
                "description": "只使用必要的价格研究工具。",
                "persona": "只在价格结构明确时交易。",
                "strategy_tags": ["focused", "price-action"],
                "risk_profile": "balanced",
                "holding_period": "3-10 trading days",
                "model": "deepseek-chat",
                "initial_cash": 1000000,
                "max_positions": 3,
                "max_position_pct": 25,
                "allowed_tools": ["get_kline"],
            },
        )

    assert catalog.status_code == 200
    tool_map = {item["name"]: item for item in catalog.json()}
    assert tool_map["place_order"]["required"] is True
    assert tool_map["execute_code"]["category"] == "quant"
    assert created.status_code == 201
    allowed = set(created.json()["allowed_tools"])
    assert {"get_kline", "get_portfolio", "get_position", "place_order", "finish_day"} <= allowed
    assert "execute_code" not in allowed


def test_results_list_and_detail_reject_path_traversal(tmp_path):
    client = _client(tmp_path)
    results = tmp_path / "results"
    (results / "20260717_result.json").write_text(
        json.dumps({"status": "done", "agent_data": {}}),
        encoding="utf-8",
    )
    with client:
        listed = client.get("/api/results")
        assert listed.status_code == 200
        assert listed.json()[0]["file"] == "20260717_result.json"
        assert client.get("/api/results/20260717_result.json").status_code == 200
        assert client.get("/api/results/..%2Fsecret.json").status_code == 400


def test_delete_result_removes_artifact_and_clears_caches(tmp_path):
    client = _client(tmp_path)
    results = tmp_path / "results"
    path = results / "20260720_result.json"
    path.write_text(
        json.dumps({"status": "done", "agent_data": {}}),
        encoding="utf-8",
    )

    with client:
        # Populate both caches before deletion.
        assert client.get("/api/results").json()[0]["file"] == "20260720_result.json"
        assert client.get("/api/results/20260720_result.json").status_code == 200

        deleted = client.delete("/api/results/20260720_result.json")
        assert deleted.status_code == 204
        assert not path.exists()
        assert client.get("/api/results/20260720_result.json").status_code == 404
        assert client.get("/api/results/20260720_result.json/analysis").status_code == 404
        assert client.get("/api/results").json() == []


def test_delete_result_rejects_invalid_filenames(tmp_path):
    client = _client(tmp_path)
    results = tmp_path / "results"
    (results / "20260720_result.json").write_text(
        json.dumps({"status": "done", "agent_data": {}}),
        encoding="utf-8",
    )

    with client:
        assert client.delete("/api/results/..%2Fsecret_result.json").status_code == 400
        assert client.delete("/api/results/foo.txt").status_code == 400

    # Nothing was deleted by the rejected requests.
    assert (results / "20260720_result.json").is_file()


def test_delete_result_returns_404_for_missing_file(tmp_path):
    with _client(tmp_path) as client:
        assert client.delete("/api/results/20990101_result.json").status_code == 404


def test_results_list_summarizes_multi_agent_runs_without_only_showing_the_first(tmp_path):
    client = _client(tmp_path)
    results = tmp_path / "results"
    (results / "20260718_result.json").write_text(
        json.dumps(
            {
                "status": "done",
                "start_date": "2024-03-14",
                "end_date": "2024-03-15",
                "trading_days": 2,
                "agent_data": {
                    "momentum": {
                        "equity_curve": [["2024-03-14", 990_000]],
                        "metrics": {"total_return_pct": -1.0, "sharpe_ratio": -0.4},
                        "trades": [],
                    },
                    "contrarian": {
                        "equity_curve": [["2024-03-14", 1_040_000]],
                        "metrics": {"total_return_pct": 4.0, "sharpe_ratio": 1.8},
                        "trades": [],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    with client:
        listed = client.get("/api/results").json()

    summary = next(item for item in listed if item["file"] == "20260718_result.json")
    assert summary["agent_count"] == 2
    assert "metrics" not in summary  # would misleadingly imply a single agent
    assert summary["best_return"] == 4.0
    assert summary["best_agent_id"] == "contrarian"
    agent_ids = {agent["agent_id"] for agent in summary["agents"]}
    assert agent_ids == {"momentum", "contrarian"}


def test_results_summary_cache_serves_hits_and_invalidates_on_mtime_change(tmp_path):
    """Listing results must not re-parse unchanged (potentially huge) artifacts
    on every request, but must pick up rewritten files immediately."""
    import os

    client = _client(tmp_path)
    results = tmp_path / "results"
    path = results / "20260718_result.json"

    def write(return_pct: float, mtime: float) -> None:
        path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "trading_days": 1,
                    "agent_data": {
                        "agent": {
                            "equity_curve": [["2024-03-14", 1_000_000]],
                            "metrics": {"total_return_pct": return_pct},
                            "trades": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        os.utime(path, (mtime, mtime))

    with client:
        write(1.5, 1_000_000_000)
        first = client.get("/api/results").json()

        # Same mtime -> summary must come from cache, not a fresh parse.
        import traderharness.server.app as server_app

        original_summary = server_app._result_summary

        def fail_if_called(path):
            raise AssertionError("cache miss: _result_summary re-ran for unchanged file")

        server_app._result_summary = fail_if_called
        try:
            cached = client.get("/api/results").json()
        finally:
            server_app._result_summary = original_summary

        write(9.9, 2_000_000_000)
        refreshed = client.get("/api/results").json()

    assert first[0]["metrics"]["total_return_pct"] == 1.5
    assert cached == first
    assert refreshed[0]["metrics"]["total_return_pct"] == 9.9


def test_result_analysis_is_cached_until_the_artifact_changes(tmp_path):
    import os

    client = _client(tmp_path)
    results = tmp_path / "results"
    path = results / "20260718_result.json"

    def write(equity: float, mtime: float) -> None:
        path.write_text(
            json.dumps(
                {
                    "status": "done",
                    "agent_data": {
                        "agent": {
                            "equity_curve": [["2024-03-14", equity]],
                            "trades": [],
                            "trajectory": {"steps": []},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        os.utime(path, (mtime, mtime))

    import traderharness.server.app as server_app

    with client:
        write(101.0, 1_000_000_000)
        first = client.get("/api/results/20260718_result.json/analysis").json()

        original_build = server_app.build_result_analysis

        def fail_if_called(*args, **kwargs):
            raise AssertionError("cache miss: analysis re-ran for unchanged file")

        server_app.build_result_analysis = fail_if_called
        try:
            again = client.get("/api/results/20260718_result.json/analysis").json()
        finally:
            server_app.build_result_analysis = original_build

        write(202.0, 2_000_000_000)
        refreshed = client.get("/api/results/20260718_result.json/analysis").json()

    assert first["agents"]["agent"]["daily"][0]["equity"] == 101.0
    assert again == first
    assert refreshed["agents"]["agent"]["daily"][0]["equity"] == 202.0


def test_result_analysis_endpoint_returns_normalized_dossier(tmp_path):
    client = _client(tmp_path)
    results = tmp_path / "results"
    (results / "20260717_result.json").write_text(
        json.dumps(
            {
                "status": "done",
                "agent_data": {
                    "agent": {
                        "equity_curve": [["2024-03-14", 101]],
                        "trades": [],
                        "trajectory": {"steps": []},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with client:
        response = client.get("/api/results/20260717_result.json/analysis")
        invalid = client.get("/api/results/..%2Fsecret.json/analysis")

    assert response.status_code == 200
    assert response.json()["agents"]["agent"]["daily"][0]["equity"] == 101
    assert invalid.status_code == 400


def test_result_analysis_endpoint_backfills_evaluation_bars_for_untracked_trades(tmp_path):
    import pandas as pd

    dataset = tmp_path / "dataset"
    dataset.mkdir()
    daily = pd.DataFrame(
        {
            "stock_code": ["600001"] * 9,
            "date": pd.date_range("2024-03-08", periods=9, freq="D"),
            "open": [10.0 + i * 0.1 for i in range(9)],
            "high": [10.2 + i * 0.1 for i in range(9)],
            "low": [9.9 + i * 0.1 for i in range(9)],
            "close": [10.1 + i * 0.1 for i in range(9)],
            "volume": [1000 + i * 10 for i in range(9)],
        }
    )
    daily.to_parquet(dataset / "daily.parquet", index=False)
    results = tmp_path / "results"
    results.mkdir()
    client = TestClient(
        create_app(
            run_manager=FakeRunManager(),
            dataset_path=dataset,
            results_path=results,
            agents_path=tmp_path / "agents",
        )
    )
    (results / "20260719_result.json").write_text(
        json.dumps(
            {
                "status": "done",
                "agent_data": {
                    "agent": {
                        "equity_curve": [["2024-03-14", 1_000_000]],
                        "trades": [
                            {
                                "trade_date": "2024-03-14",
                                "stock_code": "600001",
                                "action": "buy",
                                "price": 10.4,
                                "quantity": 100,
                            }
                        ],
                        "trajectory": {"steps": []},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with client:
        response = client.get("/api/results/20260719_result.json/analysis")

    review = response.json()["agents"]["agent"]["trade_reviews"][0]
    # The trajectory never called get_kline for 600001, so the only way the
    # reviewer sees market context is the evaluation-only backfill — and it
    # must be labeled as such, never mistaken for agent-visible evidence.
    assert review["bars_source"] == "evaluation"
    assert review["bars"]
    assert all(bar["source"] == "evaluation" for bar in review["bars"])


def test_start_cancel_and_websocket_event_stream(tmp_path):
    with _client(tmp_path) as client:
        started = client.post(
            "/api/runs",
            json={
                "agents": ["momentum-dragon"],
                "start_date": "2024-03-14",
                "end_date": "2024-03-14",
                "initial_cash": 1000000,
                "mask_entities": True,
                "entity_mask_seed": 42,
            },
        )
        assert started.status_code == 202
        assert started.json()["id"] == "run-1"
        assert client.get("/api/runs/run-1").json()["status"] == "running"
        assert client.get("/api/runs").json()[0]["id"] == "run-1"

        with client.websocket_connect("/api/runs/run-1/events") as websocket:
            assert websocket.receive_json()["type"] == "phase_change"
            assert websocket.receive_json()["type"] == "run_end"

        assert client.delete("/api/runs/run-1").status_code == 202
        assert client.get("/api/runs/missing").status_code == 404


def test_demo_endpoint_starts_fixed_masked_replay(tmp_path):
    manager = FakeRunManager()
    app = create_app(
        run_manager=manager,
        dataset_path=tmp_path / "dataset",
        results_path=tmp_path / "results",
        agents_path=tmp_path / "agents",
    )
    with TestClient(app) as client:
        response = client.post("/api/demo")

    assert response.status_code == 202
    request = manager.started[0]
    assert request.replay is True
    assert request.start_date == "2024-03-14"
    assert request.end_date == "2024-03-14"
    assert request.mask_entities is True
    assert request.entity_mask_seed == 42
