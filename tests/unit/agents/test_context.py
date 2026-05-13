"""Tests for ContextManager."""

from finharness.agents.context import ContextManager


class TestContextManager:
    def test_add_and_retrieve(self):
        ctx = ContextManager()
        ctx.add_message({"role": "system", "content": "You are a trader."})
        ctx.add_message({"role": "user", "content": "What should I buy?"})
        assert len(ctx.messages) == 2

    def test_estimated_tokens(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "a" * 400})
        assert ctx.estimated_tokens > 0

    def test_compression_when_over_limit(self):
        ctx = ContextManager(max_context_tokens=100)
        ctx.add_message({"role": "system", "content": "sys"})
        for i in range(20):
            ctx.add_message({"role": "user", "content": "x" * 200})
        # After compression, should be much less than 20 user messages
        assert len(ctx.messages) <= 8

    def test_reset(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "hello"})
        ctx.reset()
        assert len(ctx.messages) == 0

    def test_get_messages_for_api(self):
        ctx = ContextManager()
        ctx.add_message({"role": "user", "content": "hi", "extra_field": True})
        msgs = ctx.get_messages_for_api()
        assert "extra_field" not in msgs[0]
        assert msgs[0]["content"] == "hi"
