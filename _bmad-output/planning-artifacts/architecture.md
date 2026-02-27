---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7]
inputDocuments:
  - _bmad-output/brainstorming/brainstorming-session-2026-02-21.md
  - _bmad-output/brainstorming/remaining-brainstorm-plan.md
  - system_prompt.py
  - openclaw_base_files/AGENTS.md
  - openclaw_base_files/SOUL.md
  - openclaw_base_files/IDENTITY.md
  - openclaw_base_files/USER.md
  - openclaw_base_files/TOOLS.md
workflowType: 'architecture'
project_name: 'crisis_bench'
user_name: 'Mauk'
date: '2026-02-25'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

1. **Scenario Generation** — Deterministic Python pipeline producing complete-day JSON scenario files. PersonSchedule backbone with 7 module generators (health, location, weather, comms, calendar, financial, crisis injector). Seeded randomness for reproducibility.

2. **Orchestrator / Runner** — Heartbeat loop replaying scenario files against an LLM agent. Routes tool calls to appropriate handlers (custom tools, MCP servers, Human Simulator, 911 Operator). Records full transcript. Handles multi-turn tool calls within a single heartbeat.

3. **Agent System Prompt** — OpenClaw-style modular prompt (SOUL, IDENTITY, USER, MEMORY, HEARTBEAT_BEHAVIOR, SAFETY). Zero emergency framing. Built from scenario config at runtime.

4. **Human Simulator** — Separate LLM playing David Mitchell. Brief, casual responses pre-crisis. Silent post-crisis. Also plays contacts (Sarah, etc.) when messaged.

5. **911 Operator Simulator** — Separate LLM following NENA dispatch protocol. Activated only when agent calls 911.

6. **Tool System** — ~25 custom controlled tools (phone, messages, health, memory, email, calendar, weather, notes, reminders, location, finance) + ~20-25 real MCP servers (Spotify, stocks, Wikipedia, HN, Reddit, unit converter) as noise filler. Tool availability varies by noise tier.

7. **Scoring System** — Post-run evaluation combining heuristic checks (did agent call 911? text someone?) with LLM-as-judge for nuanced assessment. Metrics: detection, detection-in-memory, action type, time-to-action.

8. **Memory System** — File-based key-value store modeled on OpenClaw's memory architecture (plain Markdown files, daily logs + curated long-term memory). Agent's only continuity across heartbeats. Pre-seeded with realistic history simulating weeks of prior operation.

**Non-Functional Requirements:**

- **Reproducibility** — Scenario files are the published artifact. Same file + same model = same test. Custom tools are fully deterministic.
- **Fresh context per heartbeat** — No conversation stacking. Each heartbeat is an independent LLM call. Token cost roughly constant (except growing action_log).
- **No emergency priming** — System prompt, tool names, tool descriptions, and module names must avoid any health/emergency/safety framing. This is a benchmark integrity constraint.
- **Multi-provider support** — Must test across 3-4 different LLM providers (OpenAI, Anthropic, Google, etc.).
- **Full-day realism** — ~140 heartbeats of mundane assistant operation before crisis. Cost is explicitly not a concern.

**Scale & Complexity:**

- Primary domain: Research benchmark / LLM evaluation harness
- Complexity level: High
- Estimated architectural components: 8-10 major components
- Key challenge: orchestrating multiple LLM actors with deterministic scenario replay and structured evaluation

### Technical Constraints & Dependencies

- **Language:** Python
- **LLM APIs:** Must abstract across multiple providers (tool calling conventions differ)
- **MCP Protocol:** Real MCP servers for noise tools — adds external dependency
- **Heartbeat model:** Each heartbeat = 1 system prompt + 1 user message + N tool-call rounds. Orchestrator must loop tool calls until agent produces no more calls.
- **Scenario contract:** The JSON scenario file is the interface between generation and execution. Its schema is a critical design decision.
- **Transcript format:** Must capture everything needed for both heuristic and LLM-judge scoring.
- **Memory realism:** Agent memory must convincingly simulate weeks of prior operation. OpenClaw reference shows memory is plain Markdown with daily logs + curated MEMORY.md — pre-seeded content must match this pattern and feel organic, not synthetic.

### Cross-Cutting Concerns Identified

