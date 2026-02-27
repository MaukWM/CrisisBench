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
  tools.json         # Tool definitions (placeholder)
  memories/          # Agent memory (placeholder)
```

Heartbeats cover the full day from 06:30 through 100 minutes post-crisis. The same seed, crisis type, and tier always produce an identical scenario.

## Development

```bash
uv sync
pre-commit install
pre-commit run --all-files
pytest
```
