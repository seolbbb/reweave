# Reweave Roadmap

## Document control

- Status: active
- Last reviewed: 2026-09-10
- Working language: English

## Status vocabulary

- planned: accepted future work that has not started.
- active: the one phase currently being executed.
- blocked: accepted work that cannot progress until a named condition changes.
- done: exit criteria and verification evidence are complete.
- superseded: intentionally replaced by a linked phase or decision.

## Current phase

- Phase: PHASE-002
- Outcome: Complete linked personalization, trust, retrieval, and Reading Room flows using
  isolated verification, then close native and real-owner acceptance through TASK-012.
  DEC-026 permits this cross-phase acceptance work before later phases can be marked done.

## Phases

### PHASE-000 — Canonical document convergence

- Status: done
- Outcome: Future agents can reconstruct the accepted Context Library product, current implementation drift, protected user values, delivery order, and exactly one Next task from repository documents alone.
- Dependencies: Clean integrated main branch at 034a206 and an approved Full interview plan.
- Entry criteria: The decision-completion interview has terminal states for every material route and the user has approved document materialization.
- Exit criteria: The four-document record is complete, routed, validated, and independently reconstructable.
  - PRODUCT_SPEC.md, ROADMAP.md, PROJECT_STATUS.md, and DECISION_LOG.md contain no placeholders.
  - AGENTS.md routes work to the four documents without changing protected PR, language, or executable-build rules.
  - The historical combined strategy is visibly superseded as the active contract but preserved as research and delivery history.
  - Strict Full validation, diff checks, and Goldfish reconstruction pass.
- Verification evidence: Strict Full validation passed with zero errors and warnings; placeholder, language, stale-canonical-reference, and scoped-diff checks passed; git diff --check passed with line-ending notices only; a fresh-context Goldfish agent reconstructed the intent, protected decisions, current implementation drift, constraints, and single Next task with no implementation-blocking ambiguity. No executable build applied because TASK-000 changed documentation only.

Tasks:

- [x] TASK-000: Materialize, validate, and independently reconstruct the approved four-document product record.

### PHASE-001 — First end-to-end Context loop

- Status: done
- Outcome: One stored conversation can become a durable Conversation Brief and linked Context Items, appear in Context Home and Explorer, retain source evidence, and participate in an explicit Save and Use web-chat loop.
- Dependencies: PHASE-000.
- Entry criteria: PHASE-000 is done and current implementation has been re-observed against the accepted product contract.
  - The canonical documents pass strict Full validation.
  - Current archive, search, import, frontend, API, and packaging behavior has been re-observed.
  - TASK-001 is still the single documented Next task.
- Exit criteria: The first stored-conversation-to-web-chat Context loop passes automated, packaged, and manual verification.
  - A selected stored conversation creates a faithful brief and zero or more supported Context Items without ordinary manual classification.
  - Context Items persist with types, epistemic labels, scopes, links, compact evidence, versions, and timestamps.
  - Context Home and Explorer render the same underlying linked data.
  - ChatGPT and Claude extension prototypes support explicit whole-chat Save and user-requested Context use.
  - Unsaved-chat reminders are non-blocking and automatic analysis is durable across restart.
  - Required automated checks, manual flows, production frontend build, Windows executable build, and packaged-app smoke test pass.