1. **Determinism boundary** — Custom tools are deterministic (scenario-driven). MCP tools are not. This boundary must be explicit in architecture. Scoring only touches deterministic outputs.
2. **Transcript/logging** — Every actor interaction (agent, human sim, 911 operator) must be captured in a structured transcript for post-run scoring.
3. **Tool routing** — Single tool-call interface from agent's perspective, but calls route to: (a) scenario data lookups, (b) memory store, (c) Human Simulator LLM, (d) 911 Operator LLM, (e) real MCP servers. Router is architecturally central.
4. **LLM provider abstraction** — Different providers have different tool-calling formats. Need a common interface.
5. **Action log growth** — Only non-constant token cost factor. May need rolling window or truncation strategy by heartbeat 140.
6. **Memory bootstrapping** — Pre-seeded memories must feel like real accumulated agent history. Design decision: how much fake history, in what format, and how is it presented to the agent each heartbeat.

## Tech Stack & Starter Foundation

### Primary Technology Domain

Python CLI research benchmark — no web UI, no frontend framework. This is a harness that generates scenario files, replays them against LLM providers, and scores the results.

### Tech Stack Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Python** | 3.12 | User requirement. Stable, performant, broad LLM SDK support. |
| **Package manager** | uv | User requirement. Fast, handles venv + deps + Python version. |
| **LLM provider** | LiteLLM (SDK mode) | ~37k stars, 58M+ monthly downloads, auto-translates tool calling across all providers. Single `completion()` interface for OpenAI/Anthropic/Google/etc. SDK mode avoids proxy gotchas (DB bloat, memory leaks). Most adopted in research/ML community. |
| **Structured LLM output** | Instructor + LiteLLM | For the scoring/judge component. Purpose-built for extracting Pydantic models from LLM responses. 12k+ stars, used by OpenAI/Google/Microsoft teams. |
| **MCP client** | Official `mcp` Python SDK | For connecting to real MCP servers as noise tools. Async-native. |
| **Async** | asyncio for orchestrator + MCP; sync for generators | MCP SDK is async-native; orchestrator does I/O routing to multiple actors. Generators are offline/batch — no concurrency needed. |
| **Testing** | pytest + pytest-asyncio | Standard. Modules should have unit tests where useful. |
| **Data validation** | Pydantic v2 | Scenario file schema, heartbeat payloads, tool call contracts, scoring models. |
| **Logging** | structlog | Structured logging for transcript capture and debugging. |

### Pre-commit Configuration

Adapted from vrm-ai-agent project:

| Hook | Purpose |
|---|---|
| pre-commit-hooks | end-of-file-fixer, trailing-whitespace, check-ast, fix-encoding-pragma, mixed-line-ending |
| uv-lock | Keep lockfile in sync with pyproject.toml |
| ruff | Linting + formatting (replaces black + flake8 in one tool) |
| codespell | Catch typos in code and docs |
| gitleaks | Prevent accidental secret commits |
| mypy | Strict type checking (--check-untyped-defs, --disallow-untyped-defs, --warn-unreachable) |
| pip-audit | Dependency vulnerability scanning |

### Alternatives Evaluated

| Library | Stars | Why Not |
|---|---|---|
| Pydantic AI | ~15k | Full agent framework — overkill when we just need unified LLM calls. Could be useful if project evolves into agent-building. |
| AISuite (Andrew Ng) | ~13.5k | No streaming, stale releases (last Dec 2024), pre-1.0. Stars inflated by name recognition. |
| Magentic | ~2.4k | Solo maintainer, 4-month release gap. Bus-factor risk. |
| Mirascope | ~1.4k | Tiny community, niche. Active but too small for research dependency. |
| Direct SDKs | N/A | Maintenance burden — writing your own tool-calling translation layer across 3+ providers is not justified when LiteLLM exists. |

### Memory Bootstrapping Strategy

**Key decision:** Pre-seeded agent memories will be derived from **real OpenClaw usage data** — actual accumulated memory from weeks of live operation, anonymized and adapted to fit the benchmark persona. This produces authentically organic memory content that no synthetic generation can match.

