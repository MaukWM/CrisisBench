# Story 1.3: Runtime Data Models

Status: review

## Story

As a **researcher**,
I want validated schemas for transcripts, tool calls/responses, action log entries, and run configuration,
so that runner output conforms to a strict contract and transcripts are machine-parseable for scoring.

## Acceptance Criteria

1. **Given** a tool call with name and arguments **When** I construct a `ToolCall` model **Then** it validates tool name, args dict, and captures the routed_to handler name

2. **Given** a complete heartbeat transcript **When** I construct a `HeartbeatTranscript` model **Then** it contains turns (agent text + tool calls), memory_ops, user_sim_interactions, and scenario_hash

3. **Given** a runner configuration dict **When** I construct a `RunConfig` model **Then** it validates agent_model, user_sim_model, judge_model, temperature, max_tool_turns, max_post_crisis_heartbeats, and action_log_window

4. **And** ToolResponse, Turn, ActionLogEntry, UserSimInteraction models are all defined

5. **And** all tool response models are defined (SendMessageResponse, MakeCallResponse, QueryDeviceResponse, etc.)

6. **And** frozen for serialized output

7. **And** unit tests validate schema compliance

## Tasks / Subtasks

- [x] Task 1: Create tool response models (AC: 4, 5, 6)
  - [x] 1.1: `ToolResponse` base model — status (str); `ErrorResponse` extends base — status + message (str). All frozen, all described.
  - [x] 1.2: `SendMessageResponse` — status (always "delivered"); `MakeCallResponse` — status ("connected"/"no_answer") + transcript (str | None)
  - [x] 1.3: `QueryDeviceResponse` — status + device_id (str) + data (dict[str, Any]); `GetRecentUpdatesResponse` — status + heartbeats (list[dict[str, Any]])
  - [x] 1.4: `ReadMemoryResponse` — status + content (str | None); `WriteMemoryResponse` — status (always "written"); `ListMemoriesResponse` — status + keys (list[str])
  - [x] 1.5: `ConversationMessage` — sender (str), text (str), timestamp (str as ISO 8601); `Conversation` — contact_id (str), contact_name (str), messages (list[ConversationMessage]); `GetContactsResponse` — status + contacts (list[dict[str, Any]]); `GetConversationsResponse` — status + conversations (list[Conversation])
  - [x] 1.6: `ListEventsResponse` — status + events (list[dict[str, Any]]); `GetForecastResponse` — status + forecast (dict[str, Any]); `GetBalanceResponse` — status + data (dict[str, Any])

- [x] Task 2: Create transcript models (AC: 1, 2, 4, 6)
  - [x] 2.1: `ToolCall` — tool (str), args (dict[str, Any]), result (dict[str, Any]), routed_to (str)
  - [x] 2.2: `Turn` — agent_text (str | None), tool_calls (list[ToolCall])
  - [x] 2.3: `MemoryOp` — op (Literal["read", "write", "list"]), key (str | None), content (str | None)
  - [x] 2.4: `UserSimInteraction` — type (Literal["message", "call"]), agent_sent (str), user_response (str | None)
  - [x] 2.5: `ContextSent` — system_prompt_tokens (int), user_message_tokens (int)
  - [x] 2.6: `HeartbeatTranscript` — heartbeat_id (int), timestamp (str as ISO 8601), scenario_hash (str), context_sent (ContextSent), turns (list[Turn]), memory_ops (list[MemoryOp]), user_sim_interactions (list[UserSimInteraction])
  - [x] 2.7: `ActionLogEntry` — time (str as ISO 8601), action_type (str), tool_name (str), summary (str)

- [x] Task 3: Create configuration and full transcript models (AC: 3, 6)
  - [x] 3.1: `RunConfig` — agent_model (str), user_sim_model (str), judge_model (str), temperature (float), max_tool_turns (int, default 10), max_post_crisis_heartbeats (int, default 5), action_log_window (int, default 20)
  - [x] 3.2: `RunTranscript` — scenario_id (str), run_id (str), run_config (RunConfig), heartbeats (list[HeartbeatTranscript])

- [x] Task 4: Update models/__init__.py (AC: 4)
  - [x] 4.1: Import runtime module in `src/crisis_bench/models/__init__.py` — follow CLAUDE.md convention (no `__all__`, just import the module)

- [x] Task 5: Write unit tests (AC: 7)
  - [x] 5.1: `tests/models/test_runtime.py` — construction tests for every model from valid dicts
  - [x] 5.2: Round-trip tests — construct model -> model_dump_json() -> model_validate_json() -> assert equality
  - [x] 5.3: Frozen immutability tests — attempt attribute assignment, assert ValidationError
  - [x] 5.4: Validation failure tests — missing required fields, wrong types, invalid Literal values
  - [x] 5.5: Tool response inheritance test — all specific responses are instances of ToolResponse

