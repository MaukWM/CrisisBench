"""Tests for Orchestrator."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import structlog.testing
from langchain_core.messages import AIMessage

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
from crisis_bench.runner.orchestrator import Orchestrator


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _mock_agent_result(text: str = "Noted.") -> dict[str, Any]:
    """Build a mock LangGraph agent result with a single AIMessage."""
    return {"messages": [AIMessage(content=text)]}


def _patch_langgraph() -> tuple[Any, ...]:
    """Return patch decorators for ChatLiteLLM and create_react_agent."""
    return (
        patch("crisis_bench.runner.orchestrator.ChatLiteLLM"),
        patch("crisis_bench.runner.orchestrator.create_react_agent"),
    )


class TestOrchestratorHeartbeats:
    """AC #3, #7: Orchestrator iterates heartbeats and detects crisis."""

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_iterates_heartbeats(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

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
        assert len(heartbeat_logs) == 5

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_respects_post_crisis_limit(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

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
        assert len(heartbeat_logs) == 4

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_logs_crisis_detection(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        crisis_logs = [e for e in logs if e["event"] == "crisis_heartbeat_reached"]
        assert len(crisis_logs) == 1
        assert crisis_logs[0]["heartbeat_id"] == 3

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_logs_run_complete(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
        default_run_config: RunConfig,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

        orchestrator = Orchestrator(small_scenario_package, default_run_config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run())
        complete_logs = [e for e in logs if e["event"] == "run_complete"]
        assert len(complete_logs) == 1
        assert complete_logs[0]["total_heartbeats"] == 5

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_calls_agent_per_heartbeat(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """Verify agent.ainvoke is called once per heartbeat."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=1,
        )
        orchestrator = Orchestrator(small_scenario_package, config)
        _run(orchestrator.run())
        # 5 heartbeats processed (3 pre-crisis + crisis + 1 post-crisis)
        assert mock_graph.ainvoke.call_count == 5


class TestOrchestratorToolRouting:
    """Verify tool routing works through the LangGraph agent."""

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_orchestrator_routes_tool_calls(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
    ) -> None:
        """Agent invocation produces tool_routed logs when tools are called by the factory."""
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

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result("Done."))
        mock_create_agent.return_value = mock_graph

        orchestrator = Orchestrator(scenario, config)

        # Set up heartbeat state so scenario data handler has data to return
        orchestrator._scenario_data_handler.set_current_heartbeat(heartbeats[0], 0)
        orchestrator._current_timestamp = heartbeats[0].timestamp

        # Manually invoke a tool to verify routing works end-to-end
        wearable_tool = next(t for t in orchestrator._lc_tools if t.name == "query_wearable")
        result_json = _run(wearable_tool.ainvoke({}))

        import json as json_mod

        parsed = json_mod.loads(result_json)
        assert parsed["status"] == "ok"

        # Verify action log was populated
        entries, total = orchestrator._action_log.get_window()
        assert total == 1
        assert entries[0].tool_name == "query_wearable"


class TestMaxToolTurns:
    """GraphRecursionError handling for max_tool_turns."""

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_max_tool_turns_reached(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """AC #2: GraphRecursionError is caught and logged."""
        from langgraph.errors import GraphRecursionError

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=GraphRecursionError("Recursion limit reached"))
        mock_create_agent.return_value = mock_graph

        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_tool_turns=2,
            max_post_crisis_heartbeats=0,
        )
        orchestrator = Orchestrator(small_scenario_package, config)
        with structlog.testing.capture_logs() as logs:
            _run(orchestrator.run(max_heartbeats=1))

        max_logs = [e for e in logs if e["event"] == "max_tool_turns_reached"]
        assert len(max_logs) == 1
        assert max_logs[0]["turns"] == 2

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_action_log_accumulates_across_heartbeats(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        small_scenario_package: ScenarioPackage,
    ) -> None:
        """AC #3, #5: Action log from heartbeat 1 appears in heartbeat 2's user message."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value=_mock_agent_result())
        mock_create_agent.return_value = mock_graph

        config = RunConfig(
            agent_model="test",
            user_sim_model="test",
            judge_model="test",
            max_post_crisis_heartbeats=0,
        )
        orchestrator = Orchestrator(small_scenario_package, config)

        # Manually record an action to simulate heartbeat 1 tool usage
        orchestrator._action_log.record(
            time="2027-06-15T10:00:00Z",
            action_type="memory",
            tool_name="list_memories",
            summary="Listed memory files",
        )

        _run(orchestrator.run(max_heartbeats=1))

        # The agent was invoked with messages containing the action log
        call_args = mock_graph.ainvoke.call_args
        messages = call_args[0][0]["messages"]
        user_msg = messages[1]["content"]
        assert "Listed memory files" in user_msg
