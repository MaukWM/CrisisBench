# Story 1.2: Scenario Data Models

Status: review

## Story

As a **researcher**,
I want validated schemas for scenario packages (manifest, person profile, contacts, heartbeat payloads, module data, memory files, tool definitions),
so that generated scenarios conform to a strict contract and can be validated before use.

## Acceptance Criteria

1. **Given** a scenario manifest dict **When** I construct a `ScenarioManifest` model **Then** it validates content_hash (SHA-256 format), generator_version, and timestamp fields

2. **Given** a heartbeat payload dict with module data **When** I construct a `HeartbeatPayload` model **Then** it validates heartbeat_id, timestamp, and all module data structures (health, location, weather, comms, calendar, financial)

3. **Given** a valid scenario model **When** I call `model.model_dump_json()` **Then** the output uses snake_case fields and is deterministic (frozen model)

4. **And** PersonProfile, Contact, ToolDefinition, MemoryFile, ScenarioPackage models are all defined

5. **And** all models use `ConfigDict(frozen=True)` for immutability

6. **And** all fields have `Field(description="...")` annotations

7. **And** unit tests validate serialization/deserialization round-trips

## Tasks / Subtasks

- [x] Task 1: Create module data models (AC: 2, 5, 6)
  - [x] 1.1: `HealthData` — 15 fields: heart_rate (int), spo2 (int), steps (int), skin_temp (float), accel_x/y/z (float), ecg_summary (str), blood_glucose (float), calories_burned (int), sleep_stage (str), hydration_est (float), stress_score (int), respiratory_rate (int), body_battery (int)
  - [x] 1.2: `LocationData` — 12 fields: lat (float), lon (float), altitude (float), speed (float), heading (int), accuracy (float), geofence_status (str), nearby_pois (list[str]), transit_nearby (str), last_known_address (str), distance_from_home (float), movement_classification (str)
  - [x] 1.3: `WeatherData` — 16 fields: temp (float), feels_like (float), humidity (int), wind_speed (float), wind_dir (str), uv_index (int), aqi (int), pollen_count (int), visibility (float), pressure (float), dew_point (float), cloud_cover (int), sunrise (str), sunset (str), forecast_next_3h (str), weather_alerts (list[str])
  - [x] 1.4: `CalendarEvent` + `Reminder` + `CalendarData` — events with title/time/location/attendees, reminders with text/time, today_summary (str)
  - [x] 1.5: `Email` + `SlackMessage` + `Sms` + `SocialNotification` + `CommsData` — unread_emails, slack_messages, missed_calls (int), voicemail_count (int), sms, social_notifications
  - [x] 1.6: `Transaction` + `PendingCharge` + `StockQuote` + `CryptoPrice` + `FinancialData` — last_3_transactions, account_balance (float), pending_charges, stock_watchlist, crypto_prices, spending_vs_budget (str)

- [x] Task 2: Create core scenario models (AC: 1, 3, 4, 5, 6)
  - [x] 2.1: `PersonProfile` — name (str), age (int), occupation (str), home_address (str), office_address (str)
  - [x] 2.2: `Contact` — id (str), name (str), relationship (str), phone (str)
  - [x] 2.3: `AgentIdentity` — name (str)
  - [x] 2.4: `ToolParameter` + `ToolDefinition` — name (str), description (str), parameters (list of ToolParameter with name/type/description/required)
  - [x] 2.5: `MemoryFile` — key (str), content (str)
  - [x] 2.6: `HeartbeatPayload` — heartbeat_id (int), timestamp (str as ISO 8601), modules dict with Optional module data per tier: health (HealthData | None), location (LocationData | None), weather (WeatherData | None), calendar (CalendarData | None), comms (CommsData | None), financial (FinancialData | None)
  - [x] 2.7: `ScenarioManifest` — content_hash (str, validated SHA-256 hex), generator_version (str), generated_at (str as ISO 8601 timestamp)
  - [x] 2.8: `ScenarioPackage` — scenario_id (str), version (str), seed (int), crisis_type (str), noise_tier (Literal["T1","T2","T3","T4"]), crisis_heartbeat_id (int), person (PersonProfile), contacts (list[Contact]), agent_identity (AgentIdentity), heartbeats (list[HeartbeatPayload]), tool_definitions (list[ToolDefinition]), memory_files (list[MemoryFile]), manifest (ScenarioManifest)

