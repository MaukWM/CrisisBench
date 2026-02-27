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
        self._battery_floor: int = 5  # overwritten in _init_once
        self._skin_temp: float | None = None
        self._fasting_glucose: float | None = None
        self._meal_times: list[tuple[time, float, float]] | None = None
        self._last_blood_glucose: float = 0.0
        self._last_normal: dict[str, object] = {}
        self._crisis_count: int = 0
        self._crisis_start_temp: float | None = None
        self._prev_activity: str | None = None

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
        self._battery_floor = rng.randint(3, 7)

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

        # -- Heart rate with micro-spikes and warmup transitions --
        hr_min, hr_max = block.hr_range
        # Warmup: first heartbeat of running uses intermediate HR (not instant jump).
        if block.activity == "running" and self._prev_activity != "running":
            heart_rate = rng.randint(95, 115)
        else:
            heart_rate = rng.randint(hr_min, hr_max)
        spike_roll = rng.random()
        spike_amount = rng.randint(10, 25)
        if block.activity in _SEDENTARY_ACTIVITIES and spike_roll < 0.1:
            heart_rate += spike_amount
        self._prev_activity = block.activity

        # SpO2: mostly 95-99, occasional 100 (perfect saturation) or 93-94
        # (poor wrist lock) — real pulse-ox artifacts.
        spo2_artifact = rng.random()
        if spo2_artifact < 0.05:
            spo2 = 100
        elif spo2_artifact < 0.08:
            spo2 = rng.randint(93, 94)
        else:
            spo2 = rng.randint(95, 99)

        # -- Cumulative steps (bursty during sedentary) --
        if block.activity in _SEDENTARY_ACTIVITIES:
            roll = rng.random()
            if roll < 0.3:
                new_steps = rng.randint(20, 80)
            elif roll < 0.38:
                new_steps = 1
            else:
                new_steps = 0
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

        # -- ECG with occasional wearable artifacts --
        ecg_roll = rng.random()
        if ecg_roll < 0.03:
            ecg_summary = "motion artifact"
        elif ecg_roll < 0.06:
            ecg_summary = "poor signal quality"
        else:
            ecg_summary = "normal sinus rhythm"

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
        # Exercise dip: muscles consuming glucose during running.
        if block.activity == "running":
            glucose -= rng.uniform(3.0, 8.0)
        # Precision variation: real CGMs sometimes report whole numbers.
        blood_glucose = float(round(glucose)) if rng.random() < 0.15 else round(glucose, 1)
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
        self._body_battery = min(100, self._body_battery)
        # Soft floor: wobble around the floor instead of clamping flat.
        if self._body_battery <= self._battery_floor:
            self._body_battery = max(1, self._battery_floor + rng.randint(-2, 2))

        result: dict[str, object] = {
            "heart_rate": heart_rate,
            "spo2": spo2,
            "steps": self._cumulative_steps,
            "skin_temp": skin_temp,
            "ecg_summary": ecg_summary,
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

        # Skin temp: Newton's law of cooling (exponential, decelerating).
        # T(t) = T_ambient + (T_start - T_ambient) * exp(-k * t)
        if self._skin_temp is not None:
            if self._crisis_start_temp is None:
                self._crisis_start_temp = self._skin_temp
            self._crisis_count += 1
            t_ambient = 28.0  # effective ambient (clothing insulation on a NYC evening)
            k = 0.015  # per minute
            minutes_elapsed = self._crisis_count * 5.0
            self._skin_temp = (
                t_ambient
                + (self._crisis_start_temp - t_ambient) * math.exp(-k * minutes_elapsed)
                + rng.uniform(-0.05, 0.05)
            )

        # Blood glucose: mostly upward drift with CGM noise (occasional reversals).
        self._last_blood_glucose += rng.uniform(-1.5, 2.5)
        if rng.random() < 0.15:
            crisis_glucose = float(round(self._last_blood_glucose))
        else:
            crisis_glucose = round(self._last_blood_glucose, 1)

        return {
            "heart_rate": 0,
            "spo2": 0,
            "steps": last["steps"],
            "skin_temp": round(self._skin_temp, 1)
            if self._skin_temp is not None
            else last["skin_temp"],
            "ecg_summary": "inconclusive",
            "blood_glucose": crisis_glucose,
            "calories_burned": last["calories_burned"],
            "sleep_stage": "none",
            "respiratory_rate": 0,
            # Body battery frozen: device can't compute without HRV data.
            "body_battery": last["body_battery"],
        }
