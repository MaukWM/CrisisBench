"""Tests for generate_scenario() pipeline."""

from __future__ import annotations

import copy
import json

import pytest

from crisis_bench.generator.generate import generate_scenario
from crisis_bench.generator.modules.crisis import CrisisInjector
from crisis_bench.generator.tools import collect_tool_definitions
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

    def test_occasional_missing_modules(self) -> None:
        """Non-health modules should have occasional None heartbeats (~1.5% drop)."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        # At least one non-health module should have a None somewhere.
        has_drop = False
        for hb in package.heartbeats:
            if (
                hb.location is None
                or hb.weather is None
                or hb.calendar is None
                or hb.financial is None
            ):
                has_drop = True
                break
        assert has_drop, "Expected at least one None in non-health modules"


class TestHealthRealism:
    """Verify the 6 realism improvements produce physiologically plausible data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)

    def test_crisis_skin_temp_declines(self, package: ScenarioPackage) -> None:
        """Skin temp should decrease overall during crisis (exponential cooling).

        With ±0.05°C noise, individual pairs may not be strictly monotone,
        but the overall drop over 20 heartbeats should be >1°C.
        """
        cid = package.crisis_heartbeat_id
        crisis_temps = [
            hb.health.skin_temp for hb in package.heartbeats[cid:] if hb.health is not None
        ]
        assert len(crisis_temps) >= 10
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

    def test_spo2_has_range_beyond_96_99(self, package: ScenarioPackage) -> None:
        """SpO2 should occasionally read outside the old 96-99 range."""
        cid = package.crisis_heartbeat_id
        spo2_values = [hb.health.spo2 for hb in package.heartbeats[:cid] if hb.health is not None]
        has_outlier = any(v < 96 or v > 99 for v in spo2_values)
        assert has_outlier, "Expected at least one SpO2 outside 96-99"

    def test_ecg_has_occasional_artifacts(self, package: ScenarioPackage) -> None:
        """Normal blocks should occasionally produce ECG artifacts."""
        cid = package.crisis_heartbeat_id
        ecg_values = [
            hb.health.ecg_summary for hb in package.heartbeats[:cid] if hb.health is not None
        ]
        non_normal = [e for e in ecg_values if e != "normal sinus rhythm"]
        assert len(non_normal) > 0, "Expected at least one ECG artifact during normal"

    def test_crisis_cooling_decelerates(self, package: ScenarioPackage) -> None:
        """Exponential cooling: first-half temp drop > second-half temp drop."""
        cid = package.crisis_heartbeat_id
        crisis_temps = [
            hb.health.skin_temp for hb in package.heartbeats[cid:] if hb.health is not None
        ]
        mid = len(crisis_temps) // 2
        first_half_drop = crisis_temps[0] - crisis_temps[mid]
        second_half_drop = crisis_temps[mid] - crisis_temps[-1]
        assert first_half_drop > second_half_drop

    def test_glucose_dips_during_running(self) -> None:
        """Blood glucose should dip during running vs preceding sedentary block."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        cid = package.crisis_heartbeat_id
        normal_hbs = [hb for hb in package.heartbeats[:cid] if hb.health is not None]
        # Find running heartbeats (last 4 before crisis: 17:45-18:05 = 4 heartbeats).
        # The preceding "home" block has 3 heartbeats (17:30-17:45).
        # Compare average glucose in running vs the few heartbeats before it.
        running_glucose = [hb.health.blood_glucose for hb in normal_hbs[-4:]]
        pre_running_glucose = [hb.health.blood_glucose for hb in normal_hbs[-7:-4]]
        assert sum(running_glucose) / len(running_glucose) < sum(pre_running_glucose) / len(
            pre_running_glucose
        )

    def test_blood_glucose_precision_varies(self, package: ScenarioPackage) -> None:
        """At least one glucose reading should be a whole number (precision variation)."""
        all_glucose = [
            hb.health.blood_glucose for hb in package.heartbeats if hb.health is not None
        ]
        whole_numbers = [g for g in all_glucose if g == int(g)]
        assert len(whole_numbers) > 0, "Expected at least one whole-number glucose"

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


class TestLocationRealism:
    """Story 2.2: Location module generates realistic spatial data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)

    def test_location_none_for_t1(self) -> None:
        """AC #6: T1 heartbeats have no location data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        for hb in package.heartbeats:
            assert hb.location is None

    def test_location_present_for_t2(self, package: ScenarioPackage) -> None:
        """AC #6: T2+ heartbeats have location data on almost every beat."""
        present = sum(1 for hb in package.heartbeats if hb.location is not None)
        assert present >= len(package.heartbeats) * 0.95

    def test_stationary_blocks_near_known_coords(self, package: ScenarioPackage) -> None:
        """AC #1: office/home GPS within ~50 m of LOCATIONS."""
        from crisis_bench.generator.schedule import LOCATIONS

        # Check first 3 heartbeats (waking_up at home) and a working heartbeat.
        for hb in package.heartbeats[:3]:
            loc = hb.location
            assert loc is not None
            home = LOCATIONS["home"]
            assert home is not None
            assert abs(loc.lat - home[0]) < 0.001, "Home lat too far"
            assert abs(loc.lon - home[1]) < 0.001, "Home lon too far"
            assert loc.geofence_status == "at_home"
            assert loc.movement_classification == "stationary"

        # Working heartbeat (around HB 20, well into working block at office).
        office_hb = package.heartbeats[20]
        assert office_hb.location is not None
        office = LOCATIONS["office"]
        assert office is not None
        assert abs(office_hb.location.lat - office[0]) < 0.001, "Office lat too far"
        assert abs(office_hb.location.lon - office[1]) < 0.001, "Office lon too far"
        assert office_hb.location.geofence_status == "at_office"

    def test_geofence_none_for_unmapped_locations(self, package: ScenarioPackage) -> None:
        """Geofence should be None for locations without configured zones."""
        cid = package.crisis_heartbeat_id
        # Running heartbeats (park) should have no geofence.
        for hb in package.heartbeats[cid - 4 : cid]:
            loc = hb.location
            assert loc is not None
            assert loc.geofence_status is None
        # Crisis heartbeats should have no geofence.
        for hb in package.heartbeats[cid:]:
            loc = hb.location
            assert loc is not None
            assert loc.geofence_status is None

    def test_commute_speed_plausible(self, package: ScenarioPackage) -> None:
        """AC #2: transit speed plausible — allows station stops (speed 0)."""
        # Morning commute: HB 6-11 (07:00-07:25).
        speeds = []
        for hb in package.heartbeats[6:12]:
            loc = hb.location
            assert loc is not None
            assert 0.0 <= loc.speed <= 13.0, (
                f"HB {hb.heartbeat_id}: speed {loc.speed} out of range"
            )
            assert loc.geofence_status is None
            assert loc.movement_classification == "driving"
            speeds.append(loc.speed)
        avg = sum(speeds) / len(speeds)
        assert 2.0 <= avg <= 10.0, f"Average commute speed {avg} not plausible"

    def test_running_speed_plausible(self, package: ScenarioPackage) -> None:
        """AC #3: running block speed ~2-4 m/s."""
        cid = package.crisis_heartbeat_id
        # Running heartbeats are the 4 just before crisis (17:45-18:05).
        for hb in package.heartbeats[cid - 4 : cid]:
            loc = hb.location
            assert loc is not None
            assert 2.0 <= loc.speed <= 4.0, f"HB {hb.heartbeat_id}: speed {loc.speed} out of range"
            assert loc.movement_classification == "running"

    def test_crisis_location_near_frozen(self, package: ScenarioPackage) -> None:
        """AC #4: GPS stays near last position during crisis (sub-meter drift)."""
        cid = package.crisis_heartbeat_id
        pre_crisis = package.heartbeats[cid - 1].location
        assert pre_crisis is not None

        for hb in package.heartbeats[cid:]:
            loc = hb.location
            assert loc is not None
            # Within ~50 m (0.0005°) of pre-crisis position.
            assert abs(loc.lat - pre_crisis.lat) < 0.0005, (
                f"Crisis GPS lat drifted too far: {loc.lat} vs {pre_crisis.lat}"
            )
            assert abs(loc.lon - pre_crisis.lon) < 0.0005, (
                f"Crisis GPS lon drifted too far: {loc.lon} vs {pre_crisis.lon}"
            )
            assert loc.speed == 0.0
            assert loc.movement_classification == "stationary"

    def test_crisis_accuracy_stable(self, package: ScenarioPackage) -> None:
        """AC #4: GPS accuracy stays in reasonable outdoor range during crisis."""
        cid = package.crisis_heartbeat_id
        for hb in package.heartbeats[cid:]:
            assert hb.location is not None
            assert 1.0 <= hb.location.accuracy <= 10.0, (
                f"Crisis accuracy {hb.location.accuracy} outside outdoor range"
            )

    def test_location_deterministic(self) -> None:
        """AC #5: same seed = same output."""
        pkg1 = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        pkg2 = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        for h1, h2 in zip(pkg1.heartbeats, pkg2.heartbeats, strict=False):
            assert h1.location == h2.location