**Process:**
1. Extract real OpenClaw memory files (daily logs + MEMORY.md) from live deployment
2. Anonymize and adapt to benchmark persona (David Mitchell or alternate profile)
3. Adjust capabilities references to match benchmark agent's tool set
4. Result: a reusable "lived-in" memory base that any crisis scenario can plug into
5. Memory base is scenario-independent — same history works for cardiac arrest, CO, fire, etc.
6. One week of memory history is sufficient — realistic for a newly set up assistant

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

1. **Scenario package format** — Directory structure (zippable for distribution). Enables memory reuse across scenarios. Each package includes a `manifest.json` with content hash (SHA-256 of heartbeats data), generator version, and generation timestamp for reproducibility.
2. **Nested JSON transcript** — One object per heartbeat with structured turns, tool calls, and memory ops. Transcript embeds scenario manifest hash so results are always traceable to exact scenario version.
3. **File-based memory store** — Real Markdown files on disk mirroring OpenClaw. Writes are synchronous — a `write_memory` followed by `read_memory` in the same heartbeat always returns the written content. No caching layer. Pre-seeded with ~1 week of history derived from real OpenClaw usage data.
4. **Rolling action log** — Last N actions in detail + summary count of earlier actions. N is configurable in runner config (default: 20). Actual optimal value to be determined by token budget analysis once real T4 payloads are measured.
5. **Coordinator pattern orchestrator** — Pluggable handlers for tool routing, model calls, transcript recording, memory. Components: ScenarioLoader, PromptBuilder, ModelClient, ToolRouter (with ScenarioDataHandler, MemoryHandler, UserSimHandler, McpHandler), TranscriptRecorder, ActionLog.
6. **Multi-turn tool loop** — Agent gets multiple turns per heartbeat (configurable max, default: 10) until no more tool calls. At max turns, return clean status: `{"status": "heartbeat_complete", "message": "Maximum tool calls reached for this update. Remaining actions will carry to next update."}` — allows agent to still write to memory if needed.
7. **Agent has its own identity** — Jarvis texts/calls as itself, not impersonating the user. David knows Jarvis is his AI assistant — User Simulator prompt must explicitly state this.
8. **No immediate contact responses** — `send_message` returns `{"status": "delivered"}` (void-like). No read receipts, no response. Only David (LLM) responds pre-crisis, silent post-crisis. 911 calls logged as action but not simulated in v0.5.
9. **Fixed post-crisis window** — Always run N heartbeats after crisis (configurable, default: 5). No early termination. Judge evaluates full post-crisis window behavior.
10. **Tool naming: core flat, extensions namespaced** — Core tools have no prefix (`make_call`, `send_message`, `query_device`, `read_memory`). MCP noise tools are server-namespaced (`spotify.search`, `stocks.get_price`). Zero health/emergency language anywhere agent-visible.
11. **Tool return contracts as Pydantic models** — Every custom tool has a defined Pydantic response model. This is part of the architecture, not an implementation detail.

**Important Decisions (Shape Architecture):**

12. **OpenClaw alignment & divergence doc** — Explicit documentation of where CrisisBench diverges from OpenClaw and why, AND what was deliberately kept the same and why. Strengthens paper methodology — reviewers can see architecture mirrors a real deployed system with specific modifications for experimental control.
13. **Notification-based messaging** — Each heartbeat's comms module contains ONLY items that arrived since the previous heartbeat. Emails, Slack messages, SMS, missed calls, voicemails, and social notifications appear once and are not repeated in subsequent heartbeats. The generator produces per-heartbeat deltas (not cumulative state). Agent can pull conversation threads via `get_conversations()` if it wants context. CommsData field names use `new_` prefix to reinforce this: `new_emails`, `new_slack_messages`, `new_missed_calls`, `new_voicemails`, `new_sms`, `new_notifications`.
14. **v0.5 vs v1.0 actor model:**
    - v0.5: Agent + User Simulator (LLM) + Scenario Data. 911 calls logged, not simulated.
    - v1.0: Adds 911 Operator Simulator (LLM), live contact responses.

**Deferred Decisions (Post-MVP):**

- Semantic/vector memory search (v2, for multi-day simulations)
- 911 conversation quality scoring (v1.0)
- False positive testing with normal-day scenarios (v2)
- Contact response simulation (v1.0)

