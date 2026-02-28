"""Model client — LiteLLM async wrapper for agent LLM calls."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import litellm
import structlog

if TYPE_CHECKING:
    from crisis_bench.models.runtime import RunConfig, ToolResponse
    from crisis_bench.models.scenario import ToolDefinition

log = structlog.get_logger()


@dataclass(frozen=True)
class ParsedToolCall:
    """A tool call from the LLM response before execution/routing."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentResponse:
    """Structured return from ModelClient."""

    text: str | None
    tool_calls: list[ParsedToolCall] = field(default_factory=list)


def _sanitize_tool_name(name: str) -> str:
    """Replace dots with double underscores for OpenAI API compatibility.

    OpenAI requires tool names to match ``^[a-zA-Z0-9_-]+$``.
    MCP tools use dotted names (e.g. ``spotify.search``).
    """
    return name.replace(".", "__")


def _restore_tool_name(sanitized: str) -> str:
    """Reverse ``_sanitize_tool_name`` — restore dotted MCP names."""
    return sanitized.replace("__", ".")


def convert_tool_definitions(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert project ToolDefinition models to OpenAI/LiteLLM function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": _sanitize_tool_name(td.name),
                "description": td.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        p.name: {"type": p.type, "description": p.description}
                        for p in td.parameters
                    },
                    "required": [p.name for p in td.parameters if p.required],
                },
            },
        }
        for td in tools
    ]


def build_assistant_message(response: AgentResponse) -> dict[str, Any]:
    """Build an assistant message dict in LiteLLM/OpenAI format from an AgentResponse."""
    msg: dict[str, Any] = {"role": "assistant", "content": response.text or ""}
    if response.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": _sanitize_tool_name(tc.name),
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in response.tool_calls
        ]
    return msg


def build_tool_result_message(tool_call_id: str, result: ToolResponse) -> dict[str, Any]:
    """Build a tool result message dict in LiteLLM/OpenAI format."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result.model_dump()),
    }


class ModelClient:
    """Wraps LiteLLM for agent LLM calls with fresh context per heartbeat."""

    def __init__(self, config: RunConfig, tool_definitions: list[ToolDefinition]) -> None:
        self.model_name = config.agent_model
        self.model_params = config.model_params
        self.tools = convert_tool_definitions(tool_definitions)
        self.log = log.bind(model=self.model_name)

    async def _call(self, messages: list[dict[str, Any]]) -> AgentResponse:
        """Execute a single LiteLLM call and parse the response."""
        response = await litellm.acompletion(
            model=self.model_name,
            messages=messages,
            tools=self.tools,
            **self.model_params,
        )

        choice = response.choices[0]
        text = choice.message.content

        parsed_calls: list[ParsedToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    self.log.error(
                        "malformed_tool_call_arguments",
                        tool_call_id=tc.id,
                        tool_name=tc.function.name,
                        raw_arguments=tc.function.arguments,
                    )
                    raise
                parsed_calls.append(
                    ParsedToolCall(
                        id=tc.id,
                        name=_restore_tool_name(tc.function.name),
                        arguments=arguments,
                    )
                )

        self.log.info(
            "model_call_complete",
            has_tool_calls=len(parsed_calls) > 0,
            tool_count=len(parsed_calls),
        )
        if parsed_calls:
            self.log.debug(
                "tool_calls_in_response",
                tool_names=[tc.name for tc in parsed_calls],
            )

        return AgentResponse(text=text, tool_calls=parsed_calls)

    async def complete(self, system_prompt: str, user_message: str) -> AgentResponse:
        """Single LiteLLM call — fresh messages list each call (NFR4: no history)."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return await self._call(messages)

    async def continue_conversation(self, messages: list[dict[str, Any]]) -> AgentResponse:
        """Continue an existing conversation with accumulated messages."""
        return await self._call(messages)
