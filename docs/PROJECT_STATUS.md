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
  created, updated, or unchanged outcomes without returning raw conversation content. Explicit
  web captures use stable provider identity rather than the import path's timestamp fallback, so
  distinct conversations with the same creation time cannot overwrite one another.
- The production Manifest V3 extension uses `nativeMessaging`, `activeTab`, and `scripting`, with
  no provider or localhost host permissions and no persistent content script. It queries and
  injects the matching adapter into the active ChatGPT or Claude tab only after the user invokes
  Save from the popup or the browser action shortcut.
- The ChatGPT adapter fails closed unless it can identify one supported HTTPS conversation URL,
  a signed-in page, consecutive complete conversation turns, a user-authored first turn, unique
  message identities, non-empty content, and bounded normalized output.
- The Claude adapter uses the same explicit action boundary and fails closed unless it can
  identify one supported HTTPS conversation UUID, a signed-in page, stable current DOM markers,
  the complete alternating turn sequence, unique message identities, non-empty content, and
  bounded normalized output.
- The popup reports created, updated, unchanged, unsupported, logged-out, changed-DOM,
  incomplete, oversized, invalid, unavailable, and incompatible outcomes with one explicit
  44-pixel Save action and no passive provider-page read.
- The desktop app publishes an atomic, short-lived runtime descriptor with an ephemeral token,
  protects the loopback availability handshake with that token, and removes only its own
  descriptor during an orderly shutdown.
- A separately packaged `ReweaveNativeHost.exe` implements bounded native-message framing,
  reads the private runtime descriptor, probes the authenticated loopback handshake, forwards a
  bounded sanitized capture to the authenticated app endpoint, and returns only bounded status
  and capture summaries without exposing the token, port, or raw conversation.
- Development registration scripts create and remove the exact per-user Chrome and Edge Native
  Messaging registry entries and restrict the host manifest to explicit extension origins.

The preceding list describes current software, not completion of the Context Library product contract.

## In progress

- TASK-000 and TASK-001 are integrated and verified.
- PHASE-001 remains active because the explicit web-chat Save and Use loop and durable
  automatic batching are not implemented.
- The first four TASK-002 slices complete the provider-neutral local capture contract, the
  secure Chrome/Edge Native Messaging scaffold, and explicit ChatGPT and Claude
  whole-conversation Save.
- The next bounded TASK-002 slice is the non-blocking unsaved-conversation reminder after an
  explicit Reweave action on the tab. TASK-003 remains the later Use Reweave flow.

## Verification evidence

### Fresh in the TASK-002 explicit Claude Save slice

- Ruff passed across the repository; 151 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning; 34 frontend tests passed; extension JavaScript syntax,
  TypeScript, and the Vite production frontend build passed.
- Fixture and boundary coverage confirms current Claude normalization, title and timestamp
  handling, logged-out and changed-DOM rejection, incomplete or streaming-turn rejection, no tab
  query or injection before Save, provider-adapter matching, production permission minimization,
  native forwarding, provider-specific popup errors, and unchanged ChatGPT behavior.
- The production manifest still has no provider host permission or persistent content script.
  The browser fixture harness temporarily granted only `https://claude.ai/*` because a
  programmatically invoked popup button does not confer `activeTab`; the shipped extension code
  and manifest were otherwise unchanged.
- Chrome for Testing and the installed Microsoft Edge each saved a different four-message Claude
  fixture through the packaged native host and app, then reported `Already up to date` on the
  identical repeat. The isolated archive contained exactly two Claude conversations and eight
  ordered messages. A changed-DOM fixture failed before persistence in both browsers.
- Both browser popup checks showed a 44-pixel primary action and no horizontal overflow. After
  Cold Turkey was disabled, the user's Chrome connected to `claude.ai` successfully and reached
  Claude's login screen; no account data or real conversation was accessed.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,374,427 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,233,179 bytes).
- The final packaged native host rejected an invalid Claude capture as `invalid_capture`, emitted
  no stderr or trailing stdout bytes, and left the isolated archive unchanged at two
  conversations and eight messages.
- Temporary browser sessions, packaged app processes, per-user Chrome and Edge registry keys,
  native-host manifests, and isolated test data were removed after verification.

### Fresh in the TASK-002 explicit ChatGPT Save slice

- Ruff passed across the repository; 151 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning; 28 frontend tests passed; extension JavaScript syntax,
  TypeScript, and the Vite production frontend build passed.
- Fixture and boundary coverage confirms current ChatGPT normalization, logged-out and
  changed-DOM rejection, incomplete-turn rejection, no tab query or injection before Save,
  production permission minimization, bounded Native Messaging forwarding, actionable errors,
  invalid-payload atomicity, and distinct same-time conversation identity.