- Verification evidence: In progress. TASK-001 is complete after its persistence, extraction,
  backend API, Context frontend, and source-evidence navigation slices passed 127 Python tests,
  23 frontend tests, Ruff, TypeScript, production frontend builds, fresh clean PyInstaller
  builds, isolated populated browser checks, and packaged startup/schema smokes. The latest
  browser checks covered live, deleted-source, and load-failure evidence paths at desktop and
  375 pixels; the packaged smoke confirmed healthy Context routes and the new frontend bundle.
  The first TASK-002 slice added and packaged the no-key local capture contract after 132 Python
  tests, 23 frontend tests, Ruff, a clean executable build, and ChatGPT/Claude created,
  unchanged-repeat, invalid-input, Library, and Search smoke paths passed. Phase exit evidence
  is not yet available. The second TASK-002 slice added the permission-minimal Manifest V3
  Chrome/Edge scaffold, authenticated Native Messaging availability boundary, separately
  packaged host, and registration tooling after 146 Python tests, 23 frontend tests, Ruff, a
  clean dual-executable build, unpacked Chrome and Edge checks, and packaged ready/unavailable
  scenarios passed. The third TASK-002 slice added action-gated ChatGPT whole-conversation Save,
  fail-closed DOM normalization, bounded native forwarding, stable capture identity, and
  actionable popup outcomes after 151 Python tests, 28 frontend tests, Ruff, JavaScript and
  TypeScript checks, a production frontend build, a clean dual-executable build, Chrome for
  Testing and installed Edge Save scenarios, and packaged created/unchanged/invalid evidence
  passed. The fourth TASK-002 slice added the same explicit whole-conversation Save path for
  Claude with provider-aware routing and fail-closed DOM normalization after 151 Python tests,
  34 frontend tests, Ruff, JavaScript and TypeScript checks, a production frontend build, a clean
  dual-executable build, Chrome for Testing and installed Edge created/unchanged/changed-DOM
  scenarios, and packaged invalid-capture atomicity passed. The fifth TASK-002 slice added the
  action-injected, page-lifetime ChatGPT and Claude unsaved reminder after 152 Python tests,
  45 frontend tests, Ruff, JavaScript and TypeScript checks, a production frontend build, a clean
  dual-executable build, structural no-text-read regressions, and packaged Chrome/Edge reminder,
  dismissal, re-Save, unavailable-app, navigation, and cleanup evidence passed.
  TASK-003 then completed authenticated provider-neutral Context assembly and explicit ChatGPT and
  Claude Use through the permission-minimal Native Messaging boundary. TASK-004 completed its
  durable capture-enqueued queue, automatic local scheduler, and optional-backfill onboarding
  slices. The final onboarding slice passed 177 Python tests, 57 frontend tests, Ruff, extension
  syntax, TypeScript, a production frontend build, desktop and 375-pixel first-run browser flows,
  a clean dual-executable build, and an isolated packaged no-key first run plus full restart with
  schema v5 and zero foreign-key violations. PHASE-001 exit evidence is complete.

Tasks:

- [x] TASK-001: Implement durable Conversation Brief and Context Item persistence, automatic extraction from one archived conversation, a minimal Context Home and Explorer view, and source-evidence navigation.
  - Completion: Durable Brief and Context Item persistence, source snapshots, scopes, versions,
    links, deletion survival, restart durability, and app-startup schema initialization are
    integrated. Source-grounded automatic extraction, versioned purpose prompts, conservative
    normalization, idempotent reuse, source-change reanalysis, and interrupted retry are
    integrated. Non-blocking analysis jobs and durable Brief and Item read APIs are integrated.
    The minimal Context Home and Explorer now render the same linked model with responsive,
    accessible loading, empty, scoped browsing, and item-detail states. Live evidence opens the
    exact supporting message, while removed sources and load failures retain compact evidence.
- [x] TASK-002: Implement the ChatGPT and Claude whole-conversation Save to Reweave extension flow with idempotent update and non-blocking save reminders.
  - First bounded slice complete: The provider-neutral local capture payload, persistence, and
    app endpoint accept complete ordered ChatGPT and Claude conversations with immediate no-key
    local persistence, stable provider/external identity, idempotent repeated saves, validation
    without partial writes, restart-readable source data, and packaged endpoint evidence.
  - Second bounded slice complete: The permission-minimal Manifest V3 scaffold uses browser
    Native Messaging, explicit extension-origin allowlisting, an ephemeral authenticated runtime
    descriptor, a separately packaged console host, and actionable ready/unavailable/incompatible
    popup states without provider page or localhost permissions. It loads unpacked in Chrome and
    Edge and passes packaged available/unavailable scenarios.
  - Third bounded slice complete: The production extension uses `activeTab` plus `scripting`
    without provider host permissions or persistent content scripts; only explicit popup or
    browser-action invocation reads the active ChatGPT conversation. The fail-closed adapter,
    bounded native forwarding, stable capture identity, and popup states cover created, updated,
    unchanged, unsupported, logged-out, changed-DOM, incomplete, unavailable, oversized, and
    invalid outcomes without partial persistence.
  - Fourth bounded slice complete: Provider-aware routing injects the Claude adapter only after
    the explicit Save action. The adapter validates supported Claude conversation UUIDs, current
    stable DOM markers, signed-in state, complete alternating turns, unique identities, and
    bounded normalized content, while the shared popup and native boundary preserve ChatGPT
    behavior and production permission minimization.
  - Fifth bounded slice complete: After an explicit successful Save, a page-lifetime controller
    detects one new complete assistant response from structural role and turn counts without
    reading message text, waits for 30 seconds of conversation inactivity, and presents a
    non-blocking prompt plus per-tab `SAVE` badge. Prompt auto-hide, dismissal and re-arming,
    explicit re-Save, unavailable-app retry, navigation and startup clearing, production
    permission minimization, Chrome/Edge packaged flows, and cleanup are verified.
