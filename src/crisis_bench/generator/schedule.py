"""PersonSchedule and ActivityBlock — the day's timeline driving all generators."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import NamedTuple


@dataclass
class ActivityBlock:
    """A single block of activity in the person's day.

    Mutable during generation; frozen Pydantic models are only constructed at
    serialisation time.
    """

    start_time: time
    end_time: time | None
    activity: str
    location_key: str
    hr_range: tuple[int, int]


# ---------------------------------------------------------------------------
# Location coordinates (NYC)
# ---------------------------------------------------------------------------

LOCATIONS: dict[str, tuple[float, float] | None] = {
    "home": (40.7851, -73.9754),
    "office": (40.7484, -73.9857),
    "transit": None,  # interpolated between origin/destination
    "restaurant": (40.7505, -73.9855),
    "central_park": (40.7812, -73.9665),
}

# ---------------------------------------------------------------------------
# Cardiac-arrest schedule constant (matches brainstorm spec)
# ---------------------------------------------------------------------------


class _RawBlock(NamedTuple):
    start: str  # HH:MM
    end: str | None  # HH:MM or None for open-ended (crisis)
    activity: str
    location_key: str  # key into LOCATIONS
    hr_range: tuple[int, int]  # (min_bpm, max_bpm)


_RAW_CARDIAC_ARREST_SCHEDULE: list[_RawBlock] = [
    _RawBlock("06:30", "06:45", "waking_up", "home", (58, 65)),
    _RawBlock("06:45", "07:00", "breakfast", "home", (62, 68)),
    _RawBlock("07:00", "07:30", "commute", "transit", (68, 75)),
    _RawBlock("07:30", "08:00", "arriving_office", "office", (65, 72)),
    _RawBlock("08:00", "10:00", "working", "office", (63, 70)),
    _RawBlock("10:00", "10:45", "meeting", "office", (66, 74)),
    _RawBlock("10:45", "12:30", "working", "office", (63, 70)),
    _RawBlock("12:30", "13:15", "lunch", "restaurant", (70, 78)),
    _RawBlock("13:15", "17:00", "working", "office", (63, 70)),
    _RawBlock("17:00", "17:30", "commute", "transit", (68, 75)),
    _RawBlock("17:30", "17:45", "home", "home", (62, 68)),
    _RawBlock("17:45", "18:05", "running", "central_park", (130, 160)),
    _RawBlock("18:05", None, "CRISIS", "central_park", (0, 0)),
]


def _parse_time(s: str) -> time:
    """Parse 'HH:MM' into a ``datetime.time``."""
    parts = s.split(":")
    return time(int(parts[0]), int(parts[1]))


def _build_schedule_constant() -> list[ActivityBlock]:
    """Convert the raw tuple list into ``ActivityBlock`` instances."""
    blocks: list[ActivityBlock] = []
    for start_s, end_s, activity, loc, hr in _RAW_CARDIAC_ARREST_SCHEDULE:
        blocks.append(
            ActivityBlock(
                start_time=_parse_time(start_s),
                end_time=_parse_time(end_s) if end_s is not None else None,
                activity=activity,
                location_key=loc,
                hr_range=hr,
            )
        )
    return blocks


CARDIAC_ARREST_SCHEDULE: list[ActivityBlock] = _build_schedule_constant()

# Default number of post-crisis heartbeats (5-minute intervals after crisis start).
_POST_CRISIS_HEARTBEATS = 20

# Heartbeat cadence in minutes.
HEARTBEAT_INTERVAL_MINUTES = 5

# Minimum allowed scenario year — ensures no LLM has training data for that date.
_MIN_SCENARIO_YEAR = 2027


class PersonSchedule:
    """A full-day schedule for the simulated person.

    Produces a deterministic timeline of ``ActivityBlock`` instances driven by
    a seeded RNG.  All timestamps are anchored to ``scenario_date``.
    """

    def __init__(
        self,
        blocks: list[ActivityBlock],
        seed: int,
        scenario_date: date | None = None,
    ) -> None:
        if scenario_date is None:
            scenario_date = date(_MIN_SCENARIO_YEAR, 6, 15)
        if scenario_date.year < _MIN_SCENARIO_YEAR:
            msg = f"scenario_date year must be >= {_MIN_SCENARIO_YEAR}, got {scenario_date.year}"
            raise ValueError(msg)

        self.blocks = blocks
        self.seed = seed
        self.scenario_date = scenario_date
        self.rng = random.Random(seed)

        # Determine crisis block (the one with end_time=None)
        crisis = [b for b in self.blocks if b.end_time is None]
        if not crisis:
            msg = "Schedule must contain a crisis block (end_time=None)"
            raise ValueError(msg)
        self._crisis_block = crisis[0]

        # Post-crisis end: crisis start + (POST_CRISIS_HEARTBEATS * interval)
        crisis_dt = self._to_datetime(self._crisis_block.start_time)
        self._post_crisis_end = crisis_dt + timedelta(
            minutes=_POST_CRISIS_HEARTBEATS * HEARTBEAT_INTERVAL_MINUTES,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def heartbeat_timestamps(self) -> list[str]:
        """Return ISO 8601 timestamps at ~5-minute intervals from first block
        start through the post-crisis window end.

        Each timestamp has 0-30 seconds of random jitter added (using
        ``self.rng``) so intervals vary between ~4:30 and ~5:30 — real
        wearables don't report at perfect 5-minute marks.  The loop still
        advances by exactly ``HEARTBEAT_INTERVAL_MINUTES`` internally so
        generators see consistent spacing.
        """
        start_dt = self._to_datetime(self.blocks[0].start_time)
        stamps: list[str] = []
        current = start_dt
        while current <= self._post_crisis_end:
            jitter = timedelta(seconds=self.rng.randint(0, 30))
            stamps.append((current + jitter).strftime("%Y-%m-%dT%H:%M:%SZ"))
            current += timedelta(minutes=HEARTBEAT_INTERVAL_MINUTES)
        return stamps

    def get_block_at(self, timestamp: str) -> ActivityBlock:
        """Return the activity block that covers *timestamp*.

        For the crisis block (no end_time), any timestamp at or after its start
        returns the crisis block.
        """
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        t = dt.time()

        # Walk blocks in reverse so the last matching block wins (handles
        # exact boundaries correctly — the new block starts at the boundary).
        for block in reversed(self.blocks):
            if block.end_time is None:
                # Crisis block: covers from start_time onward.
                if t >= block.start_time:
                    return block
            else:
                if block.start_time <= t < block.end_time:
                    return block

        msg = f"No block covers timestamp {timestamp!r} (time={t})"
        raise ValueError(msg)

    @property
    def crisis_start(self) -> datetime:
        """UTC datetime when the crisis begins."""
        return self._to_datetime(self._crisis_block.start_time)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _to_datetime(self, t: time) -> datetime:
        """Combine ``scenario_date`` with a ``time`` into a UTC datetime."""
        return datetime.combine(self.scenario_date, t, tzinfo=UTC)