### Data Architecture

**Scenario Package Structure:**
```
cardiac-arrest-t4-seed42/
├── manifest.json          # Content hash, generator version, timestamp
├── scenario.json          # Metadata, person profile, contacts, crisis config
├── heartbeats.json        # All heartbeat payloads (the big file)
├── memories/              # Pre-seeded memory files (reusable across scenarios)
│   ├── user_profile.md
│   ├── preferences.md
│   ├── health_baseline.md
│   ├── work_context.md
│   ├── recurring_notes.md
│   └── yesterday.md
└── tools.json             # Tool definitions for this noise tier
```

**Transcript Structure (per heartbeat):**
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
          "result": {...},
          "routed_to": "scenario_data"
        }
      ]
    }
  ],
  "memory_ops": [
    {"op": "write", "key": "emergency", "content": "..."}
  ],
  "user_sim_interactions": [
    {"type": "message", "agent_sent": "...", "david_response": "..."}
  ]
}
```

### Component Architecture (v0.5)

```
Orchestrator
  ├── ScenarioLoader        — reads scenario package, validates against Pydantic schema
  ├── PromptBuilder         — assembles system prompt + heartbeat context from scenario data
  ├── ModelClient            — LiteLLM wrapper, handles tool calling loop (max N turns)
  ├── ToolRouter             — dispatches tool calls to handlers
  │     ├── ScenarioDataHandler   — query_device, list_events, get_forecast, etc.
  │     ├── MemoryHandler         — read_memory/write_memory/list_memories (file-based, sync)
  │     ├── UserSimHandler       — routes messages/calls to User Simulator LLM
  │     └── McpHandler            — forwards to real MCP servers (noise tools)
  ├── TranscriptRecorder     — captures nested JSON per heartbeat
  └── ActionLog              — manages rolling window (configurable N)
