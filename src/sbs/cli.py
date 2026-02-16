"""Typer CLI application — command routing for SBS."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from sbs import __version__

app = typer.Typer(
    name="sbs",
    help="Convert ChatGPT/Claude conversations into a Zettelkasten-style Obsidian vault.",
    no_args_is_help=True,
)
prompt_app = typer.Typer(help="Prompt bundle utilities.")
eval_app = typer.Typer(help="Prompt evaluation utilities.")
app.add_typer(prompt_app, name="prompt")
app.add_typer(eval_app, name="eval")
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"sbs v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Second Brain Starter CLI."""


@app.command()
def convert(
    input_dir: Annotated[
        Path, typer.Argument(help="Directory containing exported conversation JSON files.")
    ],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output vault directory.")
    ] = Path("./vault"),
    provider: Annotated[
        str, typer.Option(help="LLM provider: anthropic | openai | google")
    ] = "anthropic",
    model: Annotated[str | None, typer.Option(help="Main model name.")] = None,
    cheap_model: Annotated[str | None, typer.Option(help="Cheap model name.")] = None,
    concurrency: Annotated[int, typer.Option(help="Max concurrent LLM calls.")] = 3,
    checkpoint_dir: Annotated[
        Path, typer.Option(help="Checkpoint directory.")
    ] = Path("./.sbs-checkpoints"),
    prompt_bundle: Annotated[
        Path | None,
        typer.Option(help="Prompt bundle file/directory path."),
    ] = None,
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
        prompt_bundle=prompt_bundle,
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
    input_dir: Annotated[
        Path, typer.Argument(help="Directory containing exported conversation JSON files.")
    ],
    provider: Annotated[
        str, typer.Option(help="LLM provider: anthropic | openai | google")
    ] = "anthropic",
    model: Annotated[str | None, typer.Option(help="Main model name.")] = None,
    cheap_model: Annotated[str | None, typer.Option(help="Cheap model name.")] = None,
) -> None:
    """Estimate token usage and cost without running the pipeline."""
    from sbs.config import Config
    from sbs.llm.cost import PRICING
    from sbs.parsers.detector import parse_directory

    config = Config(input_dir=input_dir, provider=provider, dry_run=True)  # type: ignore[arg-type]
    if model:
        config.model = model
    if cheap_model:
        config.cheap_model = cheap_model

    conversations = parse_directory(input_dir)
    total_messages = sum(len(c.messages) for c in conversations)
    total_chars = sum(
        sum(len(m.content) for m in c.messages) for c in conversations
    )
    est_tokens = total_chars // 4  # rough estimate: 4 chars per token

    console.print("[bold]Cost Estimation[/bold]")
    console.print(f"  Conversations: {len(conversations)}")
    console.print(f"  Total messages: {total_messages}")
    console.print(f"  Estimated tokens: ~{est_tokens:,}")
    console.print()

    # Estimate calls per stage
    main_pricing = PRICING.get(config.model, (3.0, 15.0))
    cheap_pricing = PRICING.get(config.cheap_model, (0.80, 4.0))

    # Rough estimates: each segment ~ 2x tokens (in+out), extraction ~3x, synthesis ~3x
    est_segment_cost = (est_tokens / 1_000_000) * cheap_pricing[0] * 2
    est_extract_cost = (est_tokens / 1_000_000) * main_pricing[0] * 3
    est_synth_cost = (est_tokens / 1_000_000) * main_pricing[0] * 3
    est_link_cost = (est_tokens / 1_000_000) * main_pricing[0] * 1
    est_validate_cost = (est_tokens / 1_000_000) * cheap_pricing[0] * 0.5
    total_est = (
        est_segment_cost + est_extract_cost + est_synth_cost + est_link_cost + est_validate_cost
    )

    console.print(f"  [bold]Estimated cost: ${total_est:.4f}[/bold]")
    console.print(
        f"  Main model ({config.model}): "
        f"${main_pricing[0]}/1M in, ${main_pricing[1]}/1M out"
    )
    console.print(
        f"  Cheap model ({config.cheap_model}): "
        f"${cheap_pricing[0]}/1M in, ${cheap_pricing[1]}/1M out"
    )


