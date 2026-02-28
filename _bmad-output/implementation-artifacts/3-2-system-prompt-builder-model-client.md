# Story 3.2: System Prompt Builder & Model Client

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **researcher**,
I want the system prompt assembled from scenario data and each heartbeat sent to an LLM via LiteLLM,
So that the agent receives proper context and can respond with text and tool calls.

## Acceptance Criteria

1. **Given** a scenario package with persona, identity, contacts, and memory files, **When** PromptBuilder assembles the system prompt, **Then** it includes SOUL, IDENTITY, USER, MEMORY_PROTOCOL, HEARTBEAT_BEHAVIOR, SAFETY sections with zero emergency framing (NFR2).

2. **Given** a heartbeat payload with module data, action log, and pending responses, **When** PromptBuilder builds the user message, **Then** it contains current_time, heartbeat_id, action_log (rolling window), pending_responses, and all module data for the tier.

3. **Given** a system prompt and user message, **When** ModelClient sends to LiteLLM, **Then** it returns the agent's response (text + optional tool calls) using the model specified in RunConfig.

4. **And** ModelClient supports any LiteLLM-compatible model string (NFR3).

5. **And** fresh context per heartbeat — no conversation history carried between calls (NFR4).

6. **And** agent identity is embedded in the prompt, not impersonating the user (FR18).

## Prerequisite

**Global rename `health` → `wearable` must be completed before this story.**

Rename the `health` module to `wearable` across the entire codebase for NFR2 compliance ("module names must have zero health/emergency/safety framing"). This is a mechanical find-and-replace:

| What | From | To |
|---|---|---|
| HeartbeatPayload field | `.health` | `.wearable` |
| Data model class | `HealthData` | `WearableData` |
| Generator class | `HealthGenerator` | `WearableGenerator` |
| Generator module file | `generator/modules/health.py` | `generator/modules/wearable.py` |
| Generator imports | `from .health import` | `from .wearable import` |
| All tests referencing health | `health` | `wearable` |

After rename: regenerate the example scenario (`crisis-bench generate --crisis cardiac_arrest --tier T4 --seed 42`) since `heartbeats.json` keys and content hash will change. Commit as a separate pre-flight commit before Story 3.2 work.

## Tasks / Subtasks

