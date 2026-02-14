# SBS Pipeline Architecture

This document describes the current `sbs` pipeline and vault semantics.

## End-to-End Flow

```text
Input JSON -> Parse -> Segment -> Extract -> Synthesize -> Link -> Validate -> Write Vault
```

`PipelineState` carries all stage outputs and is checkpointed after every stage.

## Stage Breakdown

### Stage 0: Parse (`sbs.parsers`)

- Detects export format (ChatGPT or Claude)
- Produces `NormalizedConversation[]`
- No LLM calls

### Stage 1: Segment (`sbs.agents.segmentation`)

- Splits conversations into topical `Segment[]`
- Uses cheap model for longer conversations
- Keeps short conversations as a single segment

### Stage 2: Extract (`sbs.agents.extraction`)

- Extracts structured knowledge from each segment:
  - concepts
  - decisions
  - insights
  - todos
  - open questions
  - references
  - summary
- Produces `ExtractedKnowledge[]`

### Stage 3: Synthesize (`sbs.agents.synthesis`)

- Generates atomic notes from extracted knowledge
- Classifies each note as `fleeting` or `permanent`
- Applies deterministic guardrails to stabilize classification
- Generates deterministic source notes (`SRC-*`)
- Builds `500_literature/Literature.md` index from extracted references

### Stage 4: Link (`sbs.agents.linking`)

- Clusters and links **permanent** notes
- Generates topic MOCs from sufficiently large permanent clusters
- Adds `MOC-inbox-triage.md` when fleeting notes exist
- Injects related note IDs into frontmatter

### Stage 5: Validate (`sbs.agents.validation`)

- Type-aware checks for frontmatter and content
- Link quality checks focused on permanent note graph
- Completeness checks between conversations and source notes
- LLM atomicity sampling on permanent notes only
- Produces a scored `ValidationReport`

## Vault Layout

```text
vault/
├── 100_inbox/
│   └── Run-Summary.md
├── 200_fleeting/
├── 300_permanent/
├── 400_mocs/
├── 500_literature/
│   └── Literature.md
└── 900_sources/
```

## Key Design Decisions

- Keep six stages for operational stability.
- Use cheap model for segmentation/clustering/validation and main model for extraction/synthesis/link discovery.
- Keep source/literature generation deterministic for repeatability.
- Separate fleeting and permanent notes physically for easier triage in Obsidian.

## Checkpoints

After each stage, pipeline state is saved in `.sbs-checkpoints/` and `latest.json` is refreshed.

Use:

```bash
sbs resume ./.sbs-checkpoints/latest.json
```

## Validation Command Scope

` sbs validate <vault_dir> ` reads generated note directories:

- `200_fleeting/`
- `300_permanent/`
- `500_literature/`
- `900_sources/`
