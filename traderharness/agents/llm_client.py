"""OpenAI-compatible LLM client with retry, caching, and rate limiting."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any

from traderharness.paths import llm_cache_dir

logger = logging.getLogger(__name__)

_CACHE_DIR = llm_cache_dir()

# Models that support DeepSeek-style extended thinking ("reasoning") mode.
# Matched as a prefix so date/size suffixes (e.g. "-0528") still match.
_THINKING_MODEL_PREFIXES = ("deepseek-v4-pro", "deepseek-reasoner")


class RateLimitError(Exception):
    """Raised when LLM API returns 429."""

    def __init__(self, retry_after: float = 60.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")


class LLMClient:
    """OpenAI-compatible client (works with DeepSeek, GPT, Claude, Qwen)."""

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_retries: int = 3,
        cache_enabled: bool = True,
        replay_recorder: Any | None = None,
        replay_player: Any | None = None,
        thinking: bool | None = None,
        reasoning_effort: str | None = None,
        concurrency_limiter: asyncio.Semaphore | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.cache_enabled = cache_enabled
        self._recorder = replay_recorder
        self._player = replay_player
        self._replay_step: int = 0
        self._concurrency_limiter = concurrency_limiter

        # Thinking mode detection: explicit `thinking` wins; otherwise a
        # thinking-capable model name or an explicit `reasoning_effort`
        # implies thinking mode. DeepSeek thinking mode ignores temperature,
        # so it must never be sent alongside extra_body.thinking.
        if thinking is not None:
            self._thinking = thinking
        else:
            self._thinking = bool(reasoning_effort) or self._is_thinking_model(model)
        self._reasoning_effort = reasoning_effort or ("high" if self._thinking else None)

        self._api_key = api_key or self._resolve_api_key(model)
        self._base_url = base_url or self._resolve_base_url(model)
        self._client: Any = None
        self._total_tokens = 0

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Send chat completion request. Returns the response message dict.

        Note: tool-based calls are NOT cached (agentic conversations are stateful).
        Only plain chat (no tools) is cached.
        """
        # Replay mode: return pre-recorded response
        if self._player:
            return self._player.require_response(messages=messages, tools=tools)

        if self.cache_enabled and not tools:
            cached = self._cache_get(messages, tools)
            if cached is not None:
                return cached

        response = await self._call_with_retry(messages, tools, temperature, max_tokens)

        if self.cache_enabled and not tools:
            self._cache_put(messages, tools, response)

        return response

    def record_replay_call(
        self,
        *,
        messages: list[dict],
        tools: list[dict] | None,
        output: dict,
    ) -> None:
        """Record an Agent-sanitized response for deterministic replay."""
        if self._recorder is None:
            return
        self._recorder.record_llm_call(messages=messages, tools=tools, output=output)
        self._replay_step += 1

    async def _call_with_retry(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float | None,
        max_tokens: int | None = None,
    ) -> dict:
        self._ensure_client()

        for attempt in range(self.max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                if self._thinking:
                    # DeepSeek-style thinking mode: enabled via extra_body,
                    # reasoning_effort forwarded as a top-level param.
                    # temperature is documented as having no effect in this
                    # mode, so it is intentionally never sent.
                    kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    if self._reasoning_effort:
                        kwargs["reasoning_effort"] = self._reasoning_effort
                else:
                    kwargs["temperature"] = (
                        temperature if temperature is not None else self.temperature
                    )
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                if self._concurrency_limiter is not None:
                    async with self._concurrency_limiter:
                        resp = await self._client.chat.completions.create(**kwargs)
                else:
                    resp = await self._client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message

                if resp.usage:
                    self._total_tokens += resp.usage.total_tokens

                result: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }

                finish_reason = getattr(resp.choices[0], "finish_reason", None)
                if finish_reason:
                    result["_finish_reason"] = finish_reason

                # DeepSeek thinking models return reasoning_content. This must
                # survive even when the response also carries tool_calls.
                reasoning = getattr(msg, "reasoning_content", None)
                if reasoning:
                    result["reasoning_content"] = reasoning

                if msg.tool_calls:
                    result["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                if resp.usage:
                    result["_usage"] = {
                        "prompt_tokens": resp.usage.prompt_tokens,
                        "completion_tokens": resp.usage.completion_tokens,
                        "total_tokens": resp.usage.total_tokens,
                    }
                return result

            except Exception as e:
                message = str(e).lower()
                is_rate_limited = "429" in message or "rate" in message
                is_timeout = (
                    "timeout" in message
                    or "timed out" in message
                    or e.__class__.__name__.endswith("Timeout")
                    or e.__class__.__name__.endswith("TimeoutError")
                )
                if is_rate_limited or is_timeout:
                    wait = min(2**attempt * (10 if is_rate_limited else 5), 60)
                    logger.warning(
                        "%s, waiting %ds (attempt %d/%d): %s",
                        "Rate limited" if is_rate_limited else "Transient timeout",
                        wait,
                        attempt + 1,
                        self.max_retries,
                        type(e).__name__,
                    )
                    if attempt == self.max_retries - 1:
                        if is_rate_limited:
                            raise RateLimitError(wait) from e
                        raise
                    await asyncio.sleep(wait)
                    continue
                raise

        raise RuntimeError("Max retries exceeded")

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        except ImportError:
            raise ImportError("openai not installed. Run: pip install traderharness[llm]")

    def _cache_key(self, messages: list[dict], tools: list[dict] | None) -> str:
        content = json.dumps(
            {"messages": messages, "tools": tools, "model": self.model},
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def _cache_get(self, messages: list[dict], tools: list[dict] | None) -> dict | None:
        key = self._cache_key(messages, tools)
        path = _CACHE_DIR / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _cache_put(self, messages: list[dict], tools: list[dict] | None, response: dict) -> None:
        key = self._cache_key(messages, tools)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"{key}.json"
        cacheable = {k: v for k, v in response.items() if not k.startswith("_")}
        path.write_text(json.dumps(cacheable, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _is_thinking_model(model: str) -> bool:
        lowered = model.lower()
        return any(lowered.startswith(prefix) for prefix in _THINKING_MODEL_PREFIXES)

    @staticmethod
    def _resolve_api_key(model: str) -> str:
        if "deepseek" in model.lower():
            return os.environ.get("DEEPSEEK_API_KEY", "")
        if "claude" in model.lower():
            return os.environ.get("ANTHROPIC_API_KEY", "")
        return os.environ.get("OPENAI_API_KEY", "")

    @staticmethod
    def _resolve_base_url(model: str) -> str | None:
        if "deepseek" in model.lower():
            return "https://api.deepseek.com"
        return None
