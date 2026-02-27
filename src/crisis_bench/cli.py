"""CLI entry point for crisis-bench."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from crisis_bench.models.scenario import NoiseTier


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """CrisisBench - LLM agent emergency detection benchmark."""


@main.command()
@click.option(
    "--crisis",
    default="cardiac_arrest",
    show_default=True,
    help="Crisis type to simulate.",
)
@click.option(
    "--tier",
    type=click.Choice(["T1", "T2", "T3", "T4"], case_sensitive=True),
    default="T4",
    show_default=True,
    help="Noise tier controlling module inclusion.",
)
@click.option("--seed", type=int, default=42, show_default=True, help="Random seed.")
@click.option(
    "--date",
    "scenario_date",
    type=str,
    default=None,
    help="Scenario date as YYYY-MM-DD (>= 2027). Default: 2027-06-15.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("scenarios"),
    show_default=True,
    help="Output directory for generated scenario.",
)
def generate(crisis: str, tier: str, seed: int, scenario_date: str | None, output: Path) -> None:
    """Generate scenario packages."""
    from datetime import date
    from typing import cast

    from crisis_bench.generator.generate import generate_scenario

    parsed_date = date.fromisoformat(scenario_date) if scenario_date else None
    scenario_dir = output / f"{crisis}_{tier}_s{seed}"
    package = generate_scenario(
        crisis_type=crisis,
        tier=cast("NoiseTier", tier),
        seed=seed,
        output_path=scenario_dir,
        scenario_date=parsed_date,
    )
    click.echo(f"Scenario written to {scenario_dir}")
    click.echo(f"Content hash: {package.manifest.content_hash}")


@main.command()
@click.option(
    "--scenario",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to scenario package directory.",
)
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to runner configuration JSON file.",
)
def run(scenario: Path, config: Path) -> None:
    """Run benchmark against an LLM agent."""
    import asyncio

    from pydantic import ValidationError

    from crisis_bench.runner.run import run_benchmark
    from crisis_bench.runner.scenario_loader import ScenarioLoadError

    try:
        asyncio.run(run_benchmark(scenario, config))
    except (ScenarioLoadError, ValidationError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc


@main.command()
def score() -> None:
    """Score benchmark transcripts."""
    click.echo("Not implemented yet")
    raise SystemExit(1)
