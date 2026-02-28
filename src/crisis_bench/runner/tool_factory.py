"""Tool factory — bridges scenario ToolDefinitions to LangChain StructuredTool objects."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from crisis_bench.models.scenario import ToolDefinition
    from crisis_bench.runner.orchestrator import ActionLog
    from crisis_bench.runner.tool_router import ToolRouter

log = structlog.get_logger()

# Type mapping from scenario schema strings to Python types
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _sanitize_tool_name(name: str) -> str:
    """Replace dots with double underscores for LLM API compatibility.

    OpenAI requires tool names to match ``^[a-zA-Z0-9_-]+$``.
    MCP tools use dotted names (e.g. ``spotify.search``).
    """
    return name.replace(".", "__")


def _restore_tool_name(sanitized: str) -> str:
    """Reverse ``_sanitize_tool_name`` — restore dotted MCP names."""
    return sanitized.replace("__", ".")


def _build_args_schema(tool_def: ToolDefinition) -> type:
    """Dynamically create a Pydantic model from ToolParameter list."""
    field_definitions: dict[str, Any] = {}
    for param in tool_def.parameters:
        py_type = _TYPE_MAP.get(param.type, str)
        if param.required:
            field_definitions[param.name] = (py_type, Field(description=param.description))
        else:
            field_definitions[param.name] = (
                py_type,
                Field(default=None, description=param.description),
            )

    model_name = f"{_sanitize_tool_name(tool_def.name)}_Args"
    return create_model(model_name, **field_definitions)  # type: ignore[no-any-return]


def _make_tool_coroutine(
    original_name: str,
    tool_router: ToolRouter,
    action_log: ActionLog,
    get_timestamp: Callable[[], str],
    classify_action: Callable[[str], str],
    summarize_tool_call: Callable[[str, dict[str, Any]], str],
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Create an async closure that routes a tool call and records to the action log."""

    async def _invoke(**kwargs: Any) -> str:
        tool_response, handler_name = await tool_router.route(original_name, kwargs)
        action_log.record(
            time=get_timestamp(),
            action_type=classify_action(original_name),
            tool_name=original_name,
            summary=summarize_tool_call(original_name, kwargs),
        )
        log.info(
            "tool_routed",
            tool_name=original_name,
            routed_to=handler_name,
            status=tool_response.status,
            args=kwargs,
        )
        return json.dumps(tool_response.model_dump())

    return _invoke


def create_langchain_tools(
    tool_definitions: list[ToolDefinition],
    tool_router: ToolRouter,
    action_log: ActionLog,
    get_timestamp: Callable[[], str],
    classify_action: Callable[[str], str],
    summarize_tool_call: Callable[[str, dict[str, Any]], str],
) -> list[StructuredTool]:
    """Convert scenario ToolDefinitions into LangChain StructuredTool objects."""
    tools: list[StructuredTool] = []
    for td in tool_definitions:
        original_name = td.name
        sanitized_name = _sanitize_tool_name(original_name)
        args_schema = _build_args_schema(td)

        coro = _make_tool_coroutine(
            original_name=original_name,
            tool_router=tool_router,
            action_log=action_log,
            get_timestamp=get_timestamp,
            classify_action=classify_action,
            summarize_tool_call=summarize_tool_call,
        )

        tool = StructuredTool(
            name=sanitized_name,
            description=td.description,
            coroutine=coro,
            args_schema=args_schema,
        )
        tools.append(tool)

    return tools
