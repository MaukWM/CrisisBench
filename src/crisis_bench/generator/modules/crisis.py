"""CrisisInjector — post-processing enforcement for crisis heartbeats.

Runs AFTER all module generators, BEFORE Pydantic model conversion.
Enforces critical crisis signals as a safety net over generator logic.
Adding new crisis types requires only a new profile dict.
"""

from __future__ import annotations

_FREEZE = "FREEZE"

CARDIAC_ARREST_PROFILE: dict[str, dict[str, object]] = {
    "health": {
        "heart_rate": 0,
        "spo2": 0,
        "respiratory_rate": 0,
        "ecg_summary": "inconclusive",
        "steps": _FREEZE,
        "calories_burned": _FREEZE,
        "body_battery": _FREEZE,
    },
    "location": {
        "lat": _FREEZE,
        "lon": _FREEZE,
        "speed": 0.0,
        "movement_classification": "stationary",
    },
}

_CRISIS_PROFILES: dict[str, dict[str, dict[str, object]]] = {
    "cardiac_arrest": CARDIAC_ARREST_PROFILE,
}


class CrisisInjector:
    """Post-processing enforcement layer for crisis heartbeats.

    Verifies and enforces critical crisis signals after all generators
    have run.  Modifies raw heartbeat dicts in-place.
    """

    def apply(
        self,
        raw_heartbeats: list[dict[str, object]],
        crisis_heartbeat_id: int,
        crisis_type: str,
    ) -> None:
        """Enforce crisis profile on heartbeats at and after *crisis_heartbeat_id*.

        Raises ``ValueError`` if a module required by the crisis profile
        is ``None`` at or after the crisis heartbeat (indicates a pipeline bug —
        the protected zone should have prevented module drops near crisis).
        """
        profile = _CRISIS_PROFILES.get(crisis_type)
        if profile is None:
            msg = f"No crisis profile defined for {crisis_type!r}"
            raise ValueError(msg)

        # Snapshot pre-crisis values for FREEZE resolution.
        pre_crisis = raw_heartbeats[crisis_heartbeat_id - 1] if crisis_heartbeat_id > 0 else {}

        # Resolve FREEZE sentinels once using the pre-crisis snapshot.
        resolved: dict[str, dict[str, object]] = {}
        for module_name, overrides in profile.items():
            resolved_overrides: dict[str, object] = {}
            pre_module = pre_crisis.get(module_name)
            for field, value in overrides.items():
                if value == _FREEZE:
                    if isinstance(pre_module, dict) and field in pre_module:
                        resolved_overrides[field] = pre_module[field]
                else:
                    resolved_overrides[field] = value
            resolved[module_name] = resolved_overrides

        # Enforce on every crisis heartbeat.
        for hb in raw_heartbeats[crisis_heartbeat_id:]:
            for module_name, overrides in resolved.items():
                if module_name not in hb:
                    continue  # Module not enabled for this tier
                module_data = hb[module_name]
                if module_data is None:
                    msg = (
                        f"Module {module_name!r} is None at heartbeat "
                        f"{hb['heartbeat_id']} during crisis — "
                        f"protected zone should have prevented module drops"
                    )
                    raise ValueError(msg)
                assert isinstance(module_data, dict)
                for field, value in overrides.items():
                    module_data[field] = value
