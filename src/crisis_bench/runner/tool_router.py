"""ToolRouter — dispatches tool calls to the first matching handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from crisis_bench.models.runtime import ErrorResponse, ToolResponse

if TYPE_CHECKING:
    from crisis_bench.runner.handlers.base import ToolHandler


class ToolRouter:
    """Routes tool calls to registered handlers using first-match-wins."""

    def __init__(self, handlers: list[ToolHandler]) -> None:
        self.handlers = handlers
        self.log = structlog.get_logger().bind(component="ToolRouter")

    async def route(self, tool_name: str, args: dict[str, Any]) -> tuple[ToolResponse, str]:
        """Dispatch a tool call to the first handler that can handle it.

        Returns a tuple of (response, handler_class_name).
        """
        for handler in self.handlers:
            if handler.can_handle(tool_name):
                response = await handler.handle(tool_name, args)
                handler_name = type(handler).__name__
                self.log.debug("tool_dispatched", tool_name=tool_name, routed_to=handler_name)
                return response, handler_name

        self.log.debug("tool_dispatched", tool_name=tool_name, routed_to="none")
        return ErrorResponse(status="error", message="Unknown tool"), "none"
