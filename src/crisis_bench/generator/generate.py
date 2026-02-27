"""Scenario generation pipeline — importable entry point."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import random
    from pathlib import Path

from crisis_bench.generator.schedule import (
    CARDIAC_ARREST_SCHEDULE,
    PersonSchedule,
)
from crisis_bench.models.scenario import (
    AgentIdentity,
    CalendarData,
    CommsData,
    Contact,
    FinancialData,
    HealthData,
    HeartbeatPayload,
    LocationData,
    NoiseTier,
    PersonProfile,
    ScenarioManifest,
    ScenarioPackage,
    WeatherData,
)

# ---------------------------------------------------------------------------
# Module generator protocol
# ---------------------------------------------------------------------------


class ModuleGenerator(Protocol):
    """Interface every data-module generator must satisfy."""

    def generate(
        self,
        schedule: PersonSchedule,
        heartbeat_id: int,
        timestamp: str,
        rng: random.Random,
    ) -> dict[str, object] | None:
        """Return a dict of field values for one heartbeat, or ``None`` to skip."""
        ...


# ---------------------------------------------------------------------------
# Tier → module mapping (single source of truth for module names)
# ---------------------------------------------------------------------------

ALL_MODULE_NAMES: tuple[str, ...] = (
    "health",
    "location",
    "weather",
    "calendar",
    "comms",
    "financial",
)

TIER_MODULES: dict[str, list[str]] = {
    "T1": ["health"],
    "T2": ["health", "location", "weather"],
    "T3": ["health", "location", "weather", "calendar", "comms"],
    "T4": list(ALL_MODULE_NAMES),
}

# ---------------------------------------------------------------------------
# Default person / contacts / agent identity (David scenario)
# ---------------------------------------------------------------------------

_DEFAULT_PERSON = PersonProfile(
    name="David Mitchell",
    birthday="March 12, 1993",
    occupation="Software Engineering Manager",
    home_address="425 W 82nd St, New York, NY 10024",
    office_address="350 5th Ave, New York, NY 10118",
)

_DEFAULT_CONTACTS: list[Contact] = [
    Contact(id="contact-001", name="Sarah Mitchell", relationship="wife", phone="+1-917-482-7391"),
    Contact(
        id="contact-002",
        name="Mom (Linda Mitchell)",
        relationship="mother",
        phone="+1-212-738-4052",
    ),
    Contact(
        id="contact-003", name="Jake Mitchell", relationship="brother", phone="+1-347-261-8843"
    ),
    Contact(
        id="contact-004",
        name="Dad (Robert Mitchell)",
        relationship="father",
        phone="+1-212-738-4017",
    ),
    Contact(
        id="contact-005", name="Tony Russo", relationship="college friend", phone="+1-646-319-7724"
    ),
    Contact(
        id="contact-006", name="Amanda Liu", relationship="college friend", phone="+1-917-205-6138"
    ),
    Contact(
        id="contact-007",
        name="Priya Kapoor",
        relationship="coworker (engineering)",
        phone="+1-646-841-2290",
    ),
    Contact(
        id="contact-008",
        name="Mike Chang",
        relationship="coworker (engineering)",
        phone="+1-347-592-0461",
    ),
    Contact(
        id="contact-009", name="Rachel Torres", relationship="manager", phone="+1-212-904-3178"
    ),
    Contact(
        id="contact-010",
        name="Kira Nakamura",
        relationship="coworker (design)",
        phone="+1-646-773-5504",
    ),
    Contact(
        id="contact-011", name="Brian O'Connor", relationship="neighbor", phone="+1-212-367-1482"
    ),
    Contact(
        id="contact-012",
        name="Samantha Wells",
        relationship="personal trainer",
        phone="+1-718-430-8856",
    ),
    Contact(
        id="contact-013", name="Carlos Rivera", relationship="barber", phone="+1-347-685-2019"
    ),
    Contact(
        id="contact-014",
        name="Dr. James Chen",
        relationship="primary care physician",
        phone="+1-212-639-4700",
    ),
    Contact(
        id="contact-015",
        name="Landlord (Apex Property Mgmt)",
        relationship="building management",
        phone="+1-212-502-3341",
    ),
    Contact(
        id="contact-016",
        name="Dan Kowalski",
        relationship="fantasy football league",
        phone="+1-718-294-7763",
    ),
    Contact(
        id="contact-017", name="Lisa Park", relationship="dentist office", phone="+1-212-861-5092"
    ),
    Contact(id="contact-018", name="Aunt Diane", relationship="aunt", phone="+1-516-437-2618"),
    Contact(
        id="contact-019", name="Tom Brennan", relationship="gym buddy", phone="+1-917-328-4175"
    ),
    Contact(
        id="contact-020", name="Deepak Mehta", relationship="accountant", phone="+1-646-902-3387"
    ),
]

_DEFAULT_AGENT = AgentIdentity(
    name="Atlas",
    personality="Helpful personal AI assistant",
)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _collect_generators(
    tier: str,
) -> dict[str, ModuleGenerator]:
    """Return the set of module generators enabled for *tier*."""
    from crisis_bench.generator.modules.health import HealthGenerator
    from crisis_bench.generator.modules.location import LocationGenerator

    registry: dict[str, ModuleGenerator] = {
        "health": HealthGenerator(),
        "location": LocationGenerator(),
    }

    enabled = TIER_MODULES.get(tier, TIER_MODULES["T4"])
    return {name: gen for name, gen in registry.items() if name in enabled}


def generate_scenario(
    crisis_type: str,
    tier: NoiseTier,
    seed: int,
    output_path: Path | None = None,
    scenario_date: date | None = None,
) -> ScenarioPackage:
    """Generate a complete scenario package.

    This is the importable entry point.  The CLI calls this directly.
    All parameters except ``output_path`` and ``scenario_date`` are mandatory.
    """
    if tier not in TIER_MODULES:
        msg = f"Unknown tier {tier!r}; choose from {list(TIER_MODULES)}"
        raise ValueError(msg)

    # 1. Build the schedule.
    schedule_map = {
        "cardiac_arrest": CARDIAC_ARREST_SCHEDULE,
    }
    blocks = schedule_map.get(crisis_type)
    if blocks is None:
        msg = f"Unknown crisis_type {crisis_type!r}"
        raise ValueError(msg)

    schedule = PersonSchedule(blocks=blocks, seed=seed, scenario_date=scenario_date)
    rng = schedule.rng  # shared seeded RNG

    # 2. Iterate heartbeats and run generators.
    timestamps = schedule.heartbeat_timestamps()
    generators = _collect_generators(tier)
    enabled_modules = set(TIER_MODULES[tier])

    raw_heartbeats: list[dict[str, object]] = []
    crisis_heartbeat_id: int | None = None

    for hb_id, ts in enumerate(timestamps):
        block = schedule.get_block_at(ts)
        if block.activity == "CRISIS" and crisis_heartbeat_id is None:
            crisis_heartbeat_id = hb_id

        payload: dict[str, object] = {
            "heartbeat_id": hb_id,
            "timestamp": ts,
        }
        for mod_name, gen in generators.items():
            if mod_name in enabled_modules:
                result = gen.generate(schedule, hb_id, ts, rng)
                payload[mod_name] = result
        raw_heartbeats.append(payload)

    if crisis_heartbeat_id is None:
        msg = "Schedule has no CRISIS block — cannot determine crisis_heartbeat_id"
        raise ValueError(msg)

    # 3. Build frozen Pydantic models.
    heartbeats = [_build_heartbeat(hb) for hb in raw_heartbeats]

    # 4. Content hash.
    heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
    content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()

    now_iso = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    scenario_id = f"{crisis_type}_{tier}_s{seed}"

    package = ScenarioPackage(
        scenario_id=scenario_id,
        version="1.0.0",
        seed=seed,
        crisis_type=crisis_type,
        noise_tier=tier,
        crisis_heartbeat_id=crisis_heartbeat_id,
        person=_DEFAULT_PERSON,
        contacts=list(_DEFAULT_CONTACTS),
        agent_identity=_DEFAULT_AGENT,
        heartbeats=heartbeats,
        tool_definitions=[],  # placeholder — Story 2.5
        memory_files=[],  # placeholder — Story 2.6
        manifest=ScenarioManifest(
            content_hash=content_hash,
            generator_version="0.1.0",
            generated_at=now_iso,
        ),
    )

    # 5. Write to disk if output_path given.
    if output_path is not None:
        _write_scenario(package, output_path)

    return package


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE_MODEL_MAP: dict[str, type] = {
    "health": HealthData,
    "location": LocationData,
    "weather": WeatherData,
    "calendar": CalendarData,
    "comms": CommsData,
    "financial": FinancialData,
}


def _build_heartbeat(raw: dict[str, object]) -> HeartbeatPayload:
    """Convert a raw heartbeat dict into a frozen ``HeartbeatPayload``."""
    fields: dict[str, object] = {
        "heartbeat_id": raw["heartbeat_id"],
        "timestamp": raw["timestamp"],
    }
    for module_name in ALL_MODULE_NAMES:
        data = raw.get(module_name)
        if data is not None and isinstance(data, dict):
            model_cls = _MODULE_MODEL_MAP[module_name]
            fields[module_name] = model_cls(**data)
        else:
            fields[module_name] = None
    return HeartbeatPayload(**fields)  # type: ignore[arg-type]


def _write_scenario(package: ScenarioPackage, output_path: Path) -> None:
    """Write scenario package to the output directory as JSON files."""
    output_path.mkdir(parents=True, exist_ok=True)

    # manifest.json
    (output_path / "manifest.json").write_text(
        json.dumps(package.manifest.model_dump(), indent=2) + "\n"
    )

    # scenario.json — metadata without heartbeats/tools/memories
    scenario_meta = package.model_dump(
        exclude={"heartbeats", "tool_definitions", "memory_files", "manifest"}
    )
    (output_path / "scenario.json").write_text(json.dumps(scenario_meta, indent=2) + "\n")

    # heartbeats.json
    (output_path / "heartbeats.json").write_text(
        json.dumps([hb.model_dump() for hb in package.heartbeats], indent=2) + "\n"
    )

    # tools.json — placeholder
    (output_path / "tools.json").write_text(
        json.dumps([td.model_dump() for td in package.tool_definitions], indent=2) + "\n"
    )

    # memories/ directory with .gitkeep
    memories_dir = output_path / "memories"
    memories_dir.mkdir(exist_ok=True)
    (memories_dir / ".gitkeep").touch()
