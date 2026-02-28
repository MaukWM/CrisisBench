"""Tests for Orchestrator."""

from __future__ import annotations

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock, patch

import structlog.testing

from crisis_bench.models.runtime import RunConfig
from crisis_bench.models.scenario import (
    AgentIdentity,
    Contact,
    HeartbeatPayload,
    MemoryFile,
    PersonProfile,
    ScenarioManifest,
    ScenarioPackage,
    ToolDefinition,
    WearableData,
)
from crisis_bench.runner.model_client import AgentResponse, ParsedToolCall
from crisis_bench.runner.orchestrator import Orchestrator


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


class TestOrchestratorToolRouting:
    """Verify ToolRouter + handlers are wired and route tool calls."""

    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_routes_tool_calls(
        self,
        mock_complete: AsyncMock,
    ) -> None:
        """Model returns a tool call → tool_router.route is invoked."""
        heartbeats = [
            HeartbeatPayload(
                heartbeat_id=0,
                timestamp="2027-06-15T10:00:00Z",
                wearable=WearableData(
                    heart_rate=72,
                    spo2=98,
                    steps=5000,
                    skin_temp=36.5,
                    ecg_summary="Normal sinus rhythm",
                    blood_glucose=95.0,
                    calories_burned=320,
                    sleep_stage="awake",
                    respiratory_rate=16,
                    body_battery=65,
                ),
            ),
        ]
        heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
        content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()

        scenario = ScenarioPackage(
            scenario_id="test_routing_s1",
            version="1.0.0",
            seed=1,
            crisis_type="test",
            noise_tier="T1",
            crisis_heartbeat_id=0,
            person=PersonProfile(
                name="Test User",
                birthday="January 1, 2000",
                occupation="Tester",
                home_address="123 Test St",
                office_address="456 Work Ave",
            ),
            contacts=[
                Contact(id="c1", name="Contact One", relationship="friend", phone="+1-555-0001"),
            ],
            agent_identity=AgentIdentity(name="TestBot", personality="Helpful"),
            heartbeats=heartbeats,
            tool_definitions=[
                ToolDefinition(name="query_wearable", description="test", parameters=[]),
            ],
            memory_files=[
                MemoryFile(key="test_memory", content="# Test memory"),
            ],
            persona="You are a test persona.",
            manifest=ScenarioManifest(
                content_hash=content_hash,
                generator_version="0.1.0",
                generated_at="2027-06-15T10:00:00Z",
            ),
        )
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=0,
        )

        mock_complete.return_value = AgentResponse(
            text="Let me check.",
            tool_calls=[
                ParsedToolCall(id="call_1", name="query_wearable", arguments={}),
            ],
        )

        orchestrator = Orchestrator(scenario, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())

        routed_logs = [e for e in logs if e["event"] == "tool_routed"]
        assert len(routed_logs) == 1
        assert routed_logs[0]["tool_name"] == "query_wearable"
        assert routed_logs[0]["routed_to"] == "ScenarioDataHandler"
        assert routed_logs[0]["status"] == "ok"
