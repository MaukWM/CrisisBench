# Story 3.1: Orchestrator Shell & Scenario Loading

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **researcher**,
I want the orchestrator to load a scenario package, validate it, and iterate through heartbeats in sequence,
So that the execution engine has a working skeleton I can build handlers onto.

## Acceptance Criteria

1. **Given** a valid scenario package directory, **When** ScenarioLoader reads it, **Then** it validates manifest.json, scenario.json, heartbeats.json, and tools.json against Pydantic schemas.

2. **Given** an invalid scenario package (missing file, bad schema), **When** ScenarioLoader reads it, **Then** it raises a clear validation error before any execution starts.

3. **Given** a loaded scenario, **When** the orchestrator runs, **Then** it iterates heartbeats in order, logging each heartbeat_id via structlog at INFO level.

4. **And** the `run` CLI subcommand accepts `--scenario` and `--config` arguments.

5. **And** the runner entry point is importable as a function (`run_benchmark()`).

6. **And** RunConfig is loaded and validated from the config file.

7. **And** orchestrator tracks heartbeat count and detects crisis heartbeat from scenario metadata.

## Tasks / Subtasks

- [x] Task 1: Create `src/crisis_bench/runner/scenario_loader.py` — ScenarioLoader (AC: #1, #2)
  - [x] 1.1: Implement `load_scenario(scenario_dir: Path) -> ScenarioPackage` function that reads and reassembles a ScenarioPackage from the 6 on-disk files (manifest.json, scenario.json, heartbeats.json, tools.json, persona.md, memories/*.md). This is the inverse of `generator/generate.py::_write_scenario()`.
  - [x] 1.2: File existence checks — verify all required files exist before parsing. Raise `ScenarioLoadError(f"Missing required file: {filename}")` for any absent file. Required files: manifest.json, scenario.json, heartbeats.json, tools.json, persona.md. The `memories/` directory must exist and contain at least one `.md` file.
  - [x] 1.3: JSON parsing + Pydantic validation — parse each JSON file and validate:
    - `manifest.json` → `ScenarioManifest` (validates SHA-256 format via existing field_validator)
    - `scenario.json` → partial dict (scenario_id, version, seed, crisis_type, noise_tier, crisis_heartbeat_id, person→PersonProfile, contacts→list[Contact], agent_identity→AgentIdentity)
    - `heartbeats.json` → `list[HeartbeatPayload]`
    - `tools.json` → `list[ToolDefinition]`
    - `persona.md` → read as `str` (encoding="utf-8")
    - `memories/*.md` → `list[MemoryFile]` (key = stem of filename, content = file text)
  - [x] 1.4: Content hash verification — recompute SHA-256 of heartbeats JSON using the exact same method as the generator (`json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)`) and compare to `manifest.content_hash`. Raise `ScenarioLoadError` on mismatch.
  - [x] 1.5: Reassemble into `ScenarioPackage` — construct the frozen Pydantic model from all loaded components and return it.
  - [x] 1.6: Define `ScenarioLoadError(Exception)` in the same module — used for all loader errors (missing files, bad schema, hash mismatch).

- [x] Task 2: Create `src/crisis_bench/runner/orchestrator.py` — Orchestrator shell (AC: #3, #7)
  - [x] 2.1: Implement `class Orchestrator` with `__init__(self, scenario: ScenarioPackage, config: RunConfig)` storing scenario, config, and initializing structlog logger with `scenario_id` context.
  - [x] 2.2: Implement `async def run(self) -> None` — the main heartbeat loop:
    - Iterate `self.scenario.heartbeats` in order
    - For each heartbeat, log at INFO level: `log.info("heartbeat", heartbeat_id=hb.heartbeat_id, timestamp=hb.timestamp)`
    - Track `post_crisis_count` — increment after passing `scenario.crisis_heartbeat_id`
    - Stop after `config.max_post_crisis_heartbeats` post-crisis beats (break from loop)
    - Log at INFO level when crisis heartbeat is reached: `log.info("crisis_heartbeat_reached", heartbeat_id=...)`
    - Log at INFO level on run completion: `log.info("run_complete", total_heartbeats=count, post_crisis_heartbeats=post_crisis_count)`
  - [x] 2.3: The orchestrator does NOT call any model client, tool handlers, or transcript recorder in this story. Those are wired in Stories 3.2-3.7. The loop body is a placeholder for future `await self._process_heartbeat(hb)` calls.

- [x] Task 3: Create `src/crisis_bench/runner/run.py` — Runner entry point (AC: #4, #5, #6)
  - [x] 3.1: Implement `async def run_benchmark(scenario_path: Path, config_path: Path) -> None`:
    - Load RunConfig from `config_path` (read JSON, validate with `RunConfig(**json.loads(...)`)
    - Load scenario via `load_scenario(scenario_path)`
    - Create `Orchestrator(scenario, config)`
    - Call `await orchestrator.run()`
  - [x] 3.2: The function must be importable: `from crisis_bench.runner.run import run_benchmark`

- [x] Task 4: Update `src/crisis_bench/cli.py` — Wire `run` CLI subcommand (AC: #4)
  - [x] 4.1: Replace the current `run()` stub with a Click command accepting:
    - `--scenario` (required, type=click.Path(exists=True, path_type=Path)) — path to scenario package directory
    - `--config` (required, type=click.Path(exists=True, path_type=Path)) — path to runner_config.json
  - [x] 4.2: Call `asyncio.run(run_benchmark(scenario, config))` inside the command handler
  - [x] 4.3: Catch `ScenarioLoadError` and `pydantic.ValidationError`, echo the error message, and `raise SystemExit(1)`

- [x] Task 5: Update `src/crisis_bench/runner/__init__.py` (AC: #5)
  - [x] 5.1: Import `run` and `scenario_loader` submodules (follow project convention — no __all__ simplifications, just import the files)

- [x] Task 6: Create `tests/runner/` test directory with tests (AC: #1-7)
  - [x] 6.1: Create `tests/runner/__init__.py` (empty)
  - [x] 6.2: Create `tests/runner/test_scenario_loader.py`:
    - `test_load_valid_scenario` — load from `scenarios/cardiac_arrest_T4_s42/`, verify returns ScenarioPackage with correct scenario_id, crisis_type, noise_tier, heartbeat count, tool count, memory file count, persona non-empty
    - `test_load_validates_content_hash` — load valid scenario, verify content_hash matches recomputed hash
    - `test_load_missing_file_raises` — create a temp dir missing heartbeats.json, verify ScenarioLoadError
    - `test_load_bad_json_raises` — create a temp dir with malformed JSON in manifest.json, verify error
    - `test_load_hash_mismatch_raises` — create a scenario dir, tamper with heartbeats.json content, verify ScenarioLoadError on hash mismatch
    - `test_load_memory_files` — verify loaded MemoryFile keys match files in memories/ directory
    - `test_load_persona` — verify persona is loaded as non-empty string from persona.md
  - [x] 6.3: Create `tests/runner/test_orchestrator.py`:
    - `test_orchestrator_iterates_heartbeats` — construct Orchestrator with a small ScenarioPackage fixture (e.g., 5 heartbeats, crisis at heartbeat 3, max_post_crisis=1), run it, verify all expected heartbeats are processed via structlog capture
    - `test_orchestrator_respects_post_crisis_limit` — verify orchestrator stops after max_post_crisis_heartbeats (not all heartbeats in package)
    - `test_orchestrator_logs_crisis_detection` — verify INFO log when crisis heartbeat is reached
    - `test_orchestrator_logs_run_complete` — verify completion log with counts
  - [x] 6.4: Create `tests/runner/test_run.py`:
    - `test_run_benchmark_loads_config` — write a valid RunConfig JSON to tmp_path, load a real scenario, run run_benchmark, verify no errors
    - `test_run_benchmark_invalid_config_raises` — write invalid JSON config, verify ValidationError
  - [x] 6.5: Create test fixtures in `tests/conftest.py`:
    - `small_scenario_package` — a minimal ScenarioPackage fixture with ~5 heartbeats for fast unit tests (crisis at heartbeat 3)
    - `default_run_config` — a RunConfig fixture with sensible test defaults

- [x] Task 7: Run `uv run pre-commit run --all-files` — all hooks pass (AC: all)

## Dev Notes

### ScenarioLoader — Inverse of _write_scenario()

The generator writes scenarios to disk via `_write_scenario()` in `src/crisis_bench/generator/generate.py:339-371`. The ScenarioLoader must read them back. The exact on-disk format:

```
cardiac_arrest_T4_s42/
├── manifest.json          # ScenarioManifest.model_dump() as JSON
├── scenario.json          # ScenarioPackage.model_dump(exclude={heartbeats, tool_definitions, memory_files, persona, manifest})
├── heartbeats.json        # [hb.model_dump() for hb in package.heartbeats] as JSON
├── tools.json             # [td.model_dump() for td in package.tool_definitions] as JSON
├── persona.md             # package.persona as plain text (UTF-8)
└── memories/
    ├── user_profile.md    # MemoryFile(key="user_profile", content=...)
    ├── preferences.md
    ├── work_context.md
    └── recurring_notes.md
```

**Content hash verification** must use the exact same serialization as the generator:
```python
heartbeats_json = json.dumps([hb.model_dump() for hb in heartbeats], sort_keys=True)
content_hash = hashlib.sha256(heartbeats_json.encode()).hexdigest()
```
[Source: src/crisis_bench/generator/generate.py:275-276]

**scenario.json fields** (what the loader reads back):
- scenario_id, version, seed, crisis_type, noise_tier, crisis_heartbeat_id
- person (nested PersonProfile), contacts (list[Contact]), agent_identity (nested AgentIdentity)
[Source: src/crisis_bench/generator/generate.py:349-352]

### Orchestrator — Async Shell for Future Handler Wiring

The architecture specifies an async orchestrator (`runner/` is "online, async"):
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

```
Orchestrator
  ├── ScenarioLoader        — Story 3.1 (this story)
  ├── PromptBuilder         — Story 3.2
  ├── ModelClient           — Story 3.2
  ├── ToolRouter            — Story 3.3
  │     ├── ScenarioDataHandler   — Story 3.3
  │     ├── MemoryHandler         — Story 3.3
  │     ├── UserSimHandler       — Story 3.5
  │     └── McpHandler            — Story 3.6
  ├── TranscriptRecorder     — Story 3.6
  └── ActionLog              — Story 3.4
```

In this story, the orchestrator is just the heartbeat iteration shell. The `run()` method iterates heartbeats and logs. No model calls, no tool routing, no transcript recording. Future stories will add `_process_heartbeat()` with handler wiring.

**Post-crisis window logic**: The scenario package contains all heartbeats including post-crisis ones (generator produces 20 post-crisis heartbeats via `_POST_CRISIS_HEARTBEATS = 20`). The orchestrator must respect `RunConfig.max_post_crisis_heartbeats` (default: 20) and stop after that many heartbeats past `scenario.crisis_heartbeat_id`. If the scenario has fewer post-crisis heartbeats than the config allows, the orchestrator just processes what's available.

```python
# Pseudocode for heartbeat loop
post_crisis_count = 0
for hb in self.scenario.heartbeats:
    if hb.heartbeat_id > self.scenario.crisis_heartbeat_id:
        post_crisis_count += 1
        if post_crisis_count > self.config.max_post_crisis_heartbeats:
            break
    # ... process heartbeat ...
```

### RunConfig Loading

`RunConfig` already exists in `src/crisis_bench/models/runtime.py:209-225`. It's a frozen Pydantic model with:
- `agent_model: str` (required)
- `user_sim_model: str` (required)
- `judge_model: str` (required)
- `model_params: dict[str, Any]` (default: empty dict)
- `max_tool_turns: int` (default: 10)
- `max_post_crisis_heartbeats: int` (default: 20)
- `action_log_window: int` (default: 20)

Load from JSON file: `RunConfig(**json.loads(config_path.read_text()))`. The `agent_model`, `user_sim_model`, and `judge_model` are required fields — they must be present in the config file.

### CLI Design

Current `run` stub (cli.py:69-73) returns SystemExit(1). Replace with:
```python
@main.command()
@click.option("--scenario", required=True, type=click.Path(exists=True, path_type=Path), help="Path to scenario package directory.")
@click.option("--config", required=True, type=click.Path(exists=True, path_type=Path), help="Path to runner configuration JSON file.")
def run(scenario: Path, config: Path) -> None:
    """Run benchmark against an LLM agent."""
    import asyncio
    from crisis_bench.runner.run import run_benchmark
    asyncio.run(run_benchmark(scenario, config))
```

### Windows Encoding

Previous stories encountered Windows encoding issues (cp1252 errors with emoji/special chars). Always use `encoding="utf-8"` when reading text files:
[Source: _bmad-output/implementation-artifacts/2-6-memory-bootstrapping-example-scenario.md#Debug Log References]

### structlog Configuration

structlog is already configured in `src/crisis_bench/__init__.py`. Use:
```python
import structlog
log = structlog.get_logger()
```

Log levels per architecture: DEBUG tool calls, INFO heartbeats, WARNING MCP timeouts, ERROR LLM failures. For this story, all logging is INFO level (heartbeat progression).
[Source: _bmad-output/planning-artifacts/architecture.md#Logging]

### Existing Test Patterns

- Tests live in `tests/` mirroring `src/` structure: `tests/runner/`
- conftest.py currently empty (just `from __future__ import annotations`)
- Test classes per feature area (e.g., TestMemoryFiles, TestPersona)
- Use `tmp_path` fixture for temp directories
- Existing scenario at `scenarios/cardiac_arrest_T4_s42/` can be used for integration tests
- 117 tests currently passing across generator + models

### Project Structure Notes

New files to create:
- `src/crisis_bench/runner/scenario_loader.py` — ScenarioLoader + ScenarioLoadError
- `src/crisis_bench/runner/orchestrator.py` — Orchestrator class
- `src/crisis_bench/runner/run.py` — run_benchmark() entry point
- `tests/runner/__init__.py`
- `tests/runner/test_scenario_loader.py`
- `tests/runner/test_orchestrator.py`
- `tests/runner/test_run.py`

Modified files:
- `src/crisis_bench/runner/__init__.py` — add imports
- `src/crisis_bench/cli.py` — replace run stub with real command
- `tests/conftest.py` — add scenario/config fixtures

### Pydantic Model References

All models needed for this story already exist:
- `ScenarioPackage` — src/crisis_bench/models/scenario.py:304-324
- `ScenarioManifest` — src/crisis_bench/models/scenario.py:285-301
- `HeartbeatPayload` — src/crisis_bench/models/scenario.py:270-282
- `ToolDefinition` — src/crisis_bench/models/scenario.py:251-258
- `MemoryFile` — src/crisis_bench/models/scenario.py:261-267
- `PersonProfile` — src/crisis_bench/models/scenario.py:208-218
- `Contact` — src/crisis_bench/models/scenario.py:220-229
- `AgentIdentity` — src/crisis_bench/models/scenario.py:231-237
- `RunConfig` — src/crisis_bench/models/runtime.py:209-225
- `RunTranscript` — src/crisis_bench/models/runtime.py:228-237

### Anti-Patterns to Avoid

- **Do NOT re-implement Pydantic validation** — use the existing models directly (e.g., `HeartbeatPayload(**hb_dict)` will validate automatically)
- **Do NOT use `.get()` with fallback values** on dicts that are guaranteed populated (project convention: use direct key access `d["key"]`)
- **Do NOT skip content hash verification** — it's a core reproducibility requirement (NFR1)
- **Do NOT use synchronous I/O in the orchestrator loop** — use async from the start even though this story has no actual async operations, to avoid refactoring in Story 3.2
- **Do NOT add ToolHandler/ToolRouter/TranscriptRecorder** — those are Stories 3.3-3.6
- **Do NOT define __all__** in __init__.py files (project convention)
- **Do NOT add comments, docstrings, or type annotations** to code you didn't write

### References

- [Source: src/crisis_bench/generator/generate.py:339-371] — _write_scenario() (inverse pattern for loader)
- [Source: src/crisis_bench/generator/generate.py:275-276] — Content hash computation
- [Source: src/crisis_bench/models/scenario.py:304-324] — ScenarioPackage model
- [Source: src/crisis_bench/models/scenario.py:285-301] — ScenarioManifest model with SHA-256 validator
- [Source: src/crisis_bench/models/runtime.py:209-225] — RunConfig model
- [Source: src/crisis_bench/models/runtime.py:228-237] — RunTranscript model
- [Source: src/crisis_bench/cli.py:69-73] — Current run stub to replace
- [Source: src/crisis_bench/runner/__init__.py] — Empty runner package
- [Source: src/crisis_bench/__init__.py] — structlog configuration
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — Orchestrator component layout
- [Source: _bmad-output/planning-artifacts/architecture.md#Simulation End Conditions] — Post-crisis window logic
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration Separation] — RunConfig format
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI Design] — CLI subcommand design
- [Source: _bmad-output/planning-artifacts/architecture.md#Testing conventions] — Test patterns
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.1] — Original acceptance criteria
- [Source: _bmad-output/implementation-artifacts/2-6-memory-bootstrapping-example-scenario.md] — Previous story patterns and Windows encoding lessons
- [Source: scenarios/cardiac_arrest_T4_s42/] — Existing scenario for integration tests

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Initial mypy errors with `dict[str, object]` type annotations — resolved by switching to `dict[str, Any]` and removing the generic helper function.
- Pre-existing failures: `test_sms_per_heartbeat` (comms.py) and `ruff E501` in comms.py:79 — not related to this story.

### Completion Notes List

- ScenarioLoader correctly reads and validates all 6 on-disk files as the inverse of `_write_scenario()`.
- Content hash verification uses identical serialization method as generator (json.dumps with sort_keys=True).
- Orchestrator implements async heartbeat loop with post-crisis window logic and structlog INFO logging.
- CLI `run` command accepts `--scenario` and `--config` with proper error handling for ScenarioLoadError and ValidationError.
- `run_benchmark()` is importable from `crisis_bench.runner.run`.
- All 16 new tests pass; 131/132 total tests pass (1 pre-existing failure in comms tests).
- All pre-commit hooks pass for new code (mypy, ruff, ruff-format, codespell, detect-secrets).

### File List

New files:
- src/crisis_bench/runner/scenario_loader.py
- src/crisis_bench/runner/orchestrator.py
- src/crisis_bench/runner/run.py
- tests/runner/test_scenario_loader.py
- tests/runner/test_orchestrator.py
- tests/runner/test_run.py

Modified files:
- src/crisis_bench/runner/__init__.py
- src/crisis_bench/cli.py
- tests/conftest.py

## Change Log

- 2026-02-28: Story 3.1 implemented — ScenarioLoader, Orchestrator shell, run_benchmark entry point, CLI wiring, and 16 tests.