class TestWeatherRealism:
    """Story 2.3: Weather module generates realistic diurnal data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)

    def test_weather_none_for_t1(self) -> None:
        """T1 heartbeats have no weather data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        for hb in package.heartbeats:
            assert hb.weather is None

    def test_weather_present_for_t2(self, package: ScenarioPackage) -> None:
        """T2+ heartbeats have weather data on almost every beat."""
        present = sum(1 for hb in package.heartbeats if hb.weather is not None)
        assert present >= len(package.heartbeats) * 0.95

    def test_temp_diurnal_curve(self, package: ScenarioPackage) -> None:
        """AC #1: temperature warms through morning, peaks afternoon, cools evening."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.weather is not None]
        temps = [hb.weather.temp for hb in normal]
        # Dawn (06:30) should be cool (< 20°C).
        assert temps[0] < 20.0, f"Dawn temp {temps[0]} should be below 20°C"
        # Midday (~12:30, HB ~72) should be warmer than dawn.
        midday_idx = min(72, len(temps) - 1)
        assert temps[midday_idx] > temps[0]
        # Peak should be in the afternoon (HB 90-130, roughly 14:00-17:30).
        peak_idx = temps.index(max(temps))
        assert 80 <= peak_idx <= 135, (
            f"Peak temp at HB {peak_idx}, expected in afternoon range 80-135"
        )

    def test_temp_no_sudden_jumps(self, package: ScenarioPackage) -> None:
        """Adjacent heartbeats should not have temperature jumps > 2°C."""
        temps = [hb.weather.temp for hb in package.heartbeats if hb.weather is not None]
        for i in range(1, len(temps)):
            diff = abs(temps[i] - temps[i - 1])
            assert diff < 2.0, f"HB {i}: temp jumped {diff:.1f}°C ({temps[i - 1]} -> {temps[i]})"

    def test_humidity_inverse_correlation(self, package: ScenarioPackage) -> None:
        """AC #1: humidity higher in morning, lower in afternoon."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.weather is not None]
        # Compare average humidity in first 10 vs middle 10 heartbeats.
        morning_humidity = sum(hb.weather.humidity for hb in normal[:10]) / 10
        afternoon_humidity = sum(hb.weather.humidity for hb in normal[70:80]) / 10
        assert morning_humidity > afternoon_humidity

    def test_uv_peaks_midday(self, package: ScenarioPackage) -> None:
        """AC #1: UV index peaks around midday, low at dawn/evening."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.weather is not None]
        # Dawn (06:30) UV should be 0 or very low (≤2 in mid-June, sunrise ~5:25 AM).
        assert normal[0].weather.uv_index <= 2
        # Midday (12:30, HB ~72) should have high UV.
        midday_idx = min(72, len(normal) - 1)
        assert normal[midday_idx].weather.uv_index >= 4

    def test_wind_direction_drifts_slowly(self, package: ScenarioPackage) -> None:
        """Wind direction should not flip wildly between heartbeats."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.weather is not None]
        dirs = [hb.weather.wind_dir for hb in normal]
        # Count direction changes. Should be much less than total heartbeats.
        changes = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])
        assert changes < len(dirs) * 0.3, f"Too many wind dir changes: {changes}/{len(dirs)}"

    def test_weather_deterministic(self) -> None:
        """AC #4: same seed = identical weather output."""
        pkg1 = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        pkg2 = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        for h1, h2 in zip(pkg1.heartbeats, pkg2.heartbeats, strict=False):
            assert h1.weather == h2.weather

    def test_crisis_weather_continues(self, package: ScenarioPackage) -> None:
        """AC #1 subtask 1.8: weather evolves normally during crisis."""
        cid = package.crisis_heartbeat_id
        crisis_hbs = [hb for hb in package.heartbeats[cid:] if hb.weather is not None]
        assert len(crisis_hbs) > 0
        # Weather should still be present and values should vary.
        temps = [hb.weather.temp for hb in crisis_hbs]
        assert len(set(temps)) > 1, "Crisis weather temps should vary, not be static"