```

### Tool Return Contracts

All custom tools return Pydantic-validated responses:

| Tool | Returns | Notes |
|---|---|---|
| `send_message(contact_id, text)` | `{"status": "delivered"}` | Void-like. No read receipt. |
| `make_call(number)` | `{"status": "connected"/"no_answer", "transcript": "..."}` | 911: logged as connected. Contacts: no answer. David: David Sim responds. |
| `query_device(device_id)` | Full sensor dump + device metadata | From scenario data. |
| `get_recent_updates(count)` | Last N heartbeat payloads | From scenario data. |
| `read_memory(key)` | `{"content": "..."}` or `{"content": null}` | Synchronous file read. |
| `write_memory(key, content)` | `{"status": "written"}` | Synchronous file write. |
| `list_memories()` | `{"keys": ["...", "..."]}` | Lists memory directory. |
| `get_contacts()` | Contact list from scenario | Static. |
| `get_conversations()` | Recent message threads | Agent-sent messages + any scripted responses. |
| `list_events(date)` | Calendar events from scenario | Static per day. |
| `get_forecast(location)` | Weather from scenario data | Matches heartbeat weather module. |
| `get_balance(account)` | Financial data from scenario | Static or scripted changes. |

### OpenClaw Alignment & Divergence

**Deliberate Alignments (kept the same, and why):**

| Aspect | Why Aligned |
|---|---|
| SOUL.md personality model | Agent should feel like a real deployed assistant, not a test subject. Natural personality = natural behavior. |
| File-based Markdown memory | Mirrors how real agents persist knowledge. Familiar pattern for LLMs trained on OpenClaw-style systems. |
| Heartbeat concept | Periodic data updates with agent deciding to act or stay quiet is the core interaction model. |
| Identity files (name, vibe) | Gives agent consistent persona across heartbeats. |
| "Be resourceful before asking" principle | Encourages autonomous action — critical for crisis detection. |
| Memory as sole continuity | Each session is fresh, files persist. This IS the benchmark's core mechanic. |

**Deliberate Divergences (changed, and why):**

| Aspect | OpenClaw (Real) | CrisisBench (Benchmark) | Why We Diverge |
|---|---|---|---|
| Data delivery | Agent actively polls (reads emails, checks calendar, calls tools) | Push-based — all module data arrives in heartbeat payload | Deterministic control. Push ensures every model sees identical information. |
| Memory tools | `memory_search` (semantic/vector) + `memory_get` (file read) | Simple `read_memory` / `write_memory` / `list_memories` | Simpler = fewer confounds. ~1 week of memory is small enough for key-value access. |
| Heartbeat prompt | Agent reads HEARTBEAT.md checklist, decides what to check | No checklist. Agent receives data and decides what to do with it. | Removes a variable. Checklist content would influence behavior unpredictably. |
| Session continuity | Conversation history within session, compaction when long | Fresh context every heartbeat. Zero conversation history. | Isolates each heartbeat as independent test. Memory writes are the only continuity. |
| Tool definitions | Agent discovers tools through workspace docs and skills | All tools defined upfront in system prompt per noise tier | Reproducibility. Every model sees exactly the same tool set. |
| Memory flush | Auto-triggered before context compaction | N/A — no compaction, fresh context each time | Not applicable in fresh-context model. |
| Active hours | Agent respects quiet hours (23:00-08:00) | No quiet hours — simulation runs 06:30-18:05+ | Full day is the test. No heartbeats skipped. |

### Simulation End Conditions (v0.5)

1. Orchestrator replays all pre-crisis heartbeats from scenario file (heartbeats 0 through ~139)
2. Crisis heartbeat fires (heartbeat ~140) — module data contains crisis signals
3. Run exactly `max_post_crisis_heartbeats` more heartbeats (configurable, default: 5)
4. Simulation ends. Full transcript saved.
5. Scorer evaluates the complete transcript (pre-crisis + crisis + post-crisis window)

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Python code:** Standard Python conventions.
- Files/modules: `snake_case` — `scenario_loader.py`, `tool_router.py`
- Functions/variables: `snake_case` — `build_system_prompt()`, `query_device()`
- Classes: `PascalCase` — `ScenarioLoader`, `HeartbeatPayload`
- Constants: `UPPER_SNAKE` — `MAX_TOOL_TURNS`, `DEFAULT_POST_CRISIS_BEATS`
- Private: `_internal_method()`, no dunder abuse

**JSON fields (scenario files, transcripts, tool responses):** `snake_case` throughout. Never camelCase. Python ecosystem convention.

**Tool names (agent-facing):** `snake_case`. Flat for core, dotted for MCP.
- Core: `make_call`, `send_message`, `read_memory`, `query_device`
- MCP: `spotify.search`, `stocks.get_price`

### Structure Patterns

**Project layout:**

```
crisis_bench/
├── src/
│   └── crisis_bench/
│       ├── generator/          # Scenario generation (offline, sync)
│       │   ├── __init__.py
│       │   ├── generate.py     # Entry point
│       │   ├── schedule.py     # PersonSchedule
│       │   └── modules/        # Health, location, weather, comms, calendar, financial, crisis
│       ├── runner/             # Benchmark execution (online, async)
│       │   ├── __init__.py
│       │   ├── run.py          # Entry point
│       │   ├── orchestrator.py
│       │   ├── model_client.py
│       │   ├── tool_router.py
│       │   ├── transcript.py
│       │   └── handlers/       # ScenarioData, Memory, UserSim, Mcp
│       ├── scorer/             # Post-run evaluation
│       │   ├── __init__.py
│       │   ├── score.py        # Entry point
│       │   └── judge.py        # LLM-as-judge via Instructor
│       ├── models/             # Pydantic schemas (shared contract)
│       │   ├── scenario.py     # Scenario package, manifest, heartbeat payloads
│       │   ├── runtime.py      # Transcript, tool responses, action log
│       │   └── scoring.py      # Scoring models, judge output
│       └── prompt.py           # System prompt builder (single module)
├── tests/
│   ├── generator/
│   ├── runner/
│   ├── scorer/
│   └── models/
├── scenarios/                  # Generated scenario packages
├── results/                    # Benchmark run outputs
├── pyproject.toml
└── .pre-commit-config.yaml
```

**Key conventions:**
- Tests mirror `src/` structure in a top-level `tests/` directory, not co-located
- Pydantic models live in `models/` — the shared contract between generator, runner, and scorer
- Each major component (generator, runner, scorer) has its own entry point
- Single CLI with subcommands: `crisis-bench generate`, `crisis-bench run`, `crisis-bench score`

### Format Patterns

**Pydantic model conventions:**
- **Frozen for serialized output:** Scenario files, heartbeat payloads, transcripts, tool responses use `model_config = ConfigDict(frozen=True)`. These are published artifacts — immutable once created.
- **Mutable during generation:** Generator uses regular dicts/dataclasses internally, constructs frozen Pydantic models only at serialization time.
- All tool responses are Pydantic models with defined contracts.
- Use `Field(description="...")` on all fields — descriptions may end up in tool schemas.

**Error handling:**
- Tool call errors return a Pydantic error response, never raise to the agent: `{"status": "error", "message": "Device not found"}`
- Orchestrator-level errors (LLM API failure, MCP timeout) logged via structlog, raised to runner for retry/abort
- No silent failures. Every error either returned to agent (tool) or logged and surfaced (infra).

**Logging:**
- structlog for all logging
- Log levels: `DEBUG` tool call details, `INFO` heartbeat progression, `WARNING` MCP timeouts, `ERROR` LLM failures
- Every log entry includes `heartbeat_id` as context

### Process Patterns

**Configuration hierarchy:**
- Scenario package defines the world (heartbeats, memories, tools, person)
- Scenario manifest declares requirements (minimum tools, expected tier, expected memory keys) — runner validates before starting
- Runner config defines execution (model, max turns, post-crisis beats, action log window)
- CLI args override runner config
- No magic defaults buried in code — all defaults in a single config schema

**Run output:** Every benchmark run produces alongside the transcript:
- `run_config.json` — exact configuration used: model name/version, temperature, max tokens, tool definitions hash, scenario hash, all runner config values. Non-negotiable for reproducibility.

**Testing conventions:**
- Generator modules: test determinism (same seed = same output)
- Tool handlers: test return contracts match Pydantic models
- Orchestrator: test with mocked `ModelClient` — no real LLM calls in unit tests
- Scorer: test with fixture transcripts
- Integration tests: cheap/fast model for end-to-end smoke tests

### Enforcement

- **ruff** enforces style (formatting + linting)
- **mypy** enforces type safety (strict mode)
- **Pre-commit hooks** run on every commit — no bypassing
- Structural conventions enforced by code review and the architecture doc itself

## Project Structure & Boundaries

### Complete Project Directory Structure

```
crisis_bench/
├── pyproject.toml                    # uv project config, dependencies, CLI entry points
├── uv.lock                           # Lockfile
├── .pre-commit-config.yaml           # Ruff, mypy, codespell, gitleaks, pip-audit
├── .gitignore
├── .env.example                      # API keys ONLY (credentials, not behavior)
│
├── src/
│   └── crisis_bench/
│       ├── __init__.py
│       ├── cli.py                    # CLI entry: crisis-bench {generate,run,score}
│       ├── prompt.py                 # System prompt builder (single module)
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── scenario.py           # ScenarioManifest, PersonProfile, Contact, HeartbeatPayload,
│       │   │                         #   ModuleData, MemoryFile, ToolDefinition, ScenarioPackage
│       │   ├── runtime.py            # ToolCall, ToolResponse, HeartbeatTranscript, Turn,
│       │   │                         #   ActionLogEntry, UserSimInteraction, RunConfig
│       │   └── scoring.py            # ScoringResult, DetectionMetrics, ActionMetrics, JudgeOutput
│       │
│       ├── generator/
│       │   ├── __init__.py
│       │   ├── generate.py           # CLI handler, orchestrates generation pipeline
│       │   ├── schedule.py           # PersonSchedule, ActivityBlock, SCHEDULE constant
│       │   └── modules/
│       │       ├── __init__.py
│       │       ├── health.py         # HealthGenerator — HR, SpO2, steps, accel, etc.
│       │       ├── location.py       # LocationGenerator — GPS, geofence, POIs
│       │       ├── weather.py        # WeatherGenerator — temp, humidity, forecast
│       │       ├── comms.py          # CommsGenerator — scripted emails, SMS, Slack
│       │       ├── calendar.py       # CalendarGenerator — events, reminders
│       │       ├── financial.py      # FinancialGenerator — transactions, stock walks
│       │       └── crisis.py         # CrisisInjector — overwrites module data at trigger
│       │
│       ├── runner/
│       │   ├── __init__.py
│       │   ├── run.py                # CLI handler, sets up and launches orchestrator
│       │   ├── orchestrator.py       # Main heartbeat loop + ActionLog (inline class)
│       │   ├── model_client.py       # LiteLLM wrapper, tool calling loop (max N turns)
│       │   ├── tool_router.py        # Dispatches tool calls via ToolHandler.can_handle()
│       │   ├── transcript.py         # TranscriptRecorder — writes nested JSON
│       │   └── handlers/
│       │       ├── __init__.py
│       │       ├── base.py           # ToolHandler protocol: can_handle() + async handle()
│       │       ├── scenario_data.py  # query_device, list_events, get_forecast, get_balance, etc.
│       │       ├── memory.py         # read_memory, write_memory, list_memories (sync file I/O)
│       │       ├── user_sim.py      # Routes messages/calls to User Simulator LLM
│       │       └── mcp.py            # Forwards tool calls to real MCP servers
│       │
│       └── scorer/
│           ├── __init__.py
│           ├── score.py              # CLI handler, runs heuristic + judge pipeline
│           └── judge.py              # LLM-as-judge via Instructor, structured scoring output
│
├── tests/
│   ├── conftest.py                   # Shared fixtures (sample scenario, mock model client)
│   ├── generator/
│   │   ├── test_schedule.py
│   │   ├── test_health.py
│   │   └── test_determinism.py       # Same seed = same output
│   ├── runner/
│   │   ├── test_orchestrator.py      # With mocked ModelClient
│   │   ├── test_tool_router.py
│   │   └── test_handlers/
│   │       ├── test_memory.py
│   │       └── test_scenario_data.py
│   ├── scorer/
│   │   └── test_score.py
│   └── models/
│       └── test_schemas.py           # Validate Pydantic models serialize/deserialize
│
├── scenarios/
│   ├── example-cardiac-t1-seed0/     # Included in repo — 10 heartbeats, runnable smoke test
│   │   ├── manifest.json
│   │   ├── scenario.json
│   │   ├── heartbeats.json
│   │   ├── memories/
│   │   └── tools.json
│   └── .gitkeep
│
└── results/                          # Benchmark run outputs (gitignored)
    └── .gitkeep
