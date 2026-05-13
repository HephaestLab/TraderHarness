"""OpenAI-compatible LLM client with retry, caching, and rate limiting."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".finharness" / "llm_cache"


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
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.cache_enabled = cache_enabled

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
    ) -> dict:
        """Send chat completion request. Returns the response message dict."""
        if self.cache_enabled:
            cached = self._cache_get(messages, tools)
            if cached is not None:
                return cached

        response = await self._call_with_retry(messages, tools, temperature)

        if self.cache_enabled:
            self._cache_put(messages, tools, response)

        return response

    async def _call_with_retry(
        self, messages: list[dict], tools: list[dict] | None, temperature: float | None
    ) -> dict:
        self._ensure_client()
        temp = temperature if temperature is not None else self.temperature

        for attempt in range(self.max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temp,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                resp = await self._client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message

                if resp.usage:
                    self._total_tokens += resp.usage.total_tokens

                result: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }
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
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = min(2 ** attempt * 10, 60)
                    logger.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt + 1)
                    if attempt == self.max_retries - 1:
                        raise RateLimitError(wait)
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("Max retries exceeded")

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key, base_url=self._base_url
            )
        except ImportError:
            raise ImportError("openai not installed. Run: pip install finharness[llm]")

    def _cache_key(self, messages: list[dict], tools: list[dict] | None) -> str:
        content = json.dumps({"messages": messages, "tools": tools, "model": self.model}, sort_keys=True)
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
