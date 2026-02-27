# Story 1.4: Scoring Data Models

Status: done

## Story

As a **researcher**,
I want validated schemas for scoring results, detection metrics, action metrics, and judge output,
so that evaluation results are structured, comparable, and leaderboard-ready.

## Acceptance Criteria

1. **Given** a scoring result **When** I construct a `ScoringResult` model **Then** it contains detection (binary), detection_in_memory (binary), action_type (categorical: called_911, contacted_someone, both, neither), and time_to_action (int heartbeat count, None if no action)

2. **Given** a multi-run aggregation **When** I construct an `AggregatedScore` model **Then** it contains mean, standard_deviation, confidence_interval_95, run_count, pass_at_k, and pass_pow_k fields

3. **Given** an LLM judge evaluation **When** I construct a `JudgeOutput` model **Then** it contains the judge's reasoning, per-dimension scores, and overall assessment

4. **And** all scoring models support JSON serialization for leaderboard output

5. **And** frozen for serialized output

6. **And** model constraints enforced (e.g., time_to_action >= 0)

## Tasks / Subtasks

- [x] Task 1: Create per-run heuristic scoring model (AC: 1, 4, 5, 6)
  - [x] 1.1: `ScoringResult` — scenario_id (str), run_id (str), detection (bool), detection_in_memory (bool), action_type (Literal["called_911", "contacted_someone", "both", "neither"]), time_to_action (int | None, ge=0 when present), actions_taken (list[str])

- [x] Task 2: Create judge output models (AC: 3, 4, 5)
  - [x] 2.1: `JudgeDimensionScore` — dimension (str), score (float, ge=0, le=10), reasoning (str)
  - [x] 2.2: `JudgeOutput` — reasoning (str), dimension_scores (list[JudgeDimensionScore]), overall_score (float, ge=0, le=10), overall_assessment (str)

- [x] Task 3: Create aggregation model (AC: 2, 4, 5)
  - [x] 3.1: `AggregatedScore` — mean (float), standard_deviation (float, ge=0), confidence_interval_95 (tuple[float, float]), run_count (int, ge=1), pass_at_k (float, ge=0, le=1), pass_pow_k (float, ge=0, le=1)

- [x] Task 4: Update models/__init__.py (AC: 4)
  - [x] 4.1: Import scoring module in `src/crisis_bench/models/__init__.py` — follow CLAUDE.md convention (no `__all__`, just import the module)

- [x] Task 5: Verify quality gates (AC: all)
  - [x] 5.1: Run `uv run pre-commit run --all-files` — all hooks pass
  - [x] 5.2: Run `uv run python -c "from crisis_bench.models import scoring"` — import works

## Dev Notes

### Architecture Requirements
[Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns]

**Pydantic Model Conventions (MUST follow):**
- `model_config = ConfigDict(frozen=True)` on ALL models — published artifacts, immutable once created
- `Field(description="...")` on ALL fields — descriptions may end up in tool schemas
- snake_case JSON fields throughout, never camelCase
- Use Pydantic v2 API (`model_config = ConfigDict(...)`, not old `class Config`)

**Model Location:** `src/crisis_bench/models/scoring.py`
[Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]

The architecture specifies this single file contains: ScoringResult, DetectionMetrics, ActionMetrics, JudgeOutput. We merge DetectionMetrics/ActionMetrics into ScoringResult (all fields fit naturally in one model per AC1) and add AggregatedScore and JudgeDimensionScore as supporting models.

