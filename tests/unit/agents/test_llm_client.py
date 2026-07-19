import asyncio
from types import SimpleNamespace

import pytest

from traderharness.agents.llm_client import LLMClient
from traderharness.trajectory.replay import ReplayExhaustedError


class StubReplayPlayer:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def require_response(self, *, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        if self.response is None:
            raise ReplayExhaustedError("Replay cassette exhausted")
        return self.response


@pytest.mark.asyncio
async def test_replay_client_returns_cassette_without_initializing_provider():
    player = StubReplayPlayer({"role": "assistant", "content": "replayed"})
    client = LLMClient(
        model="replay",
        api_key="",
        replay_player=player,
        cache_enabled=False,
    )

    response = await client.chat([{"role": "user", "content": "prompt"}], tools=[])

    assert response["content"] == "replayed"
    assert client._client is None
    assert player.calls == [
        {
            "messages": [{"role": "user", "content": "prompt"}],
            "tools": [],
        }
    ]


@pytest.mark.asyncio
async def test_replay_client_never_falls_back_to_network_when_exhausted():
    client = LLMClient(
        model="replay",
        api_key="",
        replay_player=StubReplayPlayer(),
        cache_enabled=False,
    )

    with pytest.raises(ReplayExhaustedError):
        await client.chat([{"role": "user", "content": "unexpected extra call"}])

    assert client._client is None


# ---------------------------------------------------------------------------
# Fakes standing in for the openai.AsyncOpenAI client surface used by
# LLMClient._call_with_retry: self._client.chat.completions.create(**kwargs).
# ---------------------------------------------------------------------------


class FakeMessage:
    def __init__(self, content=None, tool_calls=None, reasoning_content=None):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content


class FakeChoice:
    def __init__(self, message, finish_reason="stop"):
        self.message = message
        self.finish_reason = finish_reason


class FakeUsage:
    def __init__(self, prompt_tokens=10, completion_tokens=5, total_tokens=15):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class FakeResponse:
    def __init__(self, message, finish_reason="stop", usage=None):
        self.choices = [FakeChoice(message, finish_reason)]
        self.usage = usage if usage is not None else FakeUsage()


class RecordingCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeAsyncOpenAI:
    def __init__(self, responses):
        completions = RecordingCompletions(responses)
        self.chat = SimpleNamespace(completions=completions)

    @property
    def calls(self):
        return self.chat.completions.calls


class TestThinkingModeExtraBody:
    @pytest.mark.asyncio
    async def test_thinking_model_sends_thinking_extra_body_and_high_reasoning_effort(self):
        fake = FakeAsyncOpenAI([FakeResponse(FakeMessage(content="ok"))])
        client = LLMClient(model="deepseek-v4-pro", api_key="test", cache_enabled=False)
        client._client = fake

        await client.chat([{"role": "user", "content": "hi"}])

        call = fake.calls[0]
        assert call["extra_body"] == {"thinking": {"type": "enabled"}}
        assert call["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_thinking_model_does_not_send_temperature(self):
        fake = FakeAsyncOpenAI([FakeResponse(FakeMessage(content="ok"))])
        client = LLMClient(
            model="deepseek-reasoner", api_key="test", cache_enabled=False, temperature=0.9
        )
        client._client = fake

        await client.chat([{"role": "user", "content": "hi"}], temperature=0.2)

        call = fake.calls[0]
        assert "temperature" not in call

    @pytest.mark.asyncio
    async def test_non_thinking_model_sends_temperature_without_thinking_extras(self):
        fake = FakeAsyncOpenAI([FakeResponse(FakeMessage(content="ok"))])
        client = LLMClient(model="deepseek-chat", api_key="test", cache_enabled=False)
        client._client = fake

        await client.chat([{"role": "user", "content": "hi"}])

        call = fake.calls[0]
        assert call["temperature"] == pytest.approx(0.7)
        assert "extra_body" not in call
        assert "reasoning_effort" not in call

    @pytest.mark.asyncio
    async def test_explicit_thinking_flag_enables_thinking_mode_for_any_model(self):
        fake = FakeAsyncOpenAI([FakeResponse(FakeMessage(content="ok"))])
        client = LLMClient(
            model="some-custom-model", api_key="test", cache_enabled=False, thinking=True
        )
        client._client = fake

        await client.chat([{"role": "user", "content": "hi"}])

        call = fake.calls[0]
        assert call["extra_body"] == {"thinking": {"type": "enabled"}}
        assert call["reasoning_effort"] == "high"

    @pytest.mark.asyncio
    async def test_explicit_reasoning_effort_enables_thinking_mode_and_is_forwarded(self):
        fake = FakeAsyncOpenAI([FakeResponse(FakeMessage(content="ok"))])
        client = LLMClient(
            model="some-custom-model",
            api_key="test",
            cache_enabled=False,
            reasoning_effort="medium",
        )
        client._client = fake

        await client.chat([{"role": "user", "content": "hi"}])

        call = fake.calls[0]
        assert call["extra_body"] == {"thinking": {"type": "enabled"}}
        assert call["reasoning_effort"] == "medium"


class TestFinishReasonAndReasoningContent:
    @pytest.mark.asyncio
    async def test_finish_reason_is_captured_on_response(self):
        fake = FakeAsyncOpenAI(
            [FakeResponse(FakeMessage(content="partial"), finish_reason="length")]
        )
        client = LLMClient(model="deepseek-chat", api_key="test", cache_enabled=False)
        client._client = fake

        response = await client.chat([{"role": "user", "content": "hi"}])

        assert response["_finish_reason"] == "length"

    @pytest.mark.asyncio
    async def test_reasoning_content_is_preserved_alongside_tool_calls(self):
        tool_call = SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name="get_kline", arguments="{}"),
        )
        message = FakeMessage(content=None, tool_calls=[tool_call], reasoning_content="思考过程")
        fake = FakeAsyncOpenAI([FakeResponse(message)])
        client = LLMClient(model="deepseek-v4-pro", api_key="test", cache_enabled=False)
        client._client = fake

        response = await client.chat(
            [{"role": "user", "content": "hi"}], tools=[{"type": "function"}]
        )

        assert response["reasoning_content"] == "思考过程"
        assert response["tool_calls"][0]["function"]["name"] == "get_kline"


