"""Tests for generate_scenario() pipeline."""

from __future__ import annotations

import pytest

from crisis_bench.generator.generate import generate_scenario
from crisis_bench.models.scenario import ScenarioPackage


class TestGenerateScenario:
    """AC #3, #5: pipeline produces valid output and is importable."""

    def test_returns_scenario_package(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        assert isinstance(package, ScenarioPackage)

    def test_heartbeats_not_empty(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        assert len(package.heartbeats) > 0

    def test_crisis_heartbeat_id_set(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        assert package.crisis_heartbeat_id > 0

    def test_manifest_has_valid_hash(self) -> None:
        """SHA-256 hash is 64 hex chars."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        assert len(package.manifest.content_hash) == 64

    def test_health_data_present_on_all_heartbeats(self) -> None:
        """T4 includes health; every heartbeat should have it."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        for hb in package.heartbeats:
            assert hb.health is not None

    def test_crisis_vitals_absent(self) -> None:
        """Crisis heartbeats should show absent active vitals and ambiguous ECG."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        cid = package.crisis_heartbeat_id
        for hb in package.heartbeats[cid:]:
            assert hb.health is not None
            assert hb.health.heart_rate == 0
            assert hb.health.spo2 == 0
            assert hb.health.respiratory_rate == 0
            assert hb.health.ecg_summary == "inconclusive"

    def test_crisis_persists_cumulative_values(self) -> None:
        """Steps and calories should persist (not zero) during crisis."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        cid = package.crisis_heartbeat_id
        crisis_hb = package.heartbeats[cid]
        pre_crisis_hb = package.heartbeats[cid - 1]
        assert crisis_hb.health is not None
        assert pre_crisis_hb.health is not None
        # Steps should match the last normal reading (frozen, not zeroed).
        assert crisis_hb.health.steps == pre_crisis_hb.health.steps
        assert crisis_hb.health.steps > 0

    def test_cumulative_steps_increase(self) -> None:
        """Steps should be cumulative and generally increase during active periods."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        steps = [hb.health.steps for hb in package.heartbeats if hb.health is not None]
        # Steps should be non-decreasing (cumulative).
        for i in range(1, len(steps)):
            assert steps[i] >= steps[i - 1]

    def test_t1_only_has_health(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        for hb in package.heartbeats:
            assert hb.health is not None
            # Other modules not generated yet, so they'll be None.
            assert hb.location is None
            assert hb.weather is None
            assert hb.calendar is None
            assert hb.comms is None
            assert hb.financial is None

    def test_scenario_id_format(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        assert package.scenario_id == "cardiac_arrest_T2_s42"

    def test_unknown_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            generate_scenario(crisis_type="cardiac_arrest", tier="T5", seed=42)  # type: ignore[arg-type]

    def test_unknown_crisis_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown crisis_type"):
            generate_scenario(crisis_type="earthquake", tier="T4", seed=42)

    def test_pydantic_validation_passes(self) -> None:
        """The full package validates against the Pydantic schema."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        # Re-validate by round-tripping through dict → model.
        reloaded = ScenarioPackage(**package.model_dump())
        assert reloaded.scenario_id == package.scenario_id
