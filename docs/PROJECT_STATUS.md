# Reweave Project Status

## Snapshot

- Last verified: 2026-09-11 (bilingual documentation, focused regression and fresh executable verification)
- Working language: English
- Current phase: PHASE-002
- State: active
- Repository state: The README refresh started from clean `main` at b0f64c5 on
  `codex/bilingual-readme`. It changes reader documentation and its canonical record, not
  application behavior. Its verification is recorded below. The earlier product delivery
  started from a clean worktree at 2303357 on
  `codex/reading-room-product`. The required dev-PR/main integration record accompanies the
  delivered artifacts; re-observe Git tips rather than inferring them from this source snapshot.
  Historical TASK-001 through TASK-004 evidence below is not treated as a fresh run.
  DEC-026 permits isolated implementation before final real-data acceptance.
- Current implementation identity: Reading Room Context Home, Explore, Sources and global search,
  with complete-source import analysis, linked spaces, correction history, trust, Graph, Review
  and encrypted maintenance. Ask Archive, Insight Reports and the Phase 0 audit remain internal legacy data/API
  foundations; their standalone UI destinations have been removed.
- Intended product identity: Linked Context Library and explicit web-chat Context layer defined in PRODUCT_SPEC.md.

## Implemented

The following is observed in the current working tree. Verification strength and remaining
limitations are separated below; presence in this list is not final product acceptance.

- Local ChatGPT/Claude whole-conversation Save and export Import persist sources before analysis.
  Original-message keyword/optional local semantic search and source removal remain available.
- Durable analysis queues now include explicit reanalysis generations, saved provider selection,
  idle/batch scheduling, daily attempt/token reservations, pause, retry and restart recovery.
- The complete-source analysis work adds bounded sequential segments, normalized checkpoints,
  hierarchical Brief synthesis, coverage metadata and explicit incomplete states. Semantic
  reconciliation uses bounded compatible candidates and preserves user corrections. Actual key
  sends share invocation/run caps; restoring matching runs cannot rewind spent calls (DEC-029/030).
- Schema v7 stores canonical linked spaces, aliases, rename/merge revisions, source-grounded
  Briefs and Context Items, distinct observed/inferred/suggested claims, rationale, confidence,
  sensitivity, source snapshots, item links and immutable user correction/undo history.
- Progressive local Context retrieval scopes before ranking, broadens low-confidence candidates,
  expands links, and supports global keyword/optional cached semantic matching. Both Context and
  original-source search support linked-space and item-type filters with bidirectional evidence
  navigation. No local embedding model was downloaded during this task.
- Explicit Use records corrected destination intent; Work/Client/Shared/unknown use requires
  allowed scopes. Version-bound sensitive preview/confirmation is separate, expiring and one-use.
  Current chat and draft remain transient; the extension preserves the draft and never submits.
- Exception Review identifies sensitive inference, ambiguity, changed evidence, low confidence,
  stale confidence and unresolved relationships. Dismissal does not authorize external Use.
  Version-bound resolution and undo preserve the original content and source evidence.
- Reading Room Home, Explore, Sources, global Search, Import, Settings, onboarding, queue,
  correction, sharing and extension surfaces use the selected shared ivory/sage design. Graph
  and Review are auxiliary Explore views. Standalone Ask Archive and Memory Audit destinations
  are removed while their historical stored data and internal APIs remain available.
- Local Graph reads canonical items, spaces and links. Sharing excludes private/sensitive scopes,
  starts with generic labels, and exports only an explicit expiring preview. The generated PNG
  was decoded and inspected in the isolated browser; native file saving remains a manual check.
- Password-encrypted complete backups preserve source/Context/queue/settings data and exclude
  protected credentials. Exclusive restore validates staged data, uses a recovery journal,
  disconnects profiles and reports committed-but-restart-required recovery accurately. Plaintext
  backup/restore HTTP routes are retired. Derived Library deletion is separate from source removal.
- Loopback Host/exact Origin validation, maintenance leases, memory-only verification credentials,
  bounded headless lifetime and owned runtime-descriptor cleanup protect isolated operation.
  User-triggered attachment saving is explicitly enabled in the native WebView2 launcher.
- Redacted diagnostics expose allowlisted counts and runtime versions without text, source/item
  identity, local paths, provider addresses, personal instructions or keys.

## In progress

- Full accepted Windows product completion is authorized; detailed preserved scope and staged
  coverage live in `docs/execution/2026-09-09-product-completion.md`.
- TASK-005 through TASK-008 and TASK-010 have their isolated implementation evidence.
  TASK-009 and TASK-011 remain open for native Save File acceptance; phase exits and actual
  usefulness remain open. TASK-012 is the single next acceptance task under DEC-026.

