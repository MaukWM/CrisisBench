"""Tests for ModelClient."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crisis_bench.models.runtime import RunConfig
from crisis_bench.models.scenario import ToolDefinition, ToolParameter
from crisis_bench.runner.model_client import (
    AgentResponse,
    ModelClient,
    ParsedToolCall,
    convert_tool_definitions,
)


def _run(coro):  # noqa: ANN001, ANN202
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture()
def sample_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="make_call",
            description="Place a phone call",
            parameters=[
                ToolParameter(
                    name="number", type="string", description="Phone number to call", required=True
                ),
            ],
        ),
        ToolDefinition(
            name="read_memory",
            description="Read a memory file",
            parameters=[
                ToolParameter(
                    name="key", type="string", description="Memory key", required=True
                ),
            ],
        ),
    ]


@pytest.fixture()
def default_run_config() -> RunConfig:
    return RunConfig(
        agent_model="test-model",
        user_sim_model="test-sim",
        judge_model="test-judge",
    )


@pytest.fixture()
def mock_litellm_text_response() -> MagicMock:
    """Create a mock LiteLLM response with text only."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = "I'll check on that for you."
    choice.message.tool_calls = None
    response.choices = [choice]
    return response


@pytest.fixture()
def mock_litellm_tool_response() -> MagicMock:
    """Create a mock LiteLLM response with text and tool calls."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = "Let me look that up."
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = "query_device"
    tc.function.arguments = '{"device_id": "apple_watch"}'
    choice.message.tool_calls = [tc]
    response.choices = [choice]
    return response


class TestConvertToolDefinitions:
    """Test tool definition conversion to OpenAI format."""

    def test_convert_tool_definitions(
        self, sample_tool_definitions: list[ToolDefinition]
    ) -> None:
        result = convert_tool_definitions(sample_tool_definitions)
        assert len(result) == 2
        first = result[0]
        assert first["type"] == "function"
        assert first["function"]["name"] == "make_call"
        assert first["function"]["description"] == "Place a phone call"
        params = first["function"]["parameters"]
        assert params["type"] == "object"
        assert "number" in params["properties"]
        assert params["properties"]["number"]["type"] == "string"
        assert params["required"] == ["number"]


class TestModelClient:
    """AC #3, #4, #5: ModelClient wraps LiteLLM correctly."""

    @patch("litellm.acompletion", new_callable=AsyncMock)
    def test_model_client_complete_text_only(
        self,
        mock_acompletion: AsyncMock,
        mock_litellm_text_response: MagicMock,
        sample_tool_definitions: list[ToolDefinition],
        default_run_config: RunConfig,
    ) -> None:
        mock_acompletion.return_value = mock_litellm_text_response
        client = ModelClient(default_run_config, sample_tool_definitions)
        result = _run(client.complete("system prompt", "user message"))
        assert isinstance(result, AgentResponse)
        assert result.text == "I'll check on that for you."
        assert result.tool_calls == []

    @patch("litellm.acompletion", new_callable=AsyncMock)
    def test_model_client_complete_with_tool_calls(
        self,
        mock_acompletion: AsyncMock,
        mock_litellm_tool_response: MagicMock,
        sample_tool_definitions: list[ToolDefinition],
        default_run_config: RunConfig,
    ) -> None:
        mock_acompletion.return_value = mock_litellm_tool_response
        client = ModelClient(default_run_config, sample_tool_definitions)
        result = _run(client.complete("system prompt", "user message"))
        assert result.text == "Let me look that up."
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert isinstance(tc, ParsedToolCall)
        assert tc.id == "call_123"
        assert tc.name == "query_device"
        assert tc.arguments == {"device_id": "apple_watch"}

    @patch("litellm.acompletion", new_callable=AsyncMock)
    def test_model_client_fresh_context(
        self,
        mock_acompletion: AsyncMock,
        mock_litellm_text_response: MagicMock,
        sample_tool_definitions: list[ToolDefinition],
        default_run_config: RunConfig,
    ) -> None:
        """Verify that ModelClient.complete() builds a fresh messages list each call."""
        mock_acompletion.return_value = mock_litellm_text_response
        client = ModelClient(default_run_config, sample_tool_definitions)
        _run(client.complete("system prompt 1", "user message 1"))
        _run(client.complete("system prompt 2", "user message 2"))
        # Both calls should have fresh 2-message lists.
        assert mock_acompletion.call_count == 2
        call1_messages = mock_acompletion.call_args_list[0].kwargs["messages"]
        call2_messages = mock_acompletion.call_args_list[1].kwargs["messages"]
        assert len(call1_messages) == 2
        assert len(call2_messages) == 2
        assert call1_messages[1]["content"] == "user message 1"
        assert call2_messages[1]["content"] == "user message 2"

    @patch("litellm.acompletion", new_callable=AsyncMock)
    def test_model_client_passes_model_params(
        self,
        mock_acompletion: AsyncMock,
        mock_litellm_text_response: MagicMock,
        sample_tool_definitions: list[ToolDefinition],
    ) -> None:
        config = RunConfig(
            agent_model="test-model",
            user_sim_model="test-sim",
            judge_model="test-judge",
            model_params={"temperature": 0.7, "max_tokens": 1000},
        )
        mock_acompletion.return_value = mock_litellm_text_response
        client = ModelClient(config, sample_tool_definitions)
        _run(client.complete("system", "user"))
        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 1000
