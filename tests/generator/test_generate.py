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
        """AC #6: T2+ heartbeats have location data."""
        for hb in package.heartbeats:
            assert hb.location is not None

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
        """T2+ heartbeats have weather data."""
        for hb in package.heartbeats:
            assert hb.weather is not None

    def test_temp_diurnal_curve(self, package: ScenarioPackage) -> None:
        """AC #1: temperature warms through morning, peaks afternoon, cools evening."""
        cid = package.crisis_heartbeat_id
        normal = [hb for hb in package.heartbeats[:cid] if hb.weather is not None]
        temps = [hb.weather.temp for hb in normal]
        # First reading (06:30) should be cooler than midday (~12:30, HB ~72).
        early = temps[0]
        midday_idx = min(72, len(temps) - 1)
        midday = temps[midday_idx]
        assert midday > early, f"Midday {midday} should be warmer than dawn {early}"

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
        # Dawn (06:30) UV should be 0 or very low.
        assert normal[0].weather.uv_index <= 1
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
