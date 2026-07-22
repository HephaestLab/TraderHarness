"""Tests for traderharness._hashseed — replay-determinism seed guard."""

import pytest

from traderharness import _hashseed


def test_noop_when_seed_already_pinned(monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "42")
    calls = []
    monkeypatch.setattr(_hashseed.subprocess, "call", lambda *a, **k: calls.append((a, k)) or 0)
    _hashseed.ensure_fixed_hash_seed()
    assert calls == []


def test_reruns_with_pinned_seed_when_unset(monkeypatch):
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)
    calls = []
    monkeypatch.setattr(
        _hashseed.subprocess, "call", lambda *a, **k: calls.append((a, k)) or 7
    )
    with pytest.raises(SystemExit) as excinfo:
        _hashseed.ensure_fixed_hash_seed()
    assert excinfo.value.code == 7
    assert len(calls) == 1
    assert calls[0][1]["env"]["PYTHONHASHSEED"] == "0"


def test_keyboard_interrupt_maps_to_130(monkeypatch):
    monkeypatch.delenv("PYTHONHASHSEED", raising=False)

    def _interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(_hashseed.subprocess, "call", _interrupted)
    with pytest.raises(SystemExit) as excinfo:
        _hashseed.ensure_fixed_hash_seed()
    assert excinfo.value.code == 130


def test_rerun_command_routes_console_script_via_module(monkeypatch):
    monkeypatch.setattr(
        _hashseed.sys, "argv", [r"D:\finharness\.venv\Scripts\traderharness.exe", "run", "-a", "x"]
    )
    cmd = _hashseed._rerun_command()
    assert cmd[1:] == ["-m", "traderharness", "run", "-a", "x"]


def test_rerun_command_routes_pytest_via_module(monkeypatch):
    monkeypatch.setattr(_hashseed.sys, "argv", [r"C:\venv\Scripts\pytest.exe", "tests/", "-q"])
    cmd = _hashseed._rerun_command()
    assert cmd[1:] == ["-m", "pytest", "tests/", "-q"]


def test_rerun_command_keeps_plain_script(monkeypatch):
    monkeypatch.setattr(_hashseed.sys, "argv", ["scripts/run_backtest.py", "--fast"])
    cmd = _hashseed._rerun_command()
    assert cmd[1:] == ["scripts/run_backtest.py", "--fast"]