### Scoring System Overview
[Source: _bmad-output/planning-artifacts/epics.md#Epic 4]

**FR9 — Scoring System:** Post-run evaluation combining code-based heuristic checks (did agent call 911? text someone?) with LLM-as-judge (Instructor + LiteLLM). Metrics: detection, detection-in-memory, action type, time-to-action.

**FR10 — Multi-Run Pipeline:** K=5-10 runs per scenario per agent. Report mean + 95% CI. Support pass@k and pass^k metrics. Action frequency distributions.

**NFR8 — Statistical Rigor:** 95% confidence intervals on all scores. Multi-run aggregation. Report run count, cost, variance. Never show single-run scores without CI.

### Model Design Decisions

**ScoringResult fields:**
- `detection` (bool): Did the agent detect the anomaly? True if any action taken.
- `detection_in_memory` (bool): Did the agent write about the anomaly in memory?
- `action_type` (Literal): Categorical — what did the agent do? "called_911", "contacted_someone", "both", or "neither".
- `time_to_action` (int | None): Heartbeats after crisis before first action. None if no action taken. Constrained >= 0.
- `actions_taken` (list[str]): Specific actions for frequency analysis in Story 4.3 (e.g., ["make_call:911", "send_message:wife"]). Supports action_frequency distribution in aggregation.
- `scenario_id` + `run_id`: For traceability — every result links back to its source.

**JudgeOutput fields:**
- Story 4.2 says the judge evaluates "communication quality, verification behavior, escalation appropriateness". The `JudgeDimensionScore` model captures per-dimension scores with free-form dimension names — the actual dimensions are defined by the judge prompt (Story 4.2), not hard-coded here.
- `overall_score` (float, 0-10): The judge's holistic rating.
- `overall_assessment` (str): Free-text summary from the judge.
- Story 4.2 says "heuristic scores are passed to the judge as context" — the JudgeOutput may reference heuristic results but doesn't embed them. That composition is the scorer's job.

**AggregatedScore fields:**
- Generic aggregation of detection rate across K runs.
- `confidence_interval_95` as `tuple[float, float]` — Pydantic v2 handles tuples natively, and they're naturally immutable.
- `pass_at_k`: Unbiased estimator `1 - C(n-c, k) / C(n, k)` per Story 4.3. Float 0-1.
- `pass_pow_k`: Probability all k trials succeed. Float 0-1.
- Computation logic is NOT in the model (that's Story 4.3). The model is just the data contract.

**What's NOT in this story:**
- Leaderboard wrapper models (ScenarioScore, AgentScore, Leaderboard) — those are Story 4.4's concern.
- Aggregation computation logic — that's Story 4.3.
- Judge prompt and scoring rubric — that's Story 4.2.
- Heuristic scoring logic (transcript scanning) — that's Story 4.1.

### Field Constraints
- `time_to_action`: `Field(ge=0)` on `int | None` — Pydantic v2 applies constraint only when value is not None.
- `JudgeDimensionScore.score` and `JudgeOutput.overall_score`: `Field(ge=0, le=10)` — 0-10 scale.
- `AggregatedScore.standard_deviation`: `Field(ge=0)` — standard deviation cannot be negative.
- `AggregatedScore.run_count`: `Field(ge=1)` — need at least 1 run.
- `AggregatedScore.pass_at_k` and `pass_pow_k`: `Field(ge=0, le=1)` — probabilities.

### Previous Story Learnings (Story 1.2 + 1.3)
[Source: _bmad-output/implementation-artifacts/1-2-scenario-data-models.md + 1-3-runtime-data-models.md]

- 25 models in scenario.py, 22 models in runtime.py — all ConfigDict(frozen=True) + Field(description="...")
- `from __future__ import annotations` BREAKS Pydantic v2 validators at runtime. Do NOT use it.
- mypy strict mode: all functions need return types, all params need type annotations
- ruff line-length is 99 chars
- Pattern: supporting models defined before the models that reference them (e.g., JudgeDimensionScore before JudgeOutput)
- `dict[str, Any]` requires `from typing import Any` import
- `Literal` requires `from typing import Literal` import
- `tuple[float, float]` works natively in Python 3.12 — no import needed
- Pre-commit includes mypy as local hook (`uv run mypy src/`)
- Pydantic has excellent mypy support — no `# type: ignore` needed for models
- RunConfig.temperature was replaced with `model_params: dict[str, Any]` for provider flexibility — scoring models don't need this pattern but it shows the codebase evolves
- `__init__.py` uses `from crisis_bench.models import module  # noqa: F401` pattern

### NFR2 Compliance (CRITICAL)
[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions]

Zero health/emergency/safety framing in field names, model names, or descriptions. `ScoringResult`, `JudgeOutput`, `AggregatedScore` are fine — they describe scoring mechanics, not crisis types. Do NOT use names like `EmergencyScore`, `CrisisDetection`, `HealthAlert`.

### Critical Anti-Patterns to Avoid
- Do NOT add scenario models (ScenarioManifest, HeartbeatPayload) — those are in scenario.py (Story 1.2)
- Do NOT add runtime models (ToolCall, ToolResponse, RunConfig) — those are in runtime.py (Story 1.3)
- Do NOT implement scoring logic — these are data contracts only
- Do NOT implement aggregation computation — that's Story 4.3
- Do NOT add leaderboard/report wrapper models — that's Story 4.4
- Do NOT use `from __future__ import annotations` with Pydantic models
- Do NOT use Pydantic v1 API
- Do NOT add mutable models — everything is frozen (published artifacts)
- Do NOT use `__all__` in `__init__.py` — CLAUDE.md convention
- Do NOT write unit tests for Pydantic schema models — user preference

### Project Structure Notes

- Model file: `src/crisis_bench/models/scoring.py` (new, architecture-specified)
- Init update: `src/crisis_bench/models/__init__.py` (modify — add scoring import)
- No test file — user preference (Pydantic model tests considered unnecessary)
- No new files outside these two locations

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries — scoring.py location]
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns — Pydantic conventions]
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — NFR2]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4 — ACs and requirements]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1 — Heuristic Scorer (consumer)]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.2 — LLM-as-Judge (consumer)]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.3 — Multi-Run Pipeline (consumer)]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.4 — Leaderboard Output (consumer)]
- [Source: _bmad-output/implementation-artifacts/1-2-scenario-data-models.md — Previous story learnings]
- [Source: _bmad-output/implementation-artifacts/1-3-runtime-data-models.md — Previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

None — clean implementation, no issues encountered.

### Completion Notes List

- Created `scoring.py` with 4 frozen Pydantic v2 models: `ScoringResult`, `JudgeDimensionScore`, `JudgeOutput`, `AggregatedScore`
- All models use `ConfigDict(frozen=True)` and `Field(description="...")` per architecture conventions
- All field constraints applied: `ge=0` on time_to_action, `ge=0/le=10` on scores, `ge=0/le=1` on probabilities, `ge=1` on run_count, `ge=0` on standard_deviation
- `confidence_interval_95` uses native `tuple[float, float]` — immutable and Pydantic v2 native
- Updated `__init__.py` with scoring import (ruff auto-merged into grouped import)
- Pre-commit passes clean (mypy, ruff, ruff-format, codespell, pip-audit all green)
- Import verification passes
- No tests per user preference (Pydantic schema tests considered unnecessary)
- NFR2 compliant: no health/emergency/safety framing in names or descriptions

### Change Log

- 2026-02-27: Implemented all scoring data models (Tasks 1-5) — ScoringResult, JudgeDimensionScore, JudgeOutput, AggregatedScore

### File List

- `src/crisis_bench/models/scoring.py` (new)
- `src/crisis_bench/models/__init__.py` (modified)
