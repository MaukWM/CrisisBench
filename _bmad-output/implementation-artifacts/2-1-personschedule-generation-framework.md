# Story 2.1: PersonSchedule & Generation Framework

Status: done

## Story

As a **researcher**,
I want a PersonSchedule that defines David's full day as activity blocks with HR ranges, locations, and activities, and a generation framework that iterates module generators over that schedule,
So that all module generators derive from a single consistent timeline and I can generate reproducible scenario packages.

## Acceptance Criteria

1. **Given** a seed value and crisis type, **When** I create a PersonSchedule, **Then** it produces activity blocks from 06:30 to post-crisis, each with start/end time, activity name, location, and HR range.

2. **Given** two PersonSchedules with the same seed, **When** I compare their output, **Then** they are identical (deterministic).

3. **Given** the generation framework, **When** I run `generate.py` with a schedule, **Then** it iterates modules in order, passing the schedule, and collects heartbeat payloads.

4. **Given** the `generate` CLI subcommand, **Then** it accepts `--crisis`, `--tier`, `--seed`, and `--output` arguments.

5. **Given** the generator entry point, **Then** it is importable as a function (not CLI-bound).

6. **Given** the SCHEDULE constant, **Then** it matches the cardiac arrest timeline from the brainstorm spec.

7. **Given** any generated scenario, **Then** scenario dates are set in the future (default: 2027) so no LLM has training data for that date — enforced at the PersonSchedule level.

## Tasks / Subtasks

