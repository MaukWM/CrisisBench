"""Tests for ToolRouter."""

from __future__ import annotations

import asyncio
from typing import Any

from crisis_bench.models.runtime import ErrorResponse, ToolResponse
from crisis_bench.runner.tool_router import ToolRouter


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class _FakeHandlerA:
    """Handles tool_a only."""

    def can_handle(self, tool_name: str) -> bool:
        return tool_name == "tool_a"

    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse:
        return ToolResponse(status="ok_a")


class _FakeHandlerB:
    """Handles tool_a and tool_b."""

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in {"tool_a", "tool_b"}

    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse:
        return ToolResponse(status="ok_b")


class TestToolRouter:
    def test_route_to_first_matching_handler(self) -> None:
        """First handler that can_handle wins, even if later ones also can."""
        router = ToolRouter(handlers=[_FakeHandlerA(), _FakeHandlerB()])
        response, handler_name = _run(router.route("tool_a", {}))
        assert response.status == "ok_a"
        assert handler_name == "_FakeHandlerA"

    def test_route_unknown_tool(self) -> None:
        """Unrecognized tool returns ErrorResponse with 'Unknown tool'."""
        router = ToolRouter(handlers=[_FakeHandlerA()])
        response, handler_name = _run(router.route("no_such_tool", {}))
        assert isinstance(response, ErrorResponse)
        assert response.status == "error"
        assert response.message == "Unknown tool"
        assert handler_name == "none"

    def test_route_returns_handler_name(self) -> None:
        """route() returns the handler class name as the second element."""
        router = ToolRouter(handlers=[_FakeHandlerB()])
        response, handler_name = _run(router.route("tool_b", {}))
        assert response.status == "ok_b"
        assert handler_name == "_FakeHandlerB"
