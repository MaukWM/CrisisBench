"""Tests for tool_factory — ToolDefinition → LangChain StructuredTool bridge."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from crisis_bench.models.runtime import ToolResponse
from crisis_bench.models.scenario import ToolDefinition, ToolParameter
from crisis_bench.runner.orchestrator import ActionLog, _classify_action, _summarize_tool_call
from crisis_bench.runner.tool_factory import (
    _build_args_schema,
    _restore_tool_name,
    _sanitize_tool_name,
    create_langchain_tools,
)


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _sanitize_tool_name / _restore_tool_name
# ---------------------------------------------------------------------------


class TestSanitizeToolName:
    """Roundtrip and edge cases for tool name sanitization."""

    def test_roundtrip_dotted_name(self) -> None:
        original = "mcp.spotify.search"
        assert _restore_tool_name(_sanitize_tool_name(original)) == original

    def test_flat_name_unchanged(self) -> None:
        assert _sanitize_tool_name("query_wearable") == "query_wearable"

    def test_dots_become_double_underscores(self) -> None:
        assert _sanitize_tool_name("a.b.c") == "a__b__c"

    def test_restore_double_underscores(self) -> None:
        assert _restore_tool_name("a__b__c") == "a.b.c"


# ---------------------------------------------------------------------------
# _build_args_schema
# ---------------------------------------------------------------------------


class TestBuildArgsSchema:
    """Dynamic Pydantic model creation from ToolParameter lists."""

    def test_required_params(self) -> None:
        td = ToolDefinition(
            name="make_call",
            description="Place a call",
            parameters=[
                ToolParameter(
                    name="number", type="string", description="Phone number", required=True
                ),
            ],
        )
        schema = _build_args_schema(td)
        assert issubclass(schema, BaseModel)
        assert "number" in schema.model_fields
        assert schema.model_fields["number"].is_required()

    def test_optional_params(self) -> None:
        td = ToolDefinition(
            name="get_recent_updates",
            description="Get updates",
            parameters=[
                ToolParameter(
                    name="count", type="integer", description="How many", required=False
                ),
            ],
        )
        schema = _build_args_schema(td)
        assert "count" in schema.model_fields
        assert not schema.model_fields["count"].is_required()

    def test_type_mapping(self) -> None:
        td = ToolDefinition(
            name="test_types",
            description="Test",
            parameters=[
                ToolParameter(name="s", type="string", description="str", required=True),
                ToolParameter(name="i", type="integer", description="int", required=True),
                ToolParameter(name="f", type="number", description="float", required=True),
                ToolParameter(name="b", type="boolean", description="bool", required=True),
            ],
        )
        schema = _build_args_schema(td)
        assert schema.model_fields["s"].annotation is str
        assert schema.model_fields["i"].annotation is int
        assert schema.model_fields["f"].annotation is float
        assert schema.model_fields["b"].annotation is bool

    def test_empty_params(self) -> None:
        td = ToolDefinition(name="list_memories", description="List all", parameters=[])
        schema = _build_args_schema(td)
        assert issubclass(schema, BaseModel)
        assert len(schema.model_fields) == 0


# ---------------------------------------------------------------------------
# create_langchain_tools
# ---------------------------------------------------------------------------


class TestCreateLangchainTools:
    """Integration: ToolDefinition → StructuredTool with routing and logging."""

    @pytest.fixture()
    def tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="query_wearable",
                description="Query wearable data",
                parameters=[],
            ),
            ToolDefinition(
                name="mcp.spotify.search",
                description="Search Spotify",
                parameters=[
                    ToolParameter(
                        name="query", type="string", description="Search query", required=True
                    ),
                ],
            ),
        ]

    @pytest.fixture()
    def mock_router(self) -> AsyncMock:
        router = AsyncMock()
        router.route.return_value = (
            ToolResponse(status="ok"),
            "TestHandler",
        )
        return router

    @pytest.fixture()
    def action_log(self) -> ActionLog:
        return ActionLog(window_size=20)

    def test_correct_count(
        self,
        tool_definitions: list[ToolDefinition],
        mock_router: AsyncMock,
        action_log: ActionLog,
    ) -> None:
        tools = create_langchain_tools(
            tool_definitions,
            mock_router,
            action_log,
            get_timestamp=lambda: "2027-06-15T10:00:00Z",
            classify_action=_classify_action,
            summarize_tool_call=_summarize_tool_call,
        )
        assert len(tools) == 2

    def test_sanitized_names(
        self,
        tool_definitions: list[ToolDefinition],
        mock_router: AsyncMock,
        action_log: ActionLog,
    ) -> None:
        tools = create_langchain_tools(
            tool_definitions,
            mock_router,
            action_log,
            get_timestamp=lambda: "2027-06-15T10:00:00Z",
            classify_action=_classify_action,
            summarize_tool_call=_summarize_tool_call,
        )
        names = [t.name for t in tools]
        assert "query_wearable" in names
        assert "mcp__spotify__search" in names

    def test_delegates_to_router(
        self,
        tool_definitions: list[ToolDefinition],
        mock_router: AsyncMock,
        action_log: ActionLog,
    ) -> None:
        tools = create_langchain_tools(
            tool_definitions,
            mock_router,
            action_log,
            get_timestamp=lambda: "2027-06-15T10:00:00Z",
            classify_action=_classify_action,
            summarize_tool_call=_summarize_tool_call,
        )
        wearable_tool = next(t for t in tools if t.name == "query_wearable")
        result = _run(wearable_tool.ainvoke({}))
        mock_router.route.assert_called_once_with("query_wearable", {})
        parsed = json.loads(result)
        assert parsed["status"] == "ok"

    def test_records_action_log(
        self,
        tool_definitions: list[ToolDefinition],
        mock_router: AsyncMock,
        action_log: ActionLog,
    ) -> None:
        tools = create_langchain_tools(
            tool_definitions,
            mock_router,
            action_log,
            get_timestamp=lambda: "2027-06-15T10:00:00Z",
            classify_action=_classify_action,
            summarize_tool_call=_summarize_tool_call,
        )
        wearable_tool = next(t for t in tools if t.name == "query_wearable")
        _run(wearable_tool.ainvoke({}))
        entries, total = action_log.get_window()
        assert total == 1
        assert entries[0].tool_name == "query_wearable"
        assert entries[0].action_type == "query"

    def test_returns_json(
        self,
        tool_definitions: list[ToolDefinition],
        mock_router: AsyncMock,
        action_log: ActionLog,
    ) -> None:
        tools = create_langchain_tools(
            tool_definitions,
            mock_router,
            action_log,
            get_timestamp=lambda: "2027-06-15T10:00:00Z",
            classify_action=_classify_action,
            summarize_tool_call=_summarize_tool_call,
        )
        wearable_tool = next(t for t in tools if t.name == "query_wearable")
        result = _run(wearable_tool.ainvoke({}))
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "status" in parsed
