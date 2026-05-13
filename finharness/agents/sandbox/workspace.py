"""AgentWorkspace — isolated filesystem for each agent."""

from __future__ import annotations

from pathlib import Path


class AgentWorkspace:
    """Provides an isolated directory per agent for reading/writing files."""

    def __init__(self, agent_id: str, base_dir: str | Path = "./workspaces") -> None:
        self._root = Path(base_dir) / agent_id
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def write(self, filename: str, content: str) -> Path:
        path = self._safe_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def read(self, filename: str) -> str:
        path = self._safe_path(filename)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filename}")
        return path.read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        return [str(p.relative_to(self._root)) for p in self._root.rglob("*") if p.is_file()]

    def exists(self, filename: str) -> bool:
        return self._safe_path(filename).exists()

    def _safe_path(self, filename: str) -> Path:
        resolved = (self._root / filename).resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            raise ValueError(f"Path traversal detected: {filename}")
        return resolved
