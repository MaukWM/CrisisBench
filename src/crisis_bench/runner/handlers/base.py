"""ToolHandler protocol — core abstraction for the tool dispatch system."""

from typing import Any, Protocol

from crisis_bench.models.runtime import ToolResponse


class ToolHandler(Protocol):
    """Protocol that all tool handlers must satisfy.

    Handlers are registered with ToolRouter in priority order.
    First handler whose ``can_handle`` returns True wins.
    """

    def can_handle(self, tool_name: str) -> bool: ...

    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse: ...
