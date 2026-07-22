"""Persisted LLM API settings for the local Web console.

Settings live in ``~/.traderharness/settings.json`` (the ``TRADERHARNESS_HOME``
override applies) under the ``"llm"`` key::

    {"llm": {"api_key": "sk-...", "base_url": "https://..."}}

Credential resolution priority (see :func:`resolve_llm_credentials`):

1. Environment variables — the per-model rules used by ``LLMClient``
   (``DEEPSEEK_API_KEY`` / ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``), with
   ``DEEPSEEK_API_KEY`` doubling as a generic relay-station key for any model
   (historical CLI behavior), plus ``DEEPSEEK_BASE_URL``.
2. ``settings.json`` written from the Web console settings page.
3. Built-in defaults (DeepSeek models → ``https://api.deepseek.com``).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from traderharness.paths import get_home

_DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"


def _settings_path() -> Path:
    return get_home() / "settings.json"


def _load_root() -> dict:
    try:
        raw = json.loads(_settings_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_root(data: dict) -> None:
    """Atomically replace settings.json (write temp file, then rename)."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_llm_settings() -> dict:
    """Return the persisted ``llm`` section; ``{}`` when missing or corrupt."""
    llm = _load_root().get("llm")
    return dict(llm) if isinstance(llm, dict) else {}


def save_llm_settings(api_key: str | None = None, base_url: str | None = None) -> None:
    """Update the ``llm`` section atomically.

    ``None`` leaves the stored field untouched; an empty string removes it.
    """
    data = _load_root()
    llm = data.get("llm")
    if not isinstance(llm, dict):
        llm = {}
    if api_key is not None:
        if api_key:
            llm["api_key"] = api_key
        else:
            llm.pop("api_key", None)
    if base_url is not None:
        if base_url:
            llm["base_url"] = base_url
        else:
            llm.pop("base_url", None)
    if llm:
        data["llm"] = llm
    else:
        data.pop("llm", None)
    _write_root(data)


def clear_llm_settings() -> None:
    """Remove the whole ``llm`` section, preserving any other root keys."""
    data = _load_root()
    if "llm" not in data:
        return
    data.pop("llm", None)
    _write_root(data)


def mask_api_key(key: str) -> str:
    """Mask a key like ``sk-...dUWD`` (first 3 + last 4); short keys fully hidden."""
    if not key:
        return ""
    if len(key) <= 7:
        return "*" * len(key)
    return f"{key[:3]}...{key[-4:]}"


def _env_api_key(model: str) -> str:
    lowered = model.lower()
    if "deepseek" in lowered:
        specific = os.environ.get("DEEPSEEK_API_KEY", "")
    elif "claude" in lowered:
        specific = os.environ.get("ANTHROPIC_API_KEY", "")
    else:
        specific = os.environ.get("OPENAI_API_KEY", "")
    # Generic fallback: DEEPSEEK_API_KEY doubles as a relay-station key for
    # any model (historical CLI behavior, kept so relay users set one pair of
    # env vars for every provider).
    return specific or os.environ.get("DEEPSEEK_API_KEY", "")


def _env_base_url(model: str) -> str:
    # A relay station serves every model through one endpoint, so the override
    # applies to any model, not just DeepSeek.
    return os.environ.get("DEEPSEEK_BASE_URL", "")


def _default_base_url(model: str) -> str:
    if "deepseek" in model.lower():
        return _DEEPSEEK_DEFAULT_BASE_URL
    return ""


def _resolve(model: str) -> tuple[str, str, str, str]:
    """Return ``(api_key, key_source, base_url, base_url_source)``.

    Sources are ``"env"``, ``"settings"``, ``"default"`` (base_url only), or
    ``"none"``.
    """
    settings = load_llm_settings()

    api_key = _env_api_key(model)
    key_source = "env" if api_key else "none"
    if not api_key:
        stored_key = str(settings.get("api_key") or "")
        if stored_key:
            api_key, key_source = stored_key, "settings"

    base_url = _env_base_url(model)
    url_source = "env" if base_url else "none"
    if not base_url:
        stored_url = str(settings.get("base_url") or "")
        if stored_url:
            base_url, url_source = stored_url, "settings"
    if not base_url:
        default_url = _default_base_url(model)
        if default_url:
            base_url, url_source = default_url, "default"

    return api_key, key_source, base_url, url_source


def resolve_llm_credentials(model: str) -> tuple[str, str | None]:
    """Resolve ``(api_key, base_url)`` for ``model``: env > settings > default.

    ``api_key`` is ``""`` when nothing is configured; ``base_url`` is ``None``
    when no override applies (non-DeepSeek models fall through to the SDK
    default).
    """
    api_key, _, base_url, _ = _resolve(model)
    return api_key, base_url or None


def llm_config_status(model: str = "deepseek-chat") -> dict:
    """Status payload for the Web console; never contains the full key."""
    api_key, key_source, base_url, url_source = _resolve(model)
    return {
        "configured": bool(api_key),
        "source": key_source,
        "api_key_masked": mask_api_key(api_key),
        "base_url": base_url,
        "base_url_source": url_source,
    }
