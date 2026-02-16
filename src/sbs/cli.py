"""Typer CLI application — command routing for SBS."""

from __future__ import annotations

import os
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
    from sbs.prompting.registry import (
        PromptBundle,
        default_prompt_map,
        write_prompt_bundle,
        write_prompt_registry,
    )

    bundle = PromptBundle(bundle_id="default", prompts=default_prompt_map())
    bundle_dir = output_dir / "bundles" / bundle.bundle_id
    write_prompt_bundle(bundle, bundle_dir, overwrite=force)

    registry_path = write_prompt_registry(output_dir, bundle.bundle_id)

    console.print(f"[green]Prompt bundle initialized:[/green] {bundle_dir}")
    console.print(f"  Registry updated: {registry_path}")


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


def _resolve_eval_bundle(bundle_ref: str, prompts_root: Path):
    from sbs.prompting.registry import load_prompt_bundle, resolve_bundle_path

    bundle_path = resolve_bundle_path(bundle_ref, prompts_root=prompts_root)
    bundle = load_prompt_bundle(bundle_path)
    return bundle, bundle_path


def _default_stage_configs(configs_dir: Path) -> dict[str, Path]:
    return {
        "segmentation": configs_dir / "promptfooconfig.stage-segmentation.yaml",
        "extraction": configs_dir / "promptfooconfig.stage-extraction.yaml",
        "synthesis": configs_dir / "promptfooconfig.stage-synthesis.yaml",
        "linking": configs_dir / "promptfooconfig.stage-linking.yaml",
        "validation": configs_dir / "promptfooconfig.stage-validation.yaml",
    }


def _run_eval_bundle(
    *,
    bundle_ref: str,
    stage: str,
    datasets_dir: Path,
    configs_dir: Path,
    runs_dir: Path,
    prompts_root: Path,
    config_override: Path | None,
):
    from sbs.evals.promptfoo import parse_promptfoo_metrics, run_promptfoo_eval
    from sbs.evals.tracker import EvalTracker, compute_dataset_hash
    from sbs.models.evals import EvalRun

    valid_stages = {"segmentation", "extraction", "synthesis", "linking", "validation", "all"}
    if stage not in valid_stages:
        raise typer.BadParameter(f"Invalid stage '{stage}'.")

    bundle, bundle_path = _resolve_eval_bundle(bundle_ref, prompts_root=prompts_root)
    tracker = EvalTracker(runs_dir)
    run_id = tracker.new_run_id()

    stage_configs = _default_stage_configs(configs_dir)
    if stage == "all":
        selected_stages = list(stage_configs)
        if config_override is not None:
            raise typer.BadParameter("--config can only be used when --stage is not 'all'.")
    else:
        selected_stages = [stage]

    dataset_hash = compute_dataset_hash(datasets_dir) if datasets_dir.exists() else "no-dataset"
    metrics = {}
    total_cost = 0.0
    total_latency = 0.0
    used_configs: list[str] = []

    raw_dir = runs_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for stage_name in selected_stages:
        config_path = config_override or stage_configs[stage_name]
        if not config_path.exists():
            raise FileNotFoundError(f"Promptfoo config not found: {config_path}")

        output_path = raw_dir / f"{run_id}-{bundle.bundle_id}-{stage_name}.json"
        env = dict(os.environ)
        env["SBS_PROMPT_BUNDLE"] = str(bundle_path)
        env["SBS_DATASETS_DIR"] = str(datasets_dir)
        env["SBS_EVAL_STAGE"] = stage_name

        payload = run_promptfoo_eval(config_path=config_path, output_path=output_path, env=env)
        metric, cost, latency = parse_promptfoo_metrics(payload)
        metrics[stage_name] = metric
        total_cost += cost
        total_latency += latency
        used_configs.append(str(config_path))

    global_score = (
        sum(metric.score for metric in metrics.values()) / len(metrics)
        if metrics
        else 0.0
    )
    run = EvalRun(
        run_id=run_id,
        bundle_id=bundle.bundle_id,
        dataset_hash=dataset_hash,
        stage=stage,  # type: ignore[arg-type]
        metrics=metrics,
        global_score=global_score,
        estimated_cost_usd=total_cost,
        latency_seconds=total_latency,
        metadata={
            "bundle_path": str(bundle_path),
            "configs": used_configs,
            "datasets_dir": str(datasets_dir),
        },
    )
    run_dir = tracker.save_run(run)
    return run, run_dir


