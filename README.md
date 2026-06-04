# Reweave

Reweave is a local archive and search app for exported ChatGPT and Claude
conversations. It imports conversation exports into a local SQLite database,
indexes messages with SQLite FTS5, and lets you search, inspect, export, and
synthesize selected conversations without making the original export files the
working surface.

Insight generation is optional. When enabled, Reweave sends only the
conversations you explicitly select to the configured model provider and stores
the generated Markdown report in the same local archive database.

## How It Works

Reweave keeps the workflow intentionally local:

1. You provide exported ChatGPT or Claude data.
2. Reweave normalizes supported conversations into a stable internal model.
3. Conversations and messages are stored in SQLite.
4. Message content and titles are indexed with SQLite FTS5.
5. Search results retain conversation IDs, message indexes, roles, timestamps,
   and source paths.
6. Optional insight reports are generated only from selected conversations and
   are saved back into the local archive database.

The archive database is append-friendly and idempotent for repeated imports:
existing conversations and messages are ignored instead of duplicated.

## Features

- Import ChatGPT and Claude JSON exports from directories, single JSON files,
  or zip archives.
- Search archived messages and conversation titles with source, title, and date
  filters.
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
uv run reweave search "zettelkasten" --db ./reweave.db
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
- Search with provider, title, and date filters.
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
| `GET` | `/api/search` | Search grouped conversation results. |
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

Search, import, export, and browsing archived conversations are local operations.
LLM calls happen only when insight generation is requested. At that point,
Reweave formats the selected conversation messages as model context and sends
that context to the configured provider.

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
uv run reweave search <query> [--provider chatgpt|claude] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--title text] [--limit 20] [--db ./reweave.db]
uv run reweave show <conversation_id> [--db ./reweave.db]
uv run reweave stats [--db ./reweave.db]
uv run reweave export [conversation_id] [--query query] [-o ./exports] [--limit 50] [--db ./reweave.db]
uv run reweave app [--host 127.0.0.1] [--port 8765] [--db ./reweave.db]
uv run reweave desktop [--db ./reweave.db]
```

Search options:

- `--provider`: filter by `chatgpt` or `claude`.
- `--from`: include conversations created on or after a date.
- `--to`: include conversations created on or before a date.
- `--title`: filter by title substring.
- `--limit`: cap the number of returned matches.

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

## License

MIT