- The production manifest has no provider host permission or persistent content script. The
  browser fixture harness temporarily granted only `https://chatgpt.com/*` because a
  programmatically invoked popup button does not confer `activeTab`; the shipped extension code
  and manifest were otherwise unchanged.
- Chrome for Testing and the installed Microsoft Edge each saved a different fixture
  conversation through the packaged native host and app, then reported `Already up to date` on
  the identical repeat. The isolated archive contained exactly two conversations and four
  ordered messages. A changed-DOM fixture failed before persistence.
- Both browser popup checks showed a 44-pixel primary action and no horizontal overflow. The
  installed Chrome executable launched after Cold Turkey was disabled, but its current automated
  launch mode did not load an unpacked extension; Chrome for Testing supplied the equivalent
  Chromium extension scenario without using the user's browser profile.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,374,427 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,233,179 bytes).
- The final packaged native host rejected an invalid capture as `invalid_capture`, emitted no
  stderr or trailing stdout bytes, and left the isolated archive unchanged at two conversations
  and four messages.
- `npm audit` still reports one low-severity development-server advisory in Vite's existing
  esbuild dependency; no production server exposure or moderate, high, or critical advisory was
  introduced in this slice.

### Fresh in the TASK-002 Native Messaging scaffold slice

- 14 focused extension bridge and manifest tests passed for atomic descriptor ownership,
  environment discovery, token authorization, inactive bridge behavior, fragmented and invalid
  native-message framing, ready/unavailable/incompatible/malformed status, response secrecy,
  permission minimization, no provider page access, and accessible popup states.
- Ruff passed across the repository.
- 146 Python tests passed with one pre-existing Starlette/httpx deprecation warning.
- 23 frontend tests passed; frontend assets were not rebuilt because no `frontend/` file changed.
- The unpacked Manifest V3 extension loaded as `Reweave` in Chrome for Testing and the installed
  Microsoft Edge. Both used extension ID `kkpjbndfdpobgjobejohcegnebnnknej` for the tested path.
- With temporary per-user Native Messaging registration and isolated app data, Chrome and Edge
  rendered `Reweave is ready` while the packaged app ran; after it stopped, Chrome rendered
  `Open Reweave to continue` and a 44-pixel Retry action. The popup had no horizontal overflow,
  dark mode and reduced motion were active when requested, and the extension never received the
  loopback port or token.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,374,279 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,231,325 bytes).
- The final packaged native host accepted an exact binary-framed ping, emitted one clean framed
  response with no stderr or trailing stdout, reported `app_not_running` from isolated data,
  and created no app-data files or directories while the app was unavailable.
- Temporary browser sessions, packaged app processes, per-user Chrome and Edge registry keys,
  native-host manifests, and isolated test data were removed after verification.

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
- The local whole-conversation capture contract, secure Chrome/Edge extension bridge, ChatGPT and
  Claude DOM adapters, and explicit Save paths now exist, but Use Reweave and non-blocking
  reminders do not yet exist.
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
- Current bounded slice: Implement a non-blocking unsaved-conversation reminder for ChatGPT and
  Claude after the user has explicitly saved the tab. Install only an action-triggered,
  page-lifetime observer; keep the production manifest free of provider host permissions and
  persistent content scripts; retain only the minimum ephemeral saved baseline and dismissal
  state needed for the reminder. TASK-003 will later reuse this boundary after Use Reweave.
- Acceptance: After a successful Save, meaningful complete new turns or the accepted inactivity
  condition produce a small non-blocking Save prompt and extension badge; clicking the reminder
  reuses explicit whole-conversation Save and clears it; dismissing suppresses it until
  substantial new complete content exists; navigation, unsupported or changed DOM, streaming
  output, app unavailability, and browser restart fail closed without capture or durable browsing
  history; no provider page is read before the first explicit Reweave action.
- Verify: Add deterministic ChatGPT and Claude fixture tests for new-turn, inactivity, dismissal,
  navigation, streaming, and changed-DOM states; retain permission and pre-action access
  regressions; run full repository gates and strict document validation; create a fresh clean
  Windows executable; and exercise Chrome and Edge packaged reminder, dismissal, Save, and
  unavailable-app scenarios against isolated data.

## Resume checklist

1. Read AGENTS.md and PRODUCT_SPEC.md, PROJECT_STATUS.md, ROADMAP.md, then relevant DECISION_LOG.md entries.
2. Re-observe Git status, current code, tests, and runtime behavior.
3. Compare observed behavior with the Product Spec and record drift.
4. Confirm that the documented Next task is singular, actionable, and represented in the Roadmap.
5. Implement only that task unless the user explicitly changes scope.
6. Run repository-required checks, including the fresh Windows executable build for implementation tasks.
7. Update affected canonical documents in the same task and never replace current evidence with historical claims.
