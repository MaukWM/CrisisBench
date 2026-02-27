# Story 1.1: Project Scaffolding & Quality Gates

Status: done

## Story

As a **developer**,
I want a properly structured Python project with uv, pre-commit hooks, and src/ layout,
so that all future code has consistent quality gates from day one.

## Acceptance Criteria

1. **Given** a fresh clone of the repo **When** I run `uv sync` **Then** a virtual environment is created with Python 3.12 and all dev dependencies installed

2. **Given** the project is set up **When** I run `pre-commit run --all-files` **Then** ruff (lint+format), mypy, codespell, gitleaks, and pip-audit all execute without error

3. **Given** the src/ layout exists **When** I run `crisis-bench --help` **Then** the CLI shows generate, run, and score subcommands (stubs returning "not implemented")

4. **And** pyproject.toml defines the project metadata, dependencies, CLI entry point, and mypy/ruff config

5. **And** .env.example documents required API keys

6. **And** .gitignore covers results/, .env, __pycache__, etc.

7. **And** structlog is configured with a basic setup importable from `crisis_bench`

## Tasks / Subtasks

- [x] Task 1: Create pyproject.toml (AC: 1, 4)
  - [x] 1.1: Project metadata — name: `crisis-bench`, version: `0.1.0`, Python `>=3.12`, description, license, authors
  - [x] 1.2: Runtime dependencies — pydantic (>=2.0), litellm, structlog, instructor, mcp, click (for CLI)
  - [x] 1.3: Dev dependencies group — pytest, pytest-asyncio, mypy, ruff, pre-commit, codespell, pip-audit
  - [x] 1.4: CLI entry point — `[project.scripts] crisis-bench = "crisis_bench.cli:main"`
  - [x] 1.5: Tool configs — `[tool.ruff]` (target Python 3.12, src layout), `[tool.mypy]` (strict: check-untyped-defs, disallow-untyped-defs, warn-unreachable), `[tool.pytest.ini_options]` (asyncio_mode = "auto")
- [x] Task 2: Create src/ layout and package structure (AC: 3, 4)
  - [x] 2.1: Create `src/crisis_bench/__init__.py` — package version, structlog setup function
  - [x] 2.2: Create `src/crisis_bench/cli.py` — Click CLI with `generate`, `run`, `score` subcommands as stubs printing "Not implemented yet"
  - [x] 2.3: Create sub-package stubs — `models/__init__.py`, `generator/__init__.py`, `runner/__init__.py`, `scorer/__init__.py` (empty `__init__.py` files)
  - [x] 2.4: Create `tests/` directory structure — `tests/conftest.py`, `tests/generator/`, `tests/runner/`, `tests/scorer/`, `tests/models/` (empty dirs with `__init__.py`)
- [x] Task 3: Create .pre-commit-config.yaml (AC: 2)
  - [x] 3.1: Configure pre-commit-hooks repo — end-of-file-fixer, trailing-whitespace, check-ast, fix-encoding-pragma, mixed-line-ending
  - [x] 3.2: Configure astral-sh/uv-pre-commit — uv-lock hook
  - [x] 3.3: Configure astral-sh/ruff-pre-commit — ruff (lint) and ruff-format hooks
  - [x] 3.4: Configure codespell — codespell hook
  - [x] 3.5: Configure gitleaks — gitleaks-pre-commit hook (zricethezav/gitleaks)
  - [x] 3.6: Configure mypy — mypy hook with `--strict` equivalent flags, additional_dependencies matching runtime deps
  - [x] 3.7: Configure pip-audit — pip-audit hook (pypa/pip-audit)
- [x] Task 4: Configure structlog (AC: 7)
  - [x] 4.1: Create basic structlog configuration in `src/crisis_bench/__init__.py` — `configure_logging()` function that sets up structlog with console renderer, log level from env var, and is importable as `from crisis_bench import configure_logging`