class TestAsyncRetryBackoff:
    @pytest.mark.asyncio
    async def test_rate_limit_retry_uses_asyncio_sleep_not_blocking_time_sleep(self, monkeypatch):
        sleep_calls = []

        async def fake_asyncio_sleep(seconds):
            sleep_calls.append(seconds)

        monkeypatch.setattr(
            "traderharness.agents.llm_client.asyncio.sleep", fake_asyncio_sleep
        )

        import traderharness.agents.llm_client as llm_client_module

        assert not hasattr(llm_client_module, "time"), (
            "llm_client module must not import blocking time.sleep for retry backoff"
        )

        fake = FakeAsyncOpenAI(
            [RuntimeError("429 rate limited"), FakeResponse(FakeMessage(content="ok"))]
        )
        client = LLMClient(
            model="deepseek-chat", api_key="test", cache_enabled=False, max_retries=2
        )
        client._client = fake

        response = await client.chat([{"role": "user", "content": "hi"}])

        assert response["content"] == "ok"
        assert sleep_calls, "expected asyncio.sleep to be used for retry backoff"


class TestConcurrencyLimiter:
    @pytest.mark.asyncio
    async def test_shared_semaphore_bounds_simultaneous_calls_across_clients(self):
        state = {"current": 0, "max": 0}
        lock = asyncio.Lock()

        class TrackingCompletions:
            async def create(self, **kwargs):
                async with lock:
                    state["current"] += 1
                    state["max"] = max(state["max"], state["current"])
                await asyncio.sleep(0.05)
                async with lock:
                    state["current"] -= 1
                return FakeResponse(FakeMessage(content="ok"))

        semaphore = asyncio.Semaphore(2)
        clients = []
        for _ in range(4):
            client = LLMClient(
                model="deepseek-chat",
                api_key="test",
                cache_enabled=False,
                concurrency_limiter=semaphore,
            )
            client._client = SimpleNamespace(
                chat=SimpleNamespace(completions=TrackingCompletions())
            )
            clients.append(client)

        await asyncio.gather(
            *(client.chat([{"role": "user", "content": "hi"}]) for client in clients)
        )

        assert state["max"] <= 2