- TASK-000 through TASK-004 are integrated and verified through the required repository delivery
  loop.
- PHASE-001 exit criteria are complete after the optional-backfill onboarding passed automated,
  responsive-browser, clean executable-build, and packaged restart verification.
- The five TASK-002 slices complete the provider-neutral local capture contract, secure
  Chrome/Edge Native Messaging scaffold, explicit ChatGPT and Claude whole-conversation Save,
  and non-blocking page-lifetime unsaved reminders.
- TASK-004 is complete across durable queue, automatic local scheduler, and optional-backfill
  first-run onboarding slices.
- The former PHASE-002 real-data entry prerequisite is superseded by DEC-026. Actual private
  dogfooding remains unverified and mandatory in TASK-012; no current user archive was inspected.

## Verification evidence

### Bilingual README refresh, 2026-09-11

- Re-observed current source, manifests, launcher defaults, extension registration, Git tips,
  release availability, tests and real packaged behavior. The public repository had zero
  published releases and zero configured Actions workflows; Issues was enabled and Discussions
  disabled. The README does not advertise a downloadable public build or a passing CI badge.
- Equivalent English and Korean READMEs now lead with the product, existing synthetic app
  screenshots, first-run commands, and the Save/Import-to-Use flow. Detailed CLI, configuration,
  API discovery and checks live in `docs/DEVELOPMENT.md`. DEC-031 records the narrow owner-approved
  localization exception. AGENTS.md's protected language section was not modified.
- Reference review covered Open WebUI, AnythingLLM, Logseq and Khoj. Local file/heading links,
  Markdown parsing, image descriptions and all four shared PowerShell command blocks passed
  the documentation audit. Reference counts and verification details are in
  `docs/verification/2026-09-11/readme-refresh.md`.
- `uv sync --locked` passed. Frontend tests: 102 passed; TypeScript/Vite production build passed
  with unchanged tracked assets. An initial build through the C: alias failed on mixed resolved
  paths; rerunning from the physical D: checkout passed without a code or configuration change.
- Focused CLI/parser/registration/runtime regression: 65 passed, with one existing Starlette
  deprecation warning. All 12 help/fixture CLI invocations, Ruff, strict-full canonical validation
  (zero errors/warnings) and diff hygiene passed. Fresh PyInstaller build created both Windows executables.
  The existing packaged synthetic smoke passed Save, no-key queueing, one loopback fake-provider
  analysis, exact evidence, explicit Use, restart, idempotence, transient-draft handling and
  owned shutdown. Its privacy-safe report is `docs/verification/2026-09-11/packaged-readme-smoke.json`.
- No owner Library, native dialog, browser profile, registry registration, model download, paid
  provider call or public binary release was used. TASK-012 remains the single Next task;
  documentation delivery does not close real-owner acceptance or TASK-014 publication.

### Current execution, 2026-09-09 through 2026-09-10

- Read instructions, canonical records, the selected A image and supplied design documents.
  Git was clean at 2303357 before creating the feature branch. No owner archive was inspected.
- Original audit findings remain in `docs/verification/2026-09-10/product-scope-audit.md` as a
  historical snapshot. Reanalysis, complete-source coverage, semantic relationships, original
  source filters and idle/batch scheduling now have implementation and regression evidence.
  Independent extraction/integration reviews reproduced and closed the recorded scope,
  source identity, consent lifetime, call accounting, restore and owner/shutdown defects.
- Latest completed frontend run: 102 tests passed. TypeScript check passed. Actual browser QA
  used real local HTTP with isolated synthetic data; source correction conflict/save/undo,
  space rename/merge, search/evidence navigation, Review dismissal, graph navigation/redaction,
  encrypted preview/restore and redacted diagnostics passed the documented scenarios.
- Browser evidence is `docs/verification/2026-09-10/browser-qa-report.md` and its linked captures.
  Matched Home passed at 1280x720 and 375x812. The source-drawer Escape focus defect was fixed
  and rechecked against the exact opener. Headless download completion was canceled even for an
  independent control, so file writing is not claimed from generated Blob/PNG evidence.
  Headless browser zoom keys did not change zoom; 640x360 layout reflow was verified instead.
- A separate native launcher defect was found in installed pywebview: downloads default off.
  The launcher now enables user-triggered Save File dialogs before window creation. A mocked
  launcher contract and isolated runtime/backup/origin suite passed 73 tests; no native dialog
  was opened. Real Windows Save File interaction remains a separate owner check.
