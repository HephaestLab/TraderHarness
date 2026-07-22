"""Tests for traderharness.config.llm_settings — persisted LLM credentials."""

import json

import pytest

from traderharness.config import llm_settings


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point the app home at a temp dir and clear all LLM env credentials."""
    monkeypatch.setenv("TRADERHARNESS_HOME", str(tmp_path))
    for var in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_load_returns_empty_when_file_missing(isolated_home):
    assert llm_settings.load_llm_settings() == {}


def test_load_tolerates_corrupt_file(isolated_home):
    (isolated_home / "settings.json").write_text("{not json", encoding="utf-8")
    assert llm_settings.load_llm_settings() == {}


def test_load_tolerates_non_dict_root(isolated_home):
    (isolated_home / "settings.json").write_text("[1, 2]", encoding="utf-8")
    assert llm_settings.load_llm_settings() == {}


def test_save_and_load_roundtrip(isolated_home):
    llm_settings.save_llm_settings(api_key="sk-roundtrip", base_url="https://example.com/v1")

    on_disk = json.loads((isolated_home / "settings.json").read_text(encoding="utf-8"))
    assert on_disk == {"llm": {"api_key": "sk-roundtrip", "base_url": "https://example.com/v1"}}
    assert llm_settings.load_llm_settings() == on_disk["llm"]


def test_save_merges_and_empty_string_clears_field(isolated_home):
    llm_settings.save_llm_settings(api_key="sk-keep", base_url="https://a.example.com")
    llm_settings.save_llm_settings(base_url="https://b.example.com")
    assert llm_settings.load_llm_settings() == {
        "api_key": "sk-keep",
        "base_url": "https://b.example.com",
    }
    llm_settings.save_llm_settings(api_key="")
    assert llm_settings.load_llm_settings() == {"base_url": "https://b.example.com"}


def test_clear_llm_settings_removes_section_and_preserves_other_keys(isolated_home):
    (isolated_home / "settings.json").write_text(
        json.dumps({"other": 1, "llm": {"api_key": "sk-x"}}),
        encoding="utf-8",
    )
    llm_settings.clear_llm_settings()
    on_disk = json.loads((isolated_home / "settings.json").read_text(encoding="utf-8"))
    assert on_disk == {"other": 1}


def test_atomic_write_leaves_no_temp_files(isolated_home):
    llm_settings.save_llm_settings(api_key="sk-atomic")
    assert [p.name for p in isolated_home.iterdir()] == ["settings.json"]


def test_mask_api_key():
    assert llm_settings.mask_api_key("sk-abcdef123456dUWD") == "sk-...dUWD"
    assert llm_settings.mask_api_key("short") == "*****"
    assert llm_settings.mask_api_key("") == ""


def test_resolve_prefers_env_over_settings(monkeypatch):
    llm_settings.save_llm_settings(api_key="sk-settings", base_url="https://settings.example.com")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.example.com")

    api_key, base_url = llm_settings.resolve_llm_credentials("deepseek-chat")

    assert api_key == "sk-env"
    assert base_url == "https://env.example.com"


def test_resolve_falls_back_to_settings():
    llm_settings.save_llm_settings(api_key="sk-settings", base_url="https://settings.example.com")

    api_key, base_url = llm_settings.resolve_llm_credentials("deepseek-chat")

    assert api_key == "sk-settings"
    assert base_url == "https://settings.example.com"


def test_resolve_uses_deepseek_default_base_url():
    api_key, base_url = llm_settings.resolve_llm_credentials("deepseek-chat")

    assert api_key == ""
    assert base_url == "https://api.deepseek.com"


def test_resolve_non_deepseek_model_has_no_default_base_url(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    api_key, base_url = llm_settings.resolve_llm_credentials("claude-sonnet")

    assert api_key == "sk-ant"
    assert base_url is None


def test_resolve_deepseek_env_is_generic_relay_fallback(monkeypatch):
    """Relay users set one DEEPSEEK_* pair for every provider's model."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-relay")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://relay.example.com/v1")

    api_key, base_url = llm_settings.resolve_llm_credentials("claude-opus-4-8")

    assert api_key == "sk-relay"
    assert base_url == "https://relay.example.com/v1"


def test_resolve_model_specific_env_beats_generic_relay(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-relay")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")

    api_key, _ = llm_settings.resolve_llm_credentials("claude-opus-4-8")

    assert api_key == "sk-ant"


def test_config_status_reports_sources_and_masks_key():
    llm_settings.save_llm_settings(api_key="sk-abcdef123456dUWD")

    status = llm_settings.llm_config_status("deepseek-chat")

    assert status["configured"] is True
    assert status["source"] == "settings"
    assert status["api_key_masked"] == "sk-...dUWD"
    assert "sk-abcdef123456dUWD" not in json.dumps(status)
    assert status["base_url"] == "https://api.deepseek.com"
    assert status["base_url_source"] == "default"


def test_config_status_when_nothing_configured():
    status = llm_settings.llm_config_status("deepseek-chat")

    assert status["configured"] is False
    assert status["source"] == "none"
    assert status["api_key_masked"] == ""
    assert status["base_url_source"] == "default"
