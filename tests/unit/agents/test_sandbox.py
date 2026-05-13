"""Tests for PythonSandbox and AgentWorkspace."""

import pytest

from finharness.agents.sandbox.executor import PythonSandbox
from finharness.agents.sandbox.workspace import AgentWorkspace


class TestPythonSandbox:
    def test_basic_execution(self):
        sb = PythonSandbox()
        result = sb.execute("print(1 + 1)")
        assert result["success"] is True
        assert "2" in result["stdout"]

    def test_blocked_import(self):
        sb = PythonSandbox()
        result = sb.execute("import os")
        assert result["success"] is False
        assert "not allowed" in result["error"]

    def test_allowed_operations(self):
        sb = PythonSandbox()
        result = sb.execute("x = sum([1,2,3])\nprint(x)")
        assert result["success"] is True
        assert "6" in result["stdout"]

    def test_runtime_error_captured(self):
        sb = PythonSandbox()
        result = sb.execute("1/0")
        assert result["success"] is False
        assert "ZeroDivisionError" in result["error"]

    def test_numpy_allowed(self):
        sb = PythonSandbox()
        result = sb.execute("import numpy as np\nprint(np.mean([1,2,3]))")
        assert result["success"] is True


class TestAgentWorkspace:
    def test_write_and_read(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        ws.write("notes.txt", "hello world")
        assert ws.read("notes.txt") == "hello world"

    def test_list_files(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        ws.write("a.txt", "a")
        ws.write("sub/b.txt", "b")
        files = ws.list_files()
        assert len(files) == 2

    def test_path_traversal_blocked(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        with pytest.raises(ValueError, match="traversal"):
            ws.read("../../etc/passwd")

    def test_exists(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        assert ws.exists("nope.txt") is False
        ws.write("yes.txt", "content")
        assert ws.exists("yes.txt") is True