- [x] TASK-003: Implement the user-requested Use Reweave flow using the current chat and drafted request, with explicit context insertion and on-request refresh.
  - First bounded slice complete: The authenticated provider-neutral Context assembly contract
    accepts one bounded ChatGPT or Claude current-chat payload and non-empty draft, applies
    destination-safe scope and sensitivity filtering before deterministic local ranking,
    deduplication, and context-budget assembly, and returns insertion-ready text with compact
    item provenance without persisting the chat or draft.
  - Second bounded slice complete: The permission-minimal Chrome and Edge extension connects to
    Context assembly through Native Messaging only after explicit Use. ChatGPT and Claude adapters
    normalize the complete current chat and non-empty draft, canonical signed-in conversation URLs
    select the private cross-space policy, and unsupported or uncertain destinations fail closed.
    One bounded identifiable block is inserted before the preserved draft, concurrent edits prevent
    overwrite, and a later explicit Use replaces the block without automatic refresh or Save. The
    existing page-lifetime reminder begins after successful Use.
- [x] TASK-004: Add durable automatic batching, retry, BYOK queue behavior, usage estimates, and onboarding that recommends but does not require export backfill.
  - First bounded slice complete: Schema-v4 local queue rows are created only after an explicit web
    capture is durably saved, remain profile-independent, reuse unchanged source-version work,
    supersede stale unfinished versions, survive restart, and expose durable reads plus explicit
    retry through the existing source-grounded extraction worker. Missing-key and provider failures
    remain safely retryable; current inline or saved-profile credentials are resolved only at retry
    time and are never stored in queue rows. Repository gates, a clean dual-executable build, and an
    isolated packaged capture, repeat, restart, queue-route, schema, and cleanup smoke passed.
  - Second bounded slice complete: A wake-driven local scheduler starts with the app and after
    capture or successful saved BYOK profile connection, resolves only the active connected saved
    profile, atomically claims at most three due jobs, and serializes them through the existing
    Context worker. Schema v5 stores capped retry times plus local-only character and conservative
    token estimates, while no-key and offline deferral consume no attempt, transient failures use
    60-second, five-minute, 15-minute, then one-hour capped backoff, and explicit retry remains.
    Repository gates, a clean dual-executable build, and isolated packaged capture, restart,
    schema-v5, foreign-key, and cleanup evidence passed.
  - Third bounded slice complete: First-run onboarding visibly recommends but does not require
    whole-export backfill, lets a no-key user continue to Context and current extension capture,
    explains automatic queued analysis after saved provider connection, preserves existing Import
    and Settings destinations, and accurately labels the current unpacked Chrome/Edge installation
    path. Durable completion, keyboard focus, 44-pixel actions, desktop and 375-pixel layouts,
    repository gates, a clean dual-executable build, and isolated packaged restart evidence passed.

### PHASE-002 — Personalization, trust, and retrieval hardening

- Status: active
- Outcome: Reweave can maintain a useful model of the user with little routine management while preventing scope leakage, confident mispersonalization, and retrieval blind spots.
- Dependencies: PHASE-001.
- Entry criteria: PHASE-001 implementation is available and current code is re-observed in an
  isolated environment. DEC-026 supersedes the real-archive implementation prerequisite.
  - Synthetic functional, UI, recovery, and safety verification may support implementation.
  - Actual usefulness and the real Save-to-Use round-trip remain mandatory in TASK-012.
