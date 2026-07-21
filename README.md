# Reweave

Reweave is a local archive and search app for exported ChatGPT and Claude
conversations. It imports conversation exports into a local SQLite database,
indexes messages with SQLite FTS5, and lets you search, inspect, export, and ask
source-grounded questions without making the original export files the working
surface. Optional multilingual semantic search is downloaded only when you
enable it and runs entirely on the local device.

Insight generation is optional. When enabled, Reweave sends only the
conversations you explicitly select to the configured model provider and stores
the generated Markdown report in the same local archive database.

## How It Works

Reweave keeps the workflow intentionally local:

1. You provide exported ChatGPT or Claude data.
2. Reweave normalizes supported conversations into a stable internal model.
3. Conversations and messages are stored in SQLite.
4. Message content and titles are indexed with SQLite FTS5.
5. Exact, phrase, prefix, and substring candidates are fused into ranked results.
6. Optional semantic chunks and embeddings stay in the same local archive.
7. Search results retain conversation IDs, message indexes, roles, timestamps,
   and source paths.
8. Ask Archive retrieves its own evidence and rejects answers with missing or
   invented citations.

The archive database is append-friendly and idempotent for repeated imports.
Native provider IDs preserve existing conversation links while changed titles,
timestamps, and messages are updated. A shorter export never silently deletes
messages already in the archive.

## Features

- Import ChatGPT and Claude JSON exports from directories, single JSON files,
  or zip archives.
- Search exact phrases and partial words with source, title, and date filters.
- Choose `auto`, `keyword`, or optional local multilingual semantic search.
- Ask the archive a question and open every citation at the exact source message.
- View conversations in original message order with timestamps and source
  metadata.
- Export individual conversations or search-result dossiers as Markdown.
- Run a local React/FastAPI browser app for drag-and-drop import, search,
  selection, preview, and insight generation.
- Run the same app in a native desktop window with `pywebview`.
- Generate source-grounded insight reports with immediate progress, localized
  output, rendered Markdown, and supporting-conversation links.

## Install

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

On the current 32-query Korean and English golden set, hybrid `auto` improved
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

Ask a source-grounded question using the configured BYOK provider:

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

The web app supports:

- Drag-and-drop import for `.zip` and `.json` exports.
- Keyword, semantic, or automatic hybrid search with provider, title, and date filters.
- A document-style Ask Archive answer with verified, clickable source citations.
- Opt-in Smart search setup, progress, rebuild, index deletion, and model deletion.
- Grouped conversation results with source excerpts.
- Conversation preview in original message order.
- Multi-select conversations for insight generation.
- LLM settings for provider, model, API key, base URL, context size, and
  temperature.
- Reading generated insights in a structured report workspace.
- Copying or downloading generated insight Markdown.

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

## Insight Generation

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
`[conversation_id#mIndex]`. The report UI turns these references into links to
supporting messages. Multi-chunk source analysis runs concurrently before the
final synthesis step.

Supported providers:

- `openai`
- `anthropic`
- `gemini`
- `openai-compatible`
- `openrouter`
- `kimi`

OpenAI-compatible providers require a base URL.

### Privacy Boundary

Import, keyword search, semantic embedding, search, export, and browsing are
local operations. The semantic model is downloaded only after the user enables
Smart search and can be removed from Settings. LLM calls happen only when Ask
Archive or insight generation is requested. Ask Archive sends only its retrieved
evidence; insight generation sends only conversations selected by the user.

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
