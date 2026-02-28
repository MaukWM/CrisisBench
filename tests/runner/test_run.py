"""Tests for run_benchmark entry point."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from crisis_bench.runner.run import run_benchmark

_SCENARIO_DIR = Path("scenarios/cardiac_arrest_T4_s42")


class TestRunBenchmark:
    """AC #4, #5, #6: Runner entry point loads config and runs."""

    @patch("crisis_bench.runner.orchestrator.create_react_agent")
    @patch("crisis_bench.runner.orchestrator.ChatLiteLLM")
    def test_run_benchmark_loads_config(
        self,
        mock_chat: MagicMock,
        mock_create_agent: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="Noted.")]})
        mock_create_agent.return_value = mock_graph

        config_data = {
            "agent_model": "test-model",
            "user_sim_model": "test-sim",
            "judge_model": "test-judge",
            "max_post_crisis_heartbeats": 1,
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        asyncio.run(run_benchmark(_SCENARIO_DIR, config_path))

    def test_run_benchmark_invalid_config_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValidationError):
            asyncio.run(run_benchmark(_SCENARIO_DIR, config_path))

    def test_run_benchmark_importable(self) -> None:
        from crisis_bench.runner.run import run_benchmark as fn

        assert callable(fn)