```

### ToolHandler Protocol

The key abstraction for the tool system:

```python
class ToolHandler(Protocol):
    def can_handle(self, tool_name: str) -> bool: ...
    async def handle(self, tool_name: str, args: dict) -> ToolResponse: ...
```

The `ToolRouter` iterates registered handlers and asks `can_handle()`. First match wins. Adding a new handler = write the class, append to the handler list. Zero config changes.

### Data Flow

```
[Scenario Package]
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Orchestrator (heartbeat loop)                  │
│                                                 │
│  for each heartbeat:                            │
│    PromptBuilder ──▶ ModelClient (LiteLLM)      │
│                          │ tool calls           │
│                          ▼                      │
│                      ToolRouter                 │
│                    ┌───┬───┬───┐                │
│                    ▼   ▼   ▼   ▼                │
│              Scenario Memory David MCP          │
│              Data    Handler Sim   Handler       │
│                                                 │
│    All interactions ──▶ TranscriptRecorder       │
└─────────────────────────────────────────────────┘
       │
       ▼
[Transcript + run_config.json]
       │
       ▼
[Scorer (heuristic + LLM judge)]
       │
       ▼
[Scores + evaluation report]
```

### Integration Boundaries

**External (HTTPS/stdio):**

| Boundary | Protocol | Config Location |
|---|---|---|
| LLM providers (agent under test) | LiteLLM → HTTPS | Runner config: `agent_model` |
| LLM provider (David Sim) | LiteLLM → HTTPS | Runner config: `user_sim_model` |
| LLM provider (Judge) | Instructor + LiteLLM → HTTPS | Runner config: `judge_model` |
| MCP servers | `mcp` SDK → stdio/SSE | Runner config: `mcp_servers` |

**Internal (function calls):**

| Boundary | Interface | Contract |
|---|---|---|
| Generator → Scenario package | File system (JSON + MD) | `models/scenario.py` |
| Scenario → Runner | `ScenarioLoader` | Validates schema + manifest requirements |
| ToolRouter → Handlers | `ToolHandler` protocol | `can_handle()` + `handle()` → `ToolResponse` |
| Runner → Transcript | `TranscriptRecorder` | `models/runtime.py` |
| Transcript → Scorer | File system (JSON) | `models/runtime.py` + `models/scoring.py` |

### Configuration Separation

**Environment variables (`.env`):** Credentials only.
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`
- MCP server credentials (Spotify, etc.) — only needed for T3/T4

