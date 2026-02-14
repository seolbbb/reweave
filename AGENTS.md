# AGENTS.md

## CRITICAL: PULL REQUEST TARGET BRANCH (NEVER DELETE THIS SECTION)

> **THIS SECTION MUST NEVER BE REMOVED OR MODIFIED**

### Git Workflow

```
main (deployed/published)
   ↑
  dev (integration branch)
   ↑
feature branches (your work)
```

### Rules (MANDATORY)

| Rule | Description |
|------|-------------|
| **ALL PRs → `dev`** | Every pull request MUST target the `dev` branch |
| **NEVER PR → `main`** | PRs to `main` are **automatically rejected** by CI |
| **"Create a PR" = target `dev`** | When asked to create a new PR, it ALWAYS means targeting `dev` |
| **Merge commit ONLY** | Squash merge is **disabled** in this repo. Always use merge commit when merging PRs. |

### Why This Matters

- `main` = production/published npm package
- `dev` = integration branch where features are merged and tested
- Feature branches → `dev` → (after testing) → `main`
- Squash merge is disabled at the repository level — attempting it will fail

**If you create a PR targeting `main`, it WILL be rejected. No exceptions.**

---

## CRITICAL: ENGLISH-ONLY POLICY (NEVER DELETE THIS SECTION)

> **THIS SECTION MUST NEVER BE REMOVED OR MODIFIED**

### All Project Communications MUST Be in English

| Context | Language Requirement |
|---------|---------------------|
| **GitHub Issues** | English ONLY |
| **Pull Requests** | English ONLY (title, description, comments) |
| **Commit Messages** | English ONLY |
| **Code Comments** | English ONLY |
| **Documentation** | English ONLY |
| **AGENTS.md files** | English ONLY |

**If you're not comfortable writing in English, use translation tools. Broken English is fine. Non-English is not acceptable.**

---

## Project Overview

- **Repository:** `seolbbb/second-brain-starter`
- **Package name:** `sbs`
- **Version:** 0.1.0
- **Language:** Python 3.11+
- **License:** MIT
- **Package manager:** uv (with `uv.lock`)
- **Build backend:** Hatchling

### What This Project Does

`second-brain-starter` (sbs) is a CLI tool that converts exported ChatGPT and Claude conversation JSON files into a **Zettelkasten-style Obsidian vault**. It uses LLMs in a multi-stage pipeline to parse, segment, extract knowledge, synthesize atomic notes, discover links, and validate output quality.

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| CLI framework | Typer |
| Terminal UI | Rich (progress spinners, styled output) |
| Data validation | Pydantic v2 |
| LLM provider A | Anthropic SDK (`AsyncAnthropic`, `tool_use` for structured output) |
| LLM provider B | OpenAI SDK (`AsyncOpenAI`, `json_schema` response format) |
| Config loading | python-dotenv |
| YAML rendering | PyYAML |
| Package manager | uv |
| Build backend | Hatchling |
| Test framework | pytest + pytest-asyncio |
| Linter/Formatter | Ruff |

---

## Project Structure

```
second-brain-starter/
├── pyproject.toml              # Project config, dependencies, tool configs
├── uv.lock                     # Locked dependencies
├── .env.example                # Environment variable template
│
├── src/sbs/                    # Main package
│   ├── __init__.py             # Version: 0.1.0
│   ├── cli.py                  # Typer CLI entry point (convert, estimate, resume, validate)
│   ├── config.py               # Pydantic Config model (env vars + CLI options)
│   │
│   ├── agents/                 # Pipeline stage agents
│   │   ├── base.py             # BaseAgent ABC
│   │   ├── segmentation.py     # Stage 1: split conversations into topical segments
│   │   ├── extraction.py       # Stage 2: extract structured knowledge
│   │   ├── synthesis.py        # Stage 3: write atomic notes + source notes
│   │   ├── linking.py          # Stage 4: cluster notes, find links, create MOCs
│   │   └── validation.py       # Stage 5: quality checks
│   │
│   ├── llm/                    # LLM abstraction layer
│   │   ├── client.py           # LLMClient (provider-agnostic wrapper)
│   │   ├── cost.py             # Token pricing table + cost tracking
│   │   ├── prompts.py          # All prompt templates
│   │   └── providers/
│   │       ├── anthropic.py    # Anthropic Claude provider
│   │       └── openai.py       # OpenAI provider
│   │
│   ├── models/                 # Pydantic data models
│   │   ├── __init__.py         # Re-exports all public models
│   │   ├── conversation.py     # NormalizedMessage, NormalizedConversation
│   │   ├── extraction.py       # ConceptItem, DecisionItem, InsightItem, etc.
│   │   ├── note.py             # DraftNote, NoteFrontmatter, NoteLink, MOC
│   │   ├── pipeline.py         # PipelineState, CostSummary, ValidationReport
│   │   └── segment.py          # Segment
│   │
│   ├── parsers/                # Input format parsers
│   │   ├── base.py             # ConversationParser Protocol
│   │   ├── chatgpt.py          # ChatGPT conversations.json parser
│   │   ├── claude.py           # Claude JSON export parser
│   │   └── detector.py         # Auto-detect format + parse directory
│   │
│   ├── output/                 # Vault writing
│   │   ├── writer.py           # write_vault() — writes notes/mocs/sources dirs
│   │   ├── templates.py        # Markdown + YAML frontmatter rendering
│   │   └── naming.py           # slugify(), sanitize_filename()
│   │
│   └── pipeline/               # Pipeline orchestration
│       ├── runner.py           # run_pipeline(), resume_pipeline()
│       └── checkpoint.py       # CheckpointManager — JSON save/load of PipelineState
│
└── tests/
    ├── conftest.py             # Shared fixtures (fixture paths)
    ├── fixtures/
    │   ├── chatgpt_sample.json # Sample ChatGPT export
    │   └── claude_sample.json  # Sample Claude export
    ├── test_agents.py          # Agent unit tests (no LLM calls)
    ├── test_llm.py             # Cost calculations, LLMClient init tests
    ├── test_models.py          # Pydantic model round-trip tests
    ├── test_output.py          # Template rendering + filesystem write tests
    ├── test_parsers.py         # Parser tests against fixture JSON files
    └── test_pipeline.py        # CheckpointManager save/load tests
```

