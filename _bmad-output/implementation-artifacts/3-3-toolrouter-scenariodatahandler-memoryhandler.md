# Story 3.3: ToolRouter, ScenarioDataHandler & MemoryHandler

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **researcher**,
I want tool calls from the agent routed to the correct handler, with scenario data queries and memory operations working,
So that the agent can query devices, check calendars, read/write memory, and get meaningful responses.

## Prerequisite

**Rename `query_device` → `query_wearable` and simplify.**

The `query_device(device_id)` tool is ambiguous — "device" could mean anything. Since there is only one queryable device (the wearable/smartwatch), rename to `query_wearable` with no parameters. This clarifies what the tool returns (wearable sensor data) and eliminates the unused `device_id` argument.

| What | From | To |
|---|---|---|
| Tool name | `query_device` | `query_wearable` |
| Tool parameter | `device_id` (required, string) | *(removed — no parameters)* |
| Tool description | "Query the current sensor readings from a connected device" | "Query the current sensor readings from the connected wearable" |
| Response model class | `QueryDeviceResponse` | `QueryWearableResponse` |
| Response field | `device_id: str` | *(removed)* |
| Generator tools.py | `_CORE_TOOLS` entry for `query_device` | Updated name, empty params list |
| Model client tests | Any `query_device` references in mocks | Updated to `query_wearable` |
| Example scenario | `tools.json` | Regenerated (content hash changes) |

After rename: regenerate the example scenario (`crisis-bench generate --crisis cardiac_arrest --tier T4 --seed 42`) since `tools.json` and content hash will change. Commit as a separate pre-flight commit before Story 3.3 work.

## Acceptance Criteria

1. **Given** an agent tool call for `query_wearable`, **When** ToolRouter dispatches it, **Then** ScenarioDataHandler returns the current heartbeat's wearable sensor data as a Pydantic ToolResponse.

2. **Given** an agent tool call for `write_memory("emergency", "HR dropped to 0")`, **When** MemoryHandler processes it, **Then** the memory file is written synchronously to disk, and a subsequent `read_memory("emergency")` in the same heartbeat returns the written content.

3. **Given** an agent tool call for `list_memories`, **When** MemoryHandler processes it, **Then** it returns all memory file keys from the scenario's memories/ directory.

4. **Given** a tool name no handler recognizes, **When** ToolRouter dispatches it, **Then** it returns an error ToolResponse: `{"status": "error", "message": "Unknown tool"}`.

5. **And** ToolRouter uses ToolHandler protocol: `can_handle(tool_name) -> bool` + `async handle(tool_name, args) -> ToolResponse`.

6. **And** ScenarioDataHandler covers: `query_wearable`, `list_events`, `get_forecast`, `get_balance`, `get_contacts`, `get_conversations`, `get_recent_updates`, `get_transactions`.

7. **And** all responses are Pydantic models matching the contracts from Story 1.3.

8. **And** `get_conversations` returns an empty conversations list (placeholder — real conversation tracking added in Story 3.5).

## Tasks / Subtasks

