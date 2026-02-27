"""LocationGenerator -- realistic GPS and spatial data from the PersonSchedule.

Stateful generator producing location data:
- Stationary blocks: GPS hovers around known coordinates with realistic jitter
- Commute blocks: interpolation with lateral wobble and station stops
- Running blocks: random walk from park center with running pace
- Crisis: GPS shows sub-meter drift around frozen base, stable outdoor accuracy
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random

    from crisis_bench.generator.schedule import ActivityBlock, PersonSchedule

from crisis_bench.generator.schedule import LOCATIONS

# Geofence names by location_key.
# Real devices only configure geofences for meaningful zones (home, office).
# Everything else returns None — no real user sets up "at_restaurant" geofences.
_GEOFENCE: dict[str, str] = {
    "home": "at_home",
    "office": "at_office",
}

# Movement classification by activity.
_MOVEMENT: dict[str, str] = {
    "waking_up": "stationary",
    "breakfast": "stationary",
    "commute": "driving",
    "arriving_office": "walking",
    "working": "stationary",
    "meeting": "stationary",
    "lunch": "stationary",
    "running": "running",
    "home": "stationary",
}

# Altitude ranges (meters) by location_key.
_ALTITUDE: dict[str, tuple[float, float]] = {
    "home": (8.0, 15.0),
    "office": (40.0, 80.0),
    "transit": (8.0, 15.0),
    "restaurant": (8.0, 15.0),
    "central_park": (10.0, 25.0),
}

# GPS jitter sigma (degrees) by location_key.
# Indoor ~0.00008 deg (~8 m), outdoor ~0.00003 deg (~3 m).
_SIGMA: dict[str, float] = {
    "home": 0.00008,
    "office": 0.00008,
    "restaurant": 0.00008,
    "central_park": 0.00003,
}

# Running random-walk step size (~150-200 m per 5-min heartbeat ~= 0.0015 deg).
_RUNNING_STEP = 0.0015

# Proximity threshold to decide "near park" for random-walk continuation (deg, ~550 m).
_PARK_PROXIMITY = 0.005


class LocationGenerator:
    """Generate location/GPS data for each heartbeat.

    Tracks previous position for heading computation and maintains
    crisis state for GPS freeze behaviour.
    """

    def __init__(self) -> None:
        self._prev_lat: float | None = None
        self._prev_lon: float | None = None
        self._prev_heading: int = 0
        self._crisis_count: int = 0
        self._crisis_base_lat: float | None = None
        self._crisis_base_lon: float | None = None
        self._commute_routes: list[tuple[tuple[float, float], tuple[float, float]]] | None = None

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object]:
        """Produce one heartbeat's location data.

        Always consumes exactly 6 RNG calls for determinism regardless
        of code path.
        """
        r_lat = rng.uniform(-1.0, 1.0)
        r_lon = rng.uniform(-1.0, 1.0)
        r_speed = rng.random()
        r_heading = rng.uniform(-1.0, 1.0)
        r_alt = rng.random()
        r_acc = rng.random()

        block = schedule.get_block_at(timestamp)

        if block.activity == "CRISIS":
            return self._crisis(r_lat, r_lon, r_alt, r_acc)

        if block.location_key == "transit":
            return self._transit(
                schedule,
                block,
                timestamp,
                r_lat,
                r_lon,
                r_speed,
                r_heading,
                r_alt,
                r_acc,
            )

        if block.activity == "running":
            return self._running(r_lat, r_lon, r_speed, r_heading, r_alt, r_acc)

        return self._stationary(
            block,
            r_lat,
            r_lon,
            r_speed,
            r_heading,
            r_alt,
            r_acc,
        )

    # ------------------------------------------------------------------
    # Stationary (home, office, restaurant, etc.)
    # ------------------------------------------------------------------

    def _stationary(
        self,
        block: ActivityBlock,
        r_lat: float,
        r_lon: float,
        r_speed: float,
        r_heading: float,
        r_alt: float,
        r_acc: float,
    ) -> dict[str, object]:
        coords = LOCATIONS[block.location_key]
        assert coords is not None
        base_lat, base_lon = coords

        sigma = _SIGMA[block.location_key]
        lat = base_lat + r_lat * sigma
        lon = base_lon + r_lon * sigma

        alt_lo, alt_hi = _ALTITUDE[block.location_key]
        altitude = alt_lo + r_alt * (alt_hi - alt_lo)

        movement = _MOVEMENT[block.activity]
        speed = 1.0 + r_speed * 0.8 if movement == "walking" else r_speed * 0.3

        heading = self._heading(lat, lon, r_heading)
        accuracy = 3.0 + r_acc * 7.0  # 3-10 m

        self._prev_lat = lat
        self._prev_lon = lon

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "altitude": round(altitude, 1),
            "speed": round(speed, 2),
            "heading": heading,
            "accuracy": round(accuracy, 1),
            "geofence_status": _GEOFENCE.get(block.location_key),
            "movement_classification": movement,
        }

    # ------------------------------------------------------------------
    # Transit (commute interpolation)
    # ------------------------------------------------------------------

    def _resolve_routes(
        self,
        schedule: PersonSchedule,
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Resolve origin/destination for each commute block from adjacent blocks."""
        if self._commute_routes is not None:
            return self._commute_routes

        routes: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for i, block in enumerate(schedule.blocks):
            if block.location_key != "transit":
                continue
            origin_key = schedule.blocks[i - 1].location_key if i > 0 else "home"
            dest_key = (
                schedule.blocks[i + 1].location_key if i + 1 < len(schedule.blocks) else "home"
            )
            origin = LOCATIONS[origin_key]
            dest = LOCATIONS[dest_key]
            assert origin is not None, f"Commute origin {origin_key!r} has no coords"
            assert dest is not None, f"Commute dest {dest_key!r} has no coords"
            routes.append((origin, dest))

        self._commute_routes = routes
        return routes

    def _transit(
        self,
        schedule: PersonSchedule,
        block: ActivityBlock,
        timestamp: str,
        r_lat: float,
        r_lon: float,
        r_speed: float,
        r_heading: float,
        r_alt: float,
        r_acc: float,
    ) -> dict[str, object]:
        routes = self._resolve_routes(schedule)

        # Which commute is this? Count earlier transit blocks.
        idx = sum(
            1
            for b in schedule.blocks
            if b.location_key == "transit" and b is not block and b.start_time < block.start_time
        )
        origin, dest = routes[idx]

        # Progress through block (0.0 at start, 1.0 at end).
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        t = dt.time()
        assert block.end_time is not None
        start_min = block.start_time.hour * 60 + block.start_time.minute
        end_min = block.end_time.hour * 60 + block.end_time.minute
        cur_min = t.hour * 60 + t.minute
        duration = end_min - start_min
        progress = (cur_min - start_min) / duration if duration > 0 else 0.5
        progress = max(0.0, min(1.0, progress))

        lat = origin[0] + (dest[0] - origin[0]) * progress + r_lat * 0.0002
        lon = origin[1] + (dest[1] - origin[1]) * progress + r_lon * 0.0002

        # Realistic subway: ~25% chance stopped at station, otherwise variable speed.
        speed = r_speed * 4.0 if r_speed < 0.25 else 3.0 + (r_speed - 0.25) / 0.75 * 9.0
        heading = self._heading(lat, lon, r_heading)

        alt_lo, alt_hi = _ALTITUDE["transit"]
        altitude = alt_lo + r_alt * (alt_hi - alt_lo)
        accuracy = 5.0 + r_acc * 10.0  # 5-15 m

        self._prev_lat = lat
        self._prev_lon = lon

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "altitude": round(altitude, 1),
            "speed": round(speed, 2),
            "heading": heading,
            "accuracy": round(accuracy, 1),
            "geofence_status": None,
            "movement_classification": "driving",
        }

    # ------------------------------------------------------------------
    # Running (random walk in Central Park)
    # ------------------------------------------------------------------

    def _running(
        self,
        r_lat: float,
        r_lon: float,
        r_speed: float,
        r_heading: float,
        r_alt: float,
        r_acc: float,
    ) -> dict[str, object]:
        park = LOCATIONS["central_park"]
        assert park is not None
        park_lat, park_lon = park

        # Continue random walk if near the park; otherwise reset to park center
        # (handles teleport from home block to running block).
        if (
            self._prev_lat is not None
            and self._prev_lon is not None
            and abs(self._prev_lat - park_lat) < _PARK_PROXIMITY
            and abs(self._prev_lon - park_lon) < _PARK_PROXIMITY
        ):
            base_lat, base_lon = self._prev_lat, self._prev_lon
        else:
            base_lat, base_lon = park_lat, park_lon

        lat = base_lat + r_lat * _RUNNING_STEP
        lon = base_lon + r_lon * _RUNNING_STEP

        speed = 2.5 + r_speed * 1.0  # 2.5-3.5 m/s
        heading = self._heading(lat, lon, r_heading)

        alt_lo, alt_hi = _ALTITUDE["central_park"]
        altitude = alt_lo + r_alt * (alt_hi - alt_lo)
        accuracy = 3.0 + r_acc * 5.0  # 3-8 m

        self._prev_lat = lat
        self._prev_lon = lon

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "altitude": round(altitude, 1),
            "speed": round(speed, 2),
            "heading": heading,
            "accuracy": round(accuracy, 1),
            "geofence_status": None,
            "movement_classification": "running",
        }

    # ------------------------------------------------------------------
    # Crisis (GPS shows sub-meter drift, accuracy stays stable outdoor)
    # ------------------------------------------------------------------

    def _crisis(
        self,
        r_lat: float,
        r_lon: float,
        r_alt: float,
        r_acc: float,
    ) -> dict[str, object]:
        self._crisis_count += 1

        # First crisis heartbeat: lock down the base position and heading.
        if self._crisis_base_lat is None:
            self._crisis_base_lat = self._prev_lat if self._prev_lat is not None else 40.7812
            self._crisis_base_lon = self._prev_lon if self._prev_lon is not None else -73.9665

        base_lat = self._crisis_base_lat
        base_lon = self._crisis_base_lon
        assert base_lon is not None  # set together with base_lat

        # Sub-meter GPS drift around the frozen base (~3 m outdoor sigma).
        drift_sigma = 0.00003
        lat = base_lat + r_lat * drift_sigma
        lon = base_lon + r_lon * drift_sigma

        # Altitude: park-level with ±3 m jitter (real GPS altitude noise).
        altitude = 15.0 + r_alt * 6.0 - 3.0  # 12-18 m

        # Heading: locked at last known value (meaningless at speed=0,
        # most devices just report the last fix heading).

        # Stable outdoor accuracy: 3-8 m (stationary GPS actually improves, but
        # "stable with noise" is enough to not be a synthetic tell).
        accuracy = 3.0 + r_acc * 5.0

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "altitude": round(altitude, 1),
            "speed": 0.0,
            "heading": self._prev_heading,
            "accuracy": round(accuracy, 1),
            "geofence_status": None,
            "movement_classification": "stationary",
        }

    # ------------------------------------------------------------------
    # Heading computation
    # ------------------------------------------------------------------

    def _heading(self, lat: float, lon: float, r_heading: float) -> int:
        """Compute heading from previous position with noise."""
        if self._prev_lat is not None and self._prev_lon is not None:
            dlat = lat - self._prev_lat
            dlon = lon - self._prev_lon
            if abs(dlat) > 1e-8 or abs(dlon) > 1e-8:
                angle = math.degrees(math.atan2(dlon, dlat))
                h = (int(angle) + 360) % 360
                h = (h + int(r_heading * 10)) % 360
                self._prev_heading = h
                return h

        # No movement or first heartbeat -- drift from previous heading.
        h = (self._prev_heading + int(r_heading * 30)) % 360
        self._prev_heading = h
        return h
