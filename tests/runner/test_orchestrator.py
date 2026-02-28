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

    @patch(
        "crisis_bench.runner.model_client.ModelClient.continue_conversation",
        new_callable=AsyncMock,
    )
    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_orchestrator_routes_tool_calls(
        self,
        mock_complete: AsyncMock,
        mock_continue: AsyncMock,
    ) -> None:
        """Model returns a tool call → tool_router.route is invoked, then loop terminates."""
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
        mock_continue.return_value = AgentResponse(text="Done.", tool_calls=[])

        orchestrator = Orchestrator(scenario, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())

        routed_logs = [e for e in logs if e["event"] == "tool_routed"]
        assert len(routed_logs) == 1
        assert routed_logs[0]["tool_name"] == "query_wearable"
        assert routed_logs[0]["routed_to"] == "ScenarioDataHandler"
        assert routed_logs[0]["status"] == "ok"

        # Verify multi-turn: complete called once, continue_conversation called once
        assert mock_complete.call_count == 1
        assert mock_continue.call_count == 1


class TestMultiTurnToolLoop:
    """AC #1, #2, #3, #5, #6, #7: Multi-turn tool loop behavior."""

    @patch(
        "crisis_bench.runner.model_client.ModelClient.continue_conversation",
        new_callable=AsyncMock,
    )
    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_multi_turn_tool_loop(
        self,
        mock_complete: AsyncMock,
        mock_continue: AsyncMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """AC #1: Agent makes tool call, results sent back, loop terminates when no more calls."""
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=0,
        )
        mock_complete.return_value = AgentResponse(
            text="Let me check.",
            tool_calls=[ParsedToolCall(id="call_1", name="list_memories", arguments={})],
        )
        mock_continue.return_value = AgentResponse(text="All done.", tool_calls=[])

        orchestrator = Orchestrator(small_scenario_package, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run(max_heartbeats=1))

        # complete called once per heartbeat (turn 0), continue once (turn 1)
        assert mock_complete.call_count == 1
        assert mock_continue.call_count == 1

        # tool_routed log should appear
        routed_logs = [e for e in logs if e["event"] == "tool_routed"]
        assert len(routed_logs) == 1
        assert routed_logs[0]["tool_name"] == "list_memories"
        assert routed_logs[0]["routed_to"] == "MemoryHandler"

        # agent_response logged for both turns
        agent_logs = [e for e in logs if e["event"] == "agent_response"]
        assert len(agent_logs) == 2
        assert agent_logs[0]["turn"] == 0
        assert agent_logs[1]["turn"] == 1

    @patch(
        "crisis_bench.runner.model_client.ModelClient.continue_conversation",
        new_callable=AsyncMock,
    )
    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_max_tool_turns_reached(
        self,
        mock_complete: AsyncMock,
        mock_continue: AsyncMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """AC #2: Loop stops at max_tool_turns, final tool calls executed, INFO log emitted."""
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_tool_turns=2,
            max_post_crisis_heartbeats=0,
        )
        # Both always return tool calls — loop should be capped at max_tool_turns
        mock_complete.return_value = AgentResponse(
            text="Checking...",
            tool_calls=[ParsedToolCall(id="call_1", name="list_memories", arguments={})],
        )
        mock_continue.return_value = AgentResponse(
            text="More...",
            tool_calls=[ParsedToolCall(id="call_2", name="list_memories", arguments={})],
        )

        orchestrator = Orchestrator(small_scenario_package, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run(max_heartbeats=1))

        # Turn 0: complete returns tool call → turn_count=1, execute, 1<2 → loop
        # Turn 1: continue returns tool call → turn_count=2, execute, 2>=2 → break
        # Total: 1 complete + 1 continue = 2 model calls
        assert mock_complete.call_count == 1
        assert mock_continue.call_count == 1

        # max_tool_turns_reached log
        max_logs = [e for e in logs if e["event"] == "max_tool_turns_reached"]
        assert len(max_logs) == 1
        assert max_logs[0]["turns"] == 2

        # Tool calls from final turn are still executed (AC #2)
        routed_logs = [e for e in logs if e["event"] == "tool_routed"]
        assert len(routed_logs) == 2  # 1 from turn 0, 1 from turn 1

    @patch(
        "crisis_bench.runner.model_client.ModelClient.continue_conversation",
        new_callable=AsyncMock,
    )
    @patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
    def test_action_log_accumulates_across_heartbeats(
        self,
        mock_complete: AsyncMock,
        mock_continue: AsyncMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """AC #3, #5: Action log from heartbeat 1 appears in heartbeat 2's user message."""
        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=0,
        )
        # First heartbeat: tool call, then done
        # Second heartbeat: no tool calls
        call_count = 0

        async def mock_complete_side_effect(system_prompt, user_message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AgentResponse(
                    text="Checking.",
                    tool_calls=[ParsedToolCall(id="call_1", name="list_memories", arguments={})],
                )
            return AgentResponse(text="Noted.", tool_calls=[])

        mock_complete.side_effect = mock_complete_side_effect
        mock_continue.return_value = AgentResponse(text="Done.", tool_calls=[])

        orchestrator = Orchestrator(small_scenario_package, config)
        _run(orchestrator.run(max_heartbeats=2))

        # On the second heartbeat, complete is called with user_message containing action log
        assert mock_complete.call_count == 2
        second_call_user_message = mock_complete.call_args_list[1].args[1]
        assert "Listed memory files" in second_call_user_message
