"""Agent 工作目录管理 — 提供隔离的持久化文件系统。

从源项目 backend/agents/agentic/workspace.py 完整迁移。
含文件数量/大小配额限制。
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_WORKSPACE_SIZE_MB = 10
MAX_FILES = 100


class AgentWorkspace:
    """管理单个 Agent 的独立工作目录。"""

    def __init__(self, agent_id: str, base_dir: str | Path = "./workspaces") -> None:
        self.agent_id = agent_id
        self._root = Path(base_dir) / agent_id
        self._init_dirs()

    def _init_dirs(self) -> None:
        for sub in ("scripts", "notes", "data", "journal"):
            (self._root / sub).mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def write(self, filename: str, content: str) -> Path:
        path = self._safe_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        all_files = list(self._root.rglob("*"))
        file_count = sum(1 for f in all_files if f.is_file())
        if file_count >= MAX_FILES and not path.exists():
            raise ValueError(f"文件数量超限: 最多 {MAX_FILES} 个文件")

        total_size = sum(f.stat().st_size for f in all_files if f.is_file())
        if total_size + len(content.encode()) > MAX_WORKSPACE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"工作目录超过 {MAX_WORKSPACE_SIZE_MB}MB 限制")

        path.write_text(content, encoding="utf-8")
        return path

    def read(self, filename: str) -> str:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")
        content = path.read_text(encoding="utf-8")
        if len(content) > 8192:
            content = content[:8192] + "\n... (文件超过8KB，已截断)"
        return content

    def list_files(self, subdir: str = "") -> list[str]:
        target = self._safe_path(subdir) if subdir else self._root
        if not target.exists():
            return []
        return [
            str(p.relative_to(self._root)).replace("\\", "/")
            for p in sorted(target.rglob("*")) if p.is_file()
        ]

    def exists(self, filename: str) -> bool:
        return self._safe_path(filename).exists()

    def _safe_path(self, filename: str) -> Path:
        resolved = (self._root / filename).resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            raise ValueError(f"路径越界: {filename}")
        return resolved