- [x] Task 5: Create project support files (AC: 5, 6)
  - [x] 5.1: Create `.env.example` — document OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY with comments
  - [x] 5.2: Update `.gitignore` — add results/, .env, __pycache__/, *.egg-info/, .mypy_cache/, .ruff_cache/, dist/, build/, .venv/
  - [x] 5.3: Create `scenarios/.gitkeep` and `results/.gitkeep` placeholder directories
- [x] Task 6: Verify all acceptance criteria (AC: 1, 2, 3)
  - [x] 6.1: Run `uv sync` — verify venv created, all deps installed, Python 3.12 active
  - [x] 6.2: Run `pre-commit install && pre-commit run --all-files` — all hooks pass
  - [x] 6.3: Run `crisis-bench --help` — verify generate, run, score subcommands visible
  - [x] 6.4: Run `python -c "from crisis_bench import configure_logging; configure_logging()"` — verify structlog works
  - [x] 6.5: Run `pytest` — verify test framework runs (even if 0 tests collected, no errors)

## Dev Notes

### Architecture Requirements
[Source: _bmad-output/planning-artifacts/architecture.md]

**Tech Stack (MUST follow exactly):**
- Python 3.12, uv package manager
- Pydantic v2 for data validation (frozen models for output, mutable during generation)
- LiteLLM SDK mode for LLM provider abstraction
- Instructor + LiteLLM for structured LLM output (scorer)
- `mcp` Python SDK for MCP client
- asyncio for orchestrator + MCP; sync for generators
- pytest + pytest-asyncio for testing
- structlog for structured logging

**CLI Design:**
- Single `crisis-bench` command with subcommands: `generate`, `run`, `score`
- Each subcommand's core logic MUST be an importable function, not CLI-bound
- Use Click (or similar) for CLI framework

**Naming Conventions (enforce throughout project):**
- Files/modules: `snake_case` — `scenario_loader.py`, `tool_router.py`
- Functions/variables: `snake_case` — `build_system_prompt()`, `query_device()`
- Classes: `PascalCase` — `ScenarioLoader`, `HeartbeatPayload`
- Constants: `UPPER_SNAKE` — `MAX_TOOL_TURNS`, `DEFAULT_POST_CRISIS_BEATS`
- JSON fields: `snake_case` throughout, never camelCase

**Logging Convention:**
- structlog for all logging
- Log levels: DEBUG tool calls, INFO heartbeats, WARNING MCP timeouts, ERROR LLM failures
- heartbeat_id in all context (future stories will use this)

**mypy Strict Mode (CRITICAL):**
- `--check-untyped-defs`
- `--disallow-untyped-defs`
- `--warn-unreachable`

### Required Project Layout
[Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]

```
crisis_bench/
├── pyproject.toml
├── .pre-commit-config.yaml
├── .gitignore
├── .env.example
├── src/
│   └── crisis_bench/
│       ├── __init__.py
│       ├── cli.py
│       ├── models/
│       │   └── __init__.py
│       ├── generator/
│       │   └── __init__.py
│       ├── runner/
│       │   └── __init__.py
│       └── scorer/
│           └── __init__.py
├── tests/
│   ├── conftest.py
│   ├── generator/
│   ├── runner/
│   ├── scorer/
│   └── models/
├── scenarios/
│   └── .gitkeep
└── results/
    └── .gitkeep
```