- Exit criteria: Personalization, scope, retrieval, prompt, correction, Review, and backup contracts pass their regression and manual scenarios.
  - Core Self, Personal, Work, Projects, and Topics scopes support cross-links and automatic routing.
  - Values and tacit knowledge are inferred into a distinct visible area with evidence, confidence, and history.
  - Direct correction updates long-term context with the documented precedence rules and undo.
  - Private, Work, Client, Shared, unknown, cross-scope, and sensitive cases satisfy their documented policies.
  - Exact duplicate, expansion, contradiction, stale, and low-confidence paths behave without silent destructive overwrite.
  - Progressive global retrieval, graph expansion, and low-confidence fallback pass a versioned golden set.
  - Prompt versions pass extraction, grounding, useful-synthesis, prompt-injection, and scope-leakage regression tests.
  - Review contains exceptions only.
  - Encrypted local backup and complete restore pass.
- Verification evidence: Linked spaces, correction, trust, retrieval, complete-source analysis,
  semantic reconciliation, Review and encrypted restore now have synthetic regression evidence.
  Reading Room browser QA exercised real local HTTP and persisted corrections, links, source
  navigation, redaction and restore. Fresh dual-executable build and framed Native Host
  Save/analysis/restart/Use passed. Exact counts and artifact identities belong to the current
  Project Status and `docs/verification/2026-09-10/` records. Native Save File completion and
  actual model/usefulness acceptance remain in TASK-012; this phase is not yet marked done.

Tasks:

- [x] TASK-005: Implement linked spaces, Core Self, inferred values and tacit knowledge, automatic routing, and visible provenance.
  - Acceptance: A selected imported or captured source enters durable analysis; evidence-backed
    Briefs and zero or more items appear in Reading Room Home and Explore, with canonical linked
    spaces, distinct sourced inference, safe Core Self routing, editable space names and preserved
    corrections. Existing data survives migration. Sources and global search remain accessible.
  - Verification: Isolated synthetic capture/import-to-analysis-to-restart API scenarios, grounded
    routing and deduplication regressions, headless A layout/accessibility checks, frontend build,
    fresh dual-executable PyInstaller build, packaged headless smoke, and strict-full documents.
  - Enabling slices: credential-safe/headless runtime, import analysis access, shared Reading Room
    shell and source-first Home, then canonical routing/linking. Full subsequent tasks stay in scope.
- [x] TASK-006: Implement correction precedence, version history, stale confidence, contradiction handling, merge review, and undo.
- [x] TASK-007: Implement destination trust, scope isolation, sensitive-use confirmation, risky-export warning, and exception Review.
- [x] TASK-008: Implement progressive global retrieval, graph expansion, full-library fallback, and the prompt/retrieval golden evaluation set.
- [ ] TASK-009: Implement encrypted local backup, one-artifact restore, source removal without derived-context cascade, and separate Library deletion.
  - Implementation and synthetic/browser restore verification complete. Native Save File
    completion remains an owner-operated acceptance check in TASK-012; no data-loss defect is
    currently known from the recorded checks. This checkbox stays open until that check passes.

### PHASE-003 — Knowledge Graph and privacy-safe sharing

- Status: planned
- Outcome: Users can discover relationships across projects, concepts, values, and insights through a graph that shares the same model as Home and Explorer.
- Dependencies: PHASE-002.
- Entry criteria: PHASE-002 has trustworthy canonical links and passing sensitive-data controls.
  - Link quality is stable enough that graph edges explain real relationships rather than visual noise.
  - Scope and sensitive-data controls pass their acceptance scenarios.
- Exit criteria: Graph discovery and explicit redacted sharing pass their product and privacy scenarios.
  - Knowledge Graph renders the canonical links used by Home, Explorer, and retrieval.
  - Users can move from graph nodes to Context Items and source evidence.
  - The graph helps reveal at least one non-obvious relationship during dogfooding.
  - Sharing is local by default and exports only user-selected, redacted, previewed content.
  - Raw personal context and evidence cannot be shared by the default flow.
