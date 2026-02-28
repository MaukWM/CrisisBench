"""Tests for Orchestrator."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import structlog.testing

from crisis_bench.models.runtime import RunConfig
from crisis_bench.runner.model_client import AgentResponse
from crisis_bench.runner.orchestrator import Orchestrator

if TYPE_CHECKING:
    from crisis_bench.models.scenario import ScenarioPackage


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class TestOrchestratorHeartbeats:
    """AC #3, #7: Orchestrator iterates heartbeats and detects crisis."""

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_iterates_heartbeats(
        self,
        mock_complete: AsyncMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=1,
        )
        orchestrator = Orchestrator(small_scenario_package, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        heartbeat_logs = [e for e in logs if e["event"] == "heartbeat"]
        # Crisis at id=3, max_post_crisis=1 → ids 0,1,2,3,4 processed
        # (5 total: 3 pre-crisis + crisis + 1 post-crisis)
        assert len(heartbeat_logs) == 5

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_respects_post_crisis_limit(
        self,
        mock_complete: AsyncMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=0,
        )
        orchestrator = Orchestrator(small_scenario_package, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        heartbeat_logs = [e for e in logs if e["event"] == "heartbeat"]
        # Crisis at id=3, max_post_crisis=0 → id=4 is first post-crisis (count=1 > 0), breaks
        # So we get heartbeats 0,1,2,3 → 4 heartbeats
        assert len(heartbeat_logs) == 4

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_logs_crisis_detection(
        self,
        mock_complete: AsyncMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        crisis_logs = [e for e in logs if e["event"] == "crisis_heartbeat_reached"]
        assert len(crisis_logs) == 1
        assert crisis_logs[0]["heartbeat_id"] == 3

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_logs_run_complete(
        self,
        mock_complete: AsyncMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        complete_logs = [e for e in logs if e["event"] == "run_complete"]
        assert len(complete_logs) == 1
        assert complete_logs[0]["total_heartbeats"] == 5

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_calls_model_per_heartbeat(
        self,
        mock_complete: AsyncMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """Verify model_client.complete is called once per heartbeat."""
        mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=1,
        )
        orchestrator = Orchestrator(small_scenario_package, config)
        _run(orchestrator.run())
        # 5 heartbeats processed (3 pre-crisis + crisis + 1 post-crisis)
        assert mock_complete.call_count == 5
        # Verify system prompt and user message are passed.
        for call in mock_complete.call_args_list:
            args = call.args
            assert len(args) == 2
            assert isinstance(args[0], str)  # system_prompt
            assert isinstance(args[1], str)  # user_message
            assert "# Who You Are" in args[0]  # system prompt has SOUL section