---

## Architecture

### Multi-Stage Pipeline

```
Stage 0: Parse      → NormalizedConversation[]         (no LLM)
Stage 1: Segment    → Segment[]                        (cheap model)
Stage 2: Extract    → ExtractedKnowledge[]              (main model)
Stage 3: Synthesize → DraftNote[] + source notes        (main model + deterministic)
Stage 4: Link       → NoteLink[] + MOC[] + final notes  (cheap + main models)
Stage 5: Validate   → ValidationReport                  (cheap model, 10% LLM sampling)
```

### Key Patterns

- **Two-tier LLM usage:** "main" model (expensive, powerful) for extraction/synthesis/linking; "cheap" model for segmentation/clustering/validation
- **Structured output:** Anthropic uses `tool_use` API; OpenAI uses `json_schema` response format — both return typed Pydantic models
- **Async concurrency:** Each stage uses `asyncio.gather()` with `asyncio.Semaphore` (configurable via `--concurrency`)
- **Checkpoint/resume:** After each stage, `PipelineState` is serialized to JSON; `latest.json` symlink/copy is always maintained
- **Protocol-based parsers:** `ConversationParser` is a `typing.Protocol` — parsers implement `can_parse()` + `parse()` without base class inheritance
- **Provider abstraction:** `LLMClient` delegates to `AnthropicProvider` or `OpenAIProvider`
- **Exponential backoff retry:** Both providers retry with delays `[1, 4, 16]` seconds on rate limit / API errors
- **Obsidian vault output:** Three directories — `notes/` (permanent atomic notes), `sources/` (source reference notes), `mocs/` (Maps of Content)

---

## CLI Commands

Entry point: `sbs` (registered via `pyproject.toml` as `sbs = "sbs.cli:app"`)

| Command | Description |
|---------|-------------|
| `sbs convert <input_dir>` | Full pipeline: parse → segment → extract → synthesize → link → validate → write vault |
| `sbs estimate <input_dir>` | Dry-run cost estimation (counts tokens, estimates USD cost by stage) |
| `sbs resume <checkpoint_path>` | Resume from a saved checkpoint JSON (skips completed stages) |
| `sbs validate <vault_dir>` | Deterministic quality checks on an existing vault |
| `sbs --version` / `sbs -V` | Print version |

### Key Options for `convert`

| Option | Default | Description |
|--------|---------|-------------|
| `-o` / `--output` | `./vault` | Vault output directory |
| `--provider` | `anthropic` | LLM provider (`anthropic` or `openai`) |
| `--model` | (provider default) | Override main model |
| `--cheap-model` | (provider default) | Override cheap model |
| `--concurrency` | `3` | Max concurrent LLM calls |
| `--checkpoint-dir` | `./.sbs-checkpoints` | Checkpoint directory |
| `--dry-run` | `false` | Estimate cost only, no LLM calls |
| `--verbose` / `-v` | `false` | Verbose logging |

---

## Development Commands

```bash
# Install dependencies
uv sync

# Run the CLI
sbs --help
sbs convert ./input-dir -o ./vault --provider anthropic

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/
```

---

## Testing Guidelines

- **Framework:** pytest + pytest-asyncio
- **Location:** `tests/` directory, fixtures in `tests/fixtures/`
- **Python path:** `src/` (configured in `pyproject.toml`)
- **Key rule:** All tests must avoid real LLM API calls. Test pure functions directly, or pass `None` as the LLM client for code paths that bypass it.
- Run `uv run pytest` before submitting any PR.

---

## Coding Conventions

- **Linter:** Ruff with rules `E, F, I, N, UP, B, SIM`
- **Line length:** 99 characters
- **Target Python:** 3.11+
- **Style:**
  - Use `async/await` for LLM calls and concurrent operations
  - Use Pydantic v2 models for all data structures
  - Use `typing.Protocol` for interface definitions (structural subtyping)
  - Keep prompt templates in `src/sbs/llm/prompts.py`
  - All configuration flows through `src/sbs/config.py` (Pydantic `Config` model)

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (required for `--provider anthropic`) |
| `OPENAI_API_KEY` | OpenAI API key (required for `--provider openai`) |
