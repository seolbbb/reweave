# Reweave Project Status

## Snapshot

- Last verified: 2026-07-21
- Working language: English
- Current phase: PHASE-001
- State: active
- Repository state: TASK-001 is complete across persistence, extraction, backend API,
  Context Home and Explorer, and source-evidence navigation. Re-observe Git on every resume.
- Current implementation identity: Local archive and search application with a primary
  Context Home and Explorer, onboarding, archive management, optional hybrid search, cited
  Ask Archive, Insight Reports, and a Phase 0 Memory Audit pilot.
- Intended product identity: Linked Context Library and explicit web-chat Context layer defined in PRODUCT_SPEC.md.

## Implemented

Current code and historical verification show:

- ChatGPT and Claude JSON and zip import into a local SQLite archive.
- Idempotent archive update behavior and safe zip extraction.
- FTS5, trigram, and optional local semantic indexing with hybrid retrieval.
- Conversation search, source inspection, and Markdown export.
- Source-grounded Ask Archive with citation validation.
- Selected-conversation Insight Reports with BYOK providers.
- LLM provider profiles, operating-system credential storage, and model discovery.
- Archive backup, restore, removal, onboarding, local web UI, and pywebview desktop packaging.
- A separate Phase 0 Memory Audit pilot with claim extraction, evidence search, human review, local sessions, and redacted export.
- Windows PyInstaller packaging through packaging/Reweave.spec.
- Durable Conversation Brief and Context Item persistence in the main archive database,
  including structured Brief fields, item types, epistemic kinds, scopes, confidence,
  sensitivity, status, immutable versions, timestamps, item links, and source evidence.
- Compact source-evidence snapshots and nullable live source links that preserve derived
  Context when an original conversation is removed.
- Idempotent Brief persistence by source and analysis version, plus app-startup Context
  schema initialization.
- A dedicated source-grounded extraction pipeline that creates one required Conversation
  Brief and zero or more supported Context Items through the configured BYOK provider.
- Versioned Auto, Project, Learning, Research/Writing, and Context Handoff prompts that treat
  archived conversation content as untrusted data and require exact source excerpts.
- Conservative normalization for epistemic kind, scope, confidence, sensitivity, evidence,
  duplicate items, interrupted analysis, and changed source conversations.
- A non-blocking backend Context analysis job API that resolves inline or saved-profile BYOK
  settings, serializes model calls, reports terminal success or failure, and reuses unchanged
  completed analysis.
- Durable Context Brief and Item list/detail APIs that expose analysis metadata, scopes,
  versions, links, compact evidence snapshots, and whether the live source still exists.
- Context is the default application surface, with Home rendering recent Conversation Briefs,
  active projects and topics, insights and lessons, decisions, open questions, follow-up, and
  actions from the linked Context model.
- Explorer renders the same Context Items through Core Self, Personal, Work, Project, Topic,
  and Destination scopes without forcing one exclusive hierarchy; multi-scope items remain
  discoverable from every applicable space.
- Context Item detail renders type, epistemic kind, sensitivity, confidence, status, version,
  scopes, compact source evidence, source availability, and link/history counts.
- Context frontend loading, empty, error, and no-items-in-scope states are explicit and the
  Home and Explorer layouts adapt to desktop and 375-pixel mobile widths.
- Every live Context evidence reference offers an explicit action that opens the supporting
  conversation around the exact message in the existing conversation drawer.
- Evidence whose source conversation was removed remains readable as a compact local snapshot
  without a misleading source action; source-load failures preserve the excerpt and explain
  the fallback inline.
- A provider-neutral explicit web capture model validates complete ordered ChatGPT and Claude
  conversations, including stable external identity, timestamps, roles, message identity,
  non-empty content, duplicate IDs, unknown fields, and bounded payload size.
- `POST /api/capture/conversations` persists valid captures immediately without an LLM key,
  reuses the archive's transactional import, FTS, and embedding-invalidation path, and reports
  created, updated, or unchanged outcomes without returning raw conversation content.

The preceding list describes current software, not completion of the Context Library product contract.

## In progress

- TASK-000 and TASK-001 are integrated and verified.
- PHASE-001 remains active because the explicit web-chat Save and Use loop and durable
  automatic batching are not implemented.
- The first TASK-002 slice completes the provider-neutral local whole-conversation capture and
  idempotent persistence contract shared by future ChatGPT and Claude extension adapters.
