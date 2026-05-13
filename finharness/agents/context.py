"""ContextManager — token estimation and automatic context compression."""

from __future__ import annotations


class ContextManager:
    """Manages conversation context with token budget awareness."""

    def __init__(self, max_context_tokens: int = 60_000) -> None:
        self._max_tokens = max_context_tokens
        self._messages: list[dict] = []

    @property
    def messages(self) -> list[dict]:
        return list(self._messages)

    @property
    def estimated_tokens(self) -> int:
        return sum(self._estimate_message_tokens(m) for m in self._messages)

    def add_message(self, message: dict) -> None:
        self._messages.append(message)
        if self.estimated_tokens > self._max_tokens:
            self._compress()

    def reset(self) -> None:
        self._messages = []

    def get_messages_for_api(self) -> list[dict]:
        return [self._clean_message(m) for m in self._messages]

    def _compress(self) -> None:
        if len(self._messages) <= 3:
            return
        system_msgs = [m for m in self._messages if m.get("role") == "system"]
        other_msgs = [m for m in self._messages if m.get("role") != "system"]
        keep_recent = other_msgs[-6:] if len(other_msgs) > 6 else other_msgs
        self._messages = system_msgs + keep_recent

    @staticmethod
    def _estimate_message_tokens(message: dict) -> int:
        content = message.get("content", "") or ""
        tool_calls = message.get("tool_calls", [])
        text_len = len(content)
        for tc in tool_calls:
            text_len += len(tc.get("function", {}).get("arguments", ""))
        return text_len // 4 + 4

    @staticmethod
    def _clean_message(message: dict) -> dict:
        clean = {"role": message["role"]}
        if message.get("content"):
            clean["content"] = message["content"]
        if message.get("tool_calls"):
            clean["tool_calls"] = message["tool_calls"]
        if message.get("tool_call_id"):
            clean["tool_call_id"] = message["tool_call_id"]
        if message.get("name"):
            clean["name"] = message["name"]
        return clean
