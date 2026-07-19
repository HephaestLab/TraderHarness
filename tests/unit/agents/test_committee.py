"""Multi-role committee advisors remain read-only and concurrent."""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from traderharness.agents.committee import (
    Advisor,
    CommitteeCoordinator,
    CommitteeMemo,
    build_committee_from_config,
)
from traderharness.agents.loop import AgentLoop
from traderharness.agents.prompt_agent import PromptAgent
from traderharness.core.entity_masking import EntityMasker
from traderharness.core.masking import DateMasker
from traderharness.tools.registry import ToolRegistry
from traderharness.trajectory.bundle import (
    ScopedReplayPlayer,
    ScopedReplayRecorder,
    advisor_scope_id,
)
from traderharness.trajectory.collector import TrajectoryCollector


class BarrierClient:
    def __init__(self, state, content):
        self.state = state
        self.content = content
        self.calls = []

    async def chat(self, messages, tools=None, temperature=None):
        self.calls.append({"messages": messages, "tools": tools})
        self.state["entered"] += 1
        if self.state["entered"] == 2:
            self.state["ready"].set()
        await asyncio.wait_for(self.state["ready"].wait(), timeout=0.2)
        return {"content": self.content}


@pytest.mark.asyncio
async def test_advisors_run_concurrently_without_tools():
    state = {"entered": 0, "ready": asyncio.Event()}
    bull_client = BarrierClient(state, "看多")
    bear_client = BarrierClient(state, "看空")
    coordinator = CommitteeCoordinator(
        [
            Advisor("bull", bull_client, "寻找上涨证据"),
            Advisor("bear", bear_client, "寻找下跌风险"),
        ]
    )

    memo = await coordinator.build_memo(
        [{"role": "user", "content": "公司-600000上涨"}],
        phase="pre_market",
        sub_window=None,
    )

    assert memo.reports == {"bull": "看多", "bear": "看空"}
    assert all(call["tools"] is None for call in bull_client.calls + bear_client.calls)
    assert "place_order" not in str(bull_client.calls + bear_client.calls)


class FailingClient:
    async def chat(self, messages, tools=None, temperature=None):
        raise RuntimeError("provider unavailable")


@pytest.mark.asyncio
async def test_advisor_failure_is_explicit_in_memo():
    coordinator = CommitteeCoordinator([Advisor("risk", FailingClient(), "检查风险")])

    memo = await coordinator.build_memo([], phase="close_window", sub_window="close_1")

    assert "ERROR RuntimeError" in memo.reports["risk"]
    assert "provider unavailable" in memo.reports["risk"]


class RecordingExecutor:
    def __init__(self, content="综合顾问意见后暂不操作", reasoning_content=None):
        self.messages = None
        self.content = content
        self.reasoning_content = reasoning_content
        self.recorded = []

    async def chat(self, messages, tools=None, temperature=None):
        self.messages = messages
        response = {"content": self.content}
        if self.reasoning_content is not None:
            response["reasoning_content"] = self.reasoning_content
        return response

    def record_replay_call(self, **call):
        self.recorded.append(call)


class StubCommittee:
    def __init__(self):
        self.calls = []

    async def build_memo(self, messages, phase, sub_window):
        self.calls.append((messages, phase, sub_window))
        return CommitteeMemo(phase, sub_window, {"risk": "仓位应保持保守"})


@pytest.mark.asyncio
async def test_agent_loop_injects_one_committee_memo_before_executor():
    executor = RecordingExecutor()
    committee = StubCommittee()
    loop = AgentLoop(
        executor,
        ToolRegistry(),
        "system",
        committee=committee,
    )
    loop._context.add_message({"role": "user", "content": "晨报"})
    ctx = SimpleNamespace(
        current_date=date(2024, 3, 4),
        current_phase="pre_market",
        _current_sub_window=None,
    )

    await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

    assert len(committee.calls) == 1
    assert committee.calls[0][1:] == ("pre_market", None)
    assert "仓位应保持保守" in str(executor.messages)


def test_prompt_agent_loads_yaml_advisor_roles(tmp_path):
    config = tmp_path / "committee.yaml"
    config.write_text(
        """
id: committee
name: Committee
advisors:
  - role: fundamentals
    model: deepseek-chat
    prompt: 检查基本面
  - role: bear
    model: deepseek-chat
    prompt: 识别下行风险
""",
        encoding="utf-8",
    )

    agent = PromptAgent(config, llm_client=RecordingExecutor())

    assert [advisor.role for advisor in agent._loop.committee.advisors] == [
        "fundamentals",
        "bear",
    ]
    assert agent._registry.get_tool("place_order") is not None


