# Prompt Automation Pipeline

This document describes the prompt iteration workflow added to SBS for the 5-stage pipeline.

## Goals

- Version prompt sets independently from code.
- Build repeatable eval datasets from local input/checkpoints.
- Run stage-wise prompt evals with Promptfoo.
- Track experiments locally without SaaS dependencies.
- Promote prompt candidates only when quality-first gates pass.

## Directory Layout

```text
prompts/
├── registry.yaml               # active bundle pointer
└── bundles/
    └── default/
        ├── bundle.yaml         # bundle metadata
        └── stages/
            ├── segmentation.yaml
            ├── extraction.yaml
            ├── synthesis.yaml
            ├── linking.yaml
            └── validation.yaml

evals/
├── datasets/                   # generated JSONL datasets
├── promptfoo/                  # stage eval templates
└── runs/
    ├── leaderboard.jsonl
    ├── latest.json
    ├── raw/                    # raw promptfoo outputs
    └── <run_id>/
        ├── metadata.json
        ├── scores.json
        ├── cost_latency.json
        └── winner_decision.json (optional)
```

## Commands

### 1) Initialize prompt bundles

```bash
uv run sbs prompt init
```

This creates a default prompt bundle from `src/sbs/llm/prompts.py` and marks it active in
`prompts/registry.yaml`.

### 2) Build datasets

```bash
uv run sbs eval build-dataset data/ --checkpoint-path .sbs-checkpoints
```

- Input-only mode creates segmentation cases.
- Checkpoint mode bootstraps extraction/synthesis/linking/validation cases from current pipeline state.

### 3) Run prompt eval

```bash
uv run sbs eval run --bundle active --stage all
```

Options:

- `--bundle`: bundle id or path (`active` resolves from registry)
- `--stage`: `segmentation|extraction|synthesis|linking|validation|all`
- `--datasets-dir`: defaults to `evals/datasets`
- `--configs-dir`: defaults to `evals/promptfoo`
- `--runs-dir`: defaults to `evals/runs`

The command exports env vars for Promptfoo templates:

- `SBS_PROMPT_BUNDLE`
- `SBS_DATASETS_DIR`
- `SBS_EVAL_STAGE`

### 4) Generate candidate bundles

```bash
uv run sbs eval tune --bundle active --iterations 1 --candidates 8
```

This creates deterministic candidate bundles under `prompts/bundles/`.
With `--auto-eval` (default), SBS attempts to run Promptfoo evals for each candidate.

### 5) Promote a bundle

```bash
uv run sbs eval promote --candidate <candidate_bundle_id>
```

Promotion is blocked unless all gates pass:

- Global score improvement >= `2.0`
- No stage regression worse than `-1.0`
- Cost increase <= `15%`

Use options to tune gate thresholds:

- `--min-improvement`
- `--max-stage-drop`
- `--cost-cap-ratio`

## Promptfoo Setup Notes

SBS calls the `promptfoo` CLI directly.

Install promptfoo:

```bash
npm i -g promptfoo
```

Stage config templates are provided in `evals/promptfoo/` and are intentionally minimal.
Customize them with your own providers/tests/assertions for production-grade signal.

## Recommended Iteration Loop

1. Keep one stable baseline bundle active.
2. Build datasets from your latest checkpoint.
3. Run baseline eval and record score.
4. Generate candidates and run evals.
5. Promote only candidates that pass gate.
6. Re-run `sbs convert` with active bundle and validate output quality.