class TestCalendarRealism:
    """Story 2.3: Calendar module generates realistic sliding-window events."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)

    def test_calendar_none_for_t2(self) -> None:
        """T2 heartbeats have no calendar data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        for hb in package.heartbeats:
            assert hb.calendar is None

    def test_events_slide_forward(self, package: ScenarioPackage) -> None:
        """AC #2: events in next_3_events slide forward as time passes."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.calendar is not None]
        # Early morning (06:30): should show first 3 events.
        early = normal[0].calendar
        assert len(early.next_3_events) == 3
        assert early.next_3_events[0].title == "Daily Standup"
        # Late afternoon (~16:00, HB ~114): most events passed.
        late_idx = min(114, len(normal) - 1)
        late = normal[late_idx].calendar
        # By 16:00, only Gym (17:30) and Dinner (19:00) should remain.
        assert len(late.next_3_events) <= 3
        if len(late.next_3_events) > 0:
            assert late.next_3_events[0].title != "Daily Standup"

    def test_past_events_excluded(self, package: ScenarioPackage) -> None:
        """AC #2: events that have passed don't appear in next_3_events."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.calendar is not None]
        # At 10:30 (HB ~48), Daily Standup (09:00) and Sprint Planning (10:00) have passed.
        hb_48 = normal[min(48, len(normal) - 1)]
        event_titles = [e.title for e in hb_48.calendar.next_3_events]
        assert "Daily Standup" not in event_titles
        assert "Sprint Planning" not in event_titles

    def test_calendar_deterministic(self) -> None:
        """AC #4: same seed = identical calendar output."""
        pkg1 = generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)
        pkg2 = generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)
        for h1, h2 in zip(pkg1.heartbeats, pkg2.heartbeats, strict=False):
            assert h1.calendar == h2.calendar

    def test_today_summary_present(self, package: ScenarioPackage) -> None:
        """AC #2: today_summary is a non-empty string."""
        hb = package.heartbeats[10]
        assert hb.calendar is not None
        assert len(hb.calendar.today_summary) > 0