- Python regression, frontend production-build and final installer evidence are recorded in
  `docs/verification/2026-09-10/final-verification.md`, together with exact executable identities.
  These are synthetic checks and packaging evidence, not real LLM quality or owner usefulness.
- The final clean PyInstaller build succeeded. The two real executables passed framed Native
  Messaging capture, no-key persistence, one loopback synthetic analysis, exact evidence, explicit
  destination-safe Use, restart, repeated-Save idempotence and owned shutdown cleanup. The raw
  privacy-safe result is `docs/verification/2026-09-10/packaged-runtime-final.json`.
- Final core Python suite: 535 passed; separate distribution-helper suite: 13 passed. Frontend:
  102 passed. The 50,343,040-byte final installer passed isolated install/uninstall, verification
  of all 720 installed file hashes and unrelated-file preservation. It started no application,
  changed no real registry or shortcut, and did not touch the owner Library.
- No paid provider call, model download, user-browser action or Native Messaging registration
  occurred. Browser-QA and packaged-test owned processes exited; no owner app was closed.
- Strict-full validation passed with zero errors/warnings. A fresh-context reviewer recovered
  the full product, priority values, DEC-026/027 interventions, implementation, constraints and
  single TASK-012 acceptance path without an unanswered implementation question. Its independent
  artifact hash check passed; it correctly kept real usefulness and Git integration outside its
  reviewed evidence. See `docs/verification/2026-09-10/handoff-reconstruction.md`.

All following "Fresh" subsection titles refer to their historical slices, not the current run.

### Fresh in the TASK-004 optional-backfill onboarding slice

- Ruff passed across the repository; all 177 Python tests passed; all 57 frontend tests passed;
  production extension JavaScript syntax, TypeScript, the Vite production build, and final diff
  checks passed.
- First-run regressions cover visibly recommended but optional export backfill, direct no-import
  continuation, no-key behavior, automatic queued analysis after saved provider connection,
  current Chrome/Edge extension guidance, the preserved Import and Settings destinations, durable
  completion, existing-user behavior, and fail-closed onboarding when archive counts are unknown.
- Browser flows at 1280 by 720 and 375 by 812 pixels passed recommended-backfill, direct skip,
  no-key Context, Settings, and existing Import paths with no console warnings or errors and no
  horizontal overflow. The corrected mobile dialog uses an internal vertical scroll area, step
  headings receive focus after navigation, and the extension setup link plus core actions meet the
  44-pixel target.
- A fresh clean PyInstaller build created `dist/Reweave/Reweave.exe` (17,405,681 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,234,930 bytes).
- The isolated packaged app returned healthy HTTP, served the new hashed frontend bundle and its
  optional-backfill, automatic-queue, and current-extension copy, exposed an empty no-key Context
  library with no connected provider, and returned healthy HTTP with the same bundle after a full
  process restart. Its database reported `context_schema_version=5`, zero conversations, messages,
  Briefs, and Context Items, and zero foreign-key violations. Both packaged processes stopped and
  all isolated browser and package data was removed.
- A read-only check of the product owner's default local database found schema version 2, zero
  conversations and messages, and no Context schema yet. No conversation content was read. This is
  current evidence for the PHASE-002 entry blocker, not an implementation failure in TASK-004.
- Strict Full document validation passed with zero errors and warnings.

### Fresh in the TASK-004 automatic scheduler slice

- Ruff passed across the repository; all 177 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning. Deterministic coverage includes schema-v4-to-v5 migration,
  bounded atomic claims, source-version concurrency, startup, capture, and profile-connect wakeup,
  no-key and offline attempt-free deferral, local estimates before provider invocation, safe
  transient failure state, capped retry scheduling, explicit retry, terminal idempotency, and
  provider failover error classification.
- All 54 frontend tests passed; TypeScript and the Vite production build passed and reproduced the
  packaged web assets. `git diff --check` passed with line-ending notices only.
- A fresh clean PyInstaller build created `dist/Reweave/Reweave.exe` (17,405,681 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,234,930 bytes).
- The isolated packaged app returned healthy HTTP, accepted one authenticated no-key capture as
  created, and kept its queue job pending with zero attempts and no estimate because no saved BYOK
  profile was connected. After a forced process stop and full packaged restart, the same job ID,
  pending state, and zero-attempt count remained readable.
- The isolated packaged database reported `context_schema_version=5`, one pending zero-attempt
  queue row with no scheduled retry or usage estimate, and zero foreign-key violations. Both
  packaged processes stopped and the isolated database, descriptor, profile, model, import, and
  extraction paths were removed.

### Fresh in the TASK-004 durable analysis-queue slice