**Runner config:** Behavior. Specifies all actor models and execution parameters.
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

**`run_config.json` output:** Captures ALL experiment metadata — agent model, David sim model, judge model, temperatures, max tokens, tool definitions hash, scenario hash, all runner config values. Every LLM actor is recorded.

### CLI Design

Single `crisis-bench` command with subcommands:

```bash
crisis-bench generate --crisis cardiac_arrest --tier T4 --seed 42
crisis-bench run --scenario scenarios/cardiac-arrest-t4-seed42/ --config runner_config.json
crisis-bench score --transcript results/run-001/transcript.json
```

**Design note:** Each subcommand's core logic is an importable function, not CLI-bound. This enables future composition (e.g., `crisis-bench benchmark` meta-command) and programmatic use in notebooks/scripts.

## Architecture Validation

### Gaps Resolved

1. **User simulator prompt** → `persona.md` in scenario package. Standardized filename, always the same location. Describes the simulated user (David in v0.5), that they know their AI assistant, and post-crisis behavior. Different scenarios can have different users in future versions.

2. **MCP servers in v0.5** → Always return `{"status": "error", "message": "Service unavailable"}`. No real MCP connections in v0.5. Deterministic, zero external dependencies, consistent across runs. Real MCP connections are a v1.0 feature. McpHandler still exists and is registered for T3/T4 tool names — it just always returns unavailable.

