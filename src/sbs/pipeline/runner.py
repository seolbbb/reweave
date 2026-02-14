"""Pipeline runner — sequential stage execution."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

console = Console()


async def run_pipeline(config) -> None:
    """Run the full conversion pipeline."""
    console.print("[bold green]Pipeline started[/bold green]")
    if config.dry_run:
        console.print("[yellow]Dry-run mode — no LLM calls will be made.[/yellow]")
        return
    console.print("[yellow]Pipeline stages not yet implemented.[/yellow]")


async def resume_pipeline(checkpoint_path: Path, verbose: bool = False) -> None:
    """Resume pipeline from checkpoint."""
    console.print(f"[bold]Resuming from:[/bold] {checkpoint_path}")
    console.print("[yellow]Resume not yet implemented.[/yellow]")
