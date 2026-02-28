# Story 3.4: Multi-Turn Tool Loop & Action Log

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a **researcher**,
I want the agent to make multiple tool calls per heartbeat (up to configurable max), with each action recorded in a rolling action log,
So that the agent can chain reasoning (e.g., query wearable -> detect anomaly -> call 911) within a single heartbeat.

## Acceptance Criteria

1. **Given** an agent response with tool calls, **When** the orchestrator processes the heartbeat, **Then** it executes tool calls, returns results to the agent, and loops until the agent produces no more tool calls or `max_tool_turns` is reached.

2. **Given** `max_tool_turns` is reached, **When** the loop terminates, **Then** the tool calls from the final turn are still executed and recorded in the action log, but no further LLM call is made. A log message at INFO level records the limit was hit.

3. **Given** actions taken across heartbeats, **When** ActionLog provides entries for a new heartbeat, **Then** it includes the last N actions in detail (N = `config.action_log_window`, default 20) plus a total count of all actions.

4. **And** action log entries record: time (from heartbeat timestamp), action_type (category string), tool_name, and a brief human-readable summary.

5. **And** the action log is included in the user message for each heartbeat via PromptBuilder (already wired — currently receives empty lists).

6. **And** the multi-turn tool loop is logged at DEBUG level via structlog, with an INFO-level summary per heartbeat of total turns and tool calls.

7. **And** tool results are fed back to the LLM in the correct LiteLLM message format (assistant message with tool_calls + tool result messages).

## Tasks / Subtasks

