# Reweave development guide

[English README](../README.md) · [Korean README](../README.ko.md)

Use the [README quick start](../README.md#quick-start) for installation and your
first interaction with the app. This guide covers developer commands and local
archive tools. The supported desktop target is Windows.

## Setup and verification

Requirements: Python 3.11+, uv, and Node.js 22.12+ with npm. From the repository root:

```powershell
uv sync --locked
cd frontend
npm ci
npm test
npm run build
cd ..
uv run pytest
uv run ruff check src/ tests/
```

`npm run build` runs TypeScript checks and writes Vite assets to
`src/reweave/web/dist`. Build these assets before packaging the desktop or Python
distribution. Run Node/Vite from the repository's physical path if the checkout is
accessed through a Windows junction; mixing the alias and resolved paths can fail
asset emission.

Every implementation delivery also requires the clean Windows executable build:

```powershell
.venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\Reweave.spec
```

Verify both `dist\Reweave\Reweave.exe` and `dist\Reweave\ReweaveNativeHost.exe`.
Keep the whole bundle together. See the [installer guide](../packaging/installer/README.md)
for the separate NSIS installer build and isolated installation checks. `uv build`
builds the Python distribution; it does not replace the Windows build.

The existing packaged smoke uses only synthetic data, a loopback fake provider,
memory-only credentials, and hidden owned processes:

```powershell
uv run python scripts/verify_packaged_runtime.py --data-dir .pytest_cache/readme-smoke --report .pytest_cache/readme-smoke.json
```

Choose a new data directory below `.pytest_cache` for each run; an existing one is
rejected. The check exercises both executables, Save, no-key persistence, analysis,
source evidence, explicit Use, restart, idempotence, and shutdown. It does not prove
native dialogs, real provider quality, or personal usefulness. Do not use owner
data, browser profiles, OS credentials, or visible desktop interaction for automated checks.

For canonical documentation, run the installed project-record validator:

```powershell
& .venv\Scripts\python.exe "$env:USERPROFILE\.codex\skills\manage-project-intent\scripts\validate_project_docs.py" --root . --strict full
```

This command requires the maintainer's `manage-project-intent` skill installation;
it is not needed to run Reweave. Read [AGENTS.md](../AGENTS.md) for the full delivery
agreement. All PRs target `dev`; merge commits are required.

## CLI reference

Archive CLI commands work without a frontend build. They default to
`./reweave.db`, independently of the desktop's default Library. Close another
app/CLI owner before operating on the same database.

```powershell
uv run reweave --help
uv run reweave import ./tests/fixtures/chatgpt_sample.json --db ./reweave.db
uv run reweave search "notes" --mode keyword --db ./reweave.db
uv run reweave stats --db ./reweave.db
```

| Command | Purpose |
| --- | --- |
| `import <path>` | Import a supported JSON, ZIP, or directory of exports. |
| `search <query>` | Find matching conversations and messages. |
| `show <conversation_id>` | Read a saved conversation. |
| `export <conversation_id> -o ./exports` | Export one conversation as Markdown. |
| `export --query "notes" -o ./exports` | Export matching results as a Markdown dossier. |
| `stats` | Show archive counts. |
| `index` | Download the optional local embedding model if needed and index changed chunks. |
| `app --db ./reweave.db` | Serve the browser UI and local API on `127.0.0.1:8765`. |
| `desktop` | Open the desktop window and its Native Messaging bridge. |

Use `uv run reweave <command> --help` for current options. Search accepts
`--provider chatgpt|claude`, `--from YYYY-MM-DD`, `--to YYYY-MM-DD`, `--title`, and
`--limit`. Pass the same `--db` path to each command when working with a specific archive.

The historical `ask` CLI and archive-answer/insight APIs remain for compatibility.
They may call a configured remote provider. They are not the current user-facing
Context workflow; the desktop creates Conversation Briefs and Context Items.

## Search modes

| Mode | Behavior | When to use it |
| --- | --- | --- |
| `auto` | Combines keyword and local semantic ranking when the model/index is ready; otherwise falls back to keyword. | Everyday search. |
| `keyword` | Local phrase, identifier, prefix, and substring matching without a model. | Error messages, commands, names, code symbols, or remembered wording. |
| `semantic` | Local meaning-based ranking; requires the model and a ready index. | Finding a remembered idea or inspecting semantic retrieval. |

`uv run reweave index --db ./reweave.db` explicitly enables the model download and
indexing. Smart search in Settings provides the corresponding UI. Search does not
send conversation content to an LLM provider. Benchmark methodology and historical
measurements are in [Search Evaluation](search-evaluation.md); those measurements
are not guarantees for other hardware or datasets.

## Configuration

| Setting | Scope and default |
| --- | --- |
| `--db <path>` | Explicit database path for the chosen CLI, app, or desktop command. |
| `REWEAVE_DB` | Database override; otherwise CLI/app use `./reweave.db`, and desktop uses the application-data directory. |
| `REWEAVE_DATA_DIR` | Data, imports, settings, model cache, and bridge directory; normally `%LOCALAPPDATA%\Reweave` on Windows. Desktop also uses its database unless overridden. |
| `REWEAVE_EXPORT_DIR` | Default CLI Markdown export directory; `./exports`. |
| Settings → provider profiles | Preferred desktop configuration for provider, model, connection, and OS-stored keys. |

To point the browser app at the default desktop database, first close the desktop:

```powershell
uv run reweave app --db "$env:LOCALAPPDATA\Reweave\reweave.db"
```

For an isolated development Library, set the data directory and pass its database
explicitly. These environment changes affect only the current PowerShell session:

```powershell
$env:REWEAVE_DATA_DIR = Join-Path (Get-Location) '.pytest_cache\development-library'
uv run reweave app --db (Join-Path $env:REWEAVE_DATA_DIR 'reweave.db') --port 8876
```

The CLI configuration can read `.env` and legacy `REWEAVE_LLM_*` variables. Prefer
Settings and the OS credential store for desktop keys; never commit `.env`, keys,
bridge descriptors, or real Library data. Automatic Context analysis uses an active
connected saved profile, not just a legacy environment key.

## Local API

After `uv run reweave app`, open [interactive API docs](http://127.0.0.1:8765/docs)
or [OpenAPI JSON](http://127.0.0.1:8765/openapi.json) for the current endpoint schema.
[`/api/health`](http://127.0.0.1:8765/api/health) reports readiness. Keep the server
on loopback; it is not a public hosting interface. The app validates Host and Origin,
and extension operations use a separate authenticated Native Messaging boundary.

## Repository map

```text
frontend/          React/TypeScript Reading Room interface
extension/         Chrome/Edge Save and Use extension
src/reweave/       Python archive, Context, retrieval, API, and desktop runtime
tests/             Regression tests, synthetic fixtures, and evaluation sets
scripts/           Native Messaging, packaging, and isolated verification tools
packaging/         PyInstaller bundle and Windows installer
docs/              Product contract, roadmap, decisions, and verification evidence
```

Read the [Product Spec](PRODUCT_SPEC.md), [Project Status](PROJECT_STATUS.md),
[Roadmap](ROADMAP.md), and relevant [Decisions](DECISION_LOG.md) before changing
product behavior. Keep the READMEs aligned in commands, capabilities, privacy,
and limits. Detailed canonical records stay in English under DEC-031.
