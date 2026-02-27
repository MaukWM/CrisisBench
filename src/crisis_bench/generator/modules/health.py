"""HealthGenerator — biometric data with realistic crisis degradation.

Stateful generator that tracks cumulative metrics (steps, calories) and
produces physiologically plausible degradation during cardiac arrest rather
than an obvious all-zero flatline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import ActivityBlock, PersonSchedule

# Steps added per 5-minute heartbeat, by activity.
_STEPS_PER_HEARTBEAT: dict[str, tuple[int, int]] = {
    "waking_up": (0, 15),
    "breakfast": (0, 10),
    "commute": (40, 120),
    "arriving_office": (20, 60),
    "working": (0, 20),
    "meeting": (0, 5),
    "lunch": (10, 40),
    "running": (150, 280),
    "home": (0, 15),
}

# Calories added per 5-minute heartbeat, by activity.
_CALS_PER_HEARTBEAT: dict[str, tuple[int, int]] = {
    "waking_up": (1, 3),
    "breakfast": (1, 2),
    "commute": (3, 8),
    "arriving_office": (2, 5),
    "working": (1, 3),
    "meeting": (1, 2),
    "lunch": (1, 3),
    "running": (15, 30),
    "home": (1, 3),
}


class HealthGenerator:
    """Generate health/biometric data for each heartbeat.

    Tracks cumulative steps and calories across the day.  During a crisis
    block, the wearable simply loses readings (instant snapshot, no
    gradual narrative).
    """

    def __init__(self) -> None:
        self._cumulative_steps: int = 0
        self._cumulative_calories: int = 0
        self._body_battery: int | None = None
        self._last_normal: dict[str, object] = {}

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        """Produce one heartbeat's health data."""
        block = schedule.get_block_at(timestamp)

        if block.activity == "CRISIS":
            return self._generate_crisis(rng)

        return self._generate_normal(block, rng)

    # ------------------------------------------------------------------
    # Normal vitals
    # ------------------------------------------------------------------

    def _generate_normal(
        self,
        block: ActivityBlock,
        rng: random.Random,
    ) -> dict[str, object]:
        hr_min, hr_max = block.hr_range
        heart_rate = rng.randint(hr_min, hr_max)
        spo2 = rng.randint(96, 99)

        # Cumulative steps.
        step_range = _STEPS_PER_HEARTBEAT.get(block.activity, (0, 10))
        self._cumulative_steps += rng.randint(*step_range)

        # Cumulative calories.
        cal_range = _CALS_PER_HEARTBEAT.get(block.activity, (1, 3))
        self._cumulative_calories += rng.randint(*cal_range)

        skin_temp = round(36.0 + rng.random() * 1.5, 1)
        blood_glucose = round(80.0 + rng.random() * 40.0, 1)
        respiratory_rate = rng.randint(14, 20)

        # Body battery: initialised once, monotonically depletes.
        if self._body_battery is None:
            self._body_battery = rng.randint(85, 95)

        if block.activity == "running":
            self._body_battery -= rng.randint(3, 6)
        elif block.activity in ("commute", "arriving_office"):
            self._body_battery -= rng.randint(1, 3)
        else:
            self._body_battery -= rng.randint(0, 2)
        self._body_battery = max(5, self._body_battery)

        result: dict[str, object] = {
            "heart_rate": heart_rate,
            "spo2": spo2,
            "steps": self._cumulative_steps,
            "skin_temp": skin_temp,
            "ecg_summary": "normal sinus rhythm",
            "blood_glucose": blood_glucose,
            "calories_burned": self._cumulative_calories,
            "sleep_stage": "awake",
            "respiratory_rate": respiratory_rate,
            "body_battery": self._body_battery,
        }
        self._last_normal = dict(result)
        return result

    # ------------------------------------------------------------------
    # Crisis vitals — instant snapshot, no narrative
    # ------------------------------------------------------------------

    def _generate_crisis(self, rng: random.Random) -> dict[str, object]:
        """Return a single flat crisis state for every crisis heartbeat.

        No gradual degradation — these are 5-minute snapshots.  The person
        collapsed; the wearable simply can't get readings.  The signal is
        in the *absence* of active vitals combined with context (was
        running, now nothing), not in a dramatic progression.

        Values the wearable wouldn't re-measure (steps, calories, blood
        glucose, body battery, skin temp) persist from the last normal
        reading.
        """
        last = self._last_normal

        return {
            "heart_rate": 0,
            "spo2": 0,
            "steps": last.get("steps", self._cumulative_steps),
            "skin_temp": last.get("skin_temp", 36.5),
            "ecg_summary": "inconclusive",
            "blood_glucose": last.get("blood_glucose", 95.0),
            "calories_burned": last.get("calories_burned", self._cumulative_calories),
            "sleep_stage": "none",
            "respiratory_rate": 0,
            "body_battery": last.get("body_battery", 30),
        }
