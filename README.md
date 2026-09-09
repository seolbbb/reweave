# Reweave

Reweave is a local Windows Context Library for ChatGPT and Claude conversations.
Save a whole web chat or import an export, then return to its decisions, lessons,
projects and source evidence in the Reading Room. Explicit **Use Reweave** brings
relevant allowed context into a later chat draft without submitting it.

The archive and Library stay on your device. A connected BYOK provider analyzes
saved sources within a visible daily allowance; without a key, capture, browsing
and keyword search still work. Optional multilingual semantic search runs locally
and downloads its model only when you enable Smart search.

## How it works

1. Import a ChatGPT/Claude export, or use the extension's explicit Save action.
2. Reweave stores the conversation before queued analysis begins.
3. Analysis produces a Conversation Brief and supported Context Items with exact
   evidence. Long sources use bounded resumable parts and show incomplete progress.
4. Home highlights decisions and useful context. Explore follows linked spaces;
   Search finds Context and original sources globally.
5. Correct an item or its space when needed. Version history and undo preserve
   your changes. Review is reserved for exceptions, ambiguity and conflicts.
6. In a later supported web chat, write a request and choose Use. Confirm the
   destination when needed; restricted scopes and sensitive material have separate
   controls. Reweave adds a bounded context block before the unchanged draft.

Repeated imports and Saves are idempotent. Explicit reanalysis can use a new
model while preserving user corrections. Removing a source keeps derived evidence
snapshots; removing the derived Library is a separate explicit action.

## Features

- Shared Reading Room design across Home, Explore, Sources, Search, Import,
  Settings, onboarding, correction, backup, Review and extension controls.
- Source-grounded observed, inferred and suggested items, with linked projects,
  topics, Core Self, Personal, Work and destination scopes.
- Source and Context keyword/semantic search with space/type filters and
  bidirectional navigation to the original message.
- Versioned corrections, space rename/merge, relationship rationale, confidence
  decay, exception Review and explicit undo.
- Scope-aware Use with expiring sensitive consent, draft preservation, duplicate
  block replacement and no automatic submission or conversation capture.
- Local relationship Graph and explicitly previewed, redacted PNG sharing.
- Encrypted complete Library backup/restore, disconnected restored credentials,
  and redacted diagnostic export.

The current completion evidence and remaining owner acceptance are recorded in
[Project Status](docs/PROJECT_STATUS.md). Automated or synthetic verification does
not establish personal usefulness. The [Product Spec](docs/PRODUCT_SPEC.md) and
[Roadmap](docs/ROADMAP.md) define the full accepted scope.

## Windows package

Build the desktop bundle with `packaging/Reweave.spec`, then run
`scripts/build_windows_installer.py` to produce `dist/Reweave-Setup.exe`.
The per-user installer includes both executables and the unpacked extension.
It does not launch the app, enable automatic startup or register browser access.
See [Windows installation](packaging/installer/README.md) for the separate
Chrome/Edge registration step, safe update/removal and isolated verification.

Windows Save File and real browser-account checks are separate from headless
package tests. Current limits and final acceptance are in Project Status.
The [beta preparation guide](docs/release/README.md) records installation, privacy,
public support boundaries and the owner decisions required before publication.

## Development install