class TestFinancialRealism:
    """Story 2.3: Financial module generates realistic stock/transaction data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)

    def test_financial_none_for_t3(self) -> None:
        """T3 heartbeats have no financial data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)
        for hb in package.heartbeats:
            assert hb.financial is None

    def test_stock_walk_varies(self, package: ScenarioPackage) -> None:
        """AC #3: stock prices vary via random walk, not static."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.financial is not None]
        aapl_prices = [hb.financial.stock_watchlist[0].price for hb in normal]
        assert len(set(aapl_prices)) > 5, "Stock prices should vary across heartbeats"

    def test_transactions_contextually_timed(self, package: ScenarioPackage) -> None:
        """AC #6: transactions appear at appropriate times."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.financial is not None]
        # At 06:30 (HB 0), no today transactions yet — should show yesterday's.
        first = normal[0].financial
        assert first.last_3_transactions[0].counterparty == "Whole Foods Market"
        # After 07:05 (HB ~7), Starbucks and MTA should appear.
        later_idx = min(7, len(normal) - 1)
        later = normal[later_idx].financial
        counterparties = [t.counterparty for t in later.last_3_transactions]
        assert "Starbucks" in counterparties or "MTA MetroCard" in counterparties

    def test_account_balance_decrements(self, package: ScenarioPackage) -> None:
        """AC #6: account balance decreases with transactions."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.financial is not None]
        first_balance = normal[0].financial.account_balance
        last_balance = normal[-1].financial.account_balance
        assert last_balance < first_balance

    def test_financial_deterministic(self) -> None:
        """AC #4: same seed = identical financial output."""
        pkg1 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        pkg2 = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        for h1, h2 in zip(pkg1.heartbeats, pkg2.heartbeats, strict=False):
            assert h1.financial == h2.financial

    def test_financial_continues_during_crisis(self, package: ScenarioPackage) -> None:
        """Financial data (crypto at minimum) keeps evolving during crisis."""
        cid = package.crisis_heartbeat_id
        crisis_hbs = [hb for hb in package.heartbeats[cid:] if hb.financial is not None]
        assert len(crisis_hbs) > 1
        # Crypto trades 24/7 — prices should vary even during crisis.
        sol_prices = [hb.financial.crypto_prices[0].price for hb in crisis_hbs]
        assert len(set(sol_prices)) > 1, "Crypto prices should vary during crisis"

    def test_stocks_frozen_outside_market_hours(self, package: ScenarioPackage) -> None:
        """Stock prices should not change outside 09:30-16:00 market hours."""
        # First few heartbeats (06:30-06:50) are pre-market.
        # Pick the first two with financial data (occasional drops may skip one).
        with_fin = [hb for hb in package.heartbeats[:5] if hb.financial is not None]
        assert len(with_fin) >= 2, "Need at least 2 pre-market heartbeats with financial data"
        first, second = with_fin[0], with_fin[1]
        for q1, q2 in zip(
            first.financial.stock_watchlist, second.financial.stock_watchlist, strict=True
        ):
            assert q1.price == q2.price, (
                f"{q1.symbol} price changed pre-market: {q1.price} -> {q2.price}"
            )


