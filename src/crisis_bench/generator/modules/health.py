"""HealthGenerator — realistic biometric data with crisis sensor drift.

Stateful generator producing physiologically plausible vitals:
- Blood glucose follows meal-driven curves (not random noise)
- Skin temp drifts via random walk (not independent samples)
- Body battery depletes with occasional recovery during rest
- Steps are bursty during sedentary periods
- Heart rate has micro-spikes during desk work

During crisis, passive sensors (temp, glucose) continue drifting while
active sensors (HR, SpO2, resp) read zero — distinguishing collapse from
device removal.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import ActivityBlock, PersonSchedule

# Activities where the person is mostly sitting/stationary.
_SEDENTARY_ACTIVITIES: frozenset[str] = frozenset(
    {
        "waking_up",
        "breakfast",
        "working",
        "meeting",
        "home",
    }
)

# Steps added per 5-minute heartbeat for active activities (min, max).
_STEPS_PER_HEARTBEAT: dict[str, tuple[int, int]] = {
    "commute": (40, 120),
    "arriving_office": (20, 60),
    "lunch": (10, 40),
    "running": (150, 280),
}

# Calories added per 5-minute heartbeat, by activity.
# Includes basal metabolic rate (~6 cal/5 min for a 34yo male) plus activity.
# ~139 pre-crisis heartbeats should total ~1100-1300 cal (realistic for 06:30-18:05).
_CALS_PER_HEARTBEAT: dict[str, tuple[int, int]] = {
    "waking_up": (5, 9),
    "breakfast": (5, 9),
    "commute": (8, 14),
    "arriving_office": (7, 12),
    "working": (6, 10),
    "meeting": (6, 10),
    "lunch": (7, 11),
    "running": (25, 45),
    "home": (5, 9),
}

# Skin temp random walk choices (biased toward no change).
_SKIN_TEMP_STEPS: list[float] = [-0.1, -0.05, 0.0, 0.0, 0.0, 0.05, 0.1]


def _glucose_meal_response(
    minutes_since_meal: float,
    amplitude: float,
    t_peak: float,
) -> float:
    """Gamma-curve glucose response to a meal.

    Returns the mg/dL contribution above baseline at the given time after
    eating.  Peaks at *t_peak* minutes with magnitude *amplitude*.
    """
    if minutes_since_meal <= 0:
        return 0.0
    ratio = minutes_since_meal / t_peak
    return amplitude * ratio * math.exp(1.0 - ratio)


class HealthGenerator:
    """Generate health/biometric data for each heartbeat.

    Tracks cumulative and stateful metrics across the day.  During a crisis
    block, active sensors fail while passive sensors continue drifting.
    """

    def __init__(self) -> None:
        self._cumulative_steps: int = 0
        self._cumulative_calories: int = 0
        self._body_battery: int | None = None
        self._skin_temp: float | None = None
        self._fasting_glucose: float | None = None
        self._meal_times: list[tuple[time, float, float]] | None = None
        self._last_blood_glucose: float = 0.0
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

        return self._generate_normal(schedule, block, timestamp, rng)

    # ------------------------------------------------------------------
    # First-call initialisation (consumes RNG deterministically)
    # ------------------------------------------------------------------

    def _init_once(self, schedule: PersonSchedule, rng: random.Random) -> None:
        """Extract meal times and set per-scenario constants. Called once."""
        meals: list[tuple[time, float, float]] = []
        for block in schedule.blocks:
            if block.activity in ("breakfast", "lunch"):
                amplitude = 30.0 + rng.random() * 20.0  # 30-50 mg/dL spike
                t_peak = 40.0 + rng.random() * 10.0  # 40-50 min to peak
                meals.append((block.start_time, amplitude, t_peak))
        self._meal_times = meals
        self._fasting_glucose = 88.0 + rng.random() * 7.0  # 88-95 mg/dL
        self._skin_temp = 36.2 + rng.random() * 0.3  # 36.2-36.5

    # ------------------------------------------------------------------
    # Normal vitals
    # ------------------------------------------------------------------

    def _generate_normal(
        self,
        schedule: PersonSchedule,
        block: ActivityBlock,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        # Lazy init on first heartbeat.
        if self._meal_times is None:
            self._init_once(schedule, rng)

        # -- Heart rate with micro-spikes --
        hr_min, hr_max = block.hr_range
        heart_rate = rng.randint(hr_min, hr_max)
        spike_roll = rng.random()
        spike_amount = rng.randint(10, 25)
        if block.activity in _SEDENTARY_ACTIVITIES and spike_roll < 0.1:
            heart_rate += spike_amount

        spo2 = rng.randint(96, 99)

        # -- Cumulative steps (bursty during sedentary) --
        if block.activity in _SEDENTARY_ACTIVITIES:
            new_steps = rng.randint(20, 80) if rng.random() < 0.3 else 0
        else:
            new_steps = rng.randint(*_STEPS_PER_HEARTBEAT[block.activity])
        self._cumulative_steps += new_steps

        # -- Cumulative calories --
        self._cumulative_calories += rng.randint(*_CALS_PER_HEARTBEAT[block.activity])

        # -- Skin temp (random walk) --
        assert self._skin_temp is not None
        step = rng.choice(_SKIN_TEMP_STEPS)
        if block.activity == "running":
            step += 0.05
        self._skin_temp = max(36.0, min(37.2, self._skin_temp + step))
        skin_temp = round(self._skin_temp, 1)

        # -- Blood glucose (meal-driven curve) --
        assert self._fasting_glucose is not None
        assert self._meal_times is not None
        ts_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        ts_minutes = ts_dt.hour * 60 + ts_dt.minute
        glucose = self._fasting_glucose
        for meal_start, amplitude, t_peak in self._meal_times:
            meal_minutes = meal_start.hour * 60 + meal_start.minute
            delta = float(ts_minutes - meal_minutes)
            glucose += _glucose_meal_response(delta, amplitude, t_peak)
        glucose += rng.uniform(-3.0, 3.0)
        blood_glucose = round(glucose, 1)
        self._last_blood_glucose = blood_glucose

        respiratory_rate = rng.randint(14, 20)

        # -- Body battery (depletes with occasional recovery during rest) --
        if self._body_battery is None:
            self._body_battery = rng.randint(85, 95)

        if block.activity == "running":
            self._body_battery -= rng.randint(3, 6)
        elif block.activity in ("commute", "arriving_office"):
            self._body_battery -= rng.randint(1, 3)
        elif block.activity in _SEDENTARY_ACTIVITIES:
            if rng.random() < 0.2:
                self._body_battery += rng.randint(1, 2)
            else:
                self._body_battery -= rng.randint(0, 2)
        else:
            self._body_battery -= rng.randint(0, 2)
        self._body_battery = max(5, min(100, self._body_battery))

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
    # Crisis vitals — passive sensors drift, active sensors fail
    # ------------------------------------------------------------------

    def _generate_crisis(self, rng: random.Random) -> dict[str, object]:
        """Active sensors read zero; passive sensors continue drifting.

        Distinguishes collapse from device removal: a removed device
        reports nothing at all, but a device on a collapsed person still
        measures skin temperature (slowly cooling) and blood glucose
        (CGM still functional, slight upward drift as cells stop consuming).
        """
        last = self._last_normal

        # Skin temp: slow decline (~0.1C per 5-min heartbeat).
        if self._skin_temp is not None:
            self._skin_temp -= 0.1
            self._skin_temp = max(34.0, self._skin_temp)

        # Blood glucose: slight upward drift (cells stop consuming).
        self._last_blood_glucose += rng.uniform(0.0, 2.0)

        return {
            "heart_rate": 0,
            "spo2": 0,
            "steps": last["steps"],
            "skin_temp": round(self._skin_temp, 1)
            if self._skin_temp is not None
            else last["skin_temp"],
            "ecg_summary": "inconclusive",
            "blood_glucose": round(self._last_blood_glucose, 1),
            "calories_burned": last["calories_burned"],
            "sleep_stage": "none",
            "respiratory_rate": 0,
            "body_battery": last["body_battery"],
        }
