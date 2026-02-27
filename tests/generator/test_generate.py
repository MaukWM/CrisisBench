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


class TestHealthRealism:
    """Verify the 6 realism improvements produce physiologically plausible data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)

    def test_crisis_skin_temp_declines(self, package: ScenarioPackage) -> None:
        """Skin temp should monotonically decrease during crisis (cooling body)."""
        cid = package.crisis_heartbeat_id
        crisis_temps = [
            hb.health.skin_temp for hb in package.heartbeats[cid:] if hb.health is not None
        ]
        assert len(crisis_temps) >= 10
        for i in range(1, len(crisis_temps)):
            assert crisis_temps[i] <= crisis_temps[i - 1]
        # Over 20 heartbeats at -0.1°C each, expect >1°C total drop.
        assert crisis_temps[0] - crisis_temps[-1] > 1.0

    def test_crisis_blood_glucose_drifts_up(self, package: ScenarioPackage) -> None:
        """Blood glucose should drift upward during crisis (cells stop consuming)."""
        cid = package.crisis_heartbeat_id
        crisis_glucose = [
            hb.health.blood_glucose for hb in package.heartbeats[cid:] if hb.health is not None
        ]
        assert len(crisis_glucose) >= 10
        # Overall trend must be upward.
        assert crisis_glucose[-1] > crisis_glucose[0]

    def test_blood_glucose_meal_response(self, package: ScenarioPackage) -> None:
        """Blood glucose should spike after breakfast and lunch meals."""
        cid = package.crisis_heartbeat_id
        normal_hbs = package.heartbeats[:cid]
        glucose_values = [hb.health.blood_glucose for hb in normal_hbs if hb.health is not None]
        # Find the baseline (first few readings before breakfast kicks in).
        baseline = glucose_values[0]
        peak = max(glucose_values)
        # Meal response should cause at least a 15 mg/dL spike above baseline.
        assert peak - baseline > 15.0

    def test_skin_temp_stays_in_range(self, package: ScenarioPackage) -> None:
        """Normal skin temp should stay within 36.0-37.2°C."""
        cid = package.crisis_heartbeat_id
        for hb in package.heartbeats[:cid]:
            assert hb.health is not None
            assert 36.0 <= hb.health.skin_temp <= 37.2

    def test_steps_bursty_during_sedentary(self, package: ScenarioPackage) -> None:
        """During sedentary blocks, >50% of heartbeats should add zero steps (bursty)."""
        cid = package.crisis_heartbeat_id
        normal_hbs = [hb for hb in package.heartbeats[:cid] if hb.health is not None]
        # Compute step deltas.
        deltas = [
            normal_hbs[i].health.steps - normal_hbs[i - 1].health.steps
            for i in range(1, len(normal_hbs))
        ]
        zero_deltas = sum(1 for d in deltas if d == 0)
        # At least some zeros (bursty pattern — sedentary periods have many zeros).
        assert zero_deltas > len(deltas) * 0.3
        # But not all zeros — there should be some bursts.
        assert zero_deltas < len(deltas)

    def test_body_battery_occasionally_recovers(self, package: ScenarioPackage) -> None:
        """Body battery should occasionally increase during rest, but trend down overall."""
        cid = package.crisis_heartbeat_id
        normal_hbs = [hb for hb in package.heartbeats[:cid] if hb.health is not None]
        batteries = [hb.health.body_battery for hb in normal_hbs]
        deltas = [batteries[i] - batteries[i - 1] for i in range(1, len(batteries))]
        # At least one positive delta (recovery).
        assert any(d > 0 for d in deltas), "Expected at least one body battery recovery"
        # Net trend should be downward.
        assert batteries[-1] < batteries[0]

    def test_hr_micro_spikes_during_sedentary(self, package: ScenarioPackage) -> None:
        """At least one HR should spike above the block's max range during sedentary work."""
        # Working blocks have hr_range (63, 70). Spikes add 10-25.
        package_hrs = []
        cid = package.crisis_heartbeat_id
        for hb in package.heartbeats[:cid]:
            if hb.health is not None and hb.health.heart_rate > 70:
                package_hrs.append(hb.health.heart_rate)
        # With ~139 pre-crisis heartbeats and 10% spike chance during many
        # sedentary blocks, we expect at least a few spikes above 70.
        assert len(package_hrs) > 0, "Expected at least one HR spike above 70 BPM"