- The next bounded TASK-002 slice is a secure Chrome/Edge extension-to-local-app connection
  scaffold and availability handshake; provider DOM adapters and Save UI follow after it.

## Verification evidence

### Fresh in the TASK-002 local capture contract slice

- Five focused capture tests passed for ChatGPT and Claude payloads, no-key persistence,
  restart reads, exact content and order, idempotent update and unchanged outcomes, FTS update,
  duplicate message identity, timestamp validation, and invalid or empty payload atomicity.
- Ruff passed across the repository.
- 132 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 23 frontend tests passed; frontend assets were not rebuilt because no frontend file changed.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,370,194 bytes).
- The packaged executable accepted ChatGPT and Claude captures without an LLM key, returned
  created then unchanged for an identical repeat, rejected an empty capture with HTTP 422,
  exposed both conversations in Library and Search, advertised the capture route in OpenAPI,
  and remained running for an isolated 8-second smoke. Temporary data and processes were removed.

### Fresh in the TASK-001 source-evidence navigation slice

- Ruff passed across the repository.
- 127 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 23 frontend tests passed, including live-evidence target validation and retained-source
  fallback rendering.
- TypeScript and the Vite production frontend build passed; packaged web assets were rebuilt.
- Browser checks against an isolated mixed live/deleted-source Context Item confirmed the
  exact-message drawer, target highlighting, context/all-message controls, close-button focus,
  Escape dismissal, retained snapshot copy, and inline failure fallback.
- At 375 by 812 pixels the evidence view had no horizontal overflow, the source action was 44
  pixels high, reduced-motion mode was active, and page errors and framework overlays were absent.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,364,647 bytes).
- The packaged executable remained running for an isolated 8-second smoke, returned healthy
  HTTP, exposed the Context Item route, and served a bundle containing both source-open and
  retained-fallback behavior. The temporary databases and processes were removed.

### Fresh in the TASK-001 Context Home and Explorer slice

- Ruff passed across the repository.
- 127 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 22 frontend tests passed, including default Context navigation, accessible Home/Explorer
  tabs, multi-scope discovery, and Brief-only section rendering.
- TypeScript and the Vite production frontend build passed; packaged web assets were rebuilt.
- Desktop and 375-pixel browser checks against an isolated populated Context database showed
  Home, Explorer, scope switching, item detail, compact evidence, sensitivity, and Brief-only
  fields with no page or console errors, no horizontal overflow, reduced-motion support, and
  no interactive target smaller than 44 by 44 pixels.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,364,647 bytes).
- The packaged executable remained running for an isolated 8-second smoke, returned healthy
  HTTP, exposed the Context Item route in OpenAPI, and served a frontend bundle containing the
  new Linked Context Library UI. The temporary databases and processes were removed.

### Fresh in the TASK-001 backend Context API slice

- 17 focused Context persistence, extraction, and API tests passed, including async success,
  unchanged-source reuse, saved-profile credential resolution, terminal failure, validation
  and not-found behavior, restart reads, and retained evidence after source deletion.
- Ruff passed across the repository.
- 127 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 19 frontend tests passed.
- TypeScript and the Vite production frontend build passed; packaged web assets were rebuilt.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,364,624 bytes).
- The packaged executable exposed healthy HTTP and Context-analysis OpenAPI routes, remained
  running for an isolated 8-second smoke, and created a Context schema v3 database with no
  foreign-key violations.

### Fresh in the TASK-001 extraction slice

- 14 focused persistence and extraction tests passed, covering restart durability, schema-v1
  migration, exact-evidence enforcement, prompt-injection boundaries, conservative labels,
  zero-item Briefs, duplicate merging, interrupted retry, idempotent reuse, and changed-source
  reanalysis.
- Ruff passed across the repository.
- 124 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 19 frontend tests passed.
- TypeScript and the Vite production frontend build passed; packaged web assets were rebuilt.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,345,691 bytes).
- The packaged executable remained running for an isolated 8-second startup smoke and was
  then stopped; its isolated database reported `context_schema_version=3` with no foreign-key
  violations.

### Fresh in the TASK-001 persistence slice

- Targeted Context persistence coverage passed inside the full suite for round-trip and
  restart durability, analysis-version idempotency, immutable item revisions, source deletion
  with retained evidence, invalid metadata rejection, and app-startup schema initialization.
- Ruff passed across the repository.
- 116 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 19 frontend tests passed.
- TypeScript and the Vite production frontend build passed; packaged web assets were rebuilt.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,343,817 bytes).
- The packaged executable remained running for an isolated 8-second startup smoke and was
  then stopped; its isolated database reported `context_schema_version=1` with no foreign-key
  violations.