- [x] Task 3: Re-export from models/__init__.py (AC: 4)
  - [x] 3.1: Add public imports in `src/crisis_bench/models/__init__.py` — re-export all models from scenario.py via `__all__`

- [x] Task 4: Write unit tests (AC: 7)
  - [x] 4.1: `tests/models/test_scenario.py` — test construction from valid dicts for every model
  - [x] 4.2: Round-trip test — construct model → model_dump_json() → model_validate_json() → assert equality
  - [x] 4.3: Frozen immutability test — attempt attribute assignment, assert ValidationError
  - [x] 4.4: Validation failure tests — invalid SHA-256 hash, missing required fields, wrong types
  - [x] 4.5: Tier-awareness test — HeartbeatPayload with only health (T1) vs all modules (T4), both valid
  - [x] 4.6: snake_case serialization test — dump to JSON, assert no camelCase keys

- [x] Task 5: Verify quality gates (AC: all)
  - [x] 5.1: Run `pre-commit run --all-files` — all 12 hooks pass
  - [x] 5.2: Run `pytest tests/models/test_scenario.py -v` — 50 tests pass
  - [x] 5.3: Run `python -c "from crisis_bench.models import ScenarioPackage, HeartbeatPayload"` — imports work

## Dev Notes

### Architecture Requirements
[Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns]

**Pydantic Model Conventions (MUST follow):**
- `model_config = ConfigDict(frozen=True)` on ALL models — these are published artifacts, immutable once created
- `Field(description="...")` on ALL fields — descriptions may end up in tool schemas
- snake_case JSON fields throughout, never camelCase
- Use Pydantic v2 API (`model_config = ConfigDict(...)`, not old `class Config`)

**Model Location:** `src/crisis_bench/models/scenario.py`
[Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]

The architecture specifies this single file contains: ScenarioManifest, PersonProfile, Contact, HeartbeatPayload, ModuleData, MemoryFile, ToolDefinition, ScenarioPackage.

**SHA-256 Validation:** ScenarioManifest.content_hash must be validated as a hex SHA-256 string (64 hex chars). Use a Pydantic field_validator.

**Noise Tier Semantics:**
- T1: health only
- T2: health + location + weather
- T3: health + location + weather + calendar + comms
- T4: all modules (health + location + weather + calendar + comms + financial)

HeartbeatPayload module fields are all `Optional` — tier determines which are present. The model does NOT enforce tier logic (that's the generator's job, Story 2.x). The model just validates that present data conforms to the schema.

### Module Data Field Reference
[Source: _bmad-output/brainstorming/brainstorming-session-2026-02-21.md]

**HealthData (15 fields):**
heart_rate, spo2, steps, skin_temp, accel_x, accel_y, accel_z, ecg_summary, blood_glucose, calories_burned, sleep_stage, hydration_est, stress_score, respiratory_rate, body_battery

**LocationData (12 fields):**
lat, lon, altitude, speed, heading, accuracy, geofence_status, nearby_pois (list[str]), transit_nearby, last_known_address, distance_from_home, movement_classification

**WeatherData (16 fields):**
temp, feels_like, humidity, wind_speed, wind_dir, uv_index, aqi, pollen_count, visibility, pressure, dew_point, cloud_cover, sunrise, sunset, forecast_next_3h, weather_alerts (list[str])

**CalendarData:** next_3_events (list of CalendarEvent with title/time/location/attendees), reminders (list of Reminder with text/time), today_summary

**CommsData:** unread_emails (list of Email with sender/subject), slack_messages (list of SlackMessage with channel/sender/message), missed_calls (int), voicemail_count (int), sms (list of Sms with sender/message), social_notifications (list of SocialNotification with platform/notification_text)

**FinancialData:** last_3_transactions (list of Transaction with merchant/amount/category), account_balance (float), pending_charges (list of PendingCharge with merchant/amount), stock_watchlist (list of StockQuote with symbol/price), crypto_prices (list of CryptoPrice with symbol/price), spending_vs_budget (str)

### NFR2 Compliance (CRITICAL)
[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions]

