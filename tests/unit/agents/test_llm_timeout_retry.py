"""Transient API timeouts must be retried like rate limits."""

from unittest.mock import MagicMock

import pytest

from traderharness.agents.llm_client import LLMClient


class APITimeoutError(Exception):
    pass


@pytest.mark.asyncio
async def test_retries_api_timeout_then_succeeds():
    client = LLMClient(
        model="deepseek-chat", api_key="test", cache_enabled=False, max_retries=3
    )
    client._client = MagicMock()
    attempts = {"n": 0}

    async def create(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise APITimeoutError("Request timed out")
        message = MagicMock(content="ok", tool_calls=None, reasoning_content=None)
        choice = MagicMock(message=message, finish_reason="stop")
        return MagicMock(choices=[choice], usage=None)

    client._client.chat.completions.create = create
    result = await client.chat([{"role": "user", "content": "hi"}])
    assert attempts["n"] == 3
    assert result["content"] == "ok"