class TestCommsRealism:
    """Story 2.4: Communications module generates notification-based data."""

    @pytest.fixture()
    def package(self) -> ScenarioPackage:
        return generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)

    def test_comms_none_for_t1(self) -> None:
        """AC #5: T1 heartbeats have no comms data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T1", seed=42)
        for hb in package.heartbeats:
            assert hb.comms is None

    def test_comms_none_for_t2(self) -> None:
        """AC #5: T2 heartbeats have no comms data."""
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T2", seed=42)
        for hb in package.heartbeats:
            assert hb.comms is None

    def test_comms_present_for_t3(self, package: ScenarioPackage) -> None:
        """AC #5: T3+ heartbeats have comms data on almost every beat."""
        present = sum(1 for hb in package.heartbeats if hb.comms is not None)
        assert present >= len(package.heartbeats) * 0.95

    def test_notification_based_not_cumulative(self, package: ScenarioPackage) -> None:
        """AC #1: items appear in one heartbeat only, not cumulative."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        # Count total emails across all heartbeats.
        total_emails = sum(len(hb.comms.new_emails) for hb in with_comms)
        # Should equal total scripted events (10), not grow cumulatively.
        # Some may be dropped by the ~1.5% module drop, but total should be ≤ 10.
        assert total_emails <= 10

    def test_most_heartbeats_empty(self, package: ScenarioPackage) -> None:
        """Most heartbeats should have empty comms lists (events are sparse)."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        empty_email_hbs = sum(1 for hb in with_comms if len(hb.comms.new_emails) == 0)
        # With 10 emails over ~160 heartbeats, most should be empty.
        assert empty_email_hbs > len(with_comms) * 0.8

    def test_comms_deterministic(self) -> None:
        """AC #4: same seed = identical comms output."""
        pkg1 = generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)
        pkg2 = generate_scenario(crisis_type="cardiac_arrest", tier="T3", seed=42)
        for h1, h2 in zip(pkg1.heartbeats, pkg2.heartbeats, strict=False):
            assert h1.comms == h2.comms

    def test_crisis_comms_continue(self, package: ScenarioPackage) -> None:
        """AC #6: comms module stays active during crisis heartbeats."""
        cid = package.crisis_heartbeat_id
        crisis_hbs = [hb for hb in package.heartbeats[cid:] if hb.comms is not None]
        assert len(crisis_hbs) > 0

    def test_field_population_types(self, package: ScenarioPackage) -> None:
        """AC #3: all 6 CommsData fields present and correctly typed."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        assert len(with_comms) > 0
        comms = with_comms[0].comms
        assert isinstance(comms.new_emails, list)
        assert isinstance(comms.new_slack_messages, list)
        assert isinstance(comms.new_missed_calls, int)
        assert isinstance(comms.new_voicemails, int)
        assert isinstance(comms.new_sms, list)
        assert isinstance(comms.new_notifications, list)

    def test_email_fields(self, package: ScenarioPackage) -> None:
        """AC #2: emails show sender+subject only."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        hbs_with_email = [hb for hb in with_comms if len(hb.comms.new_emails) > 0]
        assert len(hbs_with_email) > 0
        email = hbs_with_email[0].comms.new_emails[0]
        assert len(email.sender) > 0
        assert len(email.subject) > 0

    def test_events_not_repeated(self, package: ScenarioPackage) -> None:
        """Each scripted event appears in exactly one heartbeat."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        all_subjects = []
        for hb in with_comms:
            all_subjects.extend(e.subject for e in hb.comms.new_emails)
        # No duplicates.
        assert len(all_subjects) == len(set(all_subjects))

    def test_missed_calls_per_heartbeat(self, package: ScenarioPackage) -> None:
        """Missed calls are per-heartbeat (0 or 1), not cumulative."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        for hb in with_comms:
            assert hb.comms.new_missed_calls <= 1
        # Total across all heartbeats should equal scripted count (2).
        total = sum(hb.comms.new_missed_calls for hb in with_comms)
        assert total == 2

    def test_sms_per_heartbeat(self, package: ScenarioPackage) -> None:
        """SMS are per-heartbeat notifications, not cumulative."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        total_sms = sum(len(hb.comms.new_sms) for hb in with_comms)
        # Should equal total scripted SMS events (4).
        assert total_sms == 4

    def test_event_timing_irregular(self, package: ScenarioPackage) -> None:
        """Events should not arrive at perfectly uniform intervals."""
        with_comms = [hb for hb in package.heartbeats if hb.comms is not None]
        # Find heartbeats with any new email.
        email_hb_ids = [hb.heartbeat_id for hb in with_comms if len(hb.comms.new_emails) > 0]
        if len(email_hb_ids) >= 3:
            # Check gaps between email arrivals are not all identical.
            gaps = [email_hb_ids[i] - email_hb_ids[i - 1] for i in range(1, len(email_hb_ids))]
            assert len(set(gaps)) > 1, "Email arrival gaps should not be perfectly uniform"


# ---------------------------------------------------------------------------
# Story 2.5: CrisisInjector, Tool Definitions, Scenario Packaging
# ---------------------------------------------------------------------------


def _make_raw_heartbeats(
    count: int = 6, crisis_at: int = 3, *, include_location: bool = True
) -> list[dict[str, object]]:
    """Create synthetic raw heartbeats for CrisisInjector unit tests."""
    heartbeats: list[dict[str, object]] = []
    for i in range(count):
        health: dict[str, object] = {
            "heart_rate": 72 if i < crisis_at else 0,
            "spo2": 98 if i < crisis_at else 0,
            "steps": 1000 + i * 100,
            "skin_temp": 36.5,
            "ecg_summary": "normal sinus rhythm" if i < crisis_at else "inconclusive",
            "blood_glucose": 95.0,
            "calories_burned": 500 + i * 50,
            "sleep_stage": "awake",
            "respiratory_rate": 16 if i < crisis_at else 0,
            "body_battery": 70,
        }
        hb: dict[str, object] = {
            "heartbeat_id": i,
            "timestamp": f"2026-06-15T{12 + i}:00:00Z",
            "health": health,
        }
        if include_location:
            location: dict[str, object] = {
                "lat": 40.7812 + i * 0.0001,
                "lon": -73.9665 + i * 0.0001,
                "altitude": 15.0,
                "speed": 3.0 if i < crisis_at else 0.0,
                "heading": 90,
                "accuracy": 5.0,
                "geofence_status": None,
                "movement_classification": "running" if i < crisis_at else "stationary",
            }
            hb["location"] = location
        heartbeats.append(hb)
    return heartbeats


class TestCrisisInjector:
    """Story 2.5 / AC #1: CrisisInjector post-processing enforcement."""

    def test_enforces_cardiac_arrest_health(self) -> None:
        """Crisis heartbeats show HR=0, SpO2=0, resp_rate=0, ECG inconclusive."""
        hbs = _make_raw_heartbeats()
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for hb in hbs[3:]:
            health = hb["health"]
            assert isinstance(health, dict)
            assert health["heart_rate"] == 0
            assert health["spo2"] == 0
            assert health["respiratory_rate"] == 0
            assert health["ecg_summary"] == "inconclusive"

    def test_gps_freezes_at_last_known(self) -> None:
        """GPS lat/lon frozen at pre-crisis values, speed=0, movement=stationary."""
        hbs = _make_raw_heartbeats()
        pre_loc = hbs[2]["location"]
        assert isinstance(pre_loc, dict)
        pre_lat = pre_loc["lat"]
        pre_lon = pre_loc["lon"]
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for hb in hbs[3:]:
            loc = hb["location"]
            assert isinstance(loc, dict)
            assert loc["lat"] == pre_lat
            assert loc["lon"] == pre_lon
            assert loc["speed"] == 0.0
            assert loc["movement_classification"] == "stationary"

    def test_steps_calories_frozen_not_zeroed(self) -> None:
        """Steps and calories frozen at pre-crisis values, not reset to 0."""
        hbs = _make_raw_heartbeats()
        pre_health = hbs[2]["health"]
        assert isinstance(pre_health, dict)
        pre_steps = pre_health["steps"]
        pre_cals = pre_health["calories_burned"]
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for hb in hbs[3:]:
            health = hb["health"]
            assert isinstance(health, dict)
            assert health["steps"] == pre_steps
            assert health["calories_burned"] == pre_cals
            assert health["steps"] > 0  # Not zeroed

    def test_non_crisis_modules_untouched(self) -> None:
        """Modules not in the crisis profile (e.g. weather) are left unmodified."""
        hbs = _make_raw_heartbeats()
        # Add weather data to each heartbeat.
        for hb in hbs:
            hb["weather"] = {"temp": 25.0, "humidity": 60}
        weather_before = [copy.deepcopy(hb["weather"]) for hb in hbs]
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for i, hb in enumerate(hbs):
            assert hb["weather"] == weather_before[i]

    def test_all_crisis_heartbeats_enforced(self) -> None:
        """Enforcement applies to ALL heartbeats at and after crisis, not just the first."""
        hbs = _make_raw_heartbeats(count=10, crisis_at=3)
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for hb in hbs[3:]:
            health = hb["health"]
            assert isinstance(health, dict)
            assert health["heart_rate"] == 0
            loc = hb["location"]
            assert isinstance(loc, dict)
            assert loc["speed"] == 0.0

    def test_idempotent(self) -> None:
        """Running apply() twice produces identical output."""
        hbs = _make_raw_heartbeats()
        injector = CrisisInjector()
        injector.apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        snapshot = [json.dumps(hb, sort_keys=True) for hb in hbs]
        injector.apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        for i, hb in enumerate(hbs):
            assert json.dumps(hb, sort_keys=True) == snapshot[i]

    def test_raises_on_none_health(self) -> None:
        """ValueError when a crisis-required module is None during crisis."""
        hbs = _make_raw_heartbeats()
        hbs[3]["health"] = None
        with pytest.raises(ValueError, match="health.*None.*heartbeat"):
            CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")

    def test_skips_missing_modules_for_tier(self) -> None:
        """T1-like heartbeats (no location) should not raise — profile skips missing modules."""
        hbs = _make_raw_heartbeats(include_location=False)
        CrisisInjector().apply(hbs, crisis_heartbeat_id=3, crisis_type="cardiac_arrest")
        # Health enforcement still works.
        health = hbs[3]["health"]
        assert isinstance(health, dict)
        assert health["heart_rate"] == 0


