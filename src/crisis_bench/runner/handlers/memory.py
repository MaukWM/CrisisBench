"""MemoryHandler — file-based memory read/write/list for agent memory operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from crisis_bench.models.runtime import (
    ListMemoriesResponse,
    ReadMemoryResponse,
    ToolResponse,
    WriteMemoryResponse,
)

if TYPE_CHECKING:
    from pathlib import Path

    from crisis_bench.models.scenario import MemoryFile

_MEMORY_TOOLS = frozenset({"read_memory", "write_memory", "list_memories"})


class MemoryHandler:
    """Handles memory tool calls with synchronous file-based storage."""

    def __init__(self, memory_dir: Path, initial_files: list[MemoryFile]) -> None:
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        for mf in initial_files:
            (self.memory_dir / f"{mf.key}.md").write_text(mf.content, encoding="utf-8")
        self.log = structlog.get_logger().bind(handler="MemoryHandler")

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in _MEMORY_TOOLS

    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse:
        self.log.debug("handling_tool", tool_name=tool_name)
        if tool_name == "read_memory":
            return self._read_memory(args)
        if tool_name == "write_memory":
            return self._write_memory(args)
        return self._list_memories(args)

    def _read_memory(self, args: dict[str, Any]) -> ReadMemoryResponse:
        key = args["key"]
        path = self.memory_dir / f"{key}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            return ReadMemoryResponse(status="ok", content=content)
        return ReadMemoryResponse(status="ok", content=None)

    def _write_memory(self, args: dict[str, Any]) -> WriteMemoryResponse:
        key = args["key"]
        content = args["content"]
        (self.memory_dir / f"{key}.md").write_text(content, encoding="utf-8")
        return WriteMemoryResponse(status="written")

    def _list_memories(self, args: dict[str, Any]) -> ListMemoriesResponse:
        keys = sorted(p.stem for p in self.memory_dir.glob("*.md"))
        return ListMemoriesResponse(status="ok", keys=keys)
