"""Tests for PythonSandbox and AgentWorkspace."""

import pytest

from finharness.agents.sandbox.executor import PythonSandbox
from finharness.agents.sandbox.workspace import AgentWorkspace


class TestPythonSandbox:
    def test_basic_execution(self):
        sb = PythonSandbox()
        result = sb.execute("print(1 + 1)")
        assert result.error is None
        assert "2" in result.stdout

    def test_blocked_import(self):
        sb = PythonSandbox()
        result = sb.execute("import os")
        assert result.error is not None
        assert "禁止" in result.error or "不允许" in result.error

    def test_allowed_operations(self):
        sb = PythonSandbox()
        result = sb.execute("x = sum([1,2,3])\nprint(x)")
        assert result.error is None
        assert "6" in result.stdout

    def test_runtime_error_captured(self):
        sb = PythonSandbox()
        result = sb.execute("1/0")
        assert result.error is not None
        assert "ZeroDivisionError" in result.error

    def test_numpy_allowed(self):
        sb = PythonSandbox()
        result = sb.execute("import numpy as np\nprint(np.mean([1,2,3]))")
        assert result.error is None

    def test_ast_blocks_eval(self):
        sb = PythonSandbox()
        result = sb.execute("eval('1+1')")
        assert result.error is not None

    def test_inject_data(self):
        import pandas as pd
        sb = PythonSandbox()
        df = pd.DataFrame({"close": [100, 101, 102]})
        result = sb.execute("_result_ = len(df_test)", injected_data={"df_test": df})
        assert result.error is None
        assert result.result == 3


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
        assert len(files) >= 2

    def test_path_traversal_blocked(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        with pytest.raises(ValueError):
            ws.read("../../etc/passwd")

    def test_exists(self, tmp_path):
        ws = AgentWorkspace("test_agent", base_dir=tmp_path)
        assert ws.exists("nope.txt") is False
        ws.write("yes.txt", "content")
        assert ws.exists("yes.txt") is True

    def test_file_count_limit(self, tmp_path):
        from finharness.agents.sandbox import workspace as ws_mod
        old_max = ws_mod.MAX_FILES
        ws_mod.MAX_FILES = 5
        try:
            ws = AgentWorkspace("test_agent", base_dir=tmp_path)
            for i in range(5):
                ws.write(f"file_{i}.txt", "x")
            with pytest.raises(ValueError):
                ws.write("overflow.txt", "x")
        finally:
            ws_mod.MAX_FILES = old_max