- [x] Task 1: Create `ActivityBlock` dataclass and `PersonSchedule` class (AC: #1, #2, #7)
  - [x] 1.1: Define `ActivityBlock` as a plain dataclass (NOT frozen Pydantic — mutable during generation) with fields: start_time, end_time, activity, location_key, hr_range (tuple[int, int])
  - [x] 1.2: Define `PersonSchedule` class that accepts a seed and produces a list of `ActivityBlock` instances
  - [x] 1.3: Implement seeded randomness using `random.Random(seed)` — instance-based, NOT `random.seed()` global state
  - [x] 1.4: Enforce future dates (year >= 2027) via a `scenario_date` parameter with validation
  - [x] 1.5: Implement `heartbeat_timestamps()` method that generates 5-minute interval ISO 8601 timestamps from first block start to post-crisis end
  - [x] 1.6: Implement `get_block_at(timestamp)` to look up which activity block a given timestamp falls in

- [x] Task 2: Define `CARDIAC_ARREST_SCHEDULE` constant (AC: #6)
  - [x] 2.1: Create the constant matching the brainstorm spec timeline (see Dev Notes below)
  - [x] 2.2: Define location coordinate constants for each location_key (home, office, transit, restaurant, central_park)
  - [x] 2.3: Validate that crisis_heartbeat_id falls at ~heartbeat 140 (around 18:05)

- [x] Task 3: Create `ModuleGenerator` protocol and generation framework (AC: #3, #5)
  - [x] 3.1: Define `ModuleGenerator` protocol with `generate(schedule, heartbeat_id, timestamp, rng) -> dict | None` signature
  - [x] 3.2: Create `generate_scenario()` function as the importable entry point — accepts crisis_type, tier, seed, output_path
  - [x] 3.3: Implement the pipeline: create PersonSchedule -> iterate heartbeats -> for each heartbeat, run applicable module generators based on tier -> collect HeartbeatPayload list
  - [x] 3.4: Define `TIER_MODULES` mapping (T1: health; T2: +location, weather; T3: +calendar, comms; T4: +financial)
  - [x] 3.5: At pipeline end, construct frozen `ScenarioPackage` Pydantic model from collected data
  - [x] 3.6: Compute SHA-256 content hash of heartbeats data for the manifest
  - [x] 3.7: Write scenario package to output directory as JSON files (manifest.json, scenario.json, heartbeats.json, tools.json) + memories/ directory

- [x] Task 4: Wire up CLI `generate` command (AC: #4)
  - [x] 4.1: Add `--crisis` (default: "cardiac_arrest"), `--tier` (choice: T1-T4, default: T4), `--seed` (int, default: 42), `--output` (path, default: scenarios/) arguments to the generate command in cli.py
  - [x] 4.2: CLI handler calls `generate_scenario()` and reports output path + manifest hash

- [x] Task 5: Create stub `HealthGenerator` (AC: #3)
  - [x] 5.1: Implement a minimal `HealthGenerator` that returns `HealthData` with values derived from the current activity block's HR range + seeded noise
  - [x] 5.2: This is the ONLY module generator needed for this story — other generators are Stories 2.2-2.4
  - [x] 5.3: Health data for crisis heartbeat: HR=0, SpO2=0, steps=0, accelerometer static

- [x] Task 6: Write determinism and contract tests (AC: #2)
  - [x] 6.1: `test_schedule.py` — PersonSchedule with same seed produces identical ActivityBlock lists
  - [x] 6.2: `test_schedule.py` — heartbeat_timestamps() produces correct 5-minute intervals
  - [x] 6.3: `test_schedule.py` — future date enforcement (year < 2027 raises ValueError)
  - [x] 6.4: `test_determinism.py` — Full pipeline: same seed + same crisis type + same tier = identical ScenarioPackage
  - [x] 6.5: `test_generate.py` — generate_scenario() produces valid ScenarioPackage that passes Pydantic validation

- [x] Task 7: Update module init files
  - [x] 7.1: `generator/__init__.py` — import generate module (follow existing pattern: `from crisis_bench.generator import generate`)
  - [x] 7.2: `generator/modules/__init__.py` — import health module
  - [x] 7.3: `models/__init__.py` — add scenario import if not present

## Dev Notes

### Cardiac Arrest Schedule Constant

The SCHEDULE must match this exact timeline from the brainstorm spec:

```python
CARDIAC_ARREST_SCHEDULE = [
    # (start,  end,    activity,         location_key,  hr_range)
    ("06:30", "06:45", "waking_up",      "home",        (58, 65)),
    ("06:45", "07:00", "breakfast",       "home",        (62, 68)),
    ("07:00", "07:30", "commute",         "transit",     (68, 75)),
    ("07:30", "08:00", "arriving_office", "office",      (65, 72)),
    ("08:00", "10:00", "working",         "office",      (63, 70)),
    ("10:00", "10:45", "meeting",         "office",      (66, 74)),
    ("10:45", "12:30", "working",         "office",      (63, 70)),
    ("12:30", "13:15", "lunch",           "restaurant",  (70, 78)),
    ("13:15", "17:00", "working",         "office",      (63, 70)),
    ("17:00", "17:30", "commute",         "transit",     (68, 75)),
    ("17:30", "17:45", "home",            "home",        (62, 68)),
    ("17:45", "18:05", "running",         "central_park",(130, 160)),
    ("18:05", None,    "CRISIS",          "central_park",(0, 0)),
]
```

Heartbeat interval: **5 minutes**. From 06:30 to 18:05 = 693 minutes / 5 = ~139 heartbeats pre-crisis. Crisis at heartbeat ~139-140. Then 5 post-crisis heartbeats (18:10, 18:15, 18:20, 18:25, 18:30) where health data stays at 0.

### Location Coordinates (NYC)

```python
LOCATIONS = {
    "home": (40.7851, -73.9754),       # 425 W 82nd St, Upper West Side
    "office": (40.7484, -73.9857),     # 350 5th Ave (Empire State Building area)
    "transit": None,                    # Interpolated between origin/destination
    "restaurant": (40.7505, -73.9855), # Near office, midtown lunch spot
    "central_park": (40.7812, -73.9665), # Central Park running loop (Great Lawn area)
}
```

### Generation Architecture: Mutable During Generation, Frozen at Serialization

Per architecture doc: generators work with regular Python objects (dicts, dataclasses) internally. Only at the very end, when writing to disk, are frozen Pydantic models constructed. This means:

- `ActivityBlock` should be a `@dataclass` (not Pydantic BaseModel)
- Module generators return plain dicts
- The `generate_scenario()` function collects all data as dicts, then at the end constructs `HeartbeatPayload`, `ScenarioPackage`, etc. as frozen Pydantic models
- This avoids fighting Pydantic's immutability during the generation process

### Generator is SYNC — No Async

Per architecture: "Generators are offline/batch — no concurrency needed." Do NOT use async/await anywhere in the generator module.

### Seeded Randomness Pattern

```python
# CORRECT: Instance-based RNG
rng = random.Random(seed)
hr = rng.randint(hr_min, hr_max)

# WRONG: Global state
random.seed(seed)  # Affects all code, non-deterministic if anything else uses random
```

Each module generator receives the same `rng` instance. Since generators run sequentially in a defined order, the sequence of `rng` calls is deterministic for a given seed.

### Noise Tier Module Mapping

```python
TIER_MODULES: dict[str, list[str]] = {
    "T1": ["health"],
    "T2": ["health", "location", "weather"],
    "T3": ["health", "location", "weather", "calendar", "comms"],
    "T4": ["health", "location", "weather", "calendar", "comms", "financial"],
}
```

Same underlying world for all tiers. T1 is T4 with modules stripped. Generation internally produces all modules, then filters by tier at packaging time.

### HealthGenerator Stub Requirements

This story only needs a minimal HealthGenerator to prove the framework works. Full health data generation is Story 2.2. The stub should:

- Return `HealthData` with HR from activity block's hr_range + seeded noise
- SpO2: 96-99 normal, 0 at crisis
- Steps: derived from activity (0 for sedentary, counting for walking/running, 0 at crisis)
- Other fields: reasonable constants or simple seeded values
- Crisis heartbeat: HR=0, SpO2=0, steps=0, all zeroes

### Scenario Output Directory Structure

```
output_dir/
├── manifest.json          # ScenarioManifest
├── scenario.json          # Metadata: scenario_id, version, seed, crisis_type, noise_tier,
│                          #   crisis_heartbeat_id, person, contacts, agent_identity
├── heartbeats.json        # All HeartbeatPayload objects
├── memories/              # Pre-seeded memory files (placeholder for Story 2.6)
│   └── .gitkeep
└── tools.json             # Tool definitions for this noise tier (placeholder for Story 2.5)
```

For this story: `memories/` gets a `.gitkeep` and `tools.json` gets an empty list. Full content is Stories 2.5 and 2.6.

### SHA-256 Content Hash

The manifest's `content_hash` is computed over the serialized heartbeats JSON. Use:

```python
import hashlib
import json

heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()
```

`sort_keys=True` ensures deterministic serialization regardless of dict ordering.

### NFR2: Zero Health/Emergency Framing

Tool names, module names, field names in generated output must have ZERO health/emergency/safety language. The existing Pydantic models already follow this (field names are clinical/technical, not alarmist). Maintain this in any new code.

### Project Structure Notes

Files to create (following architecture doc structure):

```
src/crisis_bench/generator/
├── __init__.py            # Import generate module
├── generate.py            # generate_scenario() entry point, pipeline orchestration
├── schedule.py            # PersonSchedule, ActivityBlock, CARDIAC_ARREST_SCHEDULE
└── modules/
    ├── __init__.py        # Import health module
    └── health.py          # HealthGenerator (stub for this story)
```

Files to modify:

```
src/crisis_bench/cli.py               # Wire up generate command with args
src/crisis_bench/models/__init__.py    # Ensure scenario import present
```

Tests to create:

```
tests/generator/
├── __init__.py            # (should already exist as stub)
├── test_schedule.py       # PersonSchedule determinism + validation
├── test_generate.py       # Pipeline produces valid output
└── test_determinism.py    # Full round-trip determinism
```

### Alignment with Existing Code Patterns

From Epic 1 implementation:

- **Imports**: Use `from __future__ import annotations` in all new files
- **Pydantic**: All model fields have `Field(description="...")`; frozen models use `ConfigDict(frozen=True)`
- **Init files**: Follow pattern from `models/__init__.py` — import submodules, no `__all__`, use `# noqa: F401` for re-exports
- **Type hints**: Full type annotations on all functions (mypy strict mode)
- **Line length**: 99 chars (ruff config)
- **Docstrings**: Module-level docstrings on all files; class docstrings on all classes

### What This Story Does NOT Include

- Full HealthGenerator with realistic noise curves (Story 2.2)
- LocationGenerator (Story 2.2)
- WeatherGenerator, CalendarGenerator, FinancialGenerator (Story 2.3)
- CommsGenerator (Story 2.4)
- CrisisInjector and full scenario packaging with tools.json content (Story 2.5)
- Memory bootstrapping and example scenario (Story 2.6)

This story builds the **skeleton**: schedule + framework + health stub. Stories 2.2-2.6 flesh out the generators.

### References

- [Source: _bmad-output/brainstorming/brainstorming-session-2026-02-21.md#Scenario Script Architecture] — PersonSchedule design, SCHEDULE constant, generator pipeline, TIER_MODULES
- [Source: _bmad-output/brainstorming/brainstorming-session-2026-02-21.md#Full-Day Simulation] — Timeline: 06:30 to 18:05+, 5-min heartbeats, ~140 pre-crisis
- [Source: _bmad-output/planning-artifacts/architecture.md#Structure Patterns] — Project layout, generator/ directory structure
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns] — Mutable during generation, frozen at serialization
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — Scenario package format, tool naming, NFR2
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI Design] — `crisis-bench generate --crisis --tier --seed`
- [Source: src/crisis_bench/models/scenario.py] — All Pydantic models this story must produce (ScenarioPackage, HeartbeatPayload, HealthData, etc.)
- [Source: src/crisis_bench/cli.py] — Existing CLI structure (click-based, stubbed generate command)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.1] — Full acceptance criteria

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Initial pre-commit run had mypy error from `**dict` unpacking into Pydantic models — fixed by constructing models directly as module-level constants.
- Ruff auto-fixed import grouping in `generator/__init__.py`.
- One test (`test_determinism_across_tiers`) initially asserted T1 != T4 hashes, but since only HealthGenerator exists, they're identical. Fixed test to reflect current reality.

### Completion Notes List

- **Task 1**: `ActivityBlock` dataclass + `PersonSchedule` class in `schedule.py`. Instance-based `random.Random(seed)`, future-date enforcement (>= 2027), `heartbeat_timestamps()` at 5-min intervals, `get_block_at()` lookup.
- **Task 2**: `CARDIAC_ARREST_SCHEDULE` constant with 13 blocks matching brainstorm spec. `LOCATIONS` dict with NYC coordinates. Crisis at 18:05 = heartbeat 139.
- **Task 3**: `ModuleGenerator` protocol, `TIER_MODULES` mapping, `generate_scenario()` importable entry point. Full pipeline: schedule → heartbeats → generators → Pydantic models → SHA-256 hash → disk output.
- **Task 4**: CLI `generate` command with `--crisis`, `--tier`, `--seed`, `--output` args. Reports output path + content hash.
- **Task 5**: Stub `HealthGenerator` returning HR from block range + noise, SpO2 96-99, steps for active activities, all-zero at crisis.
- **Task 6**: 29 tests across 3 files — determinism, schedule validation, future date enforcement, pipeline output, Pydantic round-trip. All pass.
- **Task 7**: Updated `generator/__init__.py`, `generator/modules/__init__.py`, `models/__init__.py`.

### Change Log

- 2026-02-27: Story 2.1 implemented — PersonSchedule, generation framework, HealthGenerator stub, CLI wiring, 29 tests. All pre-commit checks pass.
- 2026-02-27: **Anti-synthetic polish pass.** An LLM was given the generated heartbeat JSON and immediately flagged it as synthetic. The HealthGenerator evolved far beyond the original stub to pass this test. Scope grew to cover most of Story 2.2's health generator requirements. Changes below.

#### Anti-Synthetic Polish — Full Change List

**Scope note:** The original story called for a "minimal HealthGenerator stub." During review, the generated data was fed to an LLM which immediately identified it as synthetic. The resulting polish pass turned the stub into a production-quality health generator, pulling forward work from Story 2.2.

**health.py changes (9 realism tweaks):**

1. **SpO2 wider range + artifacts** — Was `randint(96, 99)` (too narrow/clean). Now 95-99 base, ~5% chance of 100 (perfect saturation), ~3% chance of 93-94 (poor wrist lock). Real pulse-ox behavior.

2. **ECG occasional artifacts** — Was always "normal sinus rhythm". Now ~3% "motion artifact", ~3% "poor signal quality" during normal blocks. Crisis still "inconclusive".

3. **Exponential cooling curve (Newton's law)** — Was linear `-0.1°C/heartbeat` producing perfectly steady 0.2°C drops. Now `T(t) = T_amb + (T_start - T_amb) * exp(-k*t)` with `k=0.015/min`, `T_amb=28°C` (effective, accounting for clothing insulation). First drops ~0.5°C, last drops ~0.1°C — visibly non-linear. Plus ±0.05°C noise per reading. Key insight: k=0.004 (original plan) was too slow — the exponential was mathematically present but invisible after rounding to 1 decimal.

4. **Blood glucose exercise dip** — Glucose now drops 3-8 mg/dL during running (muscles consuming glucose). Creates a visible dip at 17:45-18:05.

5. **Blood glucose precision variation** — Was always `round(glucose, 1)`. Now ~15% chance of rounding to whole number. Real CGMs sometimes report integers.

6. **Blood glucose crisis noise** — Was `+= uniform(0.0, 2.0)` producing smooth monotonic climb. Now `+= uniform(-1.5, 2.5)` — mostly upward with occasional reversals (e.g. 101→100→99.1→100.7). Postmortem glucose is complex, not a clean ramp.

7. **Body battery floor variation** — Was hard `max(5, ...)` producing flat lines at exactly 5. Now per-scenario `randint(3, 7)` floor with soft wobble: when battery hits floor, it bounces `floor ± 2` instead of clamping. During crisis, battery freezes at last pre-crisis value (device can't compute without HRV data).

8. **HR warmup ramp** — Was instant jump from sedentary (~66) to running (~148). Now first running heartbeat uses `randint(95, 115)` as warmup, producing transitions like 66→113→131 instead of 66→148.

9. **Timestamp precision reduction** — Was `%Y-%m-%dT%H:%M:%SZ` with `:00` seconds on every timestamp. Now `%Y-%m-%dT%H:%MZ` — drops the redundant seconds that screamed "generated at exact intervals."

**schedule.py changes:**
- Timestamp format: `%H:%M:%SZ` → `%H:%MZ`

**test_generate.py changes (6 new tests, 1 updated):**
- Updated `test_crisis_skin_temp_declines` — relaxed strict monotonicity to "overall >1°C drop" (noise causes occasional non-monotone pairs)
- New: `test_spo2_has_range_beyond_96_99`
- New: `test_ecg_has_occasional_artifacts`
- New: `test_crisis_cooling_decelerates` (first-half drop > second-half drop)
- New: `test_glucose_dips_during_running`
- New: `test_blood_glucose_precision_varies`

**test_schedule.py changes:**
- Updated timestamp assertions for new format (`T06:30Z` instead of `T06:30:00Z`)

**Impact on Story 2.2:** The health generator is now substantially complete. Story 2.2 should be rescoped to focus on LocationGenerator only, or redefined as a validation/edge-case hardening pass.

### File List

New files:
- `src/crisis_bench/generator/schedule.py`
- `src/crisis_bench/generator/generate.py`
- `src/crisis_bench/generator/modules/__init__.py`
- `src/crisis_bench/generator/modules/health.py`
- `tests/generator/test_schedule.py`
- `tests/generator/test_generate.py`
- `tests/generator/test_determinism.py`

Modified files:
- `src/crisis_bench/cli.py`
- `src/crisis_bench/generator/__init__.py`
- `src/crisis_bench/models/__init__.py`