@eval_app.command("run")
def eval_run(
    bundle: Annotated[
        str,
        typer.Option(
            "--bundle",
            help="Bundle id under prompts/bundles or path. Use 'active' for registry.",
        ),
    ] = "active",
    stage: Annotated[
        str,
        typer.Option(
            "--stage",
            help="Stage to evaluate: segmentation|extraction|synthesis|linking|validation|all.",
        ),
    ] = "all",
    datasets_dir: Annotated[
        Path,
        typer.Option("--datasets-dir", help="Evaluation datasets directory."),
    ] = Path("./evals/datasets"),
    configs_dir: Annotated[
        Path,
        typer.Option("--configs-dir", help="Promptfoo config template directory."),
    ] = Path("./evals/promptfoo"),
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Custom promptfoo config path (single-stage only)."),
    ] = None,
    runs_dir: Annotated[
        Path,
        typer.Option("--runs-dir", help="Evaluation run artifacts directory."),
    ] = Path("./evals/runs"),
    prompts_root: Annotated[
        Path,
        typer.Option("--prompts-root", help="Prompt registry root directory."),
    ] = Path("./prompts"),
) -> None:
    """Run promptfoo evaluation for a prompt bundle and persist local metrics."""
    from sbs.evals.promptfoo import PromptfooError

    try:
        run, run_dir = _run_eval_bundle(
            bundle_ref=bundle,
            stage=stage,
            datasets_dir=datasets_dir,
            configs_dir=configs_dir,
            runs_dir=runs_dir,
            prompts_root=prompts_root,
            config_override=config,
        )
    except PromptfooError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Eval run failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Eval run saved:[/green] {run_dir}")
    console.print(
        f"  run_id={run.run_id} bundle={run.bundle_id} score={run.global_score:.2f} "
        f"cost=${run.estimated_cost_usd:.4f}"
    )


@eval_app.command("tune")
def eval_tune(
    bundle: Annotated[
        str,
        typer.Option("--bundle", help="Baseline bundle id/path. Use 'active' for registry."),
    ] = "active",
    iterations: Annotated[
        int,
        typer.Option("--iterations", help="Number of tuning rounds."),
    ] = 1,
    candidates: Annotated[
        int,
        typer.Option("--candidates", help="Candidate bundles per iteration."),
    ] = 8,
    prompts_root: Annotated[
        Path,
        typer.Option("--prompts-root", help="Prompt registry root directory."),
    ] = Path("./prompts"),
    auto_eval: Annotated[
        bool,
        typer.Option(
            "--auto-eval/--no-auto-eval",
            help="Run eval automatically for generated candidates.",
        ),
    ] = True,
    stage: Annotated[
        str,
        typer.Option("--stage", help="Stage target for automated eval."),
    ] = "all",
    datasets_dir: Annotated[
        Path,
        typer.Option("--datasets-dir", help="Evaluation datasets directory."),
    ] = Path("./evals/datasets"),
    configs_dir: Annotated[
        Path,
        typer.Option("--configs-dir", help="Promptfoo config template directory."),
    ] = Path("./evals/promptfoo"),
    runs_dir: Annotated[
        Path,
        typer.Option("--runs-dir", help="Evaluation run artifacts directory."),
    ] = Path("./evals/runs"),
) -> None:
    """Generate prompt candidates and optionally auto-evaluate them."""
    from sbs.evals.promptfoo import PromptfooError
    from sbs.evals.tuner import generate_candidate_bundles, persist_candidates

    baseline_bundle, _bundle_path = _resolve_eval_bundle(bundle, prompts_root=prompts_root)
    current_bundle = baseline_bundle
    all_candidates: list[str] = []
    best_score: float | None = None
    best_bundle_id = baseline_bundle.bundle_id

    for iteration in range(iterations):
        generated = generate_candidate_bundles(
            current_bundle,
            count=candidates,
            bundle_prefix=f"{baseline_bundle.bundle_id}-it{iteration + 1}",
        )
        persist_candidates(generated, prompts_root=prompts_root, overwrite=False)
        all_candidates.extend([candidate.bundle_id for candidate in generated])

        if not auto_eval:
            current_bundle = generated[0]
            continue

        for candidate in generated:
            try:
                run, _run_dir = _run_eval_bundle(
                    bundle_ref=candidate.bundle_id,
                    stage=stage,
                    datasets_dir=datasets_dir,
                    configs_dir=configs_dir,
                    runs_dir=runs_dir,
                    prompts_root=prompts_root,
                    config_override=None,
                )
            except PromptfooError as exc:
                console.print(f"[yellow]Skipped auto-eval: {exc}[/yellow]")
                auto_eval = False
                break

            if best_score is None or run.global_score > best_score:
                best_score = run.global_score
                best_bundle_id = candidate.bundle_id
                current_bundle = candidate

    console.print(f"[bold]Generated candidates:[/bold] {len(all_candidates)}")
    for bundle_id in all_candidates:
        console.print(f"  - {bundle_id}")

    if best_score is not None:
        console.print(
            f"[green]Best candidate so far:[/green] {best_bundle_id} "
            f"(score={best_score:.2f})"
        )
    else:
        console.print(
            "[yellow]Auto-eval was not executed. "
            "Run `sbs eval run --bundle <candidate>` manually.[/yellow]"
        )


