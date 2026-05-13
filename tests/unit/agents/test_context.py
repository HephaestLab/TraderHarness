"""Tests for ContextManager."""

from finharness.agents.context import ContextManager


class TestContextManager:
    def test_add_and_retrieve(self):
        ctx = ContextManager()
        ctx.add_message({"role": "system", "content": "You are a trader."})
        ctx.add_message({"role": "user", "content": "What should I buy?"})
        assert len(ctx.messages) == 2

    def test_estimate_tokens(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "a" * 400})
        assert ctx.estimate_tokens() > 0

    def test_needs_compression(self):
        ctx = ContextManager(max_context_tokens=100)
        ctx.add_message({"role": "system", "content": "sys"})
        for i in range(20):
            ctx.add_message({"role": "user", "content": "x" * 200})
        assert ctx.needs_compression() is True

    def test_reset(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "hello"})
        ctx.reset()
        assert len(ctx.messages) == 0

    def test_messages_property(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "hi"})
        assert ctx.messages[0]["content"] == "hi"