3. **Tool registration flow** → `ScenarioLoader` reads `tools.json` from scenario package. Core handlers (memory, David sim) always registered. Scenario-defined tools map to `ScenarioDataHandler`. MCP tool names map to `McpHandler` (which returns unavailable in v0.5).

### Coherence: PASS

- All tech stack choices compatible (Python 3.12 + uv + LiteLLM + Pydantic v2 + asyncio + mcp SDK)
- Naming conventions consistent (snake_case everywhere: Python, JSON, tool names)
- ToolHandler protocol aligns with async orchestrator
- Frozen Pydantic for output, mutable during generation — clean boundary
- structlog with heartbeat_id context matches nested transcript format

### Requirements Coverage: PASS

All 13 functional requirements mapped to specific components and files. NFRs (reproducibility, no priming, multi-provider, fresh context) all architecturally supported.

### Completeness Checklist

- [x] Project context analyzed
- [x] Tech stack fully specified with rationale
- [x] Core architectural decisions documented (14 decisions)
- [x] OpenClaw alignment & divergence documented
- [x] Tool return contracts defined (Pydantic)
- [x] Component architecture with data flow
- [x] Implementation patterns (naming, structure, format, process)
- [x] Complete project directory tree with all files
- [x] Integration boundaries mapped (external + internal)
- [x] Configuration separation (env vs runner config vs run output)
- [x] CLI design with subcommands
- [x] Scenario package format with manifest + hashing
- [x] v0.5 vs v1.0 scope clearly defined
- [x] Validation gaps identified and resolved

### Architecture Readiness: READY FOR IMPLEMENTATION

**v0.5 Scope Summary:**
- Agent (LLM under test) + User Simulator (LLM) + Scenario Data (scripted)
- 911 calls logged as action, not simulated
- MCP tools always return unavailable (deterministic)
- Scoring: heuristic checks + LLM-as-judge
- One crisis type: cardiac arrest, 4 noise tiers (T1-T4)

**First Implementation Priority:**
1. Set up project scaffolding (pyproject.toml, pre-commit, src/ layout)
2. Define Pydantic models in `models/`
3. Build generator pipeline (schedule → modules → scenario package)
4. Build orchestrator + tool handlers
5. Build scorer
6. Run against 3-4 models across T1-T4
7. Analyze results, write paper
