"""Pipeline runner — sequential stage execution with checkpoint support."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from sbs.config import Config
from sbs.llm.client import LLMClient
from sbs.models.pipeline import PipelineState
from sbs.parsers.detector import parse_directory
from sbs.pipeline.checkpoint import CheckpointManager

console = Console()

# Type alias for a pipeline stage function
StageFunc = Callable[[PipelineState, LLMClient], Awaitable[None]]


async def _stage_0_parse(state: PipelineState, _llm: LLMClient) -> None:
    """Stage 0: Parse input files into normalized conversations."""
    conversations = parse_directory(state.config.input_dir)
    state.conversations = conversations
    console.print(f"  Parsed [bold]{len(conversations)}[/bold] conversations")


async def _stage_1_segment(state: PipelineState, llm: LLMClient) -> None:
    """Stage 1: Segment conversations into topical chunks."""
    from sbs.agents.segmentation import segment_conversations

    segments = await segment_conversations(state.conversations, llm, state.config)
    state.segments = segments
    console.print(f"  Created [bold]{len(segments)}[/bold] segments")


async def _stage_2_extract(state: PipelineState, llm: LLMClient) -> None:
    """Stage 2: Extract structured knowledge from segments."""
    from sbs.agents.extraction import extract_knowledge

    extractions = await extract_knowledge(state.segments, llm, state.config)
    state.extractions = extractions
    console.print(f"  Extracted knowledge from [bold]{len(extractions)}[/bold] segments")


async def _stage_3_synthesize(state: PipelineState, llm: LLMClient) -> None:
    """Stage 3: Synthesize atomic notes from extracted knowledge."""
    from sbs.agents.synthesis import synthesize_notes

    draft_notes, source_notes = await synthesize_notes(
        state.extractions, state.conversations, llm, state.config
    )
    state.draft_notes = draft_notes
    state.source_notes = source_notes
    console.print(
        f"  Synthesized [bold]{len(draft_notes)}[/bold] permanent notes, "
        f"[bold]{len(source_notes)}[/bold] source notes"
    )


async def _stage_4_link(state: PipelineState, llm: LLMClient) -> None:
    """Stage 4: Discover links and create MOCs."""
    from sbs.agents.linking import link_notes

    links, mocs, final_notes = await link_notes(state.draft_notes, llm, state.config)
    state.links = links
    state.mocs = mocs
    state.final_notes = final_notes
    console.print(
        f"  Discovered [bold]{len(links)}[/bold] links, "
        f"created [bold]{len(mocs)}[/bold] MOCs"
    )


async def _stage_5_validate(state: PipelineState, llm: LLMClient) -> None:
    """Stage 5: Validate output quality."""
    from sbs.agents.validation import validate_vault

    report = await validate_vault(state, llm)
    state.validation_report = report
    console.print(f"  Validation score: [bold]{report.score:.1f}/100[/bold]")
    if report.issues:
        console.print(f"  Issues found: {len(report.issues)}")


# Ordered list of stages
STAGES: list[tuple[str, StageFunc]] = [
    ("Parsing conversations", _stage_0_parse),
    ("Segmenting by topic", _stage_1_segment),
    ("Extracting knowledge", _stage_2_extract),
    ("Synthesizing notes", _stage_3_synthesize),
    ("Linking & MOC generation", _stage_4_link),
    ("Validating quality", _stage_5_validate),
]


async def run_pipeline(config: Config) -> PipelineState:
    """Run the full conversion pipeline."""
    console.print("[bold green]SBS Pipeline Started[/bold green]")
    console.print(f"  Provider: {config.provider} | Model: {config.model}")
    console.print(f"  Input: {config.input_dir} → Output: {config.output_dir}")

    if config.dry_run:
        conversations = parse_directory(config.input_dir)
        console.print(f"\n[yellow]Dry-run mode[/yellow] — {len(conversations)} conversations found")
        total_messages = sum(len(c.messages) for c in conversations)
        console.print(f"  Total messages: {total_messages}")
        console.print("  No LLM calls will be made.")
        state = PipelineState(config=config)
        state.conversations = conversations
        return state

    checkpoint_mgr = CheckpointManager(config.checkpoint_dir)

    state = PipelineState(
        config=config,
        started_at=datetime.now(tz=timezone.utc).isoformat(),
        input_hash=CheckpointManager.compute_input_hash(config.input_dir),
    )

    llm = LLMClient(config, cost_summary=state.cost)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        for i, (label, stage_fn) in enumerate(STAGES):
            if i in state.completed_stages:
                console.print(f"  [dim]Stage {i}: {label} (skipped — already done)[/dim]")
                continue

            task = progress.add_task(f"Stage {i}: {label}...", total=None)
            await stage_fn(state, llm)
            state.completed_stages.append(i)
            progress.remove_task(task)

            console.print(f"  [green]Stage {i}: {label} ✓[/green]")
            checkpoint_mgr.save(state, i)

    # Write output
    from sbs.output.writer import write_vault

    write_vault(state)

    console.print(f"\n[bold green]Pipeline complete![/bold green]")
    console.print(f"  Cost: ${state.cost.estimated_cost_usd:.4f}")
    console.print(f"  Tokens: {state.cost.total_input_tokens:,} in / {state.cost.total_output_tokens:,} out")

    return state


async def resume_pipeline(checkpoint_path: Path, verbose: bool = False) -> PipelineState:
    """Resume pipeline from a checkpoint."""
    checkpoint_mgr = CheckpointManager(
        checkpoint_path if checkpoint_path.is_dir() else checkpoint_path.parent
    )
    state = checkpoint_mgr.load(checkpoint_path)

    console.print(f"[bold]Resuming from checkpoint[/bold]")
    console.print(f"  Completed stages: {state.completed_stages}")

    if verbose:
        state.config.verbose = True

    llm = LLMClient(state.config, cost_summary=state.cost)

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
    ) as progress:
        for i, (label, stage_fn) in enumerate(STAGES):
            if i in state.completed_stages:
                console.print(f"  [dim]Stage {i}: {label} (skipped)[/dim]")
                continue

            task = progress.add_task(f"Stage {i}: {label}...", total=None)
            await stage_fn(state, llm)
            state.completed_stages.append(i)
            progress.remove_task(task)

            console.print(f"  [green]Stage {i}: {label} ✓[/green]")
            checkpoint_mgr.save(state, i)

    from sbs.output.writer import write_vault

    write_vault(state)

    console.print(f"\n[bold green]Pipeline resumed and complete![/bold green]")
    return state
