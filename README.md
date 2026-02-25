# CrisisBench

Benchmark measuring whether LLM agents detect life-threatening emergencies buried in routine, noisy data streams and take appropriate autonomous action.

## Quick Start

```bash
uv sync
crisis-bench generate --help
crisis-bench run --help
crisis-bench score --help
```

## Development

```bash
uv sync
pre-commit install
pre-commit run --all-files
pytest
```