- [x] Task 1: Create `src/crisis_bench/prompt.py` — PromptBuilder (AC: #1, #2, #6)
  - [x] 1.1: Define prompt section constants from approved reference `references/system_prompt.py` — SOUL, IDENTITY_TEMPLATE, USER_TEMPLATE, MEMORY_PROTOCOL, HEARTBEAT_BEHAVIOR, SAFETY, USER_MESSAGE_TEMPLATE. These templates are **approved as-is** — copy verbatim, do not modify wording.
  - [x] 1.2: Implement `format_module_data(heartbeat: HeartbeatPayload) -> str` — dump raw heartbeat module data as JSON. Use `heartbeat.model_dump(exclude={"heartbeat_id", "timestamp"}, exclude_none=True)` then `json.dumps(data, indent=2)`. This gives the LLM all module data in a parseable format with zero custom formatting code. Modules set to None by the generator (tier-dependent) are automatically excluded by `exclude_none=True`. The prerequisite rename ensures the field is already `"wearable"` not `"health"` (NFR2).
  - [x] 1.3: Move `format_action_log()` and `format_pending_responses()` from reference file verbatim.
  - [x] 1.4: Implement `class PromptBuilder`:
    - `__init__(self, scenario: ScenarioPackage)` — store scenario, pre-build system prompt (it doesn't change per heartbeat).
    - `system_prompt` property — returns the pre-built system prompt string.
    - `build_user_message(self, heartbeat: HeartbeatPayload, action_log_entries: list[ActionLogEntry], total_action_count: int, pending_responses: list[dict[str, str]]) -> str` — fills USER_MESSAGE_TEMPLATE with heartbeat data, formatted action log, formatted pending responses, and formatted module data.
  - [x] 1.5: Internal `_build_system_prompt(self) -> str` — assembles the 6 sections (SOUL + IDENTITY + USER + MEMORY_PROTOCOL + HEARTBEAT_BEHAVIOR + SAFETY) with scenario data interpolated. Uses `"\n\n".join(sections)`. Contacts are NOT included in the system prompt — the agent discovers contacts via the `get_contacts()` tool (ScenarioDataHandler, Story 3.3).

- [x] Task 2: Create `src/crisis_bench/runner/model_client.py` — ModelClient (AC: #3, #4, #5)
  - [x] 2.1: Define `ParsedToolCall` dataclass — holds `id: str`, `name: str`, `arguments: dict[str, Any]` — represents a tool call from the LLM response before execution/routing.
  - [x] 2.2: Define `AgentResponse` dataclass — holds `text: str | None`, `tool_calls: list[ParsedToolCall]` — the structured return from ModelClient.
  - [x] 2.3: Implement `convert_tool_definitions(tools: list[ToolDefinition]) -> list[dict[str, Any]]` — converts project's ToolDefinition models to OpenAI/LiteLLM function calling format:
    ```python
    {
        "type": "function",
        "function": {
            "name": td.name,
            "description": td.description,
            "parameters": {
                "type": "object",
                "properties": {p.name: {"type": p.type, "description": p.description} for p in td.parameters},
                "required": [p.name for p in td.parameters if p.required],
            }
        }
    }
    ```
  - [x] 2.4: Implement `class ModelClient`:
    - `__init__(self, config: RunConfig, tool_definitions: list[ToolDefinition])` — store model name from `config.agent_model`, model_params from `config.model_params`, and pre-convert tool definitions to LiteLLM format.
    - `async def complete(self, system_prompt: str, user_message: str) -> AgentResponse` — single LiteLLM call via `litellm.acompletion()`. Fresh messages list each call (NFR4: no history). Returns parsed AgentResponse.
  - [x] 2.5: Parse LiteLLM response in `complete()`:
    - Extract text from `response.choices[0].message.content` (may be None if tool-only response).
    - Extract tool calls from `response.choices[0].message.tool_calls` (may be None).
    - For each tool call: `ParsedToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))`. Let `json.JSONDecodeError` crash loud if arguments are malformed — log the raw arguments string at ERROR level so the developer knows it's a provider issue, not a code bug.
    - Return `AgentResponse(text=text, tool_calls=parsed_calls)`.
  - [x] 2.6: Log via structlog: DEBUG level for tool calls in response, INFO level for model call completion (model name, has_tool_calls, tool_count).

- [x] Task 3: Wire PromptBuilder + ModelClient into Orchestrator (AC: #1-5)
  - [x] 3.1: Update `Orchestrator.__init__()`:
    - Create `self.prompt_builder = PromptBuilder(scenario)`.
    - Create `self.model_client = ModelClient(config, scenario.tool_definitions)`.
  - [x] 3.2: Update `Orchestrator.run()` heartbeat loop — after existing logging, add:
    - `user_message = self.prompt_builder.build_user_message(heartbeat=hb, action_log_entries=[], total_action_count=0, pending_responses=[])` — action log empty (Story 3.4), pending responses empty (Story 3.5).
    - `response = await self.model_client.complete(self.prompt_builder.system_prompt, user_message)`.
    - Log response: `self.log.info("agent_response", heartbeat_id=hb.heartbeat_id, has_text=response.text is not None, tool_call_count=len(response.tool_calls))`.
    - Tool calls are NOT processed in this story (Stories 3.3/3.4).

- [x] Task 4: Update runner package imports
  - [x] 4.1: Update `src/crisis_bench/runner/__init__.py` — add `model_client` import (follow existing convention: `from crisis_bench.runner import model_client  # noqa: F401`).

- [x] Task 5: Create tests (AC: #1-6)
  - [x] 5.1: Create `tests/test_prompt.py`:
    - `test_system_prompt_contains_all_sections` — build system prompt from small_scenario_package fixture, verify it contains all 6 section markers (Soul heading, Identity heading, user name, memory tools, heartbeat behavior, guidelines).
    - `test_system_prompt_no_emergency_framing` — verify system prompt does not contain emergency-priming words (list: "emergency", "crisis", "health alert", "medical", "safety alert", "911", "urgent care").
    - `test_system_prompt_agent_identity` — verify system prompt contains agent name from scenario.agent_identity.name and personality.
    - `test_system_prompt_user_profile` — verify system prompt contains user name, birthday, occupation, addresses from scenario.person.
    - `test_system_prompt_no_contacts` — verify system prompt does NOT contain contact names or phone numbers (contacts are tool-discoverable, not prompt-embedded).
    - `test_user_message_contains_heartbeat_data` — build user message for a T4 heartbeat, verify it contains heartbeat_id, timestamp, module data sections.
    - `test_user_message_empty_action_log` — verify "No actions yet today." when action_log is empty.
    - `test_user_message_with_action_log` — pass action log entries, verify they appear formatted.
    - `test_user_message_skips_none_modules` — build user message for a T1 heartbeat (only wearable+location), verify weather/calendar/comms/financial keys are absent from the module data JSON.
    - `test_format_module_data_raw_json` — test that format_module_data returns valid JSON, excludes heartbeat_id/timestamp, excludes None modules, and uses `"wearable"` key (not `"health"`).
  - [x] 5.2: Create `tests/runner/test_model_client.py`:
    - `test_convert_tool_definitions` — convert sample ToolDefinition to OpenAI format, verify structure.
    - `test_model_client_complete_text_only` — mock `litellm.acompletion` to return text-only response, verify AgentResponse.text is populated and tool_calls is empty.
    - `test_model_client_complete_with_tool_calls` — mock `litellm.acompletion` to return a response with tool calls, verify AgentResponse parses tool name, id, and arguments correctly.
    - `test_model_client_fresh_context` — verify that ModelClient.complete() builds a fresh messages list each call (no conversation accumulation).
    - `test_model_client_passes_model_params` — mock acompletion, verify model_params from RunConfig are passed through.
  - [x] 5.3: Update `tests/runner/test_orchestrator.py`:
    - Existing tests must keep passing. Mock ModelClient.complete() in orchestrator tests to avoid real LLM calls.
    - `test_orchestrator_calls_model_per_heartbeat` — verify model_client.complete is called once per heartbeat with correct system prompt and user message.

- [x] Task 6: Run `uv run pre-commit run --all-files` — all hooks pass

## Dev Notes

### PromptBuilder — Using Approved Reference Templates

The `references/system_prompt.py` file contains all prompt section templates **approved by the project owner**. Copy the constants verbatim into `src/crisis_bench/prompt.py`:

| Constant | Description | Source |
|---|---|---|
| `SOUL` | Personality and behavioral principles | references/system_prompt.py:42-76 |
| `IDENTITY_TEMPLATE` | Agent name/role template with `{agent_name}`, `{agent_personality}`, `{user_name}` | references/system_prompt.py:84-94 |
| `USER_TEMPLATE` | User profile template with name, birthday, occupation, addresses | references/system_prompt.py:103-111 |
| `MEMORY_PROTOCOL` | Memory tool instructions with `{user_name}` | references/system_prompt.py:120-136 |
| `HEARTBEAT_BEHAVIOR` | Push-based update behavior with `{user_name}` | references/system_prompt.py:145-157 |
| `SAFETY` | Privacy and judgment guidelines with `{user_name}` | references/system_prompt.py:168-179 |
| `USER_MESSAGE_TEMPLATE` | Per-heartbeat message with `{heartbeat_id}`, `{timestamp}`, `{action_log_section}`, `{pending_section}`, `{module_data_section}` | references/system_prompt.py:195-207 |

Also move the helper functions `format_action_log()` and `format_pending_responses()` as-is.
[Source: references/system_prompt.py]

### Contacts Are NOT in the System Prompt

Contacts are deliberately excluded from the system prompt. The agent discovers contacts via the `get_contacts()` tool (implemented in Story 3.3 via ScenarioDataHandler). This avoids priming the agent with relationship details (wife, doctor, etc.) that could bias crisis response behavior. The SOUL section already instructs "Be resourceful before asking. Check the data. Look it up." — the agent should proactively use `get_contacts()` when it needs to reach someone.

The `assemble_system_prompt()` reference function in `references/system_prompt.py` has a `contacts` parameter and calls `format_contacts()` — the dev should **ignore** this part of the reference and NOT include contacts in the prompt assembly. The reference file's `assemble_system_prompt()` is a design sketch, not the implementation spec.
[Source: references/system_prompt.py:251-286 — assemble_system_prompt (do not follow contacts handling)]

### Module Data — Raw JSON Dump (No Custom Formatting)

The `format_module_data()` function is trivial — dump the heartbeat as raw JSON:

```python
def format_module_data(heartbeat: HeartbeatPayload) -> str:
    data = heartbeat.model_dump(
        exclude={"heartbeat_id", "timestamp"},
        exclude_none=True,
    )
    return json.dumps(data, indent=2)
```

This gives the LLM all module data in a parseable, structured format. Benefits:
- Zero custom formatting code per module type
- `exclude_none=True` handles tier filtering automatically (generator sets absent modules to None)
- Pydantic's `model_dump()` recursively serializes all nested models (events, transactions, etc.)
- The prerequisite `health` → `wearable` rename ensures the JSON key is already NFR2-compliant

LLMs parse JSON natively — there is no benefit to converting structured data into prose.
[Source: src/crisis_bench/models/scenario.py:270-282 — HeartbeatPayload]

### ModelClient — LiteLLM Async Wrapper

Use `litellm.acompletion()` (async version) since the orchestrator is async.

```python
import litellm

response = await litellm.acompletion(
    model=self.model_name,          # e.g. "anthropic/claude-sonnet-4-20250514"
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ],
    tools=self.tools,               # Pre-converted OpenAI format
    **self.model_params,            # From RunConfig.model_params
)
```

**Fresh context (NFR4):** Build the `messages` list fresh every call. Do NOT accumulate conversation history. Each heartbeat is independent.

**Tool call parsing:** LiteLLM normalizes tool calls across providers. The response object follows the OpenAI format:
- `response.choices[0].message.content` — agent text (str or None)
- `response.choices[0].message.tool_calls` — list or None
  - Each: `.id` (str), `.function.name` (str), `.function.arguments` (JSON string → parse with `json.loads`)

**Error handling — crash loud:** If `json.loads(tc.function.arguments)` raises `json.JSONDecodeError`, do NOT catch it silently. Log the raw arguments string at ERROR level with the model name and tool call ID, then let the exception propagate. This is a provider-side issue (malformed JSON from the LLM) and must be visible, not swallowed.

**Model params:** `RunConfig.model_params` is a `dict[str, Any]` for provider-specific params (temperature, max_tokens, etc.). Pass as `**kwargs` to `acompletion()`.
[Source: src/crisis_bench/models/runtime.py:209-225 — RunConfig]

### Tool Definition Conversion

`ToolDefinition` (Pydantic) → OpenAI function calling format. The ToolDefinition model stores parameters as a flat list; convert to OpenAI's nested `properties` / `required` structure.

**Input** (from scenario's tools.json):
```json
{"name": "make_call", "description": "Place a phone call", "parameters": [
  {"name": "number", "type": "string", "description": "Phone number to call", "required": true}
]}
```

**Output** (OpenAI format for LiteLLM):
```json
{"type": "function", "function": {
  "name": "make_call", "description": "Place a phone call",
  "parameters": {"type": "object",
    "properties": {"number": {"type": "string", "description": "Phone number to call"}},
    "required": ["number"]}
}}
```

Tool definitions are pre-converted once in `ModelClient.__init__()`, not per-call.
[Source: src/crisis_bench/models/scenario.py:240-258 — ToolDefinition, ToolParameter]
[Source: scenarios/cardiac_arrest_T4_s42/tools.json — 45+ tool definitions]

### Orchestrator Wiring — Minimal Changes

The orchestrator (Story 3.1) has a clean heartbeat loop shell. This story adds two components:

```python
# In __init__:
self.prompt_builder = PromptBuilder(scenario)
self.model_client = ModelClient(config, scenario.tool_definitions)

# In run() heartbeat loop, after existing logging:
user_message = self.prompt_builder.build_user_message(
    heartbeat=hb,
    action_log_entries=[],       # Empty until Story 3.4
    total_action_count=0,        # Empty until Story 3.4
    pending_responses=[],        # Empty until Story 3.5
)
response = await self.model_client.complete(
    self.prompt_builder.system_prompt,
    user_message,
)
self.log.info(
    "agent_response",
    heartbeat_id=hb.heartbeat_id,
    has_text=response.text is not None,
    tool_call_count=len(response.tool_calls),
)
```

**Do NOT** process tool calls, record transcripts, or update action log. Those are Stories 3.3, 3.4, and 3.6.
[Source: src/crisis_bench/runner/orchestrator.py — current heartbeat loop]

### User Message — Pending Responses vs Module Data

The USER_MESSAGE_TEMPLATE has three data sections:

| Section | Content | Source |
|---|---|---|
| `{action_log_section}` | Rolling window of agent's past actions | ActionLog (Story 3.4) — pass empty list for now |
| `{pending_section}` | Responses to agent's outgoing messages | UserSimHandler (Story 3.5) — pass empty list for now |
| `{module_data_section}` | All heartbeat module data (wearable, location, weather, calendar, comms, financial) | HeartbeatPayload modules |

Communications data (new emails, SMS, Slack, etc.) goes in `{module_data_section}` under "Messages & Notifications" — this is push-based data delivery per the architecture. The `{pending_section}` is reserved for interactive response tracking (e.g., David replying to agent's message via UserSimHandler).
[Source: references/system_prompt.py:183-207 — USER_MESSAGE_TEMPLATE]

### Existing Test Patterns — Mocking LiteLLM

For `test_model_client.py`, mock `litellm.acompletion` using `unittest.mock.AsyncMock`:

```python
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.fixture
def mock_litellm_response():
    """Create a mock LiteLLM response with text and tool calls."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = "I'll check the device now."
    tc = MagicMock()
    tc.id = "call_123"
    tc.function.name = "query_device"
    tc.function.arguments = '{"device_id": "apple_watch"}'
    choice.message.tool_calls = [tc]
    response.choices = [choice]
    return response

@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_model_client_complete(mock_acompletion, mock_litellm_response):
    mock_acompletion.return_value = mock_litellm_response
    # ...
```

For orchestrator tests, mock `ModelClient.complete()` to return a canned `AgentResponse`:
```python
@patch("crisis_bench.runner.model_client.ModelClient.complete", new_callable=AsyncMock)
async def test_orchestrator_calls_model(mock_complete, small_scenario_package, default_run_config):
    mock_complete.return_value = AgentResponse(text="Noted.", tool_calls=[])
    # ...
```

Existing orchestrator tests from Story 3.1 must still pass. Since they test the heartbeat loop without model calls, you may need to mock ModelClient in them too — the orchestrator now always creates a ModelClient in `__init__`.
[Source: tests/runner/test_orchestrator.py — existing tests]
[Source: tests/conftest.py — existing fixtures (small_scenario_package, default_run_config)]

### Windows Encoding

Always use `encoding="utf-8"` when reading/writing text files. Previous stories hit cp1252 errors on Windows.
[Source: _bmad-output/implementation-artifacts/3-1-orchestrator-shell-scenario-loading.md#Dev Notes]

### Project Structure Notes

New files to create:
- `src/crisis_bench/prompt.py` — PromptBuilder class + all prompt templates and formatters
- `src/crisis_bench/runner/model_client.py` — ModelClient class + ParsedToolCall + AgentResponse
- `tests/test_prompt.py` — PromptBuilder tests
- `tests/runner/test_model_client.py` — ModelClient tests

Modified files:
- `src/crisis_bench/runner/orchestrator.py` — add PromptBuilder + ModelClient wiring
- `src/crisis_bench/runner/__init__.py` — add model_client import
- `tests/runner/test_orchestrator.py` — mock ModelClient in existing tests, add new test

No modifications to:
- `src/crisis_bench/runner/run.py` — orchestrator handles everything internally
- `src/crisis_bench/cli.py` — no CLI changes needed
- `src/crisis_bench/models/` — all needed models already exist

### Pydantic Model References

All models needed already exist:
- `ScenarioPackage` — src/crisis_bench/models/scenario.py:304-324
- `PersonProfile` — src/crisis_bench/models/scenario.py:208-218
- `Contact` — src/crisis_bench/models/scenario.py:220-229
- `AgentIdentity` — src/crisis_bench/models/scenario.py:231-237
- `HeartbeatPayload` — src/crisis_bench/models/scenario.py:270-282
- `ToolDefinition` — src/crisis_bench/models/scenario.py:251-258
- `ToolParameter` — src/crisis_bench/models/scenario.py:240-248
- `RunConfig` — src/crisis_bench/models/runtime.py:209-225
- `ActionLogEntry` — src/crisis_bench/models/runtime.py:177-185

Module data models (all in scenario.py — after prerequisite rename):
- `WearableData` — fields: heart_rate, spo2, steps, skin_temp, ecg_summary, blood_glucose, calories_burned, sleep_stage, respiratory_rate, body_battery
- `LocationData` — fields: lat, lon, altitude, speed, heading, accuracy, geofence_status, movement_classification
- `WeatherData` — fields: temp, feels_like, humidity, wind_speed, wind_dir, uv_index, aqi, pollen_level, pressure, dew_point, cloud_cover
- `CalendarData` — fields: next_3_events, reminders, today_summary
- `CommsData` — fields: new_emails, new_slack_messages, new_missed_calls, new_voicemails, new_sms, new_notifications
- `FinancialData` — fields: last_3_transactions, account_balance, pending_charges, stock_watchlist, crypto_prices, spending_vs_budget

### Anti-Patterns to Avoid

- **Do NOT modify the prompt template wording** — templates from references/system_prompt.py are approved. Change structure/assembly only.
- **Do NOT add emergency/health/safety words** to ANY agent-visible string — module headings, tool names, section titles (NFR2).
- **Do NOT accumulate conversation history** — each ModelClient.complete() call builds fresh messages (NFR4).
- **Do NOT process tool calls** — just parse and return them. Tool execution is Story 3.3/3.4.
- **Do NOT add ActionLog management** — pass empty list. Story 3.4 owns ActionLog.
- **Do NOT add UserSim/pending response tracking** — pass empty list. Story 3.5 owns UserSimHandler.
- **Do NOT use `.get()` with fallback values** on guaranteed-populated dicts (project convention).
- **Do NOT define `__all__`** in any `__init__.py` (project convention).
- **Do NOT add real LLM calls in tests** — always mock `litellm.acompletion`.
- **Do NOT skip tool definitions** in ModelClient — tools must always be passed so the LLM knows what tools are available.

### References

- [Source: references/system_prompt.py] — Approved prompt templates and helpers
- [Source: src/crisis_bench/runner/orchestrator.py] — Current heartbeat loop to modify
- [Source: src/crisis_bench/runner/run.py] — Entry point (no changes needed)
- [Source: src/crisis_bench/runner/__init__.py] — Package imports to update
- [Source: src/crisis_bench/models/scenario.py:208-324] — ScenarioPackage, PersonProfile, Contact, AgentIdentity, ToolDefinition, HeartbeatPayload, all module data models
- [Source: src/crisis_bench/models/runtime.py:177-225] — ActionLogEntry, RunConfig
- [Source: scenarios/cardiac_arrest_T4_s42/tools.json] — Real tool definitions for reference
- [Source: scenarios/cardiac_arrest_T4_s42/heartbeats.json] — Real heartbeat payloads for reference
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — PromptBuilder + ModelClient placement
- [Source: _bmad-output/planning-artifacts/architecture.md#OpenClaw Alignment] — Deliberate divergences
- [Source: _bmad-output/planning-artifacts/architecture.md#Configuration Separation] — RunConfig format
- [Source: _bmad-output/planning-artifacts/architecture.md#Tool Return Contracts] — Tool naming conventions
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.2] — Original acceptance criteria
- [Source: _bmad-output/implementation-artifacts/3-1-orchestrator-shell-scenario-loading.md] — Previous story patterns and lessons
- [Source: tests/runner/test_orchestrator.py] — Existing orchestrator tests to maintain
- [Source: tests/conftest.py] — Existing fixtures (small_scenario_package, default_run_config)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None — clean implementation with no debugging needed.

### Completion Notes List

- **Prerequisite: health → wearable rename** — Renamed `HealthData` → `WearableData`, `HealthGenerator` → `WearableGenerator`, `health.py` → `wearable.py`, and all field references across src/ and tests/. Regenerated example scenario (`cardiac_arrest_T4_s42`) with updated content hash.
- **Task 1: PromptBuilder** — Created `src/crisis_bench/prompt.py` with all 7 prompt section constants copied verbatim from `references/system_prompt.py`, plus `format_action_log()`, `format_pending_responses()`, `format_module_data()` helpers and `PromptBuilder` class. System prompt pre-built in `__init__`; contacts deliberately excluded per story spec.
- **Task 2: ModelClient** — Created `src/crisis_bench/runner/model_client.py` with `ParsedToolCall` and `AgentResponse` frozen dataclasses, `convert_tool_definitions()` for ToolDefinition → OpenAI format conversion, and async `ModelClient` wrapping `litellm.acompletion()`. Fresh messages per call (NFR4), crash-loud on malformed tool call arguments, structlog INFO/DEBUG logging.
- **Task 3: Orchestrator wiring** — Added `PromptBuilder` and `ModelClient` creation in `__init__`, and per-heartbeat `build_user_message` + `complete()` calls in `run()` loop with response logging. Action log and pending responses passed as empty (Stories 3.4/3.5). Tool calls not processed (Stories 3.3/3.4).
- **Task 4: Runner imports** — Added `model_client` to `runner/__init__.py`.
- **Task 5: Tests** — Created `tests/test_prompt.py` (10 tests), `tests/runner/test_model_client.py` (5 tests), updated `tests/runner/test_orchestrator.py` (4 existing + 1 new test, all mocking ModelClient). Updated `tests/runner/test_run.py` to mock ModelClient for integration test. All 147 tests pass.
- **Task 6: Pre-commit** — mypy, ruff-format, codespell, detect-secrets, pip-audit all pass. 6 remaining ruff errors are pre-existing in untouched files.

### Change Log

- 2026-02-28: Prerequisite rename `health` → `wearable` across codebase (NFR2 compliance)
- 2026-02-28: Implemented PromptBuilder (prompt.py) and ModelClient (model_client.py)
- 2026-02-28: Wired PromptBuilder + ModelClient into Orchestrator heartbeat loop
- 2026-02-28: Added 20 tests (10 prompt, 5 model client, 5 orchestrator)

### File List

**New files:**
- src/crisis_bench/prompt.py
- src/crisis_bench/runner/model_client.py
- tests/test_prompt.py
- tests/runner/test_model_client.py

**Modified files:**
- src/crisis_bench/models/scenario.py (HealthData → WearableData, health → wearable field)
- src/crisis_bench/generator/modules/wearable.py (renamed from health.py, HealthGenerator → WearableGenerator)
- src/crisis_bench/generator/modules/__init__.py (health → wearable import)
- src/crisis_bench/generator/generate.py (all health → wearable references)
- src/crisis_bench/runner/orchestrator.py (added PromptBuilder + ModelClient wiring)
- src/crisis_bench/runner/__init__.py (added model_client import)
- tests/generator/test_generate.py (health → wearable references)
- tests/generator/test_determinism.py (health → wearable references)
- tests/runner/test_orchestrator.py (mock ModelClient, add new test)
- tests/runner/test_run.py (mock ModelClient for integration test)
- scenarios/cardiac_arrest_T4_s42/* (regenerated with wearable key)
- _bmad-output/implementation-artifacts/sprint-status.yaml (status → in-progress → review)

**Deleted files:**
- src/crisis_bench/generator/modules/health.py (renamed to wearable.py)