@pytest.mark.asyncio
async def test_executor_generated_real_identity_and_date_are_sanitized():
    executor = RecordingExecutor(
        "华域汽车在2024年3月4日值得关注",
        reasoning_content="先检查2024年3月4日的华域汽车",
    )
    loop = AgentLoop(executor, ToolRegistry(), "system")
    loop._context.add_message({"role": "user", "content": "晨报"})
    ctx = SimpleNamespace(
        current_date=date(2024, 3, 4),
        current_phase="pre_market",
        _current_sub_window=None,
        date_masker=DateMasker(date(2024, 3, 4)),
        entity_masker=EntityMasker(
            ["600741", "600742"],
            names={"600741": "华域汽车", "600742": "一汽富维"},
            seed=1,
        ),
    )

    await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

    content = loop._context.get_api_messages()[-1]["content"]
    assert "华域汽车" not in content
    assert "2024年3月4日" not in content
    assert "D+0" in content
    recorded = executor.recorded[0]["output"]["content"]
    assert "华域汽车" not in recorded
    assert "2024年3月4日" not in recorded
    recorded_reasoning = executor.recorded[0]["output"]["reasoning_content"]
    assert "华域汽车" not in recorded_reasoning
    assert "2024年3月4日" not in recorded_reasoning


@pytest.mark.asyncio
async def test_agent_loop_records_full_fidelity_llm_exchange_without_truncation():
    executor = RecordingExecutor("完整分析" * 200, reasoning_content="推理过程" * 200)
    loop = AgentLoop(executor, ToolRegistry(), "system")
    loop.trajectory = TrajectoryCollector("test")
    loop._context.add_message({"role": "user", "content": "晨报"})
    ctx = SimpleNamespace(
        current_date=date(2024, 3, 4),
        current_phase="pre_market",
        _current_sub_window=None,
    )

    await loop._run_phase(ctx, max_iter=1, exclude_tools=set())

    exchange = next(
        record for record in loop.trajectory.step_records if record.type == "llm_exchange"
    )
    next(record for record in loop.trajectory.step_records if record.type == "assistant")
    assert exchange.data["messages"][-1]["content"] == "晨报"
    assert exchange.data["response"]["content"] == "完整分析" * 200
    assert exchange.data["response"]["reasoning_content"] == "推理过程" * 200


def test_build_committee_from_config_scopes_each_advisor_to_a_replay_recorder(tmp_path):
    """Advisor LLM calls must be recordable independently, per role, for
    deterministic replay of the whole committee (executor + every advisor).
    """
    recorder = ScopedReplayRecorder()

    coordinator = build_committee_from_config(
        [
            {"role": "fundamentals", "model": "deepseek-chat", "prompt": "检查基本面"},
            {"role": "bear", "model": "deepseek-chat", "prompt": "识别下行风险"},
        ],
        agent_id="committee-1",
        replay_recorder=recorder,
    )

    fundamentals_client = next(
        a.llm_client for a in coordinator.advisors if a.role == "fundamentals"
    )
    bear_client = next(a.llm_client for a in coordinator.advisors if a.role == "bear")

    assert fundamentals_client._recorder is not None
    assert bear_client._recorder is not None
    assert fundamentals_client._recorder is not bear_client._recorder

    fundamentals_client.record_replay_call(
        messages=[{"role": "user", "content": "fundamentals prompt"}],
        tools=None,
        output={"role": "assistant", "content": "看多基本面"},
    )
    bear_client.record_replay_call(
        messages=[{"role": "user", "content": "bear prompt"}],
        tools=None,
        output={"role": "assistant", "content": "警惕下行"},
    )

    assert sorted(recorder.scope_ids) == [
        advisor_scope_id("committee-1", "bear"),
        advisor_scope_id("committee-1", "fundamentals"),
    ]
    fundamentals_entries = recorder.recorder_for(
        advisor_scope_id("committee-1", "fundamentals")
    ).entries
    bear_entries = recorder.recorder_for(advisor_scope_id("committee-1", "bear")).entries
    assert len(fundamentals_entries) == 1
    assert fundamentals_entries[0]["output"]["content"] == "看多基本面"
    assert len(bear_entries) == 1
    assert bear_entries[0]["output"]["content"] == "警惕下行"


@pytest.mark.asyncio
async def test_scoped_advisor_cassette_replays_deterministically(tmp_path):
    """A committee advisor recorded via ScopedReplayRecorder can be replayed
    from the saved bundle without touching the network.
    """
    from datetime import date

    from traderharness.trajectory.bundle import AgentManifestEntry, ReplayBundleManifest

    recorder = ScopedReplayRecorder()
    coordinator = build_committee_from_config(
        [{"role": "risk", "model": "deepseek-chat", "prompt": "检查风险"}],
        agent_id="committee-1",
        replay_recorder=recorder,
    )
    risk_advisor = coordinator.advisors[0]
    prompt = risk_advisor.build_prompt([], phase="pre_market", sub_window=None)
    risk_advisor.llm_client.record_replay_call(
        messages=prompt,
        tools=None,
        output={"role": "assistant", "content": "仓位应保持保守"},
    )

    bundle_dir = tmp_path / "bundle"
    manifest = ReplayBundleManifest(
        start_date=date(2024, 3, 4),
        end_date=date(2024, 3, 4),
        agents=[AgentManifestEntry(id="committee-1")],
    )
    recorder.save_bundle(bundle_dir, manifest)

    player = ScopedReplayPlayer(bundle_dir)
    replay_coordinator = build_committee_from_config(
        [{"role": "risk", "model": "deepseek-chat", "prompt": "检查风险"}],
        agent_id="committee-1",
        replay_player=player,
    )

    memo = await replay_coordinator.build_memo([], phase="pre_market", sub_window=None)

    assert memo.reports["risk"] == "仓位应保持保守"
