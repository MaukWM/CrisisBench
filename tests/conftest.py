"""Shared test fixtures for crisis-bench."""

from __future__ import annotations

import pytest

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
    ToolParameter,
)


@pytest.fixture()
def small_scenario_package() -> ScenarioPackage:
    """Minimal ScenarioPackage with 5 heartbeats, crisis at heartbeat 3."""
    import hashlib
    import json

    heartbeats = [
        HeartbeatPayload(heartbeat_id=i, timestamp=f"2027-06-15T10:0{i}:00Z") for i in range(5)
    ]
    heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
    content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()

    return ScenarioPackage(
        scenario_id="test_T1_s1",
        version="1.0.0",
        seed=1,
        crisis_type="test",
        noise_tier="T1",
        crisis_heartbeat_id=3,
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
            ToolDefinition(
                name="test_tool",
                description="A test tool",
                parameters=[
                    ToolParameter(
                        name="arg1", type="string", description="An argument", required=True
                    ),
                ],
            ),
        ],
        memory_files=[
            MemoryFile(key="test_memory", content="# Test memory\nSome content."),
        ],
        persona="You are a test persona.",
        manifest=ScenarioManifest(
            content_hash=content_hash,
            generator_version="0.1.0",
            generated_at="2027-06-15T10:00:00Z",
        ),
    )


@pytest.fixture()
def default_run_config() -> RunConfig:
    """RunConfig with sensible test defaults."""
    return RunConfig(
        agent_model="test-model",
        user_sim_model="test-sim-model",
        judge_model="test-judge-model",
    )
