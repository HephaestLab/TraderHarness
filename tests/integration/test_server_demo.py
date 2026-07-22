import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traderharness.paths import dataset_dir
from traderharness.server.app import create_app

_HAS_FULL_DATA = (
    (dataset_dir() / "daily.parquet").is_file()
    and (dataset_dir() / "5min_clean").is_dir()
)
_HAS_REPLAY = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "replays"
    / "momentum_dragon_2024-03-14.jsonl"
).is_file()


@pytest.mark.skipif(
    not (_HAS_FULL_DATA and _HAS_REPLAY),
    reason="requires the full real dataset and bundled replay",
)
def test_fastapi_demo_streams_events_and_persists_result():
    with TestClient(create_app()) as client:
        started = client.post("/api/demo")
        assert started.status_code == 202
        run_id = started.json()["id"]

        event_types = []
        with client.websocket_connect(f"/api/runs/{run_id}/events") as websocket:
            while "run_end" not in event_types:
                event_types.append(websocket.receive_json()["type"])

        deadline = time.time() + 30
        state = client.get(f"/api/runs/{run_id}").json()
        while state["status"] not in {"done", "failed"} and time.time() < deadline:
            time.sleep(0.05)
            state = client.get(f"/api/runs/{run_id}").json()

        assert state["status"] == "done", state
        assert {"phase_change", "tool_call", "order_placed", "run_end"} <= set(event_types)
        detail = client.get(f"/api/results/{state['result_file']}")
        assert detail.status_code == 200
        result = detail.json()
        # Trade count tracks the bundled momentum_dragon_2024-03-14.jsonl
        # trajectory; update this expectation when the cassette is re-recorded.
        assert result["agent_data"]["momentum-dragon"]["metrics"]["total_trades"] == 2
