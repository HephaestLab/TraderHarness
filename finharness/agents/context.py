"""上下文管理器 — token 估算 + 自动压缩。

直接从源项目 backend/agents/agentic/context_manager.py 迁移。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ContextManager:
    """管理 agentic 对话的 messages 列表，提供 token 估算和压缩。"""

    def __init__(
        self,
        max_context_tokens: int = 60000,
        compression_threshold: float = 0.75,
    ) -> None:
        self.max_context_tokens = max_context_tokens
        self.compression_threshold = compression_threshold
        self._messages: list[dict] = []

    @property
    def messages(self) -> list[dict]:
        return self._messages

    def add_message(self, message: dict) -> None:
        self._messages.append(message)

    def get_api_messages(self) -> list[dict]:
        """Return messages safe for the OpenAI API (no orphan tool messages)."""
        result = []
        has_pending_tool_calls = False
        for msg in self._messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                has_pending_tool_calls = True
                result.append(msg)
            elif msg.get("role") == "tool":
                if has_pending_tool_calls:
                    result.append(msg)
                # else: skip orphan tool message
            else:
                has_pending_tool_calls = False
                result.append(msg)
        return result

    def reset(self) -> None:
        self._messages = []

    def estimate_tokens(self) -> int:
        total_chars = 0
        for msg in self._messages:
            content = msg.get("content", "")
            if content:
                total_chars += len(content)
            for tc in msg.get("tool_calls", []):
                args = tc.get("function", {}).get("arguments", "")
                total_chars += len(args)
        return int(total_chars * 0.7)

    def needs_compression(self) -> bool:
        return self.estimate_tokens() > self.max_context_tokens * self.compression_threshold

    async def compress(self, llm_client=None) -> None:
        """压缩早期的 tool call/result 对为摘要。

        确保不会把 tool_calls assistant 和 tool response 分开。
        """
        if len(self._messages) < 10:
            return

        system_msgs = [m for m in self._messages if m.get("role") == "system"]
        non_system = [m for m in self._messages if m.get("role") != "system"]

        if len(non_system) <= 6:
            return

        # Find safe split point: don't split in the middle of a tool interaction
        split_idx = len(non_system) - 6
        # Walk forward to ensure we don't start to_keep with a 'tool' message
        while split_idx < len(non_system) and non_system[split_idx].get("role") == "tool":
            split_idx -= 1
        # Also don't split right after an assistant with tool_calls (keep the tool responses together)
        if split_idx > 0 and non_system[split_idx - 1].get("role") == "assistant" and non_system[split_idx - 1].get("tool_calls"):
            split_idx -= 1

        if split_idx <= 0:
            return

        to_compress = non_system[:split_idx]
        to_keep = non_system[split_idx:]

        compress_text = []
        for msg in to_compress:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "assistant" and msg.get("tool_calls"):
                tools = [tc.get("function", {}).get("name", "?") for tc in msg["tool_calls"]]
                compress_text.append(f"[调用工具: {', '.join(tools)}]")
            elif role == "tool":
                preview = content[:100] + "..." if len(content) > 100 else content
                compress_text.append(f"[工具结果: {preview}]")
            elif content:
                preview = content[:150] + "..." if len(content) > 150 else content
                compress_text.append(f"[{role}: {preview}]")

        summary_content = "=== 前序分析摘要（已压缩）===\n" + "\n".join(compress_text)

        self._messages = system_msgs + [
            {"role": "user", "content": summary_content}
        ] + to_keep

        logger.info(
            "context_compressed: compressed=%d remaining=%d est_tokens=%d",
            len(to_compress), len(self._messages), self.estimate_tokens(),
        )
