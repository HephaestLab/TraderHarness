"""Tests for the /api/config/llm endpoints — LLM credentials configurable
from the Web console without ever leaking the full API key."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from traderharness.config.llm_settings import save_llm_settings
from traderharness.server.app import create_app


class FakeRunManager:
    def start(self, request):
        return {"id": "run-1", "status": "running", "created_at": "2026-07-17T00:00:00Z"}

    def get(self, run_id):
        return None

    def list(self):
        return []

    def cancel(self, run_id):
        return False

    async def events(self, run_id):
        return
        yield


class FakeLLMClient:
    """Captures constructor kwargs and chat calls; never touches the network."""

    instances: list["FakeLLMClient"] = []
    fail_with: Exception | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat_calls: list[dict] = []
        FakeLLMClient.instances.append(self)

    async def chat(self, messages, tools=None, temperature=None, max_tokens=None):
        self.chat_calls.append(
            {"messages": messages, "tools": tools, "temperature": temperature, "max_tokens": max_tokens}
        )
        if FakeLLMClient.fail_with is not None:
            raise FakeLLMClient.fail_with
        return {"role": "assistant", "content": "pong"}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADERHARNESS_HOME", str(tmp_path / "home"))
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    FakeLLMClient.instances = []
    FakeLLMClient.fail_with = None
    return tmp_path


@pytest.fixture
def client(isolated_home: Path):
    dataset = isolated_home / "dataset"
    dataset.mkdir()
    app = create_app(
        run_manager=FakeRunManager(),
        dataset_path=dataset,
        results_path=isolated_home / "results",
        agents_path=isolated_home / "agents",
    )
    with TestClient(app) as test_client:
        yield test_client


def test_get_llm_config_reports_env_source_without_leaking_key(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-envsecret123456dUWD")

    payload = client.get("/api/config/llm").json()

    assert payload["configured"] is True
    assert payload["source"] == "env"
    assert payload["api_key_masked"] == "sk-...dUWD"
    assert payload["base_url"] == "https://api.deepseek.com"
    assert payload["base_url_source"] == "default"
    assert "sk-envsecret123456dUWD" not in json.dumps(payload)


def test_get_llm_config_reports_settings_source(client):
    save_llm_settings(api_key="sk-storedf7890abcdWXYZ", base_url="https://proxy.example.com/v1")

    payload = client.get("/api/config/llm").json()

    assert payload["configured"] is True
    assert payload["source"] == "settings"
    assert payload["api_key_masked"] == "sk-...WXYZ"
    assert payload["base_url"] == "https://proxy.example.com/v1"
    assert payload["base_url_source"] == "settings"
    assert "sk-storedf7890abcdWXYZ" not in json.dumps(payload)


def test_get_llm_config_when_unconfigured(client):
    payload = client.get("/api/config/llm").json()

    assert payload["configured"] is False
    assert payload["source"] == "none"
    assert payload["api_key_masked"] == ""
    assert payload["base_url"] == "https://api.deepseek.com"
    assert payload["base_url_source"] == "default"


def test_put_saves_and_roundtrips_without_leaking_key(client, isolated_home):
    response = client.put(
        "/api/config/llm",
        json={"api_key": "sk-newkey1234567ABCD", "base_url": "https://proxy.example.com/v1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "settings"
    assert payload["api_key_masked"] == "sk-...ABCD"
    assert "sk-newkey1234567ABCD" not in json.dumps(payload)

    on_disk = json.loads((isolated_home / "home" / "settings.json").read_text(encoding="utf-8"))
    assert on_disk["llm"] == {
        "api_key": "sk-newkey1234567ABCD",
        "base_url": "https://proxy.example.com/v1",
    }
    assert client.get("/api/config/llm").json() == payload


def test_put_rejects_invalid_base_url(client):
    assert client.put("/api/config/llm", json={"base_url": "example.com"}).status_code == 422
    assert client.put("/api/config/llm", json={"base_url": "ftp://x"}).status_code == 422


def test_put_rejects_extra_fields(client):
    assert (
        client.put("/api/config/llm", json={"api_key": "sk-xxxxxxxxYYZZ", "evil": 1}).status_code
        == 422
    )


def test_put_clear_removes_saved_settings(client):
    client.put("/api/config/llm", json={"api_key": "sk-clearable1234567"})

    cleared = client.put("/api/config/llm", json={"clear": True})

    assert cleared.status_code == 200
    payload = cleared.json()
    assert payload["configured"] is False
    assert payload["source"] == "none"


def test_llm_test_endpoint_success_uses_saved_credentials(client, monkeypatch):
    monkeypatch.setattr("traderharness.agents.llm_client.LLMClient", FakeLLMClient)
    save_llm_settings(api_key="sk-savedkey1234567", base_url="https://proxy.example.com/v1")

    response = client.post("/api/config/llm/test", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["model"] == "deepseek-chat"
    instance = FakeLLMClient.instances[0]
    assert instance.kwargs["api_key"] == "sk-savedkey1234567"
    assert instance.kwargs["base_url"] == "https://proxy.example.com/v1"
    call = instance.chat_calls[0]
    assert call["messages"] == [{"role": "user", "content": "ping"}]
    assert call["tools"] is None
    assert call["max_tokens"] == 1


def test_llm_test_endpoint_explicit_body_overrides_saved(client, monkeypatch):
    monkeypatch.setattr("traderharness.agents.llm_client.LLMClient", FakeLLMClient)
    save_llm_settings(api_key="sk-savedkey1234567")

    response = client.post(
        "/api/config/llm/test",
        json={
            "api_key": "sk-inlinekey123456789",
            "base_url": "https://inline.example.com",
            "model": "deepseek-v4-flash",
        },
    )

    assert response.json()["ok"] is True
    assert response.json()["model"] == "deepseek-v4-flash"
    instance = FakeLLMClient.instances[0]
    assert instance.kwargs["api_key"] == "sk-inlinekey123456789"
    assert instance.kwargs["base_url"] == "https://inline.example.com"
    assert instance.kwargs["model"] == "deepseek-v4-flash"


def test_llm_test_endpoint_failure_never_leaks_key(client, monkeypatch):
    monkeypatch.setattr("traderharness.agents.llm_client.LLMClient", FakeLLMClient)
    FakeLLMClient.fail_with = RuntimeError("401 Unauthorized: invalid api key sk-savedkey1234567")
    save_llm_settings(api_key="sk-savedkey1234567")

    payload = client.post("/api/config/llm/test", json={}).json()

    assert payload["ok"] is False
    assert payload["detail"]
    assert "sk-savedkey1234567" not in json.dumps(payload)


def test_llm_test_endpoint_reports_missing_key(client):
    payload = client.post("/api/config/llm/test", json={}).json()

    assert payload["ok"] is False
    assert FakeLLMClient.instances == []


def test_status_reports_llm_source(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-envkey1234567890")
    providers = client.get("/api/status").json()["providers"]
    assert providers["llm_source"] == "env"

    monkeypatch.delenv("DEEPSEEK_API_KEY")
    save_llm_settings(api_key="sk-settings123456789")
    providers = client.get("/api/status").json()["providers"]
    assert providers["llm_source"] == "settings"
    assert "sk-settings123456789" not in json.dumps(providers)
