"""Tests for MemoryHandler."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from crisis_bench.models.runtime import (
    ListMemoriesResponse,
    ReadMemoryResponse,
    WriteMemoryResponse,
)
from crisis_bench.models.scenario import MemoryFile
from crisis_bench.runner.handlers.memory import MemoryHandler


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def initial_files() -> list[MemoryFile]:
    return [
        MemoryFile(key="user_profile", content="# Profile\nName: Test User"),
        MemoryFile(key="preferences", content="# Preferences\nTheme: dark"),
    ]


@pytest.fixture()
def handler(tmp_path: Path, initial_files: list[MemoryFile]) -> MemoryHandler:
    return MemoryHandler(tmp_path / "memories", initial_files)


class TestMemoryHandlerInit:
    def test_initial_files_written_to_disk(self, handler: MemoryHandler) -> None:
        """Init writes all MemoryFile objects to disk."""
        assert (handler.memory_dir / "user_profile.md").exists()
        assert (handler.memory_dir / "preferences.md").exists()
        content = (handler.memory_dir / "user_profile.md").read_text(encoding="utf-8")
        assert "Name: Test User" in content


class TestMemoryHandlerCanHandle:
    def test_can_handle_memory_tools(self, handler: MemoryHandler) -> None:
        assert handler.can_handle("read_memory")
        assert handler.can_handle("write_memory")
        assert handler.can_handle("list_memories")

    def test_can_handle_rejects_other_tools(self, handler: MemoryHandler) -> None:
        assert not handler.can_handle("query_wearable")
        assert not handler.can_handle("get_contacts")


class TestMemoryHandlerOperations:
    def test_read_memory_existing_key(self, handler: MemoryHandler) -> None:
        response = _run(handler.handle("read_memory", {"key": "user_profile"}))
        assert isinstance(response, ReadMemoryResponse)
        assert response.status == "ok"
        assert response.content is not None
        assert "Name: Test User" in response.content

    def test_read_memory_missing_key(self, handler: MemoryHandler) -> None:
        response = _run(handler.handle("read_memory", {"key": "nonexistent"}))
        assert isinstance(response, ReadMemoryResponse)
        assert response.status == "ok"
        assert response.content is None

    def test_write_then_read_memory(self, handler: MemoryHandler) -> None:
        _run(handler.handle("write_memory", {"key": "emergency", "content": "HR dropped to 0"}))
        response = _run(handler.handle("read_memory", {"key": "emergency"}))
        assert isinstance(response, ReadMemoryResponse)
        assert response.content == "HR dropped to 0"

    def test_write_memory_response(self, handler: MemoryHandler) -> None:
        response = _run(handler.handle("write_memory", {"key": "test", "content": "data"}))
        assert isinstance(response, WriteMemoryResponse)
        assert response.status == "written"

    def test_list_memories(self, handler: MemoryHandler) -> None:
        """Initial 2 files + 1 written = 3 keys, sorted."""
        _run(handler.handle("write_memory", {"key": "emergency", "content": "alert"}))
        response = _run(handler.handle("list_memories", {}))
        assert isinstance(response, ListMemoriesResponse)
        assert response.keys == ["emergency", "preferences", "user_profile"]

    def test_write_memory_overwrite(self, handler: MemoryHandler) -> None:
        _run(handler.handle("write_memory", {"key": "user_profile", "content": "Updated content"}))
        response = _run(handler.handle("read_memory", {"key": "user_profile"}))
        assert isinstance(response, ReadMemoryResponse)
        assert response.content == "Updated content"
