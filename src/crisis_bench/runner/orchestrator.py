"""Benchmark orchestrator — heartbeat iteration shell."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

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

    async def run(self) -> None:
        """Iterate heartbeats in order, respecting the post-crisis window."""
        post_crisis_count = 0
        total_count = 0

        for hb in self.scenario.heartbeats:
            if hb.heartbeat_id > self.scenario.crisis_heartbeat_id:
                post_crisis_count += 1
                if post_crisis_count > self.config.max_post_crisis_heartbeats:
                    break

            self.log.info("heartbeat", heartbeat_id=hb.heartbeat_id, timestamp=hb.timestamp)
            total_count += 1

            if hb.heartbeat_id == self.scenario.crisis_heartbeat_id:
                self.log.info("crisis_heartbeat_reached", heartbeat_id=hb.heartbeat_id)

        self.log.info(
            "run_complete",
            total_heartbeats=total_count,
            post_crisis_heartbeats=post_crisis_count,
        )