### Fresh in this documentation task

- Repository re-observed after the other session's integration: clean main at 034a206 before documentation materialization.
- manage-project-intent bootstrap dry-run reported exactly four new documents and one AGENTS.md append with no overwrite.
- Bootstrap applied without overwriting existing files.
- Strict Full document validation passed with zero errors and warnings.
- Placeholder, English-only, stale-canonical-reference, and scoped-change checks passed.
- git diff --check passed with line-ending notices only.
- A fresh-context Goldfish agent reconstructed the product intent, priority values, interventions, accepted and superseded decisions, current implementation drift, hard constraints, and single Next task with no implementation-blocking ambiguity.
- No PyInstaller build was run because this task changed documentation and AGENTS.md only.

### Historical implementation evidence

The integrated 2026-07-21 work record reports:

- Ruff passed.
- 110 Python tests passed.
- 19 frontend tests passed.
- TypeScript and production frontend build passed.
- A fresh PyInstaller build created dist/Reweave/Reweave.exe.
- An 8-second packaged executable startup smoke passed.
- PR 10 merged to dev and dev merged to main.

These are historical merge records and were not rerun by the current documentation-only task.

## Drift and gaps

- The accepted Product Spec replaces the historical AI Memory Control Plane and manual Memory Audit direction, but current code still exposes Memory Audit as a standalone surface.
- The accepted product removes user-facing Ask Archive, but current code still implements and exposes it.
- Conversation Brief and Context Item persistence, one-conversation automatic extraction,
  backend analysis/read APIs, Context Home, Explorer, and source-evidence navigation now
  exist, but durable batching/retry, full Core Self behavior, automatic routing, Knowledge
  Graph, correction learning, and exception Review do not yet exist.
- The local whole-conversation capture contract now exists, but a Chrome/Edge extension,
  secure local connection handshake, ChatGPT and Claude DOM adapters, explicit Save and Use
  actions, and non-blocking reminders do not yet exist.
- Current Insight Reports have not yet been migrated into Conversation Brief and analysis-history behavior.
- Current archive search has not yet been reframed or connected as Sources / Evidence Search for Context.
- Current archive backup and removal do not yet satisfy the Context Library's encrypted
  version backup and separate derived-context deletion contract.
- The README and AGENTS.md project overview correctly describe the software that exists now; they must not claim future Context behavior until it is implemented.

## Blockers

- None for TASK-002.
- The public v1 scope freeze and encrypted-synchronization timing are intentionally deferred to PHASE-004 and do not block the current phase.

## Next task

- TASK-002: Implement the ChatGPT and Claude whole-conversation Save to Reweave extension
  flow with idempotent update and non-blocking save reminders.
- Current bounded slice: Create the Manifest V3 Chrome/Edge extension scaffold and the secure
  local connection and availability handshake it will use before reading any provider page.
  Select the local transport only after comparing browser support, discovery, origin exposure,
  port conflicts, and packaged-app behavior. ChatGPT and Claude DOM reading, Save UI, and
  reminders remain later TASK-002 slices.
- Acceptance: The extension can determine whether the packaged Reweave app is available and
  can reach only the intended local service through the selected transport; ordinary web pages
  do not gain capture access; unavailable, conflicting, and malformed handshake states produce
  an actionable extension status; the scaffold loads in both Chrome and Edge without reading
  page content or requesting broader host permissions than this handshake needs.
- Verify: Add automated transport, origin/authorization, discovery, unavailable-app, conflict,
  and malformed-handshake tests plus extension manifest checks; run the full repository gates
  and strict document validator; create `dist/Reweave/Reweave.exe` with the required clean
  PyInstaller command; load the unpacked extension in Chromium; and smoke the packaged handshake
  with both available and unavailable local-app states.

## Resume checklist

1. Read AGENTS.md and PRODUCT_SPEC.md, PROJECT_STATUS.md, ROADMAP.md, then relevant DECISION_LOG.md entries.
2. Re-observe Git status, current code, tests, and runtime behavior.
3. Compare observed behavior with the Product Spec and record drift.
4. Confirm that the documented Next task is singular, actionable, and represented in the Roadmap.
5. Implement only that task unless the user explicitly changes scope.
6. Run repository-required checks, including the fresh Windows executable build for implementation tasks.
7. Update affected canonical documents in the same task and never replace current evidence with historical claims.
