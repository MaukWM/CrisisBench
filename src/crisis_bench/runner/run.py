"""Runner entry point — loads config, scenario, and starts the orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

from crisis_bench.models.runtime import RunConfig
from crisis_bench.runner.orchestrator import Orchestrator
from crisis_bench.runner.scenario_loader import load_scenario


async def run_benchmark(
    scenario_path: Path,
    config_path: Path,
    *,
    max_heartbeats: int | None = None,
) -> None:
    """Load scenario and config, then run the benchmark orchestrator."""
    config = RunConfig(**json.loads(config_path.read_text(encoding="utf-8")))
    scenario = load_scenario(scenario_path)
    orchestrator = Orchestrator(scenario, config)
    await orchestrator.run(max_heartbeats=max_heartbeats)