@app.command()
def resume(
    checkpoint_path: Annotated[Path, typer.Argument(help="Path to checkpoint file or directory.")],
    prompt_bundle: Annotated[
        Path | None,
        typer.Option(help="Prompt bundle file/directory path override."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Resume a pipeline from a checkpoint."""
    import asyncio

    from sbs.pipeline.runner import resume_pipeline

    asyncio.run(resume_pipeline(checkpoint_path, verbose=verbose, prompt_bundle=prompt_bundle))


@app.command()
def validate(
    vault_dir: Annotated[Path, typer.Argument(help="Path to the Obsidian vault to validate.")],
) -> None:
    """Validate an existing vault for quality (deterministic checks only)."""
    import yaml

    from sbs.agents.validation import _check_frontmatter, _check_links
    from sbs.models.note import DraftNote, NoteFrontmatter

    console.print(f"[bold]Validating vault:[/bold] {vault_dir}")

    note_dirs = [
        vault_dir / "200_fleeting",
        vault_dir / "300_permanent",
        vault_dir / "900_sources",
        vault_dir / "500_literature",
    ]
    existing_note_dirs = [d for d in note_dirs if d.exists()]
    if not existing_note_dirs:
        console.print("[red]No generated note directories found in vault.[/red]")
        raise typer.Exit(1)

    # Read notes from vault
    notes: list[DraftNote] = []
    for note_dir in existing_note_dirs:
        for md_file in sorted(note_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue

            parts = content.split("---", 2)
            if len(parts) < 3:
                continue

            try:
                fm_data = yaml.safe_load(parts[1])
                fm = NoteFrontmatter.model_validate(fm_data)
                note_id = md_file.stem
                notes.append(
                    DraftNote(
                        id=note_id,
                        filename=md_file.name,
                        type=fm.type if fm.type != "moc" else "permanent",
                        title=note_id,
                        frontmatter=fm,
                        body=parts[2].strip(),
                    )
                )
            except Exception:
                console.print(
                    f"  [yellow]Skipping {md_file.name}: invalid frontmatter[/yellow]"
                )

    console.print(f"  Found {len(notes)} notes")

    issues = _check_frontmatter(notes)
    permanent_notes = [n for n in notes if n.type == "permanent"]
    link_issues, orphan_count = _check_links(permanent_notes, [])
    issues.extend(link_issues)

    if issues:
        for issue in issues:
            color = "red" if issue.severity == "error" else "yellow"
            note_ref = f" ({issue.note_id})" if issue.note_id else ""
            console.print(
                f"  [{color}]{issue.severity.upper()}[/{color}]: {issue.message}{note_ref}"
            )
    else:
        console.print("  [green]No issues found![/green]")

    console.print(f"  Orphan notes: {orphan_count}")


@prompt_app.command("init")
def prompt_init(
    output_dir: Annotated[
        Path, typer.Option("--output-dir", help="Prompt root directory.")
    ] = Path("./prompts"),
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite existing bundle files."),
    ] = False,
) -> None:
    """Initialize a default prompt bundle on disk."""
    import yaml

    from sbs.prompting.registry import PromptBundle, default_prompt_map, write_prompt_bundle

    bundle = PromptBundle(bundle_id="default", prompts=default_prompt_map())
    bundle_dir = output_dir / "bundles" / bundle.bundle_id
    write_prompt_bundle(bundle, bundle_dir, overwrite=force)

    registry = {
        "active_bundle": bundle.bundle_id,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_path = output_dir / "registry.yaml"
    registry_path.write_text(
        yaml.safe_dump(registry, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    console.print(f"[green]Prompt bundle initialized:[/green] {bundle_dir}")


@eval_app.command("build-dataset")
def eval_build_dataset(
    input_dir: Annotated[
        Path,
        typer.Argument(help="Directory containing exported conversation JSON files."),
    ],
    output_dir: Annotated[
        Path,
        typer.Option("--output-dir", help="Output dataset directory."),
    ] = Path("./evals/datasets"),
    checkpoint_path: Annotated[
        Path | None,
        typer.Option("--checkpoint-path", help="Checkpoint file or directory to bootstrap labels."),
    ] = None,
    max_cases_per_stage: Annotated[
        int,
        typer.Option("--max-cases-per-stage", help="Max number of cases to emit per stage."),
    ] = 80,
) -> None:
    """Build stage-wise evaluation datasets from local data/checkpoints."""
    from sbs.evals.dataset_builder import build_eval_datasets

    counts = build_eval_datasets(
        input_dir=input_dir,
        output_dir=output_dir,
        checkpoint_path=checkpoint_path,
        max_cases_per_stage=max_cases_per_stage,
    )

    console.print(f"[bold]Dataset output:[/bold] {output_dir}")
    for stage, count in counts.items():
        console.print(f"  - {stage}: {count} cases")


@eval_app.command("report")
def eval_report(
    runs_dir: Annotated[
        Path,
        typer.Option("--runs-dir", help="Evaluation run artifacts directory."),
    ] = Path("./evals/runs"),
    latest: Annotated[
        bool,
        typer.Option("--latest", help="Show latest run details."),
    ] = True,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Leaderboard row count."),
    ] = 10,
) -> None:
    """Show local evaluation leaderboard and latest run summary."""
    from sbs.evals.tracker import EvalTracker

    tracker = EvalTracker(runs_dir)
    rows = tracker.list_leaderboard(limit=limit)
    if not rows:
        console.print("[yellow]No eval runs found.[/yellow]")
        return

    console.print(f"[bold]Leaderboard ({len(rows)} most recent):[/bold]")
    for row in rows:
        console.print(
            f"  - {row.run_id} | bundle={row.bundle_id} | stage={row.stage} "
            f"| score={row.global_score:.2f} | dataset={row.dataset_hash}"
        )

    if latest:
        run = tracker.load_latest()
        if run:
            console.print("\n[bold]Latest run metrics:[/bold]")
            for stage, metric in run.metrics.items():
                console.print(
                    f"  - {stage}: score={metric.score:.2f}, "
                    f"pass_rate={metric.pass_rate:.2%}, "
                    f"cases={metric.passed_cases}/{metric.total_cases}"
                )
