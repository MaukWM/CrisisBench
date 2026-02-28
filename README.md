# CrisisBench

Benchmark measuring whether LLM agents detect life-threatening emergencies buried in routine, noisy data streams and take appropriate autonomous action.

## Quick Start

```bash
uv sync
uv run crisis-bench generate --help
uv run crisis-bench run --help
uv run crisis-bench score --help
```

## Generating Scenarios

Generate synthetic crisis scenarios with configurable noise tiers:

```bash
# Default scenario (cardiac_arrest, tier T4, seed 42)
uv run crisis-bench generate

# Specify tier and seed
uv run crisis-bench generate --tier T1 --seed 100

# All options
uv run crisis-bench generate \
  --crisis cardiac_arrest \
  --tier T4 \
  --seed 42 \
  --date 2027-06-15 \
  --output scenarios
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--crisis` | `cardiac_arrest` | Crisis type |
| `--tier` | `T4` | Noise tier (`T1`-`T4`, see below) |
| `--seed` | `42` | RNG seed for reproducibility |
| `--date` | `2027-06-15` | Scenario date (must be >= 2027) |
| `--output` | `scenarios` | Output directory |

### Tiers

| Tier | Modules | Description |
|------|---------|-------------|
| T1 | health | Medical signals only |
| T2 | + location, weather | Spatial/environmental context |
| T3 | + calendar, comms | Schedule and communication noise |
| T4 | + financial | All modules, maximum noise |

### Output

Each scenario writes to `{output}/{crisis}_{tier}_s{seed}/`:

```
cardiac_arrest_T4_s42/
  manifest.json      # Generator version, content hash, timestamp
  scenario.json      # Person profile, contacts, agent identity
  heartbeats.json    # All sensor data at 5-minute intervals
  tools.json         # Tool definitions available to the agent
  persona.md         # User simulator persona document
  memories/          # Pre-seeded agent memory files
```

Heartbeats cover the full day from 06:30 through 100 minutes post-crisis. The same seed, crisis type, and tier always produce an identical scenario.

## Running Benchmarks

Run a scenario against an LLM agent via LiteLLM:

```bash
# Full run
uv run crisis-bench run \
  --scenario scenarios/cardiac_arrest_T4_s42 \
  --config config-openai.json

# Quick inspection (first 3 heartbeats)
uv run crisis-bench run \
  --scenario scenarios/cardiac_arrest_T4_s42 \
  --config config-openai.json \
  --max-heartbeats 3
```

### Config File

Create a JSON config pointing at any LiteLLM-supported model:

```json
{
  "agent_model": "openai/gpt-5-mini",
  "user_sim_model": "openai/gpt-5-mini",
  "judge_model": "openai/gpt-5-mini",
  "max_post_crisis_heartbeats": 3,
  "model_params": {
    "reasoning_effort": "low"
  }
}
```

Set your API key in a `.env` file or environment variable (e.g. `OPENAI_API_KEY`).

### Run Options

| Flag | Default | Description |
|------|---------|-------------|
| `--scenario` | *(required)* | Path to scenario package directory |
| `--config` | *(required)* | Path to runner config JSON |
| `--max-heartbeats` | all | Stop after N heartbeats (for quick runs) |

### Tools

The agent sees tier-appropriate tools during execution. Tool calls are routed to handlers that return real scenario data:

| Tool | Handler | Description |
|------|---------|-------------|
| `query_wearable` | ScenarioDataHandler | Current wearable sensor data |
| `get_recent_updates` | ScenarioDataHandler | Last N heartbeat payloads |
| `get_contacts` | ScenarioDataHandler | Contact list |
| `get_conversations` | ScenarioDataHandler | Recent conversations |
| `list_events` | ScenarioDataHandler | Calendar events (T3+) |
| `get_forecast` | ScenarioDataHandler | Weather forecast (T2+) |
| `get_balance` | ScenarioDataHandler | Financial balance (T4) |
| `get_transactions` | ScenarioDataHandler | Recent transactions (T4) |
| `read_memory` | MemoryHandler | Read a memory file |
| `write_memory` | MemoryHandler | Write a memory file |
| `list_memories` | MemoryHandler | List memory file keys |
| `send_message` | *(not yet)* | Send message to contact |
| `make_call` | *(not yet)* | Place a phone call |

## Development

```bash
uv sync
pre-commit install
pre-commit run --all-files
uv run pytest
```
