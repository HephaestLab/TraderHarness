"""Read-only multi-role advisors with a single trading executor."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from traderharness.agents.tool_agent import ToolAgent


@dataclass(frozen=True)
class Advisor:
    role: str
    llm_client: Any
    instructions: str

    def build_prompt(self, messages: list[dict], phase: str, sub_window: str | None) -> list[dict]:
        """Build this advisor's request messages, deterministically from its
        inputs. Exposed (not private) so recorded and replayed calls can be
        verified/constructed against the exact same prompt.
        """
        transcript = json.dumps(messages[-20:], ensure_ascii=False, default=str)
        if len(transcript) > 40_000:
            transcript = transcript[-40_000:]
        return [
            {
                "role": "system",
                "content": (
                    f"你是交易委员会中的{self.role}顾问。{self.instructions}\n"
                    "你只能给出分析建议，不能调用工具、不能下单。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"阶段: {phase}; 子窗口: {sub_window or '无'}\n"
                    "以下内容已经过环境的日期与实体遮罩。请基于它给执行交易员一份"
                    f"简洁、有证据、可被反驳的建议：\n{transcript}"
                ),
            },
        ]

    async def advise(self, messages: list[dict], phase: str, sub_window: str | None) -> str:
        prompt = self.build_prompt(messages, phase, sub_window)
        response = await self.llm_client.chat(messages=prompt, tools=None)
        record_replay_call = getattr(self.llm_client, "record_replay_call", None)
        if record_replay_call is not None:
            record_replay_call(messages=prompt, tools=None, output=response)
        return (response.get("content") or response.get("reasoning_content") or "").strip()


@dataclass(frozen=True)
class CommitteeMemo:
    phase: str
    sub_window: str | None
    reports: dict[str, str]

    def to_prompt(self) -> str:
        lines = [
            "<committee_advice>",
            f"阶段: {self.phase}; 子窗口: {self.sub_window or '无'}",
            "以下是只读顾问意见。你是唯一执行者，须独立判断并对下单负责。",
        ]
        for role, report in self.reports.items():
            lines.append(f"\n[{role}]\n{report or '（未提供意见）'}")
        lines.append("</committee_advice>")
        return "\n".join(lines)


class CommitteeCoordinator:
    def __init__(self, advisors: list[Advisor]) -> None:
        if not advisors:
            raise ValueError("CommitteeCoordinator requires at least one advisor")
        roles = [advisor.role for advisor in advisors]
        if len(roles) != len(set(roles)):
            raise ValueError("Advisor roles must be unique")
        self.advisors = list(advisors)

    async def build_memo(
        self,
        messages: list[dict],
        phase: str,
        sub_window: str | None,
    ) -> CommitteeMemo:
        results = await asyncio.gather(
            *(advisor.advise(messages, phase, sub_window) for advisor in self.advisors),
            return_exceptions=True,
        )
        reports = {}
        for advisor, result in zip(self.advisors, results, strict=True):
            if isinstance(result, BaseException):
                reports[advisor.role] = f"ERROR {type(result).__name__}: {result}"
            else:
                reports[advisor.role] = result
        return CommitteeMemo(phase=phase, sub_window=sub_window, reports=reports)


def build_committee_from_config(
    configs: list[dict],
    *,
    client_factory=None,
    agent_id: str | None = None,
    replay_recorder: Any | None = None,
    replay_player: Any | None = None,
) -> CommitteeCoordinator:
    """Build advisors from YAML-compatible role/model/prompt dictionaries.

    When `agent_id` is given together with a `replay_recorder`
    (`traderharness.trajectory.bundle.ScopedReplayRecorder`) and/or
    `replay_player` (`...bundle.ScopedReplayPlayer`), and no custom
    `client_factory` overrides advisor construction, each advisor's LLM
    client is scoped to `advisor_scope_id(agent_id, role)` so its calls are
    recorded/replayed independently of the executor and of other advisors.
    """
    use_default_factory = client_factory is None
    if use_default_factory:
        from traderharness.agents.llm_client import LLMClient

        def client_factory(model):
            return LLMClient(model=model)

    wants_scoping = (
        use_default_factory
        and agent_id is not None
        and (replay_recorder is not None or replay_player is not None)
    )
    if wants_scoping:
        from traderharness.agents.llm_client import LLMClient
        from traderharness.trajectory.bundle import advisor_scope_id

    advisors = []
    for config in configs:
        role = str(config.get("role", "")).strip()
        if not role:
            raise ValueError("Each advisor requires a non-empty role")

        if wants_scoping:
            scope = advisor_scope_id(agent_id, role)
            scoped_player = replay_player.scope(scope) if replay_player is not None else None
            scoped_recorder = (
                replay_recorder.scope(scope) if replay_recorder is not None else None
            )
            llm_client = LLMClient(
                model=config.get("model"),
                api_key="replay" if scoped_player is not None else None,
                cache_enabled=False,
                replay_recorder=scoped_recorder,
                replay_player=scoped_player,
            )
        else:
            llm_client = client_factory(config.get("model"))

        advisors.append(
            Advisor(
                role=role,
                llm_client=llm_client,
                instructions=str(config.get("prompt", "")).strip(),
            )
        )
    return CommitteeCoordinator(advisors)


class CommitteeAgent(ToolAgent):
    """ToolAgent whose sole executor receives concurrent advisor memos."""

    def __init__(self, *, advisors: list[Advisor], **tool_agent_kwargs) -> None:
        super().__init__(
            committee=CommitteeCoordinator(advisors),
            **tool_agent_kwargs,
        )
