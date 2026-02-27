"""Tests for PersonSchedule, ActivityBlock, and schedule constants."""

from __future__ import annotations

from datetime import date

import pytest

from crisis_bench.generator.schedule import (
    CARDIAC_ARREST_SCHEDULE,
    HEARTBEAT_INTERVAL_MINUTES,
    LOCATIONS,
    PersonSchedule,
)


class TestPersonScheduleDeterminism:
    """AC #2: same seed → identical output."""

    def test_same_seed_produces_identical_blocks(self) -> None:
        s1 = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        s2 = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)

        ts1 = s1.heartbeat_timestamps()
        ts2 = s2.heartbeat_timestamps()
        assert ts1 == ts2

    def test_different_seed_same_timestamps(self) -> None:
        """Timestamps depend on schedule, not seed — should still match."""
        s1 = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=1)
        s2 = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=999)

        assert s1.heartbeat_timestamps() == s2.heartbeat_timestamps()


class TestHeartbeatTimestamps:
    """Validate 5-minute intervals and count."""

    def test_interval_is_five_minutes(self) -> None:
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        stamps = schedule.heartbeat_timestamps()

        # All timestamps should be parseable and 5 minutes apart.
        from datetime import datetime

        dts = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]
        for i in range(1, len(dts)):
            delta = (dts[i] - dts[i - 1]).total_seconds()
            assert delta == HEARTBEAT_INTERVAL_MINUTES * 60

    def test_starts_at_0630(self) -> None:
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        stamps = schedule.heartbeat_timestamps()
        assert stamps[0].endswith("T06:30Z")

    def test_pre_crisis_heartbeat_count(self) -> None:
        """06:30 to 18:05 = 693 min / 5 = 138.6 → ~139 heartbeats before crisis."""
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        stamps = schedule.heartbeat_timestamps()

        # Find crisis timestamp (18:05:00)
        crisis_idx = next(i for i, s in enumerate(stamps) if "T18:05Z" in s)
        # Heartbeat at 06:30 is index 0, 18:05 should be around index 139.
        assert crisis_idx == 139


class TestFutureDateEnforcement:
    """AC #7: scenario dates must be in the future (>= 2027)."""

    def test_default_date_is_2027(self) -> None:
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        assert schedule.scenario_date.year >= 2027

    def test_year_before_2027_raises(self) -> None:
        with pytest.raises(ValueError, match="2027"):
            PersonSchedule(
                blocks=CARDIAC_ARREST_SCHEDULE,
                seed=42,
                scenario_date=date(2026, 1, 1),
            )

    def test_year_2027_allowed(self) -> None:
        schedule = PersonSchedule(
            blocks=CARDIAC_ARREST_SCHEDULE,
            seed=42,
            scenario_date=date(2027, 3, 15),
        )
        assert schedule.scenario_date == date(2027, 3, 15)


class TestGetBlockAt:
    """Verify block lookup by timestamp."""

    def test_morning_returns_correct_block(self) -> None:
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        block = schedule.get_block_at("2027-06-15T07:15:00Z")
        assert block.activity == "commute"

    def test_crisis_timestamp_returns_crisis_block(self) -> None:
        schedule = PersonSchedule(blocks=CARDIAC_ARREST_SCHEDULE, seed=42)
        block = schedule.get_block_at("2027-06-15T18:10:00Z")
        assert block.activity == "CRISIS"


class TestCardiacArrestSchedule:
    """Validate the CARDIAC_ARREST_SCHEDULE constant matches the spec."""

    def test_block_count(self) -> None:
        assert len(CARDIAC_ARREST_SCHEDULE) == 13

    def test_first_block_is_waking_up(self) -> None:
        assert CARDIAC_ARREST_SCHEDULE[0].activity == "waking_up"

    def test_last_block_is_crisis(self) -> None:
        assert CARDIAC_ARREST_SCHEDULE[-1].activity == "CRISIS"
        assert CARDIAC_ARREST_SCHEDULE[-1].end_time is None

    def test_crisis_at_1805(self) -> None:
        from datetime import time

        crisis = CARDIAC_ARREST_SCHEDULE[-1]
        assert crisis.start_time == time(18, 5)

    def test_all_locations_have_coordinates(self) -> None:
        """Every location_key in the schedule has a LOCATIONS entry."""
        for block in CARDIAC_ARREST_SCHEDULE:
            assert block.location_key in LOCATIONS