- Ruff passed across the repository; all 170 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning. Focused queue, capture, Context persistence, extraction,
  and API coverage passed 31 tests for schema migration, capture-enqueue ordering, source-version
  idempotency and supersession, restart recovery, current inline and saved-profile retry,
  missing-key and provider failures, sanitized durable errors, terminal success, and credential
  non-persistence.
- All 54 frontend tests passed; TypeScript and the Vite production frontend build passed and
  reproduced the current packaged web assets. `git diff --check` passed with line-ending notices
  only.
- A fresh clean PyInstaller build created `dist/Reweave/Reweave.exe` (17,395,981 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,234,930 bytes).
- The isolated packaged app accepted an authenticated no-key capture as created, returned
  unchanged for an identical repeat, kept one pending zero-attempt job, exposed durable queue and
  retry routes, and returned that same job after a full process restart. Its SQLite database
  reported `context_schema_version=4`, one pending queue row, and zero foreign-key violations.
- Both packaged app processes stopped and the isolated database, descriptor, profile, model,
  import, and extraction paths were removed.
- Strict Full document validation passed with zero errors and warnings.

### Fresh in the TASK-003 explicit Use slice

- Ruff passed across the repository; all 164 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning; all 54 frontend tests passed; production extension
  JavaScript syntax, TypeScript, the Vite production frontend build, focused bridge and provider
  regressions, and `git diff --check` passed.
- Deterministic ChatGPT and Claude coverage verifies complete current-chat and non-empty draft
  collection only after Use, private cross-space scope handling, sensitive exclusion, unsupported
  and unknown-page rejection, streaming, empty, oversized, changed-DOM, concurrent-edit,
  app-unavailable, malformed-response, insertion, replacement, refresh, no-passive-read, Save,
  and reminder behavior.
- A fresh clean PyInstaller build created `dist/Reweave/Reweave.exe` (17,388,856 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,234,930 bytes). The packaged app published its
  authenticated runtime descriptor and served the populated Context assembly path.
- Chrome for Testing used the packaged app and native host to insert three Context Items into the
  ChatGPT fixture and refresh them while preserving the draft and one block. Installed Microsoft
  Edge inserted four items into the Claude fixture with the same refresh and preservation result.
- After the packaged app stopped, Chrome and Edge each returned `app_not_running` for Use and left
  the corresponding fixture draft unchanged. The temporary host permission existed only in the
  isolated automation copy; the production manifest remained permission-minimal.
- Temporary browser profiles, the automation extension, isolated data, packaged processes, Native
  Messaging manifests, and Chrome and Edge registry entries were removed after verification.

### Fresh in the TASK-003 Context assembly slice

- Seven focused assembly tests passed for ChatGPT and Claude normalization, bridge-token
  authentication, input bounds, empty drafts, unknown and unsafe scopes, destination and
  sensitivity filtering, deterministic ranking, exact-text and previously supplied item
  deduplication, whole-item budgeting, untrusted-item rendering, compact provenance, unavailable
  context, and no-write behavior. The focused Context, capture, and bridge regression set passed
  all 31 tests.
- Ruff passed across the repository; all 159 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning; all 45 frontend tests passed; all production extension
  JavaScript files passed syntax checks; TypeScript and the Vite production frontend build passed;
  strict project-document validation and final diff checks passed.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,388,472 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,233,179 bytes).
- The packaged app published its authenticated runtime descriptor against an isolated populated
  Context database. An unauthenticated assembly request returned HTTP 403; authenticated ChatGPT
  and Claude requests each returned the same two deterministic project items, insertion markers,
  compact provenance, and 551 characters within a 1,200-character budget.
- Packaged request no-write verification kept the isolated database at exactly four
  conversations, twelve messages, one Conversation Brief, and six Context Items. The packaged
  process and isolated temporary data were removed after the smoke.

### Fresh in the TASK-002 unsaved-reminder slice

- Ruff passed across the repository; all 152 Python tests passed with one pre-existing
  Starlette/httpx deprecation warning; all 45 frontend tests passed; extension JavaScript syntax,
  TypeScript, the Vite production frontend build, strict Full project-document validation, and
  `git diff --check` passed.
- Deterministic ChatGPT and Claude coverage confirms structural reminder snapshots do not clone
  or read message content, the exact 30-second inactivity threshold, new-assistant detection,
  eight-second prompt auto-hide with persistent badge, dismissal and re-arming, explicit
  re-Save, streaming deferral, changed-DOM and identity failure, app-unavailable retry, sender
  validation, navigation clearing, and browser-startup badge clearing.
