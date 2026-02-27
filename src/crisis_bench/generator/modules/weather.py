"""WeatherGenerator — realistic diurnal weather evolving through the day.

Stateful generator producing weather data:
- Temperature follows a sinusoidal diurnal curve (cool dawn -> warm afternoon -> cooling evening)
- Humidity inversely correlated with temperature
- Wind speed/direction drift via random walk (no sudden flips)
- UV index follows sun arc (0 at dawn, peaks midday, drops evening)
- Pressure, AQI, cloud cover drift slowly
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


class WeatherGenerator:
    """Generate weather data for each heartbeat.

    Tracks slowly-drifting values (wind, pressure, cloud cover, AQI) across
    heartbeats via random walks.  Temperature and UV are deterministic curves
    plus seeded noise.
    """

    def __init__(self) -> None:
        self._wind_speed: float | None = None
        self._wind_dir_idx: int | None = None
        self._pressure: float | None = None
        self._cloud_cover: float | None = None
        self._aqi: float | None = None
        self._pollen_level: str | None = None
        self._dew_point_base: float | None = None

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
        r_uv_noise = rng.gauss(0, 0.3)  # 5: UV noise
        r_aqi_step = rng.gauss(0, 1.0)  # 6: AQI step
        r_pressure_step = rng.gauss(0, 0.01)  # 7: pressure step
        r_cloud_step = rng.gauss(0, 2.0)  # 8: cloud cover step

        # Parse hour as fractional value for curves.
        hour = _timestamp_to_hours(timestamp)

        # --- Temperature: sinusoidal diurnal curve ---
        # NYC mid-June: min ~16C at 05:30, max ~25C at 15:00
        t_min_hour = 5.5  # sunrise
        t_max_hour = 15.0  # afternoon peak (lags solar noon)
        t_mean = 20.5
        t_amplitude = 4.5

        if t_min_hour <= hour <= t_max_hour:
            progress = (hour - t_min_hour) / (t_max_hour - t_min_hour)
            temp = t_mean + t_amplitude * math.sin(progress * math.pi)
        elif hour > t_max_hour:
            # Cooling after peak — slower decay toward evening.
            hours_past_peak = hour - t_max_hour
            temp = t_mean + t_amplitude * math.exp(-0.15 * hours_past_peak)
        else:
            # Before sunrise — cool.
            temp = t_mean - t_amplitude * 0.8

        temp += r_temp_noise
        temp = round(temp, 1)

        # --- Feels like: wind chill / heat index offset ---
        assert self._wind_speed is not None
        wind_chill = -0.1 * self._wind_speed  # wind makes it feel colder
        feels_like = round(temp + wind_chill + (0.3 if temp > 22 else -0.2), 1)

        # --- Humidity: inverse-correlated with temperature ---
        # Higher morning (~70%), lower afternoon (~45%).
        base_humidity = 70.0 - 1.8 * (temp - 16.0)
        humidity = int(max(25, min(95, base_humidity + r_humidity_noise)))

        # --- Wind speed: random walk ---
        self._wind_speed = max(0.5, min(15.0, self._wind_speed + r_wind_speed))
        wind_speed = round(self._wind_speed, 1)

        # --- Wind direction: slow drift (~10% chance of shifting one step) ---
        assert self._wind_dir_idx is not None
        if r_wind_dir < 0.1:
            self._wind_dir_idx = (self._wind_dir_idx + 1) % 8
        elif r_wind_dir > 0.9:
            self._wind_dir_idx = (self._wind_dir_idx - 1) % 8
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

        # --- AQI: slow drift ---
        assert self._aqi is not None
        self._aqi = max(15, min(80, self._aqi + r_aqi_step))
        aqi = int(self._aqi)

        # --- Pollen: static for the day ---
        assert self._pollen_level is not None
        pollen_level = self._pollen_level

        # --- Pressure: slow drift ---
        assert self._pressure is not None
        self._pressure = max(29.7, min(30.3, self._pressure + r_pressure_step))
        pressure = round(self._pressure, 2)

        # --- Dew point: derived from temp and humidity ---
        assert self._dew_point_base is not None
        # Magnus formula approximation (Celsius), then convert to Fahrenheit.
        gamma = math.log(humidity / 100.0) + (17.67 * temp) / (243.5 + temp)
        dew_c = 243.5 * gamma / (17.67 - gamma)
        dew_point = round(dew_c * 9 / 5 + 32, 1)  # Fahrenheit

        # --- Cloud cover: slow drift ---
        assert self._cloud_cover is not None
        self._cloud_cover = max(0, min(100, self._cloud_cover + r_cloud_step))
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
        self._pressure = 29.9 + rng.random() * 0.2  # 29.9-30.1 inHg
        self._cloud_cover = 20.0 + rng.random() * 30.0  # 20-50%
        self._aqi = 30.0 + rng.random() * 20.0  # 30-50
        self._pollen_level = rng.choice(_POLLEN_LEVELS)
        self._dew_point_base = 55.0 + rng.random() * 10.0  # 55-65 F


def _timestamp_to_hours(timestamp: str) -> float:
    """Extract fractional hours from ISO 8601 timestamp."""
    # Format: "2027-06-15T14:30Z"
    time_part = timestamp.split("T")[1].rstrip("Z")
    parts = time_part.split(":")
    return int(parts[0]) + int(parts[1]) / 60.0
