"""Tests for ScenarioLoader."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from crisis_bench.models.scenario import ScenarioPackage
from crisis_bench.runner.scenario_loader import ScenarioLoadError, load_scenario

_SCENARIO_DIR = Path("scenarios/cardiac_arrest_T4_s42")


class TestLoadValidScenario:
    """AC #1: ScenarioLoader reads and validates a scenario package."""

    def test_load_valid_scenario(self) -> None:
        package = load_scenario(_SCENARIO_DIR)
        assert isinstance(package, ScenarioPackage)
        assert package.scenario_id == "cardiac_arrest_T4_s42"
        assert package.crisis_type == "cardiac_arrest"
        assert package.noise_tier == "T4"
        assert len(package.heartbeats) > 0
        assert len(package.tool_definitions) > 0
        assert len(package.memory_files) > 0
        assert package.persona != ""

    def test_load_validates_content_hash(self) -> None:
        import hashlib

        package = load_scenario(_SCENARIO_DIR)
        heartbeats_json = json.dumps(
            [hb.model_dump() for hb in package.heartbeats], sort_keys=True
        )
        computed = hashlib.sha256(heartbeats_json.encode()).hexdigest()
        assert computed == package.manifest.content_hash

    def test_load_memory_files(self) -> None:
        package = load_scenario(_SCENARIO_DIR)
        memory_keys = {mf.key for mf in package.memory_files}
        expected_keys = {"user_profile", "preferences", "work_context", "recurring_notes"}
        assert memory_keys == expected_keys

    def test_load_persona(self) -> None:
        package = load_scenario(_SCENARIO_DIR)
        assert isinstance(package.persona, str)
        assert len(package.persona) > 0


class TestLoadInvalidScenario:
    """AC #2: ScenarioLoader raises clear errors for invalid packages."""

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        shutil.copytree(_SCENARIO_DIR, tmp_path / "pkg", dirs_exist_ok=True)
        (tmp_path / "pkg" / "heartbeats.json").unlink()
        with pytest.raises(ScenarioLoadError, match="Missing required file: heartbeats.json"):
            load_scenario(tmp_path / "pkg")

    def test_load_missing_memories_dir_raises(self, tmp_path: Path) -> None:
        shutil.copytree(_SCENARIO_DIR, tmp_path / "pkg", dirs_exist_ok=True)
        shutil.rmtree(tmp_path / "pkg" / "memories")
        with pytest.raises(ScenarioLoadError, match="Missing required file: memories/"):
            load_scenario(tmp_path / "pkg")

    def test_load_empty_memories_dir_raises(self, tmp_path: Path) -> None:
        shutil.copytree(_SCENARIO_DIR, tmp_path / "pkg", dirs_exist_ok=True)
        shutil.rmtree(tmp_path / "pkg" / "memories")
        (tmp_path / "pkg" / "memories").mkdir()
        with pytest.raises(ScenarioLoadError, match="directory is empty"):
            load_scenario(tmp_path / "pkg")

    def test_load_bad_json_raises(self, tmp_path: Path) -> None:
        shutil.copytree(_SCENARIO_DIR, tmp_path / "pkg", dirs_exist_ok=True)
        (tmp_path / "pkg" / "manifest.json").write_text("{bad json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_scenario(tmp_path / "pkg")

    def test_load_hash_mismatch_raises(self, tmp_path: Path) -> None:
        shutil.copytree(_SCENARIO_DIR, tmp_path / "pkg", dirs_exist_ok=True)
        # Tamper with heartbeats to break the hash
        hb_path = tmp_path / "pkg" / "heartbeats.json"
        heartbeats = json.loads(hb_path.read_text(encoding="utf-8"))
        heartbeats[0]["timestamp"] = "1999-01-01T00:00:00Z"
        hb_path.write_text(json.dumps(heartbeats, indent=2), encoding="utf-8")
        with pytest.raises(ScenarioLoadError, match="Content hash mismatch"):
            load_scenario(tmp_path / "pkg")