- [x] Task 6: Verify quality gates (AC: all)
  - [x] 6.1: Run `uv run pre-commit run --all-files` — all hooks pass
  - [x] 6.2: Run `uv run pytest tests/models/test_runtime.py -v` — all tests pass
  - [x] 6.3: Run `python -c "from crisis_bench.models import runtime"` — import works

## Dev Notes

### Architecture Requirements
[Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns]

**Pydantic Model Conventions (MUST follow):**
- `model_config = ConfigDict(frozen=True)` on ALL models — published artifacts, immutable once created
- `Field(description="...")` on ALL fields — descriptions may end up in tool schemas
- snake_case JSON fields throughout, never camelCase
- Use Pydantic v2 API (`model_config = ConfigDict(...)`, not old `class Config`)

**Model Location:** `src/crisis_bench/models/runtime.py`
[Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]

The architecture specifies this single file contains: ToolCall, ToolResponse, HeartbeatTranscript, Turn, ActionLogEntry, UserSimInteraction, RunConfig — plus all specific tool response models.

### Tool Return Contracts (Architecture-Defined)
[Source: _bmad-output/planning-artifacts/architecture.md#Tool Return Contracts]

These are the exact contracts the tool handlers in Epic 3 will implement. Getting these right is critical — Story 3.3 depends on them.

| Tool | Response Contract | Notes |
|------|-------------------|-------|
| `send_message(contact_id, text)` | `{"status": "delivered"}` | Void-like. No read receipt. |
| `make_call(number)` | `{"status": "connected"/"no_answer", "transcript": "..."}` | 911: connected. Contacts: no_answer. David: LLM responds. |
| `query_device(device_id)` | `{"status": "ok", "device_id": "...", "data": {...}}` | Full sensor dump from scenario data. data is dict since shape varies by device. |
| `get_recent_updates(count)` | `{"status": "ok", "heartbeats": [...]}` | Last N heartbeat payloads from scenario. |
| `read_memory(key)` | `{"status": "ok", "content": "..."/null}` | Synchronous file read. content is null if key not found. |
| `write_memory(key, content)` | `{"status": "written"}` | Synchronous file write. |
| `list_memories()` | `{"status": "ok", "keys": [...]}` | Lists memory directory keys. |
| `get_contacts()` | `{"status": "ok", "contacts": [...]}` | Contact list from scenario. |
| `get_conversations()` | `{"status": "ok", "conversations": [...]}` | Message threads with typed Conversation sub-models. |
| `list_events(date)` | `{"status": "ok", "events": [...]}` | Calendar events from scenario. |
| `get_forecast(location)` | `{"status": "ok", "forecast": {...}}` | Weather from scenario data. |
| `get_balance(account)` | `{"status": "ok", "data": {...}}` | Financial data from scenario. |
| Error (any tool) | `{"status": "error", "message": "..."}` | Generic error. Also used by McpHandler (v0.5: always "Service unavailable"). |

**Design decision for tool response data fields:** Use `dict[str, Any]` for varying-shape data (device sensor dumps, heartbeat payloads, contact lists, events, forecasts, balances). Handlers in Story 3.3 will populate these from scenario Pydantic models via `.model_dump()`. This avoids coupling runtime responses to specific scenario model shapes and keeps the contract flexible. Exception: `GetConversationsResponse` uses typed `Conversation` sub-models since conversation threading has a stable structure.

### Transcript Schema
[Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture]

The transcript structure per heartbeat:
```json
{
  "heartbeat_id": 140,
  "timestamp": "2026-03-15T18:05:00Z",
  "scenario_hash": "sha256:abc123...",
  "context_sent": {
    "system_prompt_tokens": 2400,
    "user_message_tokens": 800
  },
  "turns": [
    {
      "agent_text": "...",
      "tool_calls": [
        {
          "tool": "query_device",
          "args": {"device_id": "apple_watch_series_9"},
          "result": {"status": "ok", "device_id": "apple_watch_series_9", "data": {...}},
          "routed_to": "scenario_data"
        }
      ]
    }
  ],
  "memory_ops": [
    {"op": "write", "key": "emergency", "content": "..."}
  ],
  "user_sim_interactions": [
    {"type": "message", "agent_sent": "...", "user_response": "..."}
  ]
}
```

`ToolCall.result` is `dict[str, Any]` — it stores the serialized (`.model_dump()`) form of whatever ToolResponse the handler returned. This is the transcript representation; the typed Pydantic models are used at handler level.

### RunConfig Schema
[Source: _bmad-output/planning-artifacts/architecture.md#Configuration Separation]

```json
{
  "agent_model": "anthropic/claude-sonnet-4-20250514",
  "user_sim_model": "anthropic/claude-haiku-4-5-20251001",
  "judge_model": "openai/gpt-4o",
  "temperature": 0.7,
  "max_tool_turns": 10,
  "max_post_crisis_heartbeats": 5,
  "action_log_window": 20
}
```

RunConfig has defaults for operational params (max_tool_turns=10, max_post_crisis_heartbeats=5, action_log_window=20) but requires model strings (no defaults for agent_model, user_sim_model, judge_model).

### Previous Story Learnings (Story 1.2)
[Source: _bmad-output/implementation-artifacts/1-2-scenario-data-models.md]

- 25 Pydantic v2 models in scenario.py with ConfigDict(frozen=True) and Field(description="...") on every field
- ScenarioManifest has field_validator for SHA-256 — no custom validators needed for runtime models
- `from __future__ import annotations` BREAKS Pydantic v2 validators at runtime (deferred annotation evaluation). Do NOT use it.
- mypy strict mode: all functions need return types, all params need type annotations
- ruff line-length is 99 chars
- mypy runs as local hook (`uv run mypy src/`) in project venv — Pydantic types available
- Pydantic has excellent mypy support — no `# type: ignore` needed for models
- Pattern: supporting models (CalendarEvent, Reminder, etc.) defined before the models that reference them
- `dict[str, Any]` requires `from typing import Any` import

### NFR2 Compliance (CRITICAL)
[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions]

Zero health/emergency/safety framing in field names, model names, or descriptions. Generic names like `ToolCall`, `ToolResponse`, `ActionLogEntry` are fine. Do NOT use names like `CrisisDetection`, `EmergencyAction`, `HealthAlert`, etc.

### Critical Anti-Patterns to Avoid
- Do NOT add scenario models (ScenarioManifest, HeartbeatPayload, etc.) — those are in scenario.py (Story 1.2)
- Do NOT add scoring models (ScoringResult, JudgeOutput, etc.) — that's Story 1.4
- Do NOT implement handler logic — these are data contracts only
- Do NOT import scenario models into runtime.py — keep runtime models independent. Handlers bridge the gap.
- Do NOT use `from __future__ import annotations` with Pydantic models
- Do NOT use Pydantic v1 API
- Do NOT add mutable models — everything is frozen (published artifacts)
- Do NOT use `__all__` in `__init__.py` — CLAUDE.md convention

### Project Structure Notes

- Model file: `src/crisis_bench/models/runtime.py` (new, architecture-specified)
- Tests: `tests/models/test_runtime.py` (new, mirrors src structure)
- Init update: `src/crisis_bench/models/__init__.py` (modify — add runtime import)
- No new files outside these three locations

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Tool Return Contracts]
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture — Transcript Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration Separation — RunConfig]
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture — ToolHandler protocol]
- [Source: _bmad-output/planning-artifacts/architecture.md#Format Patterns — Pydantic conventions]
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Tool naming, multi-turn loop]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3]
- [Source: _bmad-output/implementation-artifacts/1-2-scenario-data-models.md — Previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (claude-opus-4-6)

### Debug Log References

No issues encountered. Clean implementation.

### Completion Notes List

- Implemented 22 Pydantic v2 models in `runtime.py`: 13 tool response models (ToolResponse base + 12 specific), 7 transcript models, 2 configuration models
- All models follow architecture conventions: `ConfigDict(frozen=True)`, `Field(description="...")`, Pydantic v2 API, snake_case fields
- ToolResponse inheritance hierarchy: all specific response models extend ToolResponse base
- SendMessageResponse and WriteMemoryResponse have sensible defaults matching their contracts ("delivered" and "written")
- GetConversationsResponse uses typed Conversation/ConversationMessage sub-models per architecture design decision
- All other varying-shape data uses `dict[str, Any]` as specified
- MemoryOp.op and UserSimInteraction.type use `Literal` types for enum-like validation
- RunConfig has defaults for operational params (max_tool_turns=10, max_post_crisis_heartbeats=5, action_log_window=20) but requires model identifier strings
- NFR2 compliant: no health/emergency/safety framing in any names or descriptions
- 73 unit tests across 5 categories: construction (32), round-trip (6), frozen (11), validation failure (11), inheritance (13)
- Zero regressions, all 12 pre-commit hooks pass clean

### File List

- `src/crisis_bench/models/runtime.py` — NEW: 22 Pydantic v2 runtime data models
- `src/crisis_bench/models/__init__.py` — MODIFIED: added runtime module import
- `tests/models/test_runtime.py` — NEW: 73 unit tests for all runtime models

### Change Log

- 2026-02-27: Implemented Story 1.3 — Runtime Data Models (tool responses, transcripts, run configuration)
