"""Tests for Orchestrator."""

from __future__ import annotations

import asyncio

import structlog.testing

from crisis_bench.models.runtime import RunConfig
from crisis_bench.models.scenario import ScenarioPackage
from crisis_bench.runner.orchestrator import Orchestrator


def _run(coro):  # noqa: ANN001, ANN202
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


class TestOrchestratorHeartbeats:
    """AC #3, #7: Orchestrator iterates heartbeats and detects crisis."""

    def test_orchestrator_iterates_heartbeats(
        self,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
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
        # Crisis at id=3, max_post_crisis=1 → ids 0,1,2,3,4 processed (5 total)
        # heartbeats: 0,1,2 are pre-crisis, 3 is crisis, 4 is post-crisis (count=1, then next would be 2>1 but there is no 5th)
        assert len(heartbeat_logs) == 5

    def test_orchestrator_respects_post_crisis_limit(
        self,
        small_scenario_package: ScenarioPackage,
    ) -> None:
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

    def test_orchestrator_logs_crisis_detection(
        self,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        crisis_logs = [e for e in logs if e["event"] == "crisis_heartbeat_reached"]
        assert len(crisis_logs) == 1
        assert crisis_logs[0]["heartbeat_id"] == 3

    def test_orchestrator_logs_run_complete(
        self,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        complete_logs = [e for e in logs if e["event"] == "run_complete"]
        assert len(complete_logs) == 1
        assert complete_logs[0]["total_heartbeats"] == 5
