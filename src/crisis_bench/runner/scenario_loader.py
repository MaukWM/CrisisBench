"""Scenario package loader — inverse of generator._write_scenario()."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from crisis_bench.models.scenario import (
    AgentIdentity,
    Contact,
    HeartbeatPayload,
    MemoryFile,
    PersonProfile,
    ScenarioManifest,
    ScenarioPackage,
    ToolDefinition,
)


class ScenarioLoadError(Exception):
    """Raised when a scenario package cannot be loaded."""


_REQUIRED_FILES = (
    "manifest.json",
    "scenario.json",
    "heartbeats.json",
    "tools.json",
    "persona.md",
)


def load_scenario(scenario_dir: Path) -> ScenarioPackage:
    """Read a scenario package directory and return a validated ScenarioPackage.

    This is the inverse of ``generator.generate._write_scenario()``.
    """
    # 1. File existence checks
    for filename in _REQUIRED_FILES:
        if not (scenario_dir / filename).exists():
            msg = f"Missing required file: {filename}"
            raise ScenarioLoadError(msg)

    memories_dir = scenario_dir / "memories"
    if not memories_dir.is_dir():
        msg = "Missing required file: memories/"
        raise ScenarioLoadError(msg)

    memory_paths = sorted(memories_dir.glob("*.md"))
    if not memory_paths:
        msg = "Missing required file: memories/*.md (directory is empty)"
        raise ScenarioLoadError(msg)

    # 2. Parse and validate JSON files
    manifest = ScenarioManifest(
        **json.loads((scenario_dir / "manifest.json").read_text(encoding="utf-8"))
    )

    scenario_meta: dict[str, Any] = json.loads(
        (scenario_dir / "scenario.json").read_text(encoding="utf-8")
    )

    heartbeat_dicts: list[dict[str, Any]] = json.loads(
        (scenario_dir / "heartbeats.json").read_text(encoding="utf-8")
    )
    heartbeats = [HeartbeatPayload(**hb) for hb in heartbeat_dicts]

    tool_dicts: list[dict[str, Any]] = json.loads(
        (scenario_dir / "tools.json").read_text(encoding="utf-8")
    )
    tool_definitions = [ToolDefinition(**td) for td in tool_dicts]

    # 3. Load text files
    persona = (scenario_dir / "persona.md").read_text(encoding="utf-8")

    memory_files = [
        MemoryFile(key=p.stem, content=p.read_text(encoding="utf-8"))
        for p in memory_paths
    ]

    # 4. Content hash verification
    heartbeats_json = json.dumps(
        [hb.model_dump() for hb in heartbeats], sort_keys=True
    )
    computed_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()
    if computed_hash != manifest.content_hash:
        msg = (
            f"Content hash mismatch: expected {manifest.content_hash}, "
            f"computed {computed_hash}"
        )
        raise ScenarioLoadError(msg)

    # 5. Reassemble into ScenarioPackage
    return ScenarioPackage(
        scenario_id=scenario_meta["scenario_id"],
        version=scenario_meta["version"],
        seed=scenario_meta["seed"],
        crisis_type=scenario_meta["crisis_type"],
        noise_tier=scenario_meta["noise_tier"],
        crisis_heartbeat_id=scenario_meta["crisis_heartbeat_id"],
        person=PersonProfile(**scenario_meta["person"]),
        contacts=[Contact(**c) for c in scenario_meta["contacts"]],
        agent_identity=AgentIdentity(**scenario_meta["agent_identity"]),
        heartbeats=heartbeats,
        tool_definitions=tool_definitions,
        memory_files=memory_files,
        persona=persona,
        manifest=manifest,
    )