Reweave requires Python 3.11 or newer. The development workflow uses
[`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
```

For the browser UI, install and build the frontend assets:

```bash
cd frontend
npm install
npm run build
cd ..
```

The Vite build writes static assets to `src/reweave/web/dist`, which is included
in Python package builds.

## Quick Start

The CLI works without the frontend build. Use `uv run` during development:

Import an export directory, JSON file, or zip archive:

```bash
uv run reweave import ./data --db ./reweave.db
```

Search the archive:

```bash
uv run reweave search "zettelkasten" --mode auto --db ./reweave.db
```

### Choosing a search mode

Start with `auto`. It uses hybrid keyword and semantic ranking when Smart search
is ready, and safely falls back to keyword search when the local model or index
is not installed.

| Mode | Use it when | Trade-off |
| --- | --- | --- |
| `auto` **(recommended)** | You are searching normally or asking a natural-language question. | Best measured recall; requires Smart search for hybrid ranking, otherwise behaves like `keyword`. |
| `keyword` | You remember an exact phrase, error message, command, name, code symbol, or distinctive partial word. | Fastest and needs no model, but can miss conversations that express the same idea with different words. |
| `semantic` | You want meaning-only retrieval, remember the idea but not its wording, or want to inspect what the semantic channel contributes. | Requires the downloaded model and a complete index; exact identifiers may rank less reliably without keyword signals. |

Practical examples:

- Use `keyword` for `"blue lantern deployment"`, `TypeError`, `current_node`,
  or a remembered part of a Korean word.
- Use `auto` for questions such as “How did I decide to organize my notes?”
  or “What was my safe database migration approach?”
- Use `semantic` mainly to isolate meaning-based results while evaluating or
  debugging retrieval. For everyday use, `auto` is usually safer.

On the historical 32-query Korean and English archive golden set, hybrid `auto` improved
Recall@10 from `0.3438` to `0.9688` while preserving all exact-query hits. On a
50,000-message archive, measured p95 latency was `162 ms` for keyword and
`717 ms` for warm hybrid search. These are reference measurements from one
Windows machine, not universal guarantees. See
[Search Evaluation](docs/search-evaluation.md) for the dataset, methodology,
commands, and reproducible benchmark scripts.

Enable local semantic search. This lazily downloads the multilingual model and
indexes only missing or changed chunks:

```bash
uv run reweave index --db ./reweave.db
```

Optional legacy CLI command for a source-grounded answer using the configured BYOK provider:

```bash
uv run reweave ask "How did I decide to structure my notes?" --mode auto --db ./reweave.db
```

Open a conversation:

```bash
uv run reweave show <conversation_id> --db ./reweave.db
```

Export Markdown:

```bash
uv run reweave export <conversation_id> -o ./exports --db ./reweave.db
uv run reweave export --query "obsidian vault" -o ./exports --db ./reweave.db
```

View archive statistics:

```bash
uv run reweave stats --db ./reweave.db
```

## Web App

Build the frontend first, then start the local app:

```bash
cd frontend
npm run build
cd ..
uv run reweave app --db ./reweave.db
```

Open `http://127.0.0.1:8765`.

The web app provides the same Reading Room and local Library flows as the desktop
app. Context activity contains provider allowance, pause/retry controls and the
active versioned prompt. Settings manages BYOK profiles and optional Smart search.
Sources retains JSON/ZIP import, original conversations and explicit source removal.
Graph and exception Review are auxiliary Explore views. Legacy Ask Archive and
Memory Audit remain internal/CLI compatibility components, with no standalone
primary UI destination.

If the frontend build is missing, `reweave app` still starts the API and prints
a warning.

### Local API

The browser UI is backed by a local FastAPI server. The API is not intended as a
public hosted service, but it is useful for local automation and testing.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Check server readiness. |
| `GET` | `/api/search?mode=auto\|keyword\|semantic` | Search grouped conversation results. |
| `GET` | `/api/semantic/status` | Read local model and index readiness. |
| `POST` | `/api/semantic/index/jobs` | Download the model if needed and index changed chunks. |
| `GET` | `/api/semantic/index/jobs/{job_id}` | Read semantic indexing progress. |
| `DELETE` | `/api/semantic/index` | Remove local embeddings and chunks. |
| `DELETE` | `/api/semantic/model` | Remove the local index and downloaded model. |
| `POST` | `/api/archive-answers/jobs` | Retrieve evidence and start a cited archive answer. |
| `GET` | `/api/archive-answers/jobs/{job_id}` | Read answer progress and the validated result. |
| `GET` | `/api/conversations/{conversation_id}` | Load one conversation and its messages. |
| `POST` | `/api/import` | Import from a directory path. |
| `POST` | `/api/import/path` | Import from a directory, JSON file, or zip path. |
| `POST` | `/api/import/upload` | Upload one or more `.json` or `.zip` files. |
| `POST` | `/api/insights` | Generate and save an insight report. |
| `POST` | `/api/insights/jobs` | Start an asynchronous insight report with immediate progress. |
| `GET` | `/api/insights/jobs/{job_id}` | Read insight progress and the completed report. |
| `GET` | `/api/insights` | List saved insight reports. |
| `GET` | `/api/insights/{report_id}` | Load one saved insight report. |

## Desktop App

Run Reweave in a native desktop window:

```bash
uv run reweave desktop
```

You can also use the installed script name:

```bash
uv run reweave-desktop
```

By default, the desktop app stores its database and imported files in the
platform-specific Reweave application data directory. Pass `--db` or set
`REWEAVE_DB` to use a specific database.

For packaged desktop builds, `packaging/reweave_desktop.py` is the PyInstaller
entrypoint and delegates to `reweave.desktop:main`.

## Supported Exports

Reweave currently supports:

- ChatGPT `conversations.json` exports.
- Claude JSON conversation exports.
- Zip archives that contain supported JSON export files.

During zip import, Reweave extracts JSON files only and ignores non-JSON assets.
Unsupported JSON files are skipped.

Zip extraction is constrained to the configured extraction directory and rejects
unsafe archive entries that would write outside that directory.

## Archive Storage

The SQLite archive stores:

- `conversations`: normalized metadata, source provider, title, timestamps,
  message count, and source path.
- `messages`: message role, content, timestamp, and original message index.
- `messages_fts`: SQLite FTS5 index over titles and message content.
- `messages_fts_trigram`: local partial-word and substring index.
- `search_chunks`: 1,500-character source chunks with 200-character overlap.
- `chunk_embeddings`: local float32 vectors for the opt-in multilingual model.
- `insight_reports`: generated Markdown reports and their selected source
  conversation IDs.

The default CLI database path is `./reweave.db`. The desktop app defaults to the
platform-specific Reweave application data directory unless `--db` or
`REWEAVE_DB` is provided.

One app or CLI command owns a Library at a time. Close the desktop app before
running a direct CLI command against the same database. Shutdown waits for active
writers before another process may open or restore that Library.

## Legacy CLI insight reports

Historical reports and APIs remain available for compatibility. New desktop analysis uses Conversation Briefs and Context Items.

Insight reports are generated from conversations you select. Reweave detects the
dominant Korean or English source language, explicitly requires that language in
the model prompt, and produces rendered Markdown with these sections:

- `Overview`
- `Key concepts`
- `Connections between conversations`
- `Agreements, contradictions, and patterns`
- `New or surprising insights`
- `Suggested follow-up questions`
- `Source references`

Important claims should include source references such as
`[conversation_id#mIndex]`. These references identify supporting messages. The legacy report generator uses
concurrent chunk analysis; the current Context pipeline uses bounded sequential
checkpoints and preserves complete-source coverage.

Supported providers:

- `openai`
- `anthropic`
- `gemini`
- `openai-compatible`
- `openrouter`
- `kimi`

OpenAI-compatible providers require a base URL.

### Privacy boundary

Import, capture, browsing, keyword search, local semantic embeddings and Library
management run locally. Smart search downloads a model only after an explicit
setup action. A connected active BYOK profile enables queued source analysis;
pause and daily attempt/token limits are visible in Context activity. Each call
contains only its bounded source parts or compatible compact relationship
candidates. Limits are conservative reservations, not a dollar spending guarantee.

Production API keys live in the operating-system credential store. Encrypted
backups exclude credentials and restore profiles disconnected. Exported diagnostics
exclude raw text, local paths and provider secrets. Graph sharing starts with
redacted generic labels and requires preview and confirmation. Use reads the current
chat and draft only after the explicit action and never persists either input.

## Configuration

Reweave loads `.env` automatically. Copy `.env.example` when you want local
defaults:

```bash
cp .env.example .env
```

Available environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `REWEAVE_DB` | `./reweave.db` | Default SQLite archive path. |
| `REWEAVE_EXPORT_DIR` | `./exports` | Default Markdown export directory. |
| `REWEAVE_LLM_PROVIDER` | `openai` | Default insight provider. |
| `REWEAVE_LLM_MODEL` | `gpt-4o-mini` | Default insight model. |
| `REWEAVE_LLM_BASE_URL` | empty | Provider base URL override. |
| `REWEAVE_LLM_API_KEY` | empty | Provider API key. |
| `REWEAVE_LLM_MAX_CONTEXT_CHARS` | `80000` | Maximum source context per model call. |
| `REWEAVE_LLM_TEMPERATURE` | `0.2` | Insight generation temperature. |

## CLI Reference

```bash
uv run reweave --help
uv run reweave import <path> [--db ./reweave.db]
uv run reweave index [--rebuild] [--db ./reweave.db]
uv run reweave search <query> [--mode auto|keyword|semantic] [--provider chatgpt|claude] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--title text] [--limit 20] [--db ./reweave.db]
uv run reweave ask <question> [--mode auto|keyword|semantic] [--db ./reweave.db]
uv run reweave show <conversation_id> [--db ./reweave.db]
uv run reweave stats [--db ./reweave.db]
uv run reweave export [conversation_id] [--query query] [-o ./exports] [--limit 50] [--db ./reweave.db]
uv run reweave app [--host 127.0.0.1] [--port 8765] [--db ./reweave.db]
uv run reweave desktop [--db ./reweave.db]
```

Search options:

- `--mode auto`: recommended default; hybrid when Smart search is ready,
  otherwise keyword fallback.
- `--mode keyword`: exact, phrase, prefix, and substring retrieval without a
  downloaded model.
- `--mode semantic`: meaning-only retrieval; fails clearly if the local index
  is not ready.
- `--provider`: filter by `chatgpt` or `claude`.
- `--from`: include conversations created on or after a date.
- `--to`: include conversations created on or before a date.
- `--title`: filter by title substring.
- `--limit`: cap the number of returned matches.

See [Choosing a search mode](#choosing-a-search-mode) for selection guidance and
[Search Evaluation](docs/search-evaluation.md) for measured quality and latency.

Export modes:

- `reweave export <conversation_id>` writes a source conversation Markdown file.
- `reweave export --query <query>` writes a search-result dossier Markdown file.

## Project Structure

```text
reweave/
+-- frontend/           # React/Vite local web app
+-- packaging/          # Desktop packaging entrypoint
+-- src/reweave/        # Python CLI, archive, API, desktop, LLM, and parser code
+-- tests/              # Python tests and fixtures
+-- pyproject.toml      # Python package metadata
+-- README.md
```

## Development

Run Python tests and linting:

```bash
uv run pytest
uv run ruff check src/ tests/
```

Run frontend checks:

```bash
cd frontend
npm test
npm run build
```

Build the Python package:

```bash
uv build
```

When changing the web app, run `npm run build` before packaging so the Python
package includes the latest static frontend.

Search quality and 50,000-message latency are covered by reproducible benchmark
scripts. See [docs/search-evaluation.md](docs/search-evaluation.md) for the
golden-query suite, commands, targets, and latest local measurements.

## License

MIT