- Verification evidence: Canonical graph navigation, privacy filtering, exact-preview consent,
  responsive views and generated PNG bytes passed isolated API/browser checks. Actual native
  image saving and a useful non-obvious relationship during dogfooding remain unverified.

Tasks:

- [x] TASK-010: Implement the navigable Knowledge Graph on the canonical Context model.
- [ ] TASK-011: Implement explicit scoped redaction, preview, and image export for privacy-safe graph sharing.
  - Implemented and verified through actual redacted PNG generation/inspection. Native file
    saving remains part of TASK-012. A rendered graph does not establish useful discovery.

### PHASE-004 — Completeness dogfooding and public beta preparation

- Status: planned
- Outcome: The product owner can use the full agreed product naturally with real data and decide whether it is ready for a Windows and Chrome/Edge Public Beta.
- Dependencies: PHASE-003.
- Entry criteria: All accepted pre-public requirements implemented so far have executable evidence and no high-priority trust defect remains.
  - All accepted pre-public product requirements implemented so far have executable evidence.
  - No unresolved high-priority scope or sensitive-data defect remains.
- Exit criteria: Sustained dogfooding is satisfactory and the product owner has resolved the remaining public-release decisions.
  - The product owner judges Context Home useful as an evolving representation of their work and thinking.
  - Use Reweave improves ordinary web-chat work without manual Context Item selection.
  - Save, analysis, correction, retrieval, scope, backup, restore, Graph, and sharing flows remain stable under sustained real use.
  - The public v1 scope-freeze decision is resolved.
  - The pre-public encrypted-synchronization decision is resolved.
  - Windows installer, Chrome/Edge distribution assets, English documentation, GitHub Issues, and GitHub Discussions support boundaries are ready.
- Verification evidence: Not available until the phase is done.

Tasks:

- [ ] TASK-012: Run sustained product-owner dogfooding, record defects and protected decisions, and converge the full accepted flow.
  - Current concrete acceptance task under DEC-026, including the remaining TASK-009/TASK-011
    native file checks and PHASE-003 graph-value gate. Earlier phase checkboxes remain open until
    their required evidence exists; this does not silently bypass the phase dependencies.
  - Mandatory final gate (DEC-026): An explicitly selected real conversation must pass Save or
    Import, approved provider analysis, restart persistence, source inspection, and explicit Use
    in the next ChatGPT/Claude conversation. Record only privacy-safe outcomes, misses,
    corrections, latency and usage. The owner must assess reduced repeated explanation and real
    reuse; synthetic tests cannot complete this task. Request provider/model/data/call/cost/stop
    approval only after preparatory work is ready. No paid call is currently authorized.
- [ ] TASK-013: Resolve the public v1 scope freeze and encrypted-synchronization timing.
- [ ] TASK-014: Prepare and verify the Windows and Chrome/Edge Public Beta release surfaces.
  - Local per-user installer, unpacked extension and English privacy/support guides are prepared
    with isolated verification. Normal owner installation, real browser registration, signing or
    an explicitly accepted unsigned distribution route, and publication remain separate gates.
    GitHub Issues is enabled; Discussions was disabled in the 2026-09-10 read-only snapshot.

## Future candidates

These candidates do not belong to the active implementation sequence unless the product owner explicitly promotes them through a new decision:

- macOS desktop support;
- Gemini and additional web-chat providers;
- account-backed encrypted synchronization;
- managed Reweave LLM usage;
- external calendar and task-manager writes;
- mobile companion experiences;
- team or collaborative Context Libraries;
- automatic background capture;
- broader document, PDF, web, or note ingestion.

## Change policy

- Change phase order only after recording the reason and downstream effects.
- Mark work done only from current verification evidence.
- Keep future candidates here rather than adding multiple Next tasks to PROJECT_STATUS.md.
- The user owns product values, public-release judgment, v1 scope freeze, and synchronization timing.
- The agent owns data schema, algorithms, implementation sequencing inside an accepted task, UI microcopy, validation design, and low-level mechanics, subject to the Product Spec.
