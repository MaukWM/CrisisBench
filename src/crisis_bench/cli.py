"""CLI entry point for crisis-bench."""

from __future__ import annotations

import click


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """CrisisBench - LLM agent emergency detection benchmark."""


@main.command()
def generate() -> None:
    """Generate scenario packages."""
    click.echo("Not implemented yet")
    raise SystemExit(1)


@main.command()
def run() -> None:
    """Run benchmark against an LLM agent."""
    click.echo("Not implemented yet")
    raise SystemExit(1)


@main.command()
def score() -> None:
    """Score benchmark transcripts."""
    click.echo("Not implemented yet")
    raise SystemExit(1)
