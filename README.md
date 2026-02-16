# second-brain-starter

`second-brain-starter` (`sbs`) converts exported ChatGPT/Claude conversations into an Obsidian vault using a multi-stage, LLM-assisted pipeline.

## What It Produces

The vault now follows a numeric, workflow-oriented layout:

```text
vault/
├── 100_inbox/         # Run summary and triage entry points
├── 200_fleeting/      # Rough notes that need refinement
├── 300_permanent/     # Durable, atomic notes
├── 400_mocs/          # Maps of Content
├── 500_literature/    # Literature index (references mentioned in conversations)
└── 900_sources/       # Conversation source notes
```

## Note Strategy

- `fleeting`: rough but promising ideas that need expansion
- `permanent`: stable, reusable notes with clear claims
- `source`: deterministic conversation references
- `literature`: aggregated reference index (`Literature.md`)
- `moc`: navigation notes over related permanent notes

## Pipeline Stages

1. Parse: normalize ChatGPT/Claude JSON into a shared model.
2. Segment: split conversations by topic.
3. Extract: structured extraction of concepts, decisions, insights, open questions, todos, and references.
4. Synthesize: generate notes and classify each as `fleeting` or `permanent`.
5. Link: discover links across permanent notes and generate MOCs.
6. Validate: run type-aware quality checks and produce a score.

## Quickstart

```bash
uv sync
uv run sbs --help
uv run sbs convert ./input-dir -o ./vault --provider anthropic
uv run sbs convert ./input-dir -o ./vault --provider google
```

## Test and Lint

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Commands

- `sbs convert <input_dir>`: run full pipeline and write vault
- `sbs estimate <input_dir>`: estimate token usage and cost
- `sbs resume <checkpoint_path>`: resume from checkpoint
- `sbs validate <vault_dir>`: deterministic vault validation
- `sbs prompt init`: scaffold `prompts/` with a default bundle + active registry
- `sbs eval build-dataset <input_dir>`: generate stage-wise JSONL eval datasets
- `sbs eval run --bundle active --stage all`: run prompt evals via Promptfoo and store local artifacts
- `sbs eval tune --bundle active`: generate candidate bundles and optionally auto-evaluate
- `sbs eval promote --candidate <bundle_id>`: promote candidate when quality gate passes

## Prompt Automation Workflow

1. Initialize prompt bundles:

```bash
uv run sbs prompt init
```

2. Build datasets from your local exports/checkpoints:

```bash
uv run sbs eval build-dataset data/ --checkpoint-path .sbs-checkpoints
```

3. Run baseline eval:

```bash
uv run sbs eval run --bundle active --stage all
```

4. Generate candidates + auto-evaluate:

```bash
uv run sbs eval tune --bundle active --iterations 1 --candidates 8
```

5. Promote candidate bundle (manual gate):

```bash
uv run sbs eval promote --candidate <candidate_bundle_id>
```

Run artifacts are stored in `evals/runs/` with leaderboard snapshots and per-run metrics.

## Requirements

- Python 3.11+
- `uv`
- One provider key:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `GOOGLE_API_KEY`
