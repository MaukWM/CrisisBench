"""Benchmark orchestrator — heartbeat iteration shell."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from crisis_bench.prompt import PromptBuilder
from crisis_bench.runner.handlers.memory import MemoryHandler
from crisis_bench.runner.handlers.scenario_data import ScenarioDataHandler
from crisis_bench.runner.model_client import ModelClient
from crisis_bench.runner.tool_router import ToolRouter

if TYPE_CHECKING:
    from crisis_bench.models.runtime import RunConfig
    from crisis_bench.models.scenario import ScenarioPackage

log = structlog.get_logger()


class Orchestrator:
    """Drives benchmark execution by iterating through scenario heartbeats."""

    def __init__(self, scenario: ScenarioPackage, config: RunConfig) -> None:
        self.scenario = scenario
        self.config = config
        self.log = log.bind(scenario_id=scenario.scenario_id)
        self.prompt_builder = PromptBuilder(scenario)
        self.model_client = ModelClient(config, scenario.tool_definitions)

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

            user_message = self.prompt_builder.build_user_message(
                heartbeat=hb,
                action_log_entries=[],
                total_action_count=0,
                pending_responses=[],
            )
            response = await self.model_client.complete(
                self.prompt_builder.system_prompt,
                user_message,
            )
            self.log.info(
                "agent_response",
                heartbeat_id=hb.heartbeat_id,
                has_text=response.text is not None,
                tool_call_count=len(response.tool_calls),
            )
            if response.text:
                self.log.info("agent_text", heartbeat_id=hb.heartbeat_id, text=response.text)

            for tc in response.tool_calls:
                tool_response, handler_name = await self.tool_router.route(tc.name, tc.arguments)
                self.log.info(
                    "tool_routed",
                    heartbeat_id=hb.heartbeat_id,
                    tool_name=tc.name,
                    routed_to=handler_name,
                    status=tool_response.status,
                )

            if hb.heartbeat_id == self.scenario.crisis_heartbeat_id:
                self.log.info("crisis_heartbeat_reached", heartbeat_id=hb.heartbeat_id)

        self.log.info(
            "run_complete",
            total_heartbeats=total_count,
            post_crisis_heartbeats=post_crisis_count,
        )