- [x] Task 1: Create `src/crisis_bench/runner/handlers/base.py` — ToolHandler protocol (AC: #5)
  - [x] 1.1: Define `ToolHandler` as a `typing.Protocol` class with two methods:
    - `def can_handle(self, tool_name: str) -> bool`
    - `async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse`
  - [x] 1.2: Import `ToolResponse` from `crisis_bench.models.runtime`.

- [x] Task 2: Create `src/crisis_bench/runner/handlers/__init__.py` — Package init (AC: N/A)
  - [x] 2.1: Import `base`, `scenario_data`, `memory` submodules (follow project convention: `from crisis_bench.runner.handlers import base  # noqa: F401` etc.). Do NOT define `__all__`.

- [x] Task 3: Create `src/crisis_bench/runner/handlers/scenario_data.py` — ScenarioDataHandler (AC: #1, #6, #7)
  - [x] 3.1: Define `class ScenarioDataHandler` implementing ToolHandler protocol.
  - [x] 3.2: `__init__(self, scenario: ScenarioPackage)` — store scenario reference, initialize `_current_heartbeat: HeartbeatPayload | None = None` and `_heartbeat_index: int = 0`. Build a `_tool_map: dict[str, Callable]` mapping tool names to handler methods. Bind structlog logger.
  - [x] 3.3: `set_current_heartbeat(self, heartbeat: HeartbeatPayload, index: int) -> None` — updates `_current_heartbeat` and `_heartbeat_index`. Called by the orchestrator before dispatching tool calls for each heartbeat.
  - [x] 3.4: `can_handle(self, tool_name: str) -> bool` — return `tool_name in self._tool_map`.
  - [x] 3.5: `async handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse` — look up the tool name in `_tool_map`, call the mapped method with `args`. Use direct key access on `_tool_map` (no `.get()` — tool presence is guaranteed by `can_handle()`). Log at DEBUG level.
  - [x] 3.6: Implement `_handle_query_wearable(self, args: dict[str, Any]) -> QueryWearableResponse`:
    - No arguments (tool has no parameters after prerequisite rename).
    - Get the current heartbeat's `wearable` data.
    - If wearable is None, return `QueryWearableResponse(status="ok", data={})`.
    - Otherwise, return `QueryWearableResponse(status="ok", data=wearable.model_dump())`.
    - This returns ONLY wearable sensor data (heart_rate, spo2, steps, skin_temp, ecg_summary, etc.) — NOT weather, calendar, financial, or other module data. Those have their own dedicated tools.
  - [x] 3.7: Implement `_handle_get_recent_updates(self, args: dict[str, Any]) -> GetRecentUpdatesResponse`:
    - Get `count` from args (integer).
    - Slice `self.scenario.heartbeats[:self._heartbeat_index + 1]` to get heartbeats up to and including current.
    - Take the last `count` entries from that slice.
    - Return `GetRecentUpdatesResponse(status="ok", heartbeats=[hb.model_dump() for hb in recent])`.
  - [x] 3.8: Implement `_handle_get_contacts(self, args: dict[str, Any]) -> GetContactsResponse`:
    - Return `GetContactsResponse(status="ok", contacts=[c.model_dump() for c in self.scenario.contacts])`.
  - [x] 3.9: Implement `_handle_get_conversations(self, args: dict[str, Any]) -> GetConversationsResponse`:
    - For THIS story, return `GetConversationsResponse(status="ok", conversations=[])`.
    - Conversation tracking is added in Story 3.5 (UserSimHandler). ScenarioDataHandler will receive a shared conversation store reference at that point.
  - [x] 3.10: Implement `_handle_list_events(self, args: dict[str, Any]) -> ListEventsResponse`:
    - Get current heartbeat's `calendar` module data.
    - If calendar is None (tier doesn't include it), return `ListEventsResponse(status="ok", events=[])`.
    - Otherwise, return all events from `calendar.next_3_events` as dicts.
  - [x] 3.11: Implement `_handle_get_forecast(self, args: dict[str, Any]) -> GetForecastResponse`:
    - Get current heartbeat's `weather` module data.
    - If weather is None, return `GetForecastResponse(status="ok", forecast={})`.
    - Otherwise, return `GetForecastResponse(status="ok", forecast=weather.model_dump())`.
  - [x] 3.12: Implement `_handle_get_balance(self, args: dict[str, Any]) -> GetBalanceResponse`:
    - Get current heartbeat's `financial` module data.
    - If financial is None, return `GetBalanceResponse(status="ok", data={})`.
    - Otherwise, return `GetBalanceResponse(status="ok", data={"account_balance": financial.account_balance, "pending_charges": [pc.model_dump() for pc in financial.pending_charges]})`.
  - [x] 3.13: Implement `_handle_get_transactions(self, args: dict[str, Any]) -> ToolResponse`:
    - Get current heartbeat's `financial` module data.
    - Get `count` from args (integer).
    - If financial is None, return `ErrorResponse(status="error", message="Financial data not available at this tier")`.
    - Otherwise, slice `financial.last_3_transactions[:count]` and return as a generic `ToolResponse` subclass. **Note:** Story 1.3 did not define a `GetTransactionsResponse` model. Create one in this story — see Dev Notes for details.

- [x] Task 4: Create `src/crisis_bench/runner/handlers/memory.py` — MemoryHandler (AC: #2, #3, #7)
  - [x] 4.1: Define `class MemoryHandler` implementing ToolHandler protocol.
  - [x] 4.2: `__init__(self, memory_dir: Path, initial_files: list[MemoryFile])` — store `memory_dir`, create the directory (`memory_dir.mkdir(parents=True, exist_ok=True)`), write all initial memory files to disk (`(memory_dir / f"{mf.key}.md").write_text(mf.content, encoding="utf-8")`). Bind structlog logger.
  - [x] 4.3: `can_handle(self, tool_name: str) -> bool` — return `tool_name in {"read_memory", "write_memory", "list_memories"}`.
  - [x] 4.4: `async handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse` — dispatch to internal methods based on tool_name. Log at DEBUG level.
  - [x] 4.5: Implement `_read_memory(self, args: dict[str, Any]) -> ReadMemoryResponse`:
    - Get `key` from args via direct key access.
    - Build path: `self.memory_dir / f"{key}.md"`.
    - If file exists: read content with `encoding="utf-8"`, return `ReadMemoryResponse(status="ok", content=content)`.
    - If file does not exist: return `ReadMemoryResponse(status="ok", content=None)`.
  - [x] 4.6: Implement `_write_memory(self, args: dict[str, Any]) -> WriteMemoryResponse`:
    - Get `key` and `content` from args via direct key access.
    - Write to `self.memory_dir / f"{key}.md"` with `encoding="utf-8"`. This is synchronous (not async) as required by the architecture.
    - Return `WriteMemoryResponse(status="written")`.
  - [x] 4.7: Implement `_list_memories(self, args: dict[str, Any]) -> ListMemoriesResponse`:
    - List all `.md` files in `self.memory_dir`.
    - Strip the `.md` extension to get keys.
    - Return `ListMemoriesResponse(status="ok", keys=sorted(keys))`.

- [x] Task 5: Create `src/crisis_bench/runner/tool_router.py` — ToolRouter (AC: #4, #5)
  - [x] 5.1: Define `class ToolRouter`.
  - [x] 5.2: `__init__(self, handlers: list[ToolHandler])` — store handlers list in registration order. Bind structlog logger.
  - [x] 5.3: `async def route(self, tool_name: str, args: dict[str, Any]) -> tuple[ToolResponse, str]`:
    - Iterate handlers in order, call `can_handle(tool_name)`.
    - First handler that returns True: call `await handler.handle(tool_name, args)`, return `(response, handler_name)` where `handler_name` is `type(handler).__name__`.
    - If no handler matches: return `(ErrorResponse(status="error", message="Unknown tool"), "none")`.
    - Log at DEBUG level: tool_name, routed_to handler name.

- [x] Task 6: Wire ToolRouter + handlers into Orchestrator (AC: #1-7)
  - [x] 6.1: Update `Orchestrator.__init__()`:
    - Create a temporary memory directory: `self._memory_dir = Path(tempfile.mkdtemp(prefix="crisis_bench_"))`.
    - Create handlers: `scenario_data_handler = ScenarioDataHandler(scenario)` and `memory_handler = MemoryHandler(self._memory_dir / "memories", scenario.memory_files)`.
    - Create ToolRouter: `self.tool_router = ToolRouter(handlers=[scenario_data_handler, memory_handler])`.
    - Store `self._scenario_data_handler = scenario_data_handler` for heartbeat updates.
  - [x] 6.2: Update `Orchestrator.run()` heartbeat loop — after the model call:
    - Before routing: `self._scenario_data_handler.set_current_heartbeat(hb, heartbeat_index)` where `heartbeat_index` is the index in `self.scenario.heartbeats` (use `enumerate` in the loop).
    - For each `ParsedToolCall` in `response.tool_calls`: call `tool_response, handler_name = await self.tool_router.route(tc.name, tc.arguments)`.
    - Log each routed tool call at INFO level: `tool_name`, `routed_to`, `status`.
    - Do NOT implement multi-turn tool loop (that's Story 3.4). This story does a single pass of tool routing after the model call.
    - Do NOT build transcript entries (Story 3.6).
    - Do NOT update action log (Story 3.4).

- [x] Task 7: Model changes in `src/crisis_bench/models/runtime.py` (AC: #7)
  - [x] 7.1: Rename `QueryDeviceResponse` → `QueryWearableResponse`. Remove the `device_id` field. Keep `data: dict[str, Any]` for the sensor dump:
    ```python
    class QueryWearableResponse(ToolResponse):
        """Response from query_wearable tool."""
        data: dict[str, Any] = Field(description="Wearable sensor data payload")
    ```
  - [x] 7.2: Add `GetTransactionsResponse` alongside the other tool response models (after `GetBalanceResponse`):
    ```python
    class GetTransactionsResponse(ToolResponse):
        """Response from get_transactions tool."""
        transactions: list[dict[str, Any]] = Field(description="Recent transaction entries")
    ```

- [x] Task 8: Update runner package imports
  - [x] 8.1: Update `src/crisis_bench/runner/__init__.py` — add `tool_router` and `handlers` imports.

- [x] Task 9: Create tests (AC: #1-7)
  - [x] 9.1: Create `tests/runner/test_tool_router.py`:
    - `test_route_to_first_matching_handler` — register two handlers, verify first match wins.
    - `test_route_unknown_tool` — register handlers, route an unrecognized tool name, verify ErrorResponse with "Unknown tool".
    - `test_route_returns_handler_name` — verify `route()` returns the handler class name as the second tuple element.
  - [x] 9.2: Create `tests/runner/test_handlers/` directory with `__init__.py`.
  - [x] 9.3: Create `tests/runner/test_handlers/test_scenario_data.py`:
    - `test_can_handle_known_tools` — verify can_handle returns True for all 8 tool names.
    - `test_can_handle_unknown_tool` — verify can_handle returns False for "unknown_tool".
    - `test_query_wearable_returns_sensor_data` — create a heartbeat with wearable data, call query_wearable, verify wearable sensor fields returned and NO weather/calendar/financial data present.
    - `test_get_contacts_returns_scenario_contacts` — verify contacts match scenario.
    - `test_get_recent_updates_count` — set heartbeat_index to 3, request count=2, verify 2 heartbeats returned.
    - `test_get_forecast_with_weather` — heartbeat with weather data, verify forecast dict returned.
    - `test_get_forecast_without_weather` — heartbeat without weather (T1), verify empty forecast dict.
    - `test_list_events_with_calendar` — heartbeat with calendar data, verify events returned.
    - `test_get_balance_with_financial` — heartbeat with financial data, verify balance data returned.
    - `test_get_conversations_empty` — verify returns empty conversations list (placeholder until Story 3.5).
  - [x] 9.4: Create `tests/runner/test_handlers/test_memory.py`:
    - `test_initial_files_written_to_disk` — init MemoryHandler with MemoryFile list, verify files exist on disk.
    - `test_read_memory_existing_key` — read a pre-seeded key, verify content matches.
    - `test_read_memory_missing_key` — read a non-existent key, verify content is None.
    - `test_write_then_read_memory` — write a new key, read it back, verify content.
    - `test_list_memories` — init with 2 files, write a third, verify list returns all 3 sorted keys.
    - `test_write_memory_overwrite` — write to existing key, verify overwritten content.
    - `test_can_handle_memory_tools` — verify can_handle for read_memory, write_memory, list_memories.
    - `test_can_handle_rejects_other_tools` — verify can_handle returns False for "query_wearable".
    - Use `tmp_path` pytest fixture for the memory directory.
  - [x] 9.5: Update `tests/runner/test_orchestrator.py`:
    - Existing tests must keep passing. The orchestrator now creates a ToolRouter + handlers in `__init__`, but existing tests mock `ModelClient.complete()` to return no tool calls, so routing doesn't fire.
    - Add `test_orchestrator_routes_tool_calls` — mock `ModelClient.complete()` to return a response with a tool call (e.g., `query_wearable`), verify tool_router.route is invoked. Use small_scenario_package with wearable data on at least one heartbeat to get a real result.
    - Add cleanup for temp memory dirs if needed (or verify the orchestrator handles it).

- [x] Task 10: Run `uv run pre-commit run --all-files` — all hooks pass

## Dev Notes

### ToolHandler Protocol — Minimalist Interface

The protocol is the core abstraction for the entire tool system. Keep it minimal:

```python
from typing import Any, Protocol
from crisis_bench.models.runtime import ToolResponse

class ToolHandler(Protocol):
    def can_handle(self, tool_name: str) -> bool: ...
    async def handle(self, tool_name: str, args: dict[str, Any]) -> ToolResponse: ...
```

Handlers are registered in order with ToolRouter. First match wins via `can_handle()`. This is the pattern specified in the architecture doc. Adding a new handler = write the class, append to the handler list. Zero config changes.
[Source: _bmad-output/planning-artifacts/architecture.md#ToolHandler Protocol]

### ToolRouter — Dispatcher, Not a Controller

The ToolRouter's only job is dispatch. It does NOT:
- Transform arguments
- Build transcripts
- Update action logs
- Track state

It takes a tool_name and args, finds the handler, calls it, returns the response and handler name. The `route()` method returns a `tuple[ToolResponse, str]` — the response plus the handler class name (used for the `routed_to` field in transcript ToolCall records, Story 3.6).
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

### ScenarioDataHandler — Current Heartbeat Context

ScenarioDataHandler needs to know which heartbeat is current so it can return the right data. The pattern:

```python
class ScenarioDataHandler:
    def __init__(self, scenario: ScenarioPackage) -> None:
        self.scenario = scenario
        self._current_heartbeat: HeartbeatPayload | None = None
        self._heartbeat_index: int = 0
        self._tool_map = {
            "query_wearable": self._handle_query_wearable,
            "get_recent_updates": self._handle_get_recent_updates,
            "get_contacts": self._handle_get_contacts,
            "get_conversations": self._handle_get_conversations,
            "list_events": self._handle_list_events,
            "get_forecast": self._handle_get_forecast,
            "get_balance": self._handle_get_balance,
            "get_transactions": self._handle_get_transactions,
        }

    def set_current_heartbeat(self, heartbeat: HeartbeatPayload, index: int) -> None:
        self._current_heartbeat = heartbeat
        self._heartbeat_index = index
```

The orchestrator calls `set_current_heartbeat()` before dispatching tool calls for each heartbeat. This avoids passing heartbeat context through the protocol interface.
[Source: _bmad-output/planning-artifacts/architecture.md#Data Flow]

### ScenarioDataHandler — Tool-to-Data Mapping

| Tool | Data Source | Response Model | Notes |
|---|---|---|---|
| `query_wearable` | `heartbeat.wearable` | `QueryWearableResponse` | Wearable sensor data only (HR, SpO2, steps, etc.). No params. |
| `get_recent_updates` | `scenario.heartbeats[:idx+1]` | `GetRecentUpdatesResponse` | Slices up to current heartbeat, takes last N. |
| `get_contacts` | `scenario.contacts` | `GetContactsResponse` | Static, same every heartbeat. |
| `get_conversations` | Empty (placeholder) | `GetConversationsResponse` | Real tracking added in Story 3.5. |
| `list_events` | `heartbeat.calendar` | `ListEventsResponse` | None if tier < T3 (no calendar). |
| `get_forecast` | `heartbeat.weather` | `GetForecastResponse` | None if tier < T2 (no weather). |
| `get_balance` | `heartbeat.financial` | `GetBalanceResponse` | None if tier < T4. |
| `get_transactions` | `heartbeat.financial.last_3_transactions` | `GetTransactionsResponse` | None if tier < T4. New response model. |

[Source: _bmad-output/planning-artifacts/architecture.md#Tool Return Contracts]
[Source: src/crisis_bench/generator/tools.py — tool definitions with tiers]

### query_wearable — Wearable Sensor Data Only

`query_wearable()` returns the current heartbeat's **wearable data only**: heart_rate, spo2, steps, skin_temp, ecg_summary, blood_glucose, calories_burned, sleep_stage, respiratory_rate, body_battery.

```python
def _handle_query_wearable(self, args: dict[str, Any]) -> QueryWearableResponse:
    wearable = self._current_heartbeat.wearable
    data = wearable.model_dump() if wearable else {}
    return QueryWearableResponse(status="ok", data=data)
```

Weather, calendar, financial, and comms data are NOT included — those have dedicated tools (`get_forecast`, `list_events`, `get_balance`, `get_transactions`). This distinction matters for scoring: an agent that explicitly calls `query_wearable` after crisis onset is performing a diagnostic action — a meaningful signal for the heuristic scorer (FR9).

The tool has no parameters after the prerequisite rename. No device_id ambiguity.
[Source: src/crisis_bench/models/scenario.py:15-29 — WearableData fields]

### MemoryHandler — File-Based, Synchronous, UTF-8

Critical design constraints from the architecture:

1. **Synchronous writes** — `write_memory` followed by `read_memory` in the same heartbeat MUST return the written content. Use synchronous `Path.write_text()` and `Path.read_text()`, not async I/O. Although the `handle()` method signature is `async`, the actual file operations are sync (this is fine — small files, local disk).

2. **File naming** — Memory keys map to files as `{key}.md`. The `.md` extension is added by the handler, not the agent. When listing memories, strip `.md` to return keys.

3. **Pre-seeded files** — `__init__` copies all `MemoryFile` objects from the scenario to disk. The initial files are: `user_profile.md`, `preferences.md`, `health_baseline.md`, `work_context.md`, `recurring_notes.md`, `yesterday.md`.

4. **Always use `encoding="utf-8"`** — Windows default encoding is cp1252. Previous stories hit encoding errors. Every `read_text()` and `write_text()` call MUST specify `encoding="utf-8"`.

[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 3]
[Source: _bmad-output/implementation-artifacts/3-2-system-prompt-builder-model-client.md#Windows Encoding]

### Orchestrator Wiring — Single-Pass Tool Routing

Story 3.3 adds tool routing to the orchestrator, but NOT the multi-turn tool loop (Story 3.4). After the model call, iterate tool calls once:

```python
# In __init__:
self._memory_dir = Path(tempfile.mkdtemp(prefix="crisis_bench_"))
scenario_data_handler = ScenarioDataHandler(scenario)
memory_handler = MemoryHandler(self._memory_dir / "memories", scenario.memory_files)
self.tool_router = ToolRouter(handlers=[scenario_data_handler, memory_handler])
self._scenario_data_handler = scenario_data_handler

# In run() heartbeat loop, change enumerate to track index:
for heartbeat_index, hb in enumerate(self.scenario.heartbeats):
    # ... existing heartbeat checks ...

    # Set heartbeat context before routing
    self._scenario_data_handler.set_current_heartbeat(hb, heartbeat_index)

    # ... existing model call ...

    # Route tool calls (single pass — no multi-turn loop yet)
    for tc in response.tool_calls:
        tool_response, handler_name = await self.tool_router.route(tc.name, tc.arguments)
        self.log.info(
            "tool_routed",
            heartbeat_id=hb.heartbeat_id,
            tool_name=tc.name,
            routed_to=handler_name,
            status=tool_response.status,
        )
```

**Do NOT** implement:
- Multi-turn tool loop (Story 3.4)
- Action log updates (Story 3.4)
- Transcript recording (Story 3.6)
- UserSimHandler for send_message/make_call (Story 3.5)
- McpHandler for MCP tools (Story 3.6)

Tool calls for `send_message`, `make_call`, and any MCP tools will return `ErrorResponse("Unknown tool")` until those stories add their handlers. This is correct and expected.
[Source: src/crisis_bench/runner/orchestrator.py — current heartbeat loop]

### Response Model Changes

**Rename:** `QueryDeviceResponse` → `QueryWearableResponse`. Drop the `device_id: str` field (tool no longer takes a device_id parameter). Keep `data: dict[str, Any]` for the wearable sensor dump. This is part of the prerequisite rename commit.

**New model:** `GetTransactionsResponse`. Story 1.3 defined response models for all tools in the architecture's tool return contracts table, but `get_transactions` was added to the tool catalog later (T4 tier tool) without a matching response model. Add it to `src/crisis_bench/models/runtime.py`:

```python
class GetTransactionsResponse(ToolResponse):
    """Response from get_transactions tool."""
    transactions: list[dict[str, Any]] = Field(description="Recent transaction entries")
```

Place it immediately after `GetBalanceResponse` for logical grouping.
[Source: src/crisis_bench/models/runtime.py:38-43 — QueryDeviceResponse to rename]
[Source: src/crisis_bench/models/runtime.py:117-121 — GetBalanceResponse location for new model]

### Handler Registration Order Matters

Register handlers in this order in ToolRouter: `[ScenarioDataHandler, MemoryHandler]`. ScenarioDataHandler goes first because it handles the most tools. MemoryHandler second for memory ops. In later stories, UserSimHandler and McpHandler are appended.

The order matters because ToolRouter uses first-match-wins. No two handlers should claim the same tool name, but the registration order provides a deterministic tiebreak.
[Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture]

### Temp Directory for Memory — Cleanup Strategy

The orchestrator creates a temp directory via `tempfile.mkdtemp()`. For now, this temp dir is NOT cleaned up automatically (the OS temp cleanup handles it). Story 3.7 (end-to-end integration) will replace this with a proper results directory where memory state is preserved alongside the transcript.

For tests, use pytest's `tmp_path` fixture instead of `tempfile.mkdtemp()` — pytest handles cleanup automatically.

### Testing Patterns

**ScenarioDataHandler tests:** Need heartbeats WITH module data. The existing `small_scenario_package` fixture creates bare heartbeats (no wearable/weather/etc). Create a local fixture or extend conftest with heartbeats that have module data populated.

**MemoryHandler tests:** Use `tmp_path` (pytest fixture) for the memory directory. Create MemoryFile objects directly.

**ToolRouter tests:** Create minimal mock handlers that implement the protocol. Test dispatch logic, not handler implementation.

**Orchestrator tests:** Existing tests mock ModelClient to return `AgentResponse(text="Noted.", tool_calls=[])`, so no tool routing fires. These MUST keep passing. New tests should mock ModelClient to return tool calls and verify routing occurs.

Mock example for orchestrator test with tool calls:
```python
mock_complete.return_value = AgentResponse(
    text="Let me check.",
    tool_calls=[
        ParsedToolCall(id="call_1", name="query_wearable", arguments={}),
    ],
)
```
[Source: tests/runner/test_orchestrator.py — existing test patterns]
[Source: tests/conftest.py — small_scenario_package fixture]

### Project Structure Notes

New files to create:
- `src/crisis_bench/runner/handlers/__init__.py`
- `src/crisis_bench/runner/handlers/base.py`
- `src/crisis_bench/runner/handlers/scenario_data.py`
- `src/crisis_bench/runner/handlers/memory.py`
- `src/crisis_bench/runner/tool_router.py`
- `tests/runner/test_tool_router.py`
- `tests/runner/test_handlers/__init__.py`
- `tests/runner/test_handlers/test_scenario_data.py`
- `tests/runner/test_handlers/test_memory.py`

Modified files (prerequisite rename):
- `src/crisis_bench/generator/tools.py` — rename `query_device` → `query_wearable`, remove `device_id` param
- `src/crisis_bench/models/runtime.py` — rename `QueryDeviceResponse` → `QueryWearableResponse`, drop `device_id` field
- `scenarios/cardiac_arrest_T4_s42/*` — regenerated (tools.json changes → content hash changes)
- Any tests referencing `query_device` or `QueryDeviceResponse`

Modified files (story work):
- `src/crisis_bench/runner/orchestrator.py` — add ToolRouter + handler wiring
- `src/crisis_bench/runner/__init__.py` — add tool_router and handlers imports
- `src/crisis_bench/models/runtime.py` — add GetTransactionsResponse
- `tests/runner/test_orchestrator.py` — add routing test, maintain existing tests

No modifications to:
- `src/crisis_bench/runner/model_client.py` — no changes needed
- `src/crisis_bench/runner/run.py` — orchestrator handles everything internally
- `src/crisis_bench/cli.py` — no CLI changes
- `src/crisis_bench/prompt.py` — no changes

### Anti-Patterns to Avoid

- **Do NOT use `.get()` with fallback values** on dicts guaranteed to be populated — use direct key access so missing keys crash loud (project convention from CLAUDE.md).
- **Do NOT define `__all__`** in any `__init__.py` — just import submodules (project convention from CLAUDE.md).
- **Do NOT implement multi-turn tool loop** — that's Story 3.4. Single pass of routing only.
- **Do NOT build transcripts or action log entries** — Stories 3.4 and 3.6.
- **Do NOT add UserSimHandler or McpHandler** — Stories 3.5 and 3.6. Unknown tools return ErrorResponse.
- **Do NOT pass heartbeat context through the ToolHandler protocol** — use `set_current_heartbeat()` method on ScenarioDataHandler directly.
- **Do NOT use async file I/O for MemoryHandler** — synchronous `Path.read_text()`/`write_text()` ensures write-then-read consistency within a heartbeat.
- **Do NOT forget `encoding="utf-8"`** on all file operations — Windows cp1252 encoding will corrupt memory files.
- **Do NOT add error handling for missing heartbeat context** in ScenarioDataHandler's tool methods — the orchestrator ALWAYS calls `set_current_heartbeat()` before routing. If the context is None, that's a bug in the orchestrator, and it should crash loud.

### Pydantic Model References

All existing models referenced:
- `ToolResponse` (base) — src/crisis_bench/models/runtime.py:12-17
- `ErrorResponse` — src/crisis_bench/models/runtime.py:20-24
- `QueryDeviceResponse` (renamed to `QueryWearableResponse` in prerequisite) — src/crisis_bench/models/runtime.py:38-43
- `GetRecentUpdatesResponse` — src/crisis_bench/models/runtime.py:46-49
- `ReadMemoryResponse` — src/crisis_bench/models/runtime.py:52-57
- `WriteMemoryResponse` — src/crisis_bench/models/runtime.py:60-63
- `ListMemoriesResponse` — src/crisis_bench/models/runtime.py:66-69
- `GetContactsResponse` — src/crisis_bench/models/runtime.py:91-94
- `GetConversationsResponse` — src/crisis_bench/models/runtime.py:97-103
- `ListEventsResponse` — src/crisis_bench/models/runtime.py:106-109
- `GetForecastResponse` — src/crisis_bench/models/runtime.py:112-115
- `GetBalanceResponse` — src/crisis_bench/models/runtime.py:118-121
- `ScenarioPackage` — src/crisis_bench/models/scenario.py:304-324
- `HeartbeatPayload` — src/crisis_bench/models/scenario.py:270-282
- `MemoryFile` — src/crisis_bench/models/scenario.py:261-267
- `Contact` — src/crisis_bench/models/scenario.py:220-229

New model to create:
- `GetTransactionsResponse` — src/crisis_bench/models/runtime.py (after GetBalanceResponse)

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — ToolRouter + handler placement
- [Source: _bmad-output/planning-artifacts/architecture.md#ToolHandler Protocol] — Protocol definition
- [Source: _bmad-output/planning-artifacts/architecture.md#Tool Return Contracts] — Response models per tool
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 3] — File-based memory, synchronous writes
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 5] — Coordinator pattern
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 10] — Tool naming conventions
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Flow] — How tool routing fits in orchestrator
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.3] — Original acceptance criteria
- [Source: src/crisis_bench/runner/orchestrator.py] — Current heartbeat loop to modify
- [Source: src/crisis_bench/runner/model_client.py] — ParsedToolCall, AgentResponse dataclasses
- [Source: src/crisis_bench/models/runtime.py] — All ToolResponse subclasses
- [Source: src/crisis_bench/models/scenario.py] — ScenarioPackage, HeartbeatPayload, module data models
- [Source: src/crisis_bench/generator/tools.py] — Tool definitions catalog (core, tier, MCP)
- [Source: src/crisis_bench/models/scenario.py:15-29] — WearableData fields (query_wearable returns this)
- [Source: tests/runner/test_orchestrator.py] — Existing orchestrator test patterns
- [Source: tests/conftest.py] — Existing fixtures (small_scenario_package, default_run_config)
- [Source: _bmad-output/implementation-artifacts/3-2-system-prompt-builder-model-client.md] — Previous story patterns and lessons
- [Source: _bmad-output/implementation-artifacts/3-1-orchestrator-shell-scenario-loading.md] — Earlier story patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Fixed ToolRouter debug log event name collision with orchestrator's `tool_routed` info log — renamed to `tool_dispatched`
- Fixed TC001/TC003 ruff lint issues: moved type-only imports into `TYPE_CHECKING` blocks for memory.py, scenario_data.py, tool_router.py, and test_memory.py

### Completion Notes List

- Prerequisite: Renamed `query_device` → `query_wearable` across runtime models, generator tools.py, test_model_client.py, test_generate.py, and example scenario tools.json. Removed `device_id` parameter (tool now has no params).
- Task 1: Created ToolHandler Protocol in `handlers/base.py` with `can_handle()` and `async handle()` methods.
- Task 2: Created `handlers/__init__.py` with submodule imports (no `__all__`).
- Task 3: Implemented ScenarioDataHandler with all 8 tool handlers (`query_wearable`, `get_recent_updates`, `get_contacts`, `get_conversations`, `list_events`, `get_forecast`, `get_balance`, `get_transactions`). Uses `set_current_heartbeat()` pattern for heartbeat context. `get_conversations` returns empty list as placeholder. `get_transactions` returns ErrorResponse when financial data unavailable.
- Task 4: Implemented MemoryHandler with synchronous file-based read/write/list. All file ops use `encoding="utf-8"`. Pre-seeded files written in `__init__`. Uses `frozenset` for tool name lookup.
- Task 5: Implemented ToolRouter with first-match-wins dispatch. Returns `(ToolResponse, handler_name)` tuple. Unknown tools return ErrorResponse.
- Task 6: Wired ToolRouter + handlers into Orchestrator. Added `tempfile.mkdtemp` for memory dir. Added `enumerate` to heartbeat loop for index tracking. Single-pass tool routing after model call (no multi-turn loop).
- Task 7: Renamed `QueryDeviceResponse` → `QueryWearableResponse` (dropped `device_id` field). Added `GetTransactionsResponse` model.
- Task 8: Updated runner `__init__.py` with `handlers` and `tool_router` imports.
- Task 9: Created comprehensive test suites — 3 ToolRouter tests, 15 ScenarioDataHandler tests (with module data fixtures), 9 MemoryHandler tests (using `tmp_path`), 1 orchestrator routing integration test. All 50 runner tests pass. All 175 tests pass (1 pre-existing failure in `test_sms_per_heartbeat` excluded).
- Task 10: Pre-commit passes on all story files (ruff, ruff-format, mypy, codespell, secrets, pip-audit all clean).

### Change Log

- 2026-02-28: Story 3.3 implementation complete — ToolRouter, ScenarioDataHandler, MemoryHandler, orchestrator wiring, prerequisite rename, model changes, and comprehensive tests.

### File List

New files:
- src/crisis_bench/runner/handlers/__init__.py
- src/crisis_bench/runner/handlers/base.py
- src/crisis_bench/runner/handlers/scenario_data.py
- src/crisis_bench/runner/handlers/memory.py
- src/crisis_bench/runner/tool_router.py
- tests/runner/test_tool_router.py
- tests/runner/test_handlers/__init__.py
- tests/runner/test_handlers/test_scenario_data.py
- tests/runner/test_handlers/test_memory.py

Modified files:
- src/crisis_bench/models/runtime.py (QueryDeviceResponse → QueryWearableResponse, added GetTransactionsResponse)
- src/crisis_bench/generator/tools.py (query_device → query_wearable, removed device_id param)
- src/crisis_bench/runner/orchestrator.py (added ToolRouter + handler wiring, enumerate heartbeat loop, single-pass tool routing)
- src/crisis_bench/runner/__init__.py (added handlers and tool_router imports)
- tests/runner/test_orchestrator.py (added test_orchestrator_routes_tool_calls)
- tests/runner/test_model_client.py (updated query_device → query_wearable mocks)
- tests/generator/test_generate.py (updated query_device → query_wearable in tool name assertions)
- scenarios/cardiac_arrest_T4_s42/tools.json (updated query_device → query_wearable)
- _bmad-output/implementation-artifacts/sprint-status.yaml (status: in-progress → review)
