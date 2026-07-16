"""Tests for traderharness.paths — single source of truth for app directories."""

from pathlib import Path

from traderharness import paths


def test_default_home_is_traderharness(monkeypatch):
    monkeypatch.delenv("TRADERHARNESS_HOME", raising=False)
    assert paths.get_home() == Path.home() / ".traderharness"


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADERHARNESS_HOME", str(tmp_path / "custom"))
    assert paths.get_home() == tmp_path / "custom"


def test_subdirs_derive_from_home(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADERHARNESS_HOME", str(tmp_path))
    assert paths.dataset_dir() == tmp_path / "dataset"
    assert paths.results_dir() == tmp_path / "results"
    assert paths.agents_dir() == tmp_path / "agents"
    assert paths.llm_cache_dir() == tmp_path / "llm_cache"
    assert paths.datasets_dir() == tmp_path / "datasets"


def test_no_legacy_finharness_references():
    """No source file may reference the legacy ~/.finharness path."""
    pkg_root = Path(__file__).resolve().parents[2] / "traderharness"
    offenders = []
    for py in pkg_root.rglob("*.py"):
        if ".finharness" in py.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(py))
    assert offenders == []
