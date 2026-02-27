"""WeatherGenerator — realistic diurnal weather evolving through the day.

Stateful generator producing weather data:
- Temperature follows a half-sine diurnal curve (cool dawn -> warm afternoon -> cooling evening)
- Humidity inversely correlated with temperature
- Wind speed/direction drift via random walk (no sudden flips)
- UV index follows sun arc (0 at dawn, peaks midday, drops evening)
- Pressure, AQI, cloud cover drift slowly via mean-reverting walks
- Pollen level chosen once per scenario

During crisis, weather continues evolving normally — weather doesn't know
someone collapsed.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import PersonSchedule

# Wind direction labels in clockwise order (index 0=N, 1=NE, ..., 7=NW).
_WIND_DIRS: list[str] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Pollen levels — chosen once per scenario, stable all day.
_POLLEN_LEVELS: list[str] = ["Low", "Medium", "High"]

# Diurnal temperature parameters (NYC mid-June).
_T_BASE = 16.0  # pre-dawn baseline (°C)
_T_PEAK = 25.0  # afternoon peak (°C)
_T_RISE_HOUR = 5.5  # sunrise / warming start
_T_PEAK_HOUR = 15.0  # hour of peak temperature


def _soft_clamp(value: float, low: float, high: float) -> float:
    """Smoothly compress values near boundaries instead of hard walls.

    Uses tanh to create an S-curve that asymptotically approaches (low, high)
    without producing the flat lines that hard ``max/min`` clamping causes.
    """
    mid = (low + high) / 2.0
    half = (high - low) / 2.0
    return mid + half * math.tanh((value - mid) / half)


def _timestamp_to_hours(timestamp: str) -> float:
    """Extract fractional hours from ISO 8601 timestamp."""
    # Format: "2027-06-15T14:30Z"
    time_part = timestamp.split("T")[1].rstrip("Z")
    parts = time_part.split(":")
    return int(parts[0]) + int(parts[1]) / 60.0


class WeatherGenerator:
    """Generate weather data for each heartbeat.

    Tracks slowly-drifting values (wind, pressure, cloud cover, AQI) across
    heartbeats via random walks.  Temperature and UV are deterministic curves
    plus seeded noise.
    """

    def __init__(self) -> None:
        self._wind_speed: float | None = None
        self._wind_dir_idx: int | None = None
        self._prevailing_dir_idx: int | None = None
        self._pressure: float | None = None
        self._cloud_cover: float | None = None
        self._aqi: float | None = None
        self._pollen_level: str | None = None

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        """Produce one heartbeat's weather data.

        Consumes exactly 8 RNG calls per heartbeat for determinism.
        """
        # Lazy init on first call.
        if self._wind_speed is None:
            self._init_once(rng)

        # 8 RNG calls — always consumed regardless of code path.
        r_temp_noise = rng.gauss(0, 0.5)  # 1: temp noise
        r_wind_speed = rng.gauss(0, 0.3)  # 2: wind speed step
        r_wind_dir = rng.random()  # 3: wind dir change chance
        r_humidity_noise = rng.gauss(0, 1.5)  # 4: humidity noise
        r_uv_noise = rng.gauss(0, 0.9)  # 5: UV noise (wide enough to stutter int rounding)
        r_aqi_step = rng.gauss(0, 1.0)  # 6: AQI step
        r_pressure_step = rng.gauss(0, 0.01)  # 7: pressure step
        r_cloud_step = rng.gauss(0, 2.0)  # 8: cloud cover step

        # Parse hour as fractional value for curves.
        hour = _timestamp_to_hours(timestamp)

        # --- Temperature: half-sine diurnal curve ---
        # Continuous profile: flat pre-dawn -> half-sine warming -> exponential cooling
        amplitude = _T_PEAK - _T_BASE
        if hour <= _T_RISE_HOUR:
            # Pre-dawn: stable at baseline.
            temp = _T_BASE
        elif hour <= _T_PEAK_HOUR:
            # Warming: half-sine from baseline to peak.
            progress = (hour - _T_RISE_HOUR) / (_T_PEAK_HOUR - _T_RISE_HOUR)
            temp = _T_BASE + amplitude * math.sin(progress * math.pi / 2)
        else:
            # Cooling after peak: exponential decay toward baseline.
            hours_past_peak = hour - _T_PEAK_HOUR
            temp = _T_BASE + amplitude * math.exp(-0.15 * hours_past_peak)

        temp += r_temp_noise
        temp = round(temp, 1)

        # --- Feels like: wind chill / heat index offset ---
        assert self._wind_speed is not None
        wind_chill = -0.1 * self._wind_speed
        feels_like = round(temp + wind_chill + (0.3 if temp > 22 else -0.2), 1)

        # --- Humidity: inverse-correlated with temperature ---
        base_humidity = 70.0 - 1.8 * (temp - _T_BASE)
        humidity = int(max(20, min(98, base_humidity + r_humidity_noise)))

        # --- Wind speed: soft-clamped random walk ---
        self._wind_speed += r_wind_speed
        self._wind_speed = _soft_clamp(self._wind_speed, 0.5, 15.0)
        wind_speed = round(self._wind_speed, 1)

        # --- Wind direction: sticky drift with prevailing-direction anchor ---
        # Only ~4% chance of shifting per beat, and biased back toward the
        # prevailing direction (set at init) so wind stays in one quadrant.
        assert self._wind_dir_idx is not None
        assert self._prevailing_dir_idx is not None
        if r_wind_dir < 0.04:
            self._wind_dir_idx = (self._wind_dir_idx + 1) % 8
        elif r_wind_dir > 0.96:
            self._wind_dir_idx = (self._wind_dir_idx - 1) % 8
        elif r_wind_dir < 0.10:
            # 6% chance: snap back one step toward prevailing direction.
            delta = (self._prevailing_dir_idx - self._wind_dir_idx) % 8
            if delta != 0:
                step = 1 if delta <= 4 else -1
                self._wind_dir_idx = (self._wind_dir_idx + step) % 8
        wind_dir = _WIND_DIRS[self._wind_dir_idx]

        # --- UV index: sun arc (0 early, peaks midday, drops evening) ---
        if 6.0 <= hour <= 20.0:
            uv_progress = (hour - 6.0) / (13.0 - 6.0)  # peaks at ~13:00
            if hour <= 13.0:
                raw_uv = 8.0 * math.sin(uv_progress * math.pi / 2)
            else:
                decay = (hour - 13.0) / 7.0
                raw_uv = 8.0 * math.cos(decay * math.pi / 2)
            uv_index = max(0, int(raw_uv + r_uv_noise))
        else:
            uv_index = 0

        # --- AQI: soft-clamped random walk ---
        assert self._aqi is not None
        self._aqi += r_aqi_step
        self._aqi = _soft_clamp(self._aqi, 15.0, 80.0)
        aqi = int(self._aqi)

        # --- Pollen: static for the day ---
        assert self._pollen_level is not None
        pollen_level = self._pollen_level

        # --- Pressure: soft-clamped random walk ---
        assert self._pressure is not None
        self._pressure += r_pressure_step
        self._pressure = _soft_clamp(self._pressure, 29.7, 30.3)
        pressure = round(self._pressure, 2)

        # --- Dew point: derived from temp and humidity (Celsius) ---
        # Magnus formula approximation.
        gamma = math.log(humidity / 100.0) + (17.67 * temp) / (243.5 + temp)
        dew_point = round(243.5 * gamma / (17.67 - gamma), 1)

        # --- Cloud cover: soft-clamped random walk ---
        assert self._cloud_cover is not None
        self._cloud_cover += r_cloud_step
        self._cloud_cover = _soft_clamp(self._cloud_cover, 0.0, 100.0)
        cloud_cover = int(self._cloud_cover)

        return {
            "temp": temp,
            "feels_like": feels_like,
            "humidity": humidity,
            "wind_speed": wind_speed,
            "wind_dir": wind_dir,
            "uv_index": uv_index,
            "aqi": aqi,
            "pollen_level": pollen_level,
            "pressure": pressure,
            "dew_point": dew_point,
            "cloud_cover": cloud_cover,
        }

    def _init_once(self, rng: random.Random) -> None:
        """Set per-scenario initial values. Called once on first generate()."""
        self._wind_speed = 3.0 + rng.random() * 4.0  # 3-7 mph
        self._wind_dir_idx = rng.randint(0, 7)
        self._prevailing_dir_idx = self._wind_dir_idx  # anchor for the day
        self._pressure = 29.9 + rng.random() * 0.2  # 29.9-30.1 inHg
        self._cloud_cover = 20.0 + rng.random() * 30.0  # 20-50%
        self._aqi = 30.0 + rng.random() * 20.0  # 30-50
        self._pollen_level = rng.choice(_POLLEN_LEVELS)