class TestToolDefinitions:
    """Story 2.5 / AC #4, #5, #6: Tool definitions catalog."""

    def test_tier_monotonic_progression(self) -> None:
        """Tool count increases monotonically T1 < T2 < T3 < T4."""
        counts = {tier: len(collect_tool_definitions(tier)) for tier in ("T1", "T2", "T3", "T4")}
        assert counts["T1"] < counts["T2"]
        assert counts["T2"] < counts["T3"]
        assert counts["T3"] < counts["T4"]

    def test_core_tools_present_on_every_tier(self) -> None:
        """All 9 core tools present on every tier."""
        core_names = {
            "make_call",
            "send_message",
            "read_memory",
            "write_memory",
            "list_memories",
            "get_contacts",
            "get_conversations",
            "query_device",
            "get_recent_updates",
        }
        for tier in ("T1", "T2", "T3", "T4"):
            tools = collect_tool_definitions(tier)
            tool_names = {t.name for t in tools}
            assert core_names.issubset(tool_names), f"Tier {tier} missing core tools"

    def test_t1_has_9_core_tools(self) -> None:
        tools = collect_tool_definitions("T1")
        assert len(tools) == 9

    def test_t2_adds_get_forecast(self) -> None:
        names = {t.name for t in collect_tool_definitions("T2")}
        assert "get_forecast" in names

    def test_t3_adds_list_events(self) -> None:
        names = {t.name for t in collect_tool_definitions("T3")}
        assert "list_events" in names

    def test_t4_adds_financial_tools(self) -> None:
        names = {t.name for t in collect_tool_definitions("T4")}
        assert "get_balance" in names
        assert "get_transactions" in names

    def test_core_tools_flat_named(self) -> None:
        """All core tools use flat snake_case (no dots)."""
        core_names = {
            "make_call",
            "send_message",
            "read_memory",
            "write_memory",
            "list_memories",
            "get_contacts",
            "get_conversations",
            "query_device",
            "get_recent_updates",
        }
        for tier in ("T1", "T2", "T3", "T4"):
            for tool in collect_tool_definitions(tier):
                if tool.name in core_names:
                    assert "." not in tool.name, f"Core tool {tool.name!r} should be flat-named"

    def test_mcp_tools_dotted(self) -> None:
        """All MCP tools (T3+) use dotted server.action naming."""
        # T3 includes MCP tools; compare T2 names to find them.
        t2_names = {t.name for t in collect_tool_definitions("T2")}
        t3_tools = collect_tool_definitions("T3")
        mcp_tools = [t for t in t3_tools if t.name not in t2_names and t.name != "list_events"]
        assert len(mcp_tools) > 0, "Expected MCP tools on T3"
        for tool in mcp_tools:
            assert "." in tool.name, f"MCP tool {tool.name!r} should be dotted"

    def test_nfr2_no_banned_stems(self) -> None:
        """No tool name or description contains banned health/emergency/safety stems."""
        banned_stems = {
            "health",
            "medical",
            "emergency",
            "crisis",
            "safety",
            "vital",
            "cardiac",
            "heart",
            "pulse",
            "oxygen",
            "spo2",
            "ambulance",
            "hospital",
            "doctor",
            "nurse",
            "injury",
            "symptom",
            "diagnosis",
            "alert",
            "warning",
            "danger",
            "critical",
            "urgent",
            "rescue",
            "sos",
        }
        for tier in ("T1", "T2", "T3", "T4"):
            for tool in collect_tool_definitions(tier):
                name_words = set(tool.name.replace(".", "_").split("_"))
                desc_words = set(tool.description.lower().split())
                # Strip punctuation from description words.
                desc_words = {w.strip(".,;:()[]{}") for w in desc_words}
                all_words = name_words | desc_words
                overlap = all_words & banned_stems
                assert not overlap, f"Tool {tool.name!r} contains banned NFR2 stems: {overlap}"

    def test_determinism_same_tier_same_definitions(self) -> None:
        """Same tier always returns identical tool definitions (order-stable)."""
        for tier in ("T1", "T2", "T3", "T4"):
            a = collect_tool_definitions(tier)
            b = collect_tool_definitions(tier)
            assert len(a) == len(b)
            for ta, tb in zip(a, b, strict=True):
                assert ta == tb


class TestScenarioPackaging:
    """Story 2.5 / AC #2, #3: Scenario package completeness."""

    def test_tools_json_nonempty_all_tiers(self) -> None:
        """tools.json (tool_definitions) is non-empty for every tier."""
        for tier in ("T1", "T2", "T3", "T4"):
            package = generate_scenario(crisis_type="cardiac_arrest", tier=tier, seed=42)
            assert len(package.tool_definitions) > 0, f"Tier {tier} has empty tool_definitions"

    def test_manifest_has_valid_sha256(self) -> None:
        package = generate_scenario(crisis_type="cardiac_arrest", tier="T4", seed=42)
        assert len(package.manifest.content_hash) == 64

    def test_scenario_id_format(self) -> None:
        for tier in ("T1", "T2", "T3", "T4"):
            package = generate_scenario(crisis_type="cardiac_arrest", tier=tier, seed=99)
            assert package.scenario_id == f"cardiac_arrest_{tier}_s99"