- A one-second identity-only page-lifetime check closes the SPA navigation gap without reading
  conversation content; both providers stop and clear state when only the conversation URL
  changes and the DOM remains still.
- The production manifest remains limited to `nativeMessaging`, `activeTab`, and `scripting`,
  with no provider host permission, static content script, or extension storage. The isolated
  browser harness added both provider host permissions and shortened reminder timers only to its
  temporary copy because programmatic popup activation does not confer `activeTab`.
- Google Chrome for Testing 145 saved the two-message ChatGPT fixture through the newly packaged
  app and native host, displayed the reminder and `SAVE` badge, updated the archive to four
  messages through the in-page Save button, cleared on dismissal, and re-armed after another
  assistant response. With the app stopped, reminder Save remained retryable and did not write;
  subsequent navigation cleared the badge.
- Installed Microsoft Edge 150 saved the four-message Claude fixture, displayed the same
  non-blocking reminder, and updated the archive to six messages through the in-page Save button.
  The combined isolated archive contained exactly two conversations and ten messages after both
  successful flows and the failed unavailable-app attempt.
- Browser screenshots confirmed the light reminder card at the lower-right without obscuring
  fixture content, one 44-pixel primary Save action, and a clear secondary dismissal action.
- A fresh clean PyInstaller build completed successfully and created
  `dist/Reweave/Reweave.exe` (17,374,427 bytes) and
  `dist/Reweave/ReweaveNativeHost.exe` (2,233,179 bytes). The packaged app published its
  authenticated bridge and served both browser flows before the unavailable-app scenario.
- Temporary browser profiles, packaged app and native-host processes, per-user Chrome and Edge
  registry keys, native-host manifest, and isolated application data were removed after QA.

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

- Implementation, generated-file evidence, isolated installation, normal native interaction and
  owner usefulness are distinct. No confirmed P1/P2 finding remains in the bounded independent
  extraction and integration reviews; that statement is not a guarantee against unknown defects.
- Native Save File completion and actual desktop 200% zoom have not been exercised because
  current authorization excludes visible windows and physical desktop interaction.
- Historical Insight Reports and Memory Audit records are preserved internally rather than
  retroactively relabeled as Conversation Briefs. Newly requested analysis uses the Context path.
- Actual extraction quality, useful cross-chat reuse and reduced repeated explanation remain
  unverified until the selected real-data acceptance in TASK-012. Synthetic tests cannot close it.
- The English local beta/privacy/support handoff is in `docs/release/`. GitHub Issues was enabled
  and Discussions disabled in the read-only 2026-09-10 snapshot. Public support enablement,
  signing/distribution, v1 scope freeze, synchronization timing and publication remain owner decisions.

## Blockers

- No implementation blocker remains from the old real-data prerequisite (DEC-026). Final
  completion still requires selected real data, approved provider costs/transmission, and the
  owner's real-use judgment. These approvals have not yet been requested or granted.
- Native installation and real account/browser interaction require separate user permission or
  a prepared manual check; no desktop interaction is authorized.
- The public v1 scope freeze and encrypted-synchronization timing are intentionally deferred to PHASE-004 and do not block the current phase.

## Next task

- TASK-012: Run the selected real-owner round-trip and close native acceptance before judging
  sustained usefulness. DEC-026 allows this acceptance work to resolve earlier open phase gates.
- Acceptance: Owner-selected Save/Import, explicitly approved provider/model/data/call/cost/stop
  bounds, real analysis, app restart, faithful source inspection and explicit draft-preserving Use.
  The owner judges reduced repeated explanation and a useful graph relationship. Verify normal
  installation/browser registration, native backup/PNG/diagnostic saving and 200% zoom through
  owner operation or separately authorized assistance. Keep source text and credentials private.
- Verify: Follow `docs/verification/2026-09-10/owner-acceptance.md`; record privacy-safe outcomes,
  real latency/cost, misses/corrections and native results. Fix evidenced defects in the same task,
  repeat relevant checks and rebuild before new delivery. Synthetic evidence never closes this task.

## Resume checklist

1. Read AGENTS.md and PRODUCT_SPEC.md, PROJECT_STATUS.md, ROADMAP.md, then relevant DECISION_LOG.md entries.
2. Re-observe Git status, current code, tests, and runtime behavior.
3. Compare observed behavior with the Product Spec and record drift.
4. Confirm that the documented Next task is singular, actionable, and represented in the Roadmap.
5. Implement only that task unless the user explicitly changes scope.
6. Run repository-required checks, including the fresh Windows executable build for implementation tasks.
7. Update affected canonical documents in the same task and never replace current evidence with historical claims.
