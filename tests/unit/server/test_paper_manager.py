import asyncio
import time
from types import SimpleNamespace

from traderharness.core.live_feed import LiveFeed
from traderharness.server.paper_manager import PaperSessionManager


class FakePaperRunner:
    def __init__(self, complete=True):
        self.feed = LiveFeed()
        self.running = False
        self.error = None
        self.complete = complete
        self.stopped = False

    def start(self):
        self.running = True
        self.feed.push(
            "paper_clock",
            agent_id="momentum-dragon",
            state="advancing",
            phase="open_1",
        )
        self.feed.push(
            "paper_quote",
            agent_id="momentum-dragon",
            source="eastmoney_1m",
            attention_codes=["600519"],
            missing_codes=[],
            request_metrics={"requests": 1, "rate_limited": 0},
            one_minute_bars=20,
            as_of="2026-08-21T09:50:00+08:00",
        )
        self.feed.push(
            "paper_snapshot",
            agent_id="momentum-dragon",
            phase="open_1",
            account={"cash": 900000, "equity": 1001000, "return_pct": 0.1},
            positions=[{"stock_code": "600519", "quantity": 100}],
            trades=[{"stock_code": "600519", "action": "buy"}],
            quote_health={"granularity": "1m"},
            observed_at="2026-08-21T09:50:00+08:00",
        )
        self.feed.push(
            "paper_clock",
            agent_id="value-sage",
            state="advancing",
            phase="open_1",
        )
        self.feed.push(
            "paper_snapshot",
            agent_id="value-sage",
            phase="open_1",
            account={"cash": 1000000, "equity": 999000, "return_pct": -0.1},
            positions=[],
            trades=[],
            quote_health={"granularity": "1m"},
            observed_at="2026-08-21T09:50:00+08:00",
        )
        if self.complete:
            self.feed.push("run_end", trading_days=1, paper=True)
            self.running = False

    def stop(self):
        self.stopped = True
        self.running = False
        if not self.feed.done:
            self.feed.push("run_end", trading_days=0, cancelled=True, paper=True)


def _request():
    return SimpleNamespace(
        agent_ids=["momentum-dragon", "value-sage"],
        session_date="2026-08-21",
        initial_cash=1_000_000,
        mode="accelerated",
        poll_seconds=60,
        max_attention_codes=8,
    )


def test_paper_manager_persists_account_quotes_and_replayable_events(tmp_path):
    runner = FakePaperRunner()
    manager = PaperSessionManager(
        runner_factory=lambda request, session_id, agents: runner,
        storage_root=tmp_path / "paper",
        dataset_root=tmp_path / "dataset",
        agent_root=tmp_path / "agents",
    )

    started = manager.start(_request())
    deadline = time.time() + 1
    while manager.get(started["id"])["status"] == "running" and time.time() < deadline:
        time.sleep(0.01)

    state = manager.get(started["id"])
    assert state["status"] == "done"
    assert state["agent_ids"] == ["momentum-dragon", "value-sage"]
    assert len(state["agents"]) == 2
    assert state["agents"][0]["account"]["equity"] == 1001000
    assert state["agents"][1]["account"]["equity"] == 999000
    assert state["account"]["equity"] == 1001000
    assert state["quote_health"]["granularity"] == "1m"
    assert state["quote_health"]["request_metrics"]["rate_limited"] == 0
    assert state["positions"][0]["stock_code"] == "600519"
    assert manager.artifact_path(started["id"], "events.jsonl").is_file()
    assert manager.artifact_path(started["id"], "../events.jsonl") is None

    async def collect():
        return [event async for event in manager.events(started["id"])]

    events = asyncio.run(collect())
    assert [event["sequence"] for event in events] == [1, 2, 3, 4, 5, 6]

    restored = PaperSessionManager(
        storage_root=tmp_path / "paper",
        dataset_root=tmp_path / "dataset",
        agent_root=tmp_path / "agents",
    ).get(started["id"])
    assert restored == state


def test_paper_manager_cancels_cooperatively(tmp_path):
    runner = FakePaperRunner(complete=False)
    manager = PaperSessionManager(
        runner_factory=lambda request, session_id, agents: runner,
        storage_root=tmp_path / "paper",
        dataset_root=tmp_path / "dataset",
        agent_root=tmp_path / "agents",
    )
    started = manager.start(_request())

    assert manager.cancel(started["id"]) is True
    assert runner.stopped is True
