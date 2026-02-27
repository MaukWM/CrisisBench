"""Full round-trip determinism tests.

AC #2: same seed + same crisis type + same tier = identical ScenarioPackage.
"""

from __future__ import annotations

from crisis_bench.generator.generate import generate_scenario


class TestFullPipelineDeterminism:
    """Verify that the entire pipeline is deterministic."""

    def test_same_inputs_produce_identical_packages(self) -> None:
        p1 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        p2 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)

        # Content hashes must match.
        assert p1.manifest.content_hash == p2.manifest.content_hash

        # Heartbeat data must match exactly.
        assert len(p1.heartbeats) == len(p2.heartbeats)
        for hb1, hb2 in zip(p1.heartbeats, p2.heartbeats, strict=False):
            assert hb1.model_dump() == hb2.model_dump()

    def test_different_seeds_produce_different_health(self) -> None:
        p1 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=1)
        p2 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=2)
        # At least one heartbeat's health data should differ.
        diffs = [
            hb1.health != hb2.health
            for hb1, hb2 in zip(p1.heartbeats, p2.heartbeats, strict=False)
            if hb1.health is not None and hb2.health is not None
        ]
        assert any(diffs)

    def test_stateful_health_fields_deterministic(self) -> None:
        """Stateful fields (skin_temp, blood_glucose, body_battery) must match
        across identical-seed runs, proving the RNG consumption order is stable."""
        p1 = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=99)
        p2 = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=99)
        for hb1, hb2 in zip(p1.heartbeats, p2.heartbeats, strict=False):
            assert hb1.health is not None
            assert hb2.health is not None
            assert hb1.health.skin_temp == hb2.health.skin_temp
            assert hb1.health.blood_glucose == hb2.health.blood_glucose
            assert hb1.health.body_battery == hb2.health.body_battery

    def test_determinism_across_tiers(self) -> None:
        """Same seed, different tiers — both produce valid packages.

        Currently T1 and T4 produce identical health data because only the
        HealthGenerator exists.  Once Stories 2.2-2.4 add more generators
        that consume RNG calls, T4 will diverge from T1.
        """
        p_t1 = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        p_t4 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)

        assert len(p_t1.heartbeats) == len(p_t4.heartbeats)
        # Both are valid packages.
        assert p_t1.manifest.content_hash
        assert p_t4.manifest.content_hash