- [x] Task 1: Refactor ModelClient for multi-turn support (AC: #1, #7)
  - [x]1.1: Extract the LiteLLM call + response parsing from `complete()` into a private `_call(self, messages: list[dict[str, Any]]) -> AgentResponse` method. This method:
    - Calls `litellm.acompletion(model=..., messages=messages, tools=self.tools, **self.model_params)`
    - Parses the response (text + tool calls) identically to current `complete()` logic
    - Returns `AgentResponse`
  - [x]1.2: Refactor `complete()` to build the `[system, user]` message list and delegate to `_call()`. Signature stays the same — no breaking changes.
  - [x]1.3: Add `async def continue_conversation(self, messages: list[dict[str, Any]]) -> AgentResponse` — a public method that delegates directly to `_call(messages)`. This is used by the orchestrator for follow-up turns within a heartbeat.

- [x] Task 2: Add LiteLLM message builder helpers in `model_client.py` (AC: #7)
  - [x]2.1: Add `def build_assistant_message(response: AgentResponse) -> dict[str, Any]` (module-level function, not a method):
    - Builds the assistant message dict in LiteLLM/OpenAI format.
    - `"role": "assistant"`, `"content": response.text or ""`.
    - If `response.tool_calls` is non-empty, add `"tool_calls"` list where each entry has:
      - `"id"`: `tc.id`
      - `"type"`: `"function"`
      - `"function"`: `{"name": _sanitize_tool_name(tc.name), "arguments": json.dumps(tc.arguments)}`
    - **Critical:** Tool names MUST be sanitized (dots -> double underscores) because the LLM API received sanitized names. Re-use the existing `_sanitize_tool_name()` function.
    - **Critical:** Arguments must be a JSON **string**, not a dict. Our `ParsedToolCall.arguments` is a dict — serialize with `json.dumps()`.
  - [x]2.2: Add `def build_tool_result_message(tool_call_id: str, result: ToolResponse) -> dict[str, Any]` (module-level function):
    - Returns `{"role": "tool", "tool_call_id": tool_call_id, "content": json.dumps(result.model_dump())}`.
    - The `content` must be a JSON string. Use `result.model_dump()` to serialize the Pydantic response.

- [x] Task 3: Create ActionLog class in `orchestrator.py` (AC: #3, #4)
  - [x]3.1: Define `class ActionLog` as an inline class in `orchestrator.py` (per architecture: "ActionLog — inline class"):
    ```python
    class ActionLog:
        def __init__(self, window_size: int) -> None:
            self._entries: list[ActionLogEntry] = []
            self._window_size = window_size

        def record(self, time: str, action_type: str, tool_name: str, summary: str) -> None:
            self._entries.append(ActionLogEntry(
                time=time, action_type=action_type,
                tool_name=tool_name, summary=summary,
            ))

        def get_window(self) -> tuple[list[ActionLogEntry], int]:
            return self._entries[-self._window_size :], len(self._entries)
    ```
  - [x]3.2: Add `_classify_action(tool_name: str) -> str` module-level helper:
    - `"query"` for: `query_wearable`, `get_recent_updates`, `get_contacts`, `get_conversations`, `list_events`, `get_forecast`, `get_balance`, `get_transactions`
    - `"memory"` for: `read_memory`, `write_memory`, `list_memories`
    - `"communication"` for: `send_message`, `make_call`
    - `"tool_call"` as default fallback for any unrecognized tool name
  - [x]3.3: Add `_summarize_tool_call(tool_name: str, args: dict[str, Any]) -> str` module-level helper that generates a brief human-readable summary:
    - `"query_wearable"` -> `"Checked wearable sensor data"`
    - `"get_recent_updates"` -> `f"Retrieved {args.get('count', '?')} recent updates"`
    - `"get_contacts"` -> `"Retrieved contacts list"`
    - `"get_conversations"` -> `"Retrieved conversations"`
    - `"list_events"` -> `"Listed calendar events"`
    - `"get_forecast"` -> `"Checked weather forecast"`
    - `"get_balance"` -> `"Checked account balance"`
    - `"get_transactions"` -> `"Retrieved recent transactions"`
    - `"read_memory"` -> `f"Read memory '{args.get('key', '?')}'"`
    - `"write_memory"` -> `f"Updated memory '{args.get('key', '?')}'"`
    - `"list_memories"` -> `"Listed memory files"`
    - `"send_message"` -> `f"Sent message to {args.get('contact_id', '?')}"`
    - `"make_call"` -> `f"Called {args.get('number', '?')}"`
    - Default -> `f"Called {tool_name}"`
    - Note: `.get()` with fallbacks is appropriate here because these args come from the LLM and are NOT guaranteed to be well-formed. This is a system boundary — cosmetic formatting should not crash.

- [x] Task 4: Implement multi-turn tool loop in Orchestrator (AC: #1, #2, #5, #6, #7)
  - [x]4.1: Add `from crisis_bench.runner.model_client import build_assistant_message, build_tool_result_message` imports.
  - [x]4.2: Create `self._action_log = ActionLog(config.action_log_window)` in `Orchestrator.__init__()`.
  - [x]4.3: Replace the current single-pass tool routing block in `run()` with the multi-turn loop. The full flow for each heartbeat:

    ```python
    # 1. Build user message with action log
    window, total = self._action_log.get_window()
    user_message = self.prompt_builder.build_user_message(
        heartbeat=hb,
        action_log_entries=window,
        total_action_count=total,
        pending_responses=[],  # Story 3.5
    )

    # 2. Build initial messages
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": self.prompt_builder.system_prompt},
        {"role": "user", "content": user_message},
    ]

    # 3. Multi-turn tool loop
    turn_count = 0
    max_turns = self.config.max_tool_turns

    while True:
        if turn_count == 0:
            response = await self.model_client.complete(
                self.prompt_builder.system_prompt, user_message,
            )
        else:
            response = await self.model_client.continue_conversation(messages)

        self.log.info(
            "agent_response",
            heartbeat_id=hb.heartbeat_id,
            turn=turn_count,
            has_text=response.text is not None,
            tool_call_count=len(response.tool_calls),
        )

        if not response.tool_calls:
            break

        turn_count += 1

        # Add assistant message to conversation
        messages.append(build_assistant_message(response))

        # Execute and record tool calls
        for tc in response.tool_calls:
            tool_response, handler_name = await self.tool_router.route(
                tc.name, tc.arguments,
            )
            self._action_log.record(
                time=hb.timestamp,
                action_type=_classify_action(tc.name),
                tool_name=tc.name,
                summary=_summarize_tool_call(tc.name, tc.arguments),
            )
            messages.append(build_tool_result_message(tc.id, tool_response))
            self.log.info(
                "tool_routed",
                heartbeat_id=hb.heartbeat_id,
                turn=turn_count,
                tool_name=tc.name,
                routed_to=handler_name,
                status=tool_response.status,
            )

        if turn_count >= max_turns:
            self.log.info(
                "max_tool_turns_reached",
                heartbeat_id=hb.heartbeat_id,
                turns=turn_count,
            )
            break

    # 4. Log heartbeat summary
    self.log.debug(
        "heartbeat_tool_summary",
        heartbeat_id=hb.heartbeat_id,
        tool_turns=turn_count,
    )
    ```
  - [x]4.4: **Initial call optimization:** On turn 0, use `self.model_client.complete()` (which builds fresh messages internally). For subsequent turns, use `self.model_client.continue_conversation(messages)` with the accumulated messages list. This avoids duplicating the initial message-building logic. The `messages` list is built up alongside for use in `continue_conversation()`.
  - [x]4.5: Keep the existing `agent_text` log after the loop if the final response has text. Remove the old single-pass `for tc in response.tool_calls` block entirely.

- [x] Task 5: Update existing tests for new Orchestrator behavior (AC: #1)
  - [x]5.1: Existing orchestrator tests mock `ModelClient.complete` to return `AgentResponse(text="Noted.", tool_calls=[])`. These should still pass without changes — zero tool calls means the loop body never fires (turn_count stays 0). Verify this.
  - [x]5.2: Update `test_orchestrator_routes_tool_calls` — currently mocks `complete` to return one tool call. The loop will now call `complete` (turn 1), route the tool call, then call `continue_conversation` (turn 2 — agent should return no tool calls). Mock `continue_conversation` to return `AgentResponse(text="Done.", tool_calls=[])`. Verify both `tool_routed` and `agent_response` logs.
  - [x]5.3: `test_orchestrator_calls_model_per_heartbeat` — may need adjustment. Currently asserts `mock_complete.call_count == 5` (one per heartbeat). With the multi-turn loop, the count depends on tool calls. Since the mock returns no tool calls, count should remain 5. Verify this.

- [x] Task 6: Create new tests (AC: #1-7)
  - [x]6.1: Create `tests/runner/test_action_log.py`:
    - `test_empty_action_log` — new ActionLog has empty window, total 0.
    - `test_record_and_retrieve` — record 3 actions, verify get_window returns all 3, total 3.
    - `test_window_size_limits_entries` — record 25 actions with window_size=20, verify get_window returns last 20, total 25.
    - `test_window_size_larger_than_entries` — record 5 actions with window_size=20, verify get_window returns all 5, total 5.
  - [x]6.2: Add to `tests/runner/test_orchestrator.py`:
    - `test_multi_turn_tool_loop` — Mock `complete` to return a tool call, mock `continue_conversation` to return no tool calls. Verify:
      - `complete` called once, `continue_conversation` called once per heartbeat
      - `tool_routed` log appears
      - `agent_response` log appears for both turns
    - `test_max_tool_turns_reached` — Mock `complete` and `continue_conversation` to ALWAYS return tool calls. Set `max_tool_turns=2` in config. Verify:
      - Loop stops after 2 tool turns
      - `max_tool_turns_reached` log appears
      - Total model calls = 1 (complete) + 2 (continue_conversation) = 3 per heartbeat
    - `test_action_log_accumulates_across_heartbeats` — Run 2 heartbeats, each with 1 tool call turn. Verify action log has entries from both heartbeats (check via the user_message passed to `complete` on the second heartbeat — it should contain action log text from the first heartbeat's actions).
  - [x]6.3: Add to `tests/runner/test_model_client.py`:
    - `test_continue_conversation` — Mock `litellm.acompletion` and verify `continue_conversation` passes the messages list through and parses the response correctly.
    - `test_build_assistant_message_with_tool_calls` — Verify the dict structure: role, content, tool_calls with sanitized names and JSON-string arguments.
    - `test_build_assistant_message_no_tool_calls` — Verify no `tool_calls` key when response has no tool calls.
    - `test_build_tool_result_message` — Verify role, tool_call_id, and JSON-serialized content.

- [x] Task 7: Run `uv run pre-commit run --all-files` — all hooks pass

## Dev Notes

### Multi-Turn Tool Loop Architecture

The loop lives in the **Orchestrator**, not ModelClient. Rationale: the orchestrator coordinates between ModelClient (LLM calls), ToolRouter (tool execution), and ActionLog (recording). ModelClient stays as a thin LLM wrapper with two public call methods.

**Loop flow per heartbeat:**
```
messages = [system, user (with action log)]

turn 0: model_client.complete(system_prompt, user_message) → response
  if no tool_calls → done
  execute tool calls via tool_router
  record in action_log
  append assistant msg + tool result msgs to messages

turn 1: model_client.continue_conversation(messages) → response
  if no tool_calls → done
  execute tool calls...
  append to messages...

... repeat until no tool_calls or turn_count >= max_tool_turns
```

[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 6]
[Source: _bmad-output/planning-artifacts/epics.md#Story 3.4]

### LiteLLM Multi-Turn Message Format

LiteLLM uses the OpenAI message format for multi-turn tool calling:

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    # Turn 1: agent calls tools
    {
        "role": "assistant",
        "content": "Let me check that.",
        "tool_calls": [
            {
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "query_wearable",  # SANITIZED name
                    "arguments": "{}",          # JSON STRING, not dict
                },
            },
        ],
    },
    # Tool results (one per tool call)
    {
        "role": "tool",
        "tool_call_id": "call_abc123",
        "content": '{"status": "ok", "data": {"heart_rate": 72, ...}}',
    },
    # Turn 2: agent responds or calls more tools
    # ...
]
```

**Two critical pitfalls:**
1. Tool names in assistant messages must be **sanitized** (`_sanitize_tool_name`). The API originally sent sanitized names; it expects them back. Our `ParsedToolCall.name` stores the **restored** name (dots restored). Re-sanitize when building the assistant message.
2. Arguments must be a JSON **string** (`json.dumps(tc.arguments)`), NOT a dict. Our `ParsedToolCall.arguments` is a parsed dict.

[Source: src/crisis_bench/runner/model_client.py:36-47 — existing sanitize/restore functions]

### ModelClient Changes — Minimal Surface

Only three changes to `model_client.py`:
1. Extract `_call(messages)` private method (refactor — no new behavior)
2. Add `continue_conversation(messages)` public method (thin wrapper)
3. Add two module-level helper functions: `build_assistant_message()` and `build_tool_result_message()`

`complete()` signature and behavior are unchanged. Existing tests pass without modification.

[Source: src/crisis_bench/runner/model_client.py:81-130 — current complete() method]

### ActionLog — Simple Rolling Window

The ActionLog is intentionally minimal:
- A list of `ActionLogEntry` objects (already defined in `models/runtime.py`)
- A `record()` method to append entries
- A `get_window()` method returning `(last_N_entries, total_count)`

The `window_size` comes from `RunConfig.action_log_window` (default 20, already in the model). The orchestrator passes this at construction.

Architecture says "inline class in orchestrator.py" — keep it in the same file, not a separate module.

[Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 4]
[Source: src/crisis_bench/models/runtime.py:182-191 — ActionLogEntry model]
[Source: src/crisis_bench/models/runtime.py:226-230 — RunConfig.max_tool_turns, action_log_window]

### PromptBuilder Integration — Already Wired

`PromptBuilder.build_user_message()` already accepts `action_log_entries: list[ActionLogEntry]` and `total_action_count: int`. The orchestrator currently passes empty lists. This story replaces those with real data from ActionLog.

The `format_action_log()` helper in `prompt.py` already formats entries as `"- {time} — {summary}"` with an "earlier actions" count. The `_ACTION_LOG_WINDOW` constant (20) in prompt.py is used only for the formatting text — the actual windowing happens in ActionLog.

No changes needed to `prompt.py`.

[Source: src/crisis_bench/prompt.py:140-160 — format_action_log()]
[Source: src/crisis_bench/prompt.py:203-224 — build_user_message()]

### Initial Call vs. Continue Call

Turn 0 uses `model_client.complete(system_prompt, user_message)` — this matches the existing interface and avoids duplicating message construction.

Turns 1+ use `model_client.continue_conversation(messages)` — the orchestrator has already built up the `messages` list with the initial system/user messages plus all tool exchanges.

This means the `messages` list needs to be populated correctly from turn 0. Build it alongside:
```python
messages = [
    {"role": "system", "content": self.prompt_builder.system_prompt},
    {"role": "user", "content": user_message},
]
# Turn 0: call complete() but also keep messages in sync
# After getting response with tool calls, append assistant + tool messages to `messages`
# Turn 1+: call continue_conversation(messages)
```

### pending_responses — Still Empty

This story does NOT implement `pending_responses` (new messages since last heartbeat). That's Story 3.5 (UserSimHandler). Continue passing `pending_responses=[]` to `build_user_message()`.

### Existing RunConfig Fields

`RunConfig` already has both fields needed:
- `max_tool_turns: int = Field(default=10)` — max tool call rounds per heartbeat
- `action_log_window: int = Field(default=20)` — rolling window size

No model changes needed.

[Source: src/crisis_bench/models/runtime.py:226-230]

### Project Structure Notes

Modified files:
- `src/crisis_bench/runner/model_client.py` — refactor `complete()`, add `continue_conversation()`, add `build_assistant_message()`, add `build_tool_result_message()`
- `src/crisis_bench/runner/orchestrator.py` — add `ActionLog` class, add `_classify_action()`, add `_summarize_tool_call()`, replace single-pass routing with multi-turn loop, wire ActionLog into heartbeat flow

New files:
- `tests/runner/test_action_log.py` — ActionLog unit tests

Modified test files:
- `tests/runner/test_orchestrator.py` — update existing routing test, add multi-turn tests
- `tests/runner/test_model_client.py` — add continue_conversation and message builder tests

No modifications to:
- `src/crisis_bench/prompt.py` — already wired for action log
- `src/crisis_bench/models/runtime.py` — ActionLogEntry and RunConfig already defined
- `src/crisis_bench/runner/handlers/` — handlers are unchanged
- `src/crisis_bench/runner/tool_router.py` — router is unchanged
- `src/crisis_bench/cli.py` — no CLI changes

### Anti-Patterns to Avoid

- **Do NOT move the loop into ModelClient** — the orchestrator coordinates ModelClient + ToolRouter + ActionLog. ModelClient stays as a thin LLM wrapper.
- **Do NOT implement transcript recording** — that's Story 3.6.
- **Do NOT implement UserSimHandler or McpHandler** — Stories 3.5 and 3.6. `send_message` and `make_call` still return ErrorResponse("Unknown tool").
- **Do NOT implement pending_responses** — Story 3.5. Keep passing empty list.
- **Do NOT use `.get()` on `_tool_map` or handler dicts** that are guaranteed populated. Only use `.get()` in `_summarize_tool_call()` where LLM args are not guaranteed.
- **Do NOT change PromptBuilder** — it already handles action log entries.
- **Do NOT forget to pass `tools=self.tools`** in `continue_conversation` calls — LiteLLM requires tools on every call for the model to make tool calls.
- **Do NOT forget `encoding="utf-8"`** on any file operations.
- **Do NOT break existing test patterns** — existing tests mock `ModelClient.complete` returning no tool calls. These must keep passing unmodified.

### Previous Story Intelligence

From Story 3.3 implementation:
- ToolRouter debug log event was renamed from `tool_routed` to `tool_dispatched` to avoid collision with orchestrator's INFO-level `tool_routed` event. The orchestrator's `tool_routed` event is the canonical one for tests.
- TYPE_CHECKING blocks are required for type-only imports (ruff TC001/TC003). Any new imports used only in annotations must go in `if TYPE_CHECKING:` blocks with `from __future__ import annotations` at the top.
- Pre-commit: mixed line endings on Windows auto-fix on first run, pass on second.
- Pre-existing test failure in `test_sms_per_heartbeat` — exclude with `-k "not test_sms_per_heartbeat"` when running targeted tests.
- Code review added path traversal guard to MemoryHandler (`_resolve_memory_path`) and `max(0, count)` clamping to `get_recent_updates`. These patterns should inform defensive coding at system boundaries.

[Source: _bmad-output/implementation-artifacts/3-3-toolrouter-scenariodatahandler-memoryhandler.md#Dev Agent Record]

### Testing Patterns

**Multi-turn loop tests require two mocks:**
- `ModelClient.complete` — for the initial turn 0 call
- `ModelClient.continue_conversation` — for subsequent turn 1+ calls

Example mock setup for a 2-turn heartbeat:
```python
mock_complete.return_value = AgentResponse(
    text="Let me check.",
    tool_calls=[ParsedToolCall(id="call_1", name="query_wearable", arguments={})],
)
mock_continue.return_value = AgentResponse(text="Done.", tool_calls=[])
```

For max_tool_turns tests, make both mocks ALWAYS return tool calls:
```python
mock_complete.return_value = AgentResponse(
    text="Checking...",
    tool_calls=[ParsedToolCall(id="call_1", name="list_memories", arguments={})],
)
mock_continue.return_value = AgentResponse(
    text="More...",
    tool_calls=[ParsedToolCall(id="call_2", name="list_memories", arguments={})],
)
```

Use `structlog.testing.capture_logs()` to verify log events.

For action log accumulation test, inspect the `user_message` arg passed to `mock_complete` on the second heartbeat — it should contain action log text from the first heartbeat's tool calls.

[Source: tests/runner/test_orchestrator.py — existing mock patterns]
[Source: tests/conftest.py — small_scenario_package fixture]

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 4] — Rolling action log
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions — Decision 6] — Multi-turn tool loop
- [Source: _bmad-output/planning-artifacts/architecture.md#Component Architecture] — Orchestrator + ActionLog
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Flow] — Tool routing in heartbeat loop
- [Source: _bmad-output/planning-artifacts/epics.md#Story 3.4] — Original acceptance criteria
- [Source: src/crisis_bench/runner/orchestrator.py] — Current heartbeat loop to modify
- [Source: src/crisis_bench/runner/model_client.py] — ModelClient to extend
- [Source: src/crisis_bench/prompt.py:140-224] — PromptBuilder already wired for action log
- [Source: src/crisis_bench/models/runtime.py:182-191] — ActionLogEntry model
- [Source: src/crisis_bench/models/runtime.py:214-230] — RunConfig with max_tool_turns, action_log_window
- [Source: tests/runner/test_orchestrator.py] — Existing test patterns
- [Source: tests/conftest.py] — Shared fixtures
- [Source: _bmad-output/implementation-artifacts/3-3-toolrouter-scenariodatahandler-memoryhandler.md] — Previous story context

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

None.

### Completion Notes List

- Refactored `ModelClient.complete()` by extracting `_call()` private method. Added `continue_conversation()` public method for multi-turn follow-ups. No breaking changes to existing `complete()` interface.
- Added `build_assistant_message()` and `build_tool_result_message()` module-level helpers in `model_client.py`. These correctly sanitize tool names (dots→`__`) and serialize arguments to JSON strings as required by LiteLLM/OpenAI format.
- Created `ActionLog` inline class in `orchestrator.py` with `record()` and `get_window()` methods. Added `_classify_action()` and `_summarize_tool_call()` helper functions.
- Replaced single-pass tool routing in `Orchestrator.run()` with multi-turn while loop. Turn 0 uses `complete()`, subsequent turns use `continue_conversation()`. Loop terminates when agent returns no tool calls or `max_tool_turns` is reached.
- Action log entries are recorded for each tool call and passed to PromptBuilder's `build_user_message()` (which was already wired to accept them).
- Updated `test_orchestrator_routes_tool_calls` to mock both `complete` and `continue_conversation`.
- Created 12 new tests in `test_action_log.py` covering ActionLog, _classify_action, and _summarize_tool_call.
- Created 3 new orchestrator tests: `test_multi_turn_tool_loop`, `test_max_tool_turns_reached`, `test_action_log_accumulates_across_heartbeats`.
- Created 5 new model_client tests: `test_continue_conversation`, `test_build_assistant_message_with_tool_calls`, `test_build_assistant_message_no_tool_calls`, `test_build_assistant_message_none_text`, `test_build_tool_result_message`.
- All 195 tests pass (1 pre-existing skip). mypy clean. ruff clean on changed files (pre-existing errors in other files noted as audit items).

### Change Log

- 2026-02-28: Implemented multi-turn tool loop, ActionLog, ModelClient refactor, message builders, and comprehensive tests.

### File List

- `src/crisis_bench/runner/model_client.py` — Modified: extracted `_call()`, added `continue_conversation()`, added `build_assistant_message()`, added `build_tool_result_message()`
- `src/crisis_bench/runner/orchestrator.py` — Modified: added `ActionLog` class, `_classify_action()`, `_summarize_tool_call()`, replaced single-pass routing with multi-turn loop
- `tests/runner/test_action_log.py` — New: 12 unit tests for ActionLog, _classify_action, _summarize_tool_call
- `tests/runner/test_orchestrator.py` — Modified: updated routing test, added 3 multi-turn tests
- `tests/runner/test_model_client.py` — Modified: added 5 tests for continue_conversation and message builders
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Modified: 3-4 status ready-for-dev → in-progress → review
