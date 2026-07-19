import asyncio
import time

from traderharness.core.live_feed import LiveFeed
from traderharness.server.app import RunRequest
from traderharness.server.run_manager import RunManager


class FakeRunner:
    def __init__(self, complete=True):
        self.feed = LiveFeed()
        self.running = False
        self.error = None
        self.result_path = None
        self.stopped = False
        self.complete = complete

    def start(self):
        self.running = True
        self.feed.push("phase_change", phase="pre_market")
        self.feed.push("tool_call", tool="get_market_overview")
        if self.complete:
            self.feed.push("run_end", trading_days=1)
            self.running = False

    def stop(self):
        self.stopped = True
        self.running = False
        if not self.feed.done:
            self.feed.push("run_end", trading_days=0, cancelled=True)


def _request():
    return RunRequest(
        agents=["momentum-dragon"],
        start_date="2024-03-14",
        end_date="2024-03-14",
        initial_cash=1_000_000,
        mask_entities=True,
        entity_mask_seed=42,
    )


def test_run_manager_journals_events_for_late_websocket_subscribers():
    runner = FakeRunner()
    manager = RunManager(runner_factory=lambda request, run_id: runner)

    state = manager.start(_request())
    deadline = time.time() + 1
    while manager.get(state["id"])["status"] == "running" and time.time() < deadline:
        time.sleep(0.01)

    async def collect():
        return [event async for event in manager.events(state["id"])]

    events = asyncio.run(collect())
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert [event["type"] for event in events] == [
        "phase_change",
        "tool_call",
        "run_end",
    ]
    assert manager.get(state["id"])["status"] == "done"


def test_run_manager_forwards_cooperative_cancellation():
    runner = FakeRunner(complete=False)
    manager = RunManager(runner_factory=lambda request, run_id: runner)
    state = manager.start(_request())

    assert manager.cancel(state["id"]) is True
    assert runner.stopped is True
    assert manager.get(state["id"])["status"] == "cancelling"


def test_run_manager_lists_runs_newest_first():
    manager = RunManager(runner_factory=lambda request, run_id: FakeRunner())
    first = manager.start(_request())
    second = manager.start(_request())

    runs = manager.list()

    assert [run["id"] for run in runs] == [second["id"], first["id"]]
