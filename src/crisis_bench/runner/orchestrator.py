"""Benchmark orchestrator — heartbeat iteration shell."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from crisis_bench.models.runtime import ActionLogEntry
from crisis_bench.prompt import PromptBuilder
from crisis_bench.runner.handlers.memory import MemoryHandler
from crisis_bench.runner.handlers.scenario_data import ScenarioDataHandler
from crisis_bench.runner.model_client import (
    ModelClient,
    build_assistant_message,
    build_tool_result_message,
)
from crisis_bench.runner.tool_router import ToolRouter

if TYPE_CHECKING:
    from crisis_bench.models.runtime import RunConfig
    from crisis_bench.models.scenario import ScenarioPackage

log = structlog.get_logger()


def _classify_action(tool_name: str) -> str:
    """Classify a tool call into an action category."""
    _QUERY_TOOLS = frozenset(
        {
            "query_wearable",
            "get_recent_updates",
            "get_contacts",
            "get_conversations",
            "list_events",
            "get_forecast",
            "get_balance",
            "get_transactions",
        }
    )
    _MEMORY_TOOLS = frozenset({"read_memory", "write_memory", "list_memories"})
    _COMMUNICATION_TOOLS = frozenset({"send_message", "make_call"})

    if tool_name in _QUERY_TOOLS:
        return "query"
    if tool_name in _MEMORY_TOOLS:
        return "memory"
    if tool_name in _COMMUNICATION_TOOLS:
        return "communication"
    return "tool_call"


_TOOL_SUMMARIES: dict[str, str | None] = {
    "query_wearable": "Checked wearable sensor data",
    "get_contacts": "Retrieved contacts list",
    "get_conversations": "Retrieved conversations",
    "list_events": "Listed calendar events",
    "get_forecast": "Checked weather forecast",
    "get_balance": "Checked account balance",
    "list_memories": "Listed memory files",
}


def _summarize_tool_call(tool_name: str, args: dict[str, Any]) -> str:
    """Generate a brief human-readable summary of a tool call."""
    static = _TOOL_SUMMARIES.get(tool_name)
    if static is not None:
        return static
    if tool_name == "get_recent_updates":
        return f"Retrieved {args.get('count', '?')} recent updates"
    if tool_name == "get_transactions":
        return f"Retrieved {args.get('count', '?')} recent transactions"
    if tool_name == "read_memory":
        return f"Read memory '{args.get('key', '?')}'"
    if tool_name == "write_memory":
        return f"Updated memory '{args.get('key', '?')}'"
    if tool_name == "send_message":
        return f"Sent message to {args.get('contact_id', '?')}"
    if tool_name == "make_call":
        return f"Called {args.get('number', '?')}"
    return f"Called {tool_name}"


class ActionLog:
    """Rolling window of tool actions across heartbeats."""

    def __init__(self, window_size: int) -> None:
        self._entries: list[ActionLogEntry] = []
        self._window_size = window_size

    def record(self, time: str, action_type: str, tool_name: str, summary: str) -> None:
        self._entries.append(
            ActionLogEntry(
                time=time,
                action_type=action_type,
                tool_name=tool_name,
                summary=summary,
            )
        )

    def get_window(self) -> tuple[list[ActionLogEntry], int]:
        return self._entries[-self._window_size :], len(self._entries)


class Orchestrator:
    """Drives benchmark execution by iterating through scenario heartbeats."""

    def __init__(self, scenario: ScenarioPackage, config: RunConfig) -> None:
        self.scenario = scenario
        self.config = config
        self.log = log.bind(scenario_id=scenario.scenario_id)
        self.prompt_builder = PromptBuilder(scenario)
        self.model_client = ModelClient(config, scenario.tool_definitions)
        self._action_log = ActionLog(config.action_log_window)

        self._memory_dir = Path(tempfile.mkdtemp(prefix="crisis_bench_"))
        self._scenario_data_handler = ScenarioDataHandler(scenario)
        memory_handler = MemoryHandler(self._memory_dir / "memories", scenario.memory_files)
        self.tool_router = ToolRouter(handlers=[self._scenario_data_handler, memory_handler])

    async def run(self, *, max_heartbeats: int | None = None) -> None:
        """Iterate heartbeats in order, respecting the post-crisis window."""
        post_crisis_count = 0
        total_count = 0

        for heartbeat_index, hb in enumerate(self.scenario.heartbeats):
            if max_heartbeats is not None and total_count >= max_heartbeats:
                self.log.info("max_heartbeats_reached", limit=max_heartbeats)
                break

            if hb.heartbeat_id > self.scenario.crisis_heartbeat_id:
                post_crisis_count += 1
                if post_crisis_count > self.config.max_post_crisis_heartbeats:
                    break

            self.log.info("heartbeat", heartbeat_id=hb.heartbeat_id, timestamp=hb.timestamp)
            total_count += 1

            self._scenario_data_handler.set_current_heartbeat(hb, heartbeat_index)

            # Build user message with action log context
            window, total = self._action_log.get_window()
            user_message = self.prompt_builder.build_user_message(
                heartbeat=hb,
                action_log_entries=window,
                total_action_count=total,
                pending_responses=[],  # Story 3.5
            )

            # Build messages list for multi-turn tracking
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.prompt_builder.system_prompt},
                {"role": "user", "content": user_message},
            ]

            # Multi-turn tool loop
            turn_count = 0
            max_turns = self.config.max_tool_turns

            while True:
                if turn_count == 0:
                    response = await self.model_client.complete(
                        self.prompt_builder.system_prompt,
                        user_message,
                    )
                else:
                    response = await self.model_client.continue_conversation(messages)

                self.log.info(
                    "agent_response",
                    heartbeat_id=hb.heartbeat_id,
                    turn=turn_count,
                    has_text=response.text is not None,
                    tool_call_count=len(response.tool_calls),
                )

                if not response.tool_calls:
                    break

                turn_count += 1

                # Add assistant message to conversation
                messages.append(build_assistant_message(response))

                # Execute and record tool calls
                for tc in response.tool_calls:
                    tool_response, handler_name = await self.tool_router.route(
                        tc.name, tc.arguments
                    )
                    self._action_log.record(
                        time=hb.timestamp,
                        action_type=_classify_action(tc.name),
                        tool_name=tc.name,
                        summary=_summarize_tool_call(tc.name, tc.arguments),
                    )
                    messages.append(build_tool_result_message(tc.id, tool_response))
                    self.log.info(
                        "tool_routed",
                        heartbeat_id=hb.heartbeat_id,
                        turn=turn_count,
                        tool_name=tc.name,
                        routed_to=handler_name,
                        status=tool_response.status,
                    )

                if turn_count >= max_turns:
                    self.log.info(
                        "max_tool_turns_reached",
                        heartbeat_id=hb.heartbeat_id,
                        turns=turn_count,
                    )
                    break

            if response.text:
                self.log.info("agent_text", heartbeat_id=hb.heartbeat_id, text=response.text)

            self.log.debug(
                "heartbeat_tool_summary",
                heartbeat_id=hb.heartbeat_id,
                tool_turns=turn_count,
            )

            if hb.heartbeat_id == self.scenario.crisis_heartbeat_id:
                self.log.info("crisis_heartbeat_reached", heartbeat_id=hb.heartbeat_id)

        self.log.info(
            "run_complete",
            total_heartbeats=total_count,
            post_crisis_heartbeats=post_crisis_count,
        )