### Pre-commit Hook Configuration
[Source: _bmad-output/planning-artifacts/architecture.md#Pre-commit Configuration]

| Hook | Repo | Purpose |
|---|---|---|
| pre-commit-hooks | pre-commit/pre-commit-hooks | end-of-file-fixer, trailing-whitespace, check-ast, fix-encoding-pragma, mixed-line-ending |
| uv-lock | astral-sh/uv-pre-commit | Keep lockfile in sync with pyproject.toml |
| ruff | astral-sh/ruff-pre-commit | Linting + formatting (replaces black + flake8) |
| codespell | codespell-project/codespell | Catch typos in code and docs |
| gitleaks | zricethezav/gitleaks | Prevent accidental secret commits |
| mypy | pre-commit/mirrors-mypy | Strict type checking |
| pip-audit | pypa/pip-audit | Dependency vulnerability scanning |

### Critical Anti-Patterns to Avoid
- Do NOT add prompt.py or any business logic files — this story is scaffolding only
- Do NOT create detailed Pydantic models — that's Stories 1.2-1.4
- Do NOT configure any MCP servers or LLM providers — that's Epic 3
- Do NOT add any health/emergency language anywhere — NFR2 benchmark integrity constraint
- CLI stubs should print "Not implemented yet" and exit, nothing more
- Keep __init__.py files minimal — just enough for the package to be importable

### .env.example Contents
```
# LLM Provider API Keys (credentials only — behavior config goes in runner_config.json)
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GOOGLE_API_KEY=your-google-api-key
```

### Project Structure Notes

- This is a greenfield project — no existing code to work around
- The existing `.gitignore` in the repo should be extended, not replaced
- The existing `system_prompt.py` at project root is a draft reference file — do not integrate it, it will be superseded by `src/crisis_bench/prompt.py` in a later story
- `_bmad/`, `_bmad-output/`, `openclaw_base_files/`, `.claude/`, `.idea/` are project tooling — do not touch
- The `src/` layout with `crisis_bench` package namespace is mandatory per architecture

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Tech Stack & Starter Foundation]
- [Source: _bmad-output/planning-artifacts/architecture.md#Pre-commit Configuration]
- [Source: _bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: _bmad-output/planning-artifacts/architecture.md#CLI Design]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Debug Log References

- Initial `hatchling.backends` build error — fixed to `hatchling.build`
- Missing README.md reference — removed `readme` field from pyproject.toml
- mypy: `package_name` not valid for `click.version_option` with types-click stubs — changed to explicit `version="0.1.0"`
- mypy: `str | None` has no `.upper()` — fixed with explicit `None` check

### Completion Notes List

- All 6 tasks with 22 subtasks completed
- pyproject.toml: hatchling build backend, click CLI, pydantic/litellm/structlog/instructor/mcp runtime deps, full dev dep group, ruff/mypy/pytest tool configs
- src/ layout matches architecture exactly: crisis_bench package with cli.py, __init__.py, 4 sub-packages (models, generator, runner, scorer)
- 7 pre-commit hooks configured and passing: pre-commit-hooks, uv-lock, ruff, codespell, gitleaks, mypy (strict), pip-audit
- structlog configure_logging() importable from crisis_bench, uses LOG_LEVEL env var
- CLI shows generate/run/score subcommands via Click
- 106 packages installed via uv sync (Python 3.12.12)
- All 12 pre-commit hooks pass
- pytest runs (0 tests collected, no errors)

### File List

- `pyproject.toml` (new)
- `.pre-commit-config.yaml` (new)
- `.env.example` (new)
- `.gitignore` (modified)
- `src/crisis_bench/__init__.py` (new)
- `src/crisis_bench/cli.py` (new)
- `src/crisis_bench/models/__init__.py` (new)
- `src/crisis_bench/generator/__init__.py` (new)
- `src/crisis_bench/runner/__init__.py` (new)
- `src/crisis_bench/scorer/__init__.py` (new)
- `tests/__init__.py` (new)
- `tests/conftest.py` (new)
- `tests/generator/__init__.py` (new)
- `tests/runner/__init__.py` (new)
- `tests/scorer/__init__.py` (new)
- `tests/models/__init__.py` (new)
- `scenarios/.gitkeep` (new)
- `results/.gitkeep` (new)
- `uv.lock` (auto-generated)

### Change Log

- 2026-02-25: Story 1.1 implemented — project scaffolding with full quality gates
- 2026-02-27: Closed. No unit tests for scaffolding story — pre-commit hooks serve as the quality gate.