@eval_app.command("promote")
def eval_promote(
    candidate: Annotated[
        str,
        typer.Option("--candidate", help="Candidate bundle id to promote."),
    ],
    baseline: Annotated[
        str | None,
        typer.Option("--baseline", help="Baseline bundle id (defaults to active bundle)."),
    ] = None,
    prompts_root: Annotated[
        Path,
        typer.Option("--prompts-root", help="Prompt registry root directory."),
    ] = Path("./prompts"),
    runs_dir: Annotated[
        Path,
        typer.Option("--runs-dir", help="Evaluation run artifacts directory."),
    ] = Path("./evals/runs"),
    min_improvement: Annotated[
        float,
        typer.Option("--min-improvement", help="Minimum global score improvement."),
    ] = 2.0,
    max_stage_drop: Annotated[
        float,
        typer.Option("--max-stage-drop", help="Maximum allowed stage-level regression."),
    ] = 1.0,
    cost_cap_ratio: Annotated[
        float,
        typer.Option("--cost-cap-ratio", help="Maximum allowed cost increase ratio."),
    ] = 0.15,
) -> None:
    """Promote a candidate bundle when it passes quality-first gating."""
    from sbs.evals.tracker import EvalTracker
    from sbs.evals.tuner import evaluate_promotion_gate
    from sbs.prompting.registry import load_prompt_registry, write_prompt_registry

    tracker = EvalTracker(runs_dir)
    registry = load_prompt_registry(prompts_root)
    baseline_bundle = baseline or str(registry.get("active_bundle", "default"))

    candidate_run = tracker.latest_for_bundle(candidate)
    baseline_run = tracker.latest_for_bundle(baseline_bundle)
    if candidate_run is None:
        console.print(f"[red]No eval run found for candidate bundle: {candidate}[/red]")
        raise typer.Exit(1)
    if baseline_run is None:
        console.print(f"[red]No eval run found for baseline bundle: {baseline_bundle}[/red]")
        raise typer.Exit(1)

    decision = evaluate_promotion_gate(
        candidate=candidate_run,
        baseline=baseline_run,
        min_improvement=min_improvement,
        max_stage_drop=max_stage_drop,
        cost_cap_ratio=cost_cap_ratio,
    )

    if not decision.passed:
        console.print("[yellow]Promotion blocked by gate:[/yellow]")
        for reason in decision.reasons:
            console.print(f"  - {reason}")
        raise typer.Exit(1)

    registry_path = write_prompt_registry(prompts_root, candidate)
    console.print(f"[green]Promoted bundle:[/green] {candidate}")
    console.print(f"  Registry updated: {registry_path}")
    for reason in decision.reasons:
        console.print(f"  - {reason}")
