"""Typer CLI application — command routing for SBS."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from sbs import __version__

app = typer.Typer(
    name="sbs",
    help="Convert ChatGPT/Claude conversations into a Zettelkasten-style Obsidian vault.",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"sbs v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-V", help="Show version and exit.", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Second Brain Starter CLI."""


@app.command()
def convert(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing exported conversation JSON files.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output vault directory.")] = Path("./vault"),
    provider: Annotated[str, typer.Option(help="LLM provider: anthropic | openai")] = "anthropic",
    model: Annotated[Optional[str], typer.Option(help="Main model name.")] = None,
    cheap_model: Annotated[Optional[str], typer.Option(help="Cheap model name.")] = None,
    concurrency: Annotated[int, typer.Option(help="Max concurrent LLM calls.")] = 3,
    checkpoint_dir: Annotated[Path, typer.Option(help="Checkpoint directory.")] = Path("./.sbs-checkpoints"),
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Estimate cost only.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging.")] = False,
) -> None:
    """Parse conversations and generate an Obsidian vault."""
    import asyncio

    from sbs.config import Config
    from sbs.pipeline.runner import run_pipeline

    config = Config(
        input_dir=input_dir,
        output_dir=output,
        provider=provider,  # type: ignore[arg-type]
        concurrency=concurrency,
        checkpoint_dir=checkpoint_dir,
        dry_run=dry_run,
        verbose=verbose,
    )
    if model:
        config.model = model
    if cheap_model:
        config.cheap_model = cheap_model

    asyncio.run(run_pipeline(config))


@app.command()
def estimate(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing exported conversation JSON files.")],
) -> None:
    """Estimate token usage and cost without running the pipeline."""
    from sbs.config import Config

    config = Config(input_dir=input_dir, dry_run=True)
    # Delegate to pipeline in dry-run mode
    import asyncio

    from sbs.pipeline.runner import run_pipeline

    asyncio.run(run_pipeline(config))


@app.command()
def resume(
    checkpoint_path: Annotated[Path, typer.Argument(help="Path to checkpoint file or directory.")],
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resume a pipeline from a checkpoint."""
    import asyncio

    from sbs.pipeline.runner import resume_pipeline

    asyncio.run(resume_pipeline(checkpoint_path, verbose=verbose))


@app.command()
def validate(
    vault_dir: Annotated[Path, typer.Argument(help="Path to the Obsidian vault to validate.")],
) -> None:
    """Validate an existing vault for quality."""
    console.print(f"[bold]Validating vault:[/bold] {vault_dir}")
    # Will be implemented in Phase 9
    console.print("[yellow]Validate command not yet implemented.[/yellow]")