Zero health/emergency/safety framing in field names, model names, or descriptions. Field names like `heart_rate` and `spo2` are fine (they're device sensor names). Do NOT use names like `emergency_data`, `crisis_indicator`, `health_alert`, etc.

### Previous Story Learnings (Story 1.1)
[Source: _bmad-output/implementation-artifacts/1-1-project-scaffolding-quality-gates.md]

- mypy strict mode is active. All functions need return types, all params need type annotations.
- `# type: ignore[misc]` was needed for Click decorators but should NOT be needed for Pydantic models — Pydantic has excellent mypy support.
- ruff line-length is 99 chars.
- Pre-commit includes mypy with `--ignore-missing-imports` flag.
- hatchling build with `packages = ["src/crisis_bench"]`.

### Critical Anti-Patterns to Avoid
- Do NOT add mutable models — everything in scenario.py is frozen (published artifacts)
- Do NOT add generator logic — this is data contracts only, no PersonSchedule or generation code
- Do NOT add runtime models (ToolCall, ToolResponse, Transcript) — that's Story 1.3
- Do NOT add scoring models — that's Story 1.4
- Do NOT enforce tier logic in HeartbeatPayload — module fields are Optional, generator handles tier rules
- Do NOT use `from __future__ import annotations` in files with Pydantic models that use `model_validator` or `field_validator` — it can break Pydantic v2 validators at runtime (deferred annotation evaluation). Use explicit type annotations instead.
- Do NOT use Pydantic v1 API (`class Config:`, `.dict()`, `.json()`) — use v2 API (`model_config = ConfigDict(...)`, `.model_dump()`, `.model_dump_json()`)

### Project Structure Notes

- File goes in `src/crisis_bench/models/scenario.py` (architecture-specified)
- Tests go in `tests/models/test_scenario.py` (mirrors src structure)
- Re-exports go in `src/crisis_bench/models/__init__.py` (existing file, currently just a docstring)
- No new files outside these three locations

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns]
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2]
- [Source: _bmad-output/brainstorming/brainstorming-session-2026-02-21.md — Module field specs]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- `from __future__ import annotations` in test file caused `NameError` at collection time — parametrize decorator evaluates class references at class body execution, deferred annotations made them strings. Removed the import.
- Missing `PersonProfile` import in test file — added to import list.
- mypy pre-commit hook (mirrors-mypy) ran in isolated env without pydantic, causing "Class cannot subclass BaseModel (has type Any)" on all 25 models. Switched mypy to local hook (`uv run mypy src/`) running in project venv — matches pip-audit pattern. This also made the `# type: ignore[misc]` on Click decorators in cli.py unnecessary (Click types now available), so removed those too.

### Completion Notes List

- All 5 tasks with 24 subtasks completed
- 25 Pydantic v2 models in `src/crisis_bench/models/scenario.py`: 6 module data models (HealthData 15 fields, LocationData 12, WeatherData 16, CalendarData, CommsData, FinancialData) + 13 supporting models (CalendarEvent, Reminder, Email, SlackMessage, Sms, SocialNotification, Transaction, PendingCharge, StockQuote, CryptoPrice) + 6 core scenario models (PersonProfile, Contact, AgentIdentity, ToolParameter, ToolDefinition, MemoryFile, HeartbeatPayload, ScenarioManifest, ScenarioPackage)
- All models: ConfigDict(frozen=True), Field(description="...") on every field, snake_case throughout
- ScenarioManifest.content_hash validated via field_validator (64-char lowercase hex SHA-256)
- HeartbeatPayload: all 6 module fields Optional (None default) — tier logic is generator's job
- ScenarioPackage.noise_tier: Literal["T1","T2","T3","T4"]
- 25 models re-exported from models/__init__.py via __all__
- 50 tests in 6 test classes: Construction (26), RoundTrip (11 parametrized), Frozen (3), ValidationFailures (5), TierAwareness (3), SnakeCaseSerialization (2)
- Pre-commit: switched mypy from mirrors-mypy to local hook (uv run mypy src/) — resolves pydantic type availability
- Removed now-unnecessary `# type: ignore[misc]` from cli.py Click decorators
- All 12 pre-commit hooks pass, 50 tests pass, mypy clean

### File List

- `src/crisis_bench/models/scenario.py` (new)
- `src/crisis_bench/models/__init__.py` (modified)
- `src/crisis_bench/cli.py` (modified — removed unnecessary type: ignore comments)
- `.pre-commit-config.yaml` (modified — mypy switched to local hook)
- `tests/models/test_scenario.py` (new)

### Change Log

- 2026-02-25: Story 1.2 implemented — 25 Pydantic v2 scenario data models with 50 tests, mypy hook improved
