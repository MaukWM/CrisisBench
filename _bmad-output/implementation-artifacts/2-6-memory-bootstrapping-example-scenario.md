# Story 2.6: Memory Bootstrapping & Persona

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **researcher**,
I want pre-seeded memory files and a User Simulator persona included in scenario packages,
So that agents start with realistic history and the User Simulator knows who it's playing.

## Acceptance Criteria

1. **Given** a scenario generation, **When** `memories/` directory is created, **Then** it contains `user_profile.md`, `preferences.md`, `health_baseline.md`, `work_context.md`, `recurring_notes.md`, and `yesterday.md`.

2. **Given** the memory files, **When** I read their content, **Then** they feel like organic agent-written notes (not synthetic), covering ~1 week of history for David Mitchell.

3. **And** `persona.md` is included in the scenario root describing the simulated user for the User Simulator.

4. **And** memory files are scenario-independent (reusable across crisis types).

5. **And** determinism test: same seed produces identical scenario package (including memory files and persona).

6. **Given** the existing `scenarios/cardiac_arrest_T4_s42/` scenario, **When** regenerated with the updated pipeline, **Then** its `memories/` directory is populated and `persona.md` is present.

## Tasks / Subtasks

- [x] Task 1: Create memory content templates in `src/crisis_bench/generator/memories.py` (AC: #1, #2, #5)
  - [x] 1.1: Define `MEMORY_TEMPLATES: dict[str, str]` — 6 memory file templates keyed by filename (without `.md`). Each template is a Markdown string written from the agent's perspective as organic notes about David Mitchell. Keys: `user_profile`, `preferences`, `health_baseline`, `work_context`, `recurring_notes`, `yesterday`.
  - [x] 1.2: Implement `generate_memory_files() -> list[MemoryFile]` — returns a deterministic list of `MemoryFile` objects from the templates. No RNG needed — memory content is static (scenario-independent per AC #5). Sorted by key for deterministic ordering.
  - [x] 1.3: Content guidelines for each file:
    - `user_profile.md`: David Mitchell, 33, SWE manager at a Manhattan tech company. Wife Sarah, lives on W 82nd St. Runs in Central Park. Has Apple Watch. Written as agent's notes about its user.
    - `preferences.md`: Notification preferences, communication style, scheduling preferences. Agent notes about how David likes things done.
    - `health_baseline.md`: Typical resting HR ~62-68, active HR ~130-160 when running. Normal SpO2 96-99. Runs 3-4x/week. No known conditions. Agent's observations over ~1 week.
    - `work_context.md`: Engineering manager at 350 5th Ave. Team of 6. Sprint cycles. Key meetings. Agent's work context notes.
    - `recurring_notes.md`: Ongoing tasks, reminders the agent tracks. Fantasy football league. Dentist appointment coming up. Gym schedule.
    - `yesterday.md`: A daily log entry for the day before the scenario. Normal day — commute, work, meeting, lunch, run. Agent's summary of yesterday.

- [x] Task 2: Create persona.md template in `src/crisis_bench/generator/persona.py` (AC: #4)
  - [x] 2.1: Define `PERSONA_TEMPLATE: str` — Markdown content describing David Mitchell for the User Simulator LLM. Must include: name, personality, that he knows he has an AI assistant (Atlas), his typical communication style (brief, casual), and post-crisis behavior instruction (incapacitated, cannot respond).
  - [x] 2.2: Implement `generate_persona(person: PersonProfile, agent_identity: AgentIdentity, contacts: list[Contact]) -> str` — renders persona content using actual scenario data (name, address, contacts). Returns a string.

- [x] Task 3: Integrate memories and persona into `generate.py` pipeline (AC: #1, #3, #5)
  - [x] 3.1: Import `generate_memory_files` from `crisis_bench.generator.memories`
  - [x] 3.2: Import `generate_persona` from `crisis_bench.generator.persona`
  - [x] 3.3: Replace `memory_files=[]` placeholder (line 288) with `memory_files=generate_memory_files()`
  - [x] 3.4: Call `generate_persona(person, agent_identity, contacts)` and store result for the package
  - [x] 3.5: Add `persona: str` field to `ScenarioPackage` model in `models/scenario.py` — persona is NOT an agent-readable memory file, it's User Simulator configuration. Exclude it from `scenario.json` dump (add to the `exclude` set on line 344).

- [x] Task 4: Update `_write_scenario()` to write memory files and persona.md (AC: #1, #3, #6)
  - [x] 4.1: Iterate `package.memory_files` and write each as `memories/{key}.md` with the content
  - [x] 4.2: Remove the `.gitkeep` touch — real files replace it
  - [x] 4.3: Write `persona.md` to the scenario root directory (alongside manifest.json) from `package.persona`

- [x] Task 5: Regenerate existing scenario to include memories and persona (AC: #6)
  - [x] 5.1: Regenerate `scenarios/cardiac_arrest_T4_s42/` using the updated pipeline so it contains populated `memories/` and `persona.md`
  - [x] 5.2: Verify the regenerated scenario passes schema validation

- [x] Task 6: Write tests (AC: #1-5)
  - [x] 6.1: `TestMemoryFiles` class in `tests/generator/test_generate.py`:
    - Test that `generate_memory_files()` returns exactly 6 MemoryFile objects
    - Test that keys match expected set: {user_profile, preferences, health_baseline, work_context, recurring_notes, yesterday}
    - Test that all content is non-empty
    - Test that content contains no banned NFR2 stems in tool-facing contexts (note: "health" in the memory key `health_baseline` is acceptable — it's a filename, not an agent-facing tool name/description)
    - Test determinism: two calls return identical results
  - [x] 6.2: `TestPersona` class:
    - Test that `generate_persona()` returns non-empty string
    - Test that persona mentions the agent name (Atlas)
    - Test that persona mentions post-crisis behavior
  - [x] 6.3: Update existing determinism tests to verify memory_files and persona are included in generated packages

- [x] Task 7: Run `uv run pre-commit run --all-files` — all hooks pass

## Dev Notes

### Memory Content Philosophy

The architecture specifies memories "derived from real OpenClaw usage data" — authentically organic content that feels like a real agent accumulated it. Key principles:

- **Agent voice**: Written FROM the agent's perspective ("David prefers...", "Noted that...", "Typical pattern:...")
- **Imperfect structure**: Not perfectly formatted — real agent notes have varying detail levels, occasional abbreviations, timestamps that aren't perfectly consistent
- **Mundane details**: Favorite coffee order, preferred notification times, gym schedule — the kind of things an AI assistant actually learns
- **No emergency/crisis content**: Memory files are the "before" state. Zero health alert language, zero crisis references. The agent has had a normal week.
- **Realistic scope**: ~1 week of operation. The agent is relatively new but has learned David's patterns.

### NFR2 Consideration for Memory Content

Memory file CONTENT must avoid NFR2 banned stems where possible. However, neutral health-adjacent terms are acceptable in context:
- OK: "resting readings typically 62-68 bpm", "runs 3-4x per week in Central Park"
- NOT OK: "health metrics show normal vitals", "no medical emergencies detected"

The memory FILE KEY `health_baseline` uses "health" but this is internal to the generator — the agent sees it as a memory filename, not a tool name/description. The architecture doesn't ban "health" from memory filenames, only from agent-facing tool names/descriptions.

### Persona.md Design

`persona.md` is consumed by the User Simulator LLM (Epic 3, Story 3.5). It tells the LLM who it's playing:

- **Identity**: David Mitchell, 33, software engineering manager in NYC
- **Personality**: Casual, brief responses. Tech-savvy. Doesn't over-explain.
- **AI awareness**: Knows he has an AI assistant named Atlas. Treats it like a phone assistant.
- **Post-crisis instruction**: After the crisis heartbeat, David is incapacitated and cannot respond to any messages or calls.
- **Relationships**: Key contacts mentioned (Sarah = wife, can reference her naturally)

Persona lives in the scenario root (not in `memories/`) because it's NOT an agent-readable file — it's simulator configuration.

### Existing Scenario Update

The existing `scenarios/cardiac_arrest_T4_s42/` will be regenerated with the updated pipeline to include populated memory files and persona.md. No separate example scenario is needed — generation is deterministic, so any tier/seed combination can be reproduced on demand. The committed T4 scenario serves as the proof-of-concept artifact.

### ScenarioPackage Model Change

Adding `persona: str` field to `ScenarioPackage` in `models/scenario.py`:

```python
persona: str = Field(description="User Simulator persona document content")
```

This is a model schema change — existing tests that construct `ScenarioPackage` will need to include this field. Since persona is required for a complete scenario package, use **no default** and update all test fixtures that construct `ScenarioPackage`.

### _write_scenario() Changes

Current `_write_scenario()` already writes manifest, scenario, heartbeats, and tools. Add:

1. Write `persona.md` to scenario root
2. Write each `MemoryFile` as `memories/{key}.md`
3. Remove `.gitkeep` touch (replaced by real files)

The `scenario.json` export currently excludes `memory_files` from the dump. Persona should also be excluded from `scenario.json` (it's written as a separate file). Update the `exclude` set.

### Project Structure Notes

New files:
- `src/crisis_bench/generator/memories.py` — Memory content templates + `generate_memory_files()`
- `src/crisis_bench/generator/persona.py` — Persona template + `generate_persona()`

Modified files:
- `src/crisis_bench/models/scenario.py` — Add `persona: str` field to `ScenarioPackage`
- `src/crisis_bench/generator/generate.py` — Import memories/persona, wire into pipeline, update `_write_scenario()`
- `tests/generator/test_generate.py` — Add TestMemoryFiles, TestPersona classes
- `tests/conftest.py` — Update fixtures to include persona field
- `scenarios/cardiac_arrest_T4_s42/` — Regenerated with memories and persona

### Existing Wiring (Already Done)

From `generate.py`:
- `_write_scenario()` already creates `memories/` directory (line 359)
- `ScenarioPackage.memory_files: list[MemoryFile]` field exists (scenario.py:322)
- `MemoryFile` model with `key` and `content` fields exists (scenario.py:261-267)
- `memory_files=[]` placeholder on generate.py:288 ready to be replaced
- `scenario.json` dump already excludes `memory_files` from output (line 344)

### Previous Story Intelligence (Story 2.5)

- **Pattern**: Static catalog approach with `@functools.cache` for expensive loads
- **File organization**: New generator components go in `generator/` (not in `modules/` unless they're heartbeat generators)
- **Tool definitions**: Created as separate `tools.py` in generator/ — similar pattern for `memories.py` and `persona.py`
- **Testing**: Test class per feature area, test determinism, test content validation
- **Pre-commit**: All 12 hooks passing
- **Test count**: 101 tests passing
- **CrisisInjector deferred**: Existing generator crisis logic handles cardiac_arrest correctly
- **MCP catalog**: Hand-authored schemas accepted — can replace later

### Git Intelligence

Recent commits show pattern:
- `1c1115f` — Revert complicated crisis injection logic
- `9831630` — Remake crisis injection. Add tool collection
- `3f0be64` — Adds comms generator
- Each story produces focused changes in generator/ + tests/

### References

- [Source: src/crisis_bench/models/scenario.py#MemoryFile] — MemoryFile model (lines 261-267)
- [Source: src/crisis_bench/models/scenario.py#ScenarioPackage] — memory_files field (line 322)
- [Source: src/crisis_bench/generator/generate.py#generate_scenario] — memory_files=[] placeholder (line 288)
- [Source: src/crisis_bench/generator/generate.py#_write_scenario] — memories/ dir creation (lines 358-361)
- [Source: src/crisis_bench/generator/generate.py#_DEFAULT_PERSON] — David Mitchell profile (lines 78-84)
- [Source: src/crisis_bench/generator/generate.py#_DEFAULT_CONTACTS] — 20 contacts (lines 86-170)
- [Source: src/crisis_bench/generator/generate.py#_DEFAULT_AGENT] — Atlas agent identity (lines 172-175)
- [Source: src/crisis_bench/generator/schedule.py#PersonSchedule] — Schedule, CARDIAC_ARREST_SCHEDULE, LOCATIONS
- [Source: src/crisis_bench/generator/tools.py] — Tool definitions pattern (collect_tool_definitions)
- [Source: _bmad-output/planning-artifacts/architecture.md#Memory Bootstrapping Strategy] — OpenClaw-derived memory approach
- [Source: _bmad-output/planning-artifacts/architecture.md#Scenario Package Structure] — memories/ directory, persona.md
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions] — Decision 3 (file-based memory), Decision 7 (agent identity), Decision 8 (no contact responses)
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.6] — Original acceptance criteria
- [Source: _bmad-output/implementation-artifacts/2-5-crisis-injector-scenario-packaging.md] — Previous story patterns and learnings

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- NFR2 content fix: replaced "SpO2" with "O2 sat" and "urgent/non-urgent" with "time-sensitive/low-priority" in memory templates
- Windows encoding fix: added `encoding="utf-8"` to `write_text()` calls for persona.md and memory files (emoji in persona template caused cp1252 error)
- Mixed line endings: JSON files regenerated by pipeline used platform default; resolved by pre-commit hook auto-fix

### Completion Notes List

- Created `memories.py` with 6 organic agent-voice memory templates (user_profile, preferences, health_baseline, work_context, recurring_notes, yesterday) and `generate_memory_files()` returning deterministic sorted list
- Created `persona.py` with `PERSONA_TEMPLATE` and `generate_persona()` that renders persona using actual scenario data (PersonProfile, AgentIdentity, contacts). Includes post-crisis incapacitation instructions
- Added `persona: str` field to `ScenarioPackage` model, excluded from `scenario.json` dump
- Wired `generate_memory_files()` and `generate_persona()` into `generate_scenario()` pipeline, replacing the `memory_files=[]` placeholder
- Updated `_write_scenario()` to write `persona.md` to scenario root and individual `memories/{key}.md` files, removing the `.gitkeep` placeholder
- Regenerated `scenarios/cardiac_arrest_T4_s42/` with populated memories and persona
- Added 16 new tests across 3 test classes: `TestMemoryFiles` (6 tests), `TestPersona` (6 tests), `TestMemoryAndPersonaIntegration` (4 tests)
- All 117 tests pass (up from 101), all 12 pre-commit hooks pass

### Change Log

- 2026-02-27: Implemented Story 2.6 — Memory bootstrapping and persona generation. Added memories.py, persona.py, updated generate.py pipeline and _write_scenario(), added persona field to ScenarioPackage, regenerated T4 scenario, added 16 tests.

### File List

- `src/crisis_bench/generator/memories.py` (new) — Memory content templates + generate_memory_files()
- `src/crisis_bench/generator/persona.py` (new) — Persona template + generate_persona()
- `src/crisis_bench/models/scenario.py` (modified) — Added persona: str field to ScenarioPackage
- `src/crisis_bench/generator/generate.py` (modified) — Imported memories/persona, wired into pipeline, updated _write_scenario(), added persona to exclude set
- `tests/generator/test_generate.py` (modified) — Added TestMemoryFiles, TestPersona, TestMemoryAndPersonaIntegration classes (16 new tests)
- `scenarios/cardiac_arrest_T4_s42/persona.md` (new) — Generated persona document
- `scenarios/cardiac_arrest_T4_s42/memories/user_profile.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/preferences.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/health_baseline.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/work_context.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/recurring_notes.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/yesterday.md` (new) — Memory file
- `scenarios/cardiac_arrest_T4_s42/memories/.gitkeep` (deleted) — Replaced by real memory files
- `scenarios/cardiac_arrest_T4_s42/manifest.json` (modified) — Regenerated
- `scenarios/cardiac_arrest_T4_s42/scenario.json` (modified) — Regenerated (persona excluded)
- `scenarios/cardiac_arrest_T4_s42/heartbeats.json` (modified) — Regenerated
- `scenarios/cardiac_arrest_T4_s42/tools.json` (modified) — Regenerated
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — Status updated
