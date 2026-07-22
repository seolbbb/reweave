# Reweave Decision Log

## Document control

- Last reviewed: 2026-07-22
- Working language: English
- Historical mapping: DEC-001 through DEC-010 preserve the former D-001 through D-010 records from PRODUCT_STRATEGY_AND_ROADMAP.md.

## Status vocabulary

- proposed: recorded but not yet accepted.
- accepted: currently governs product or architecture behavior.
- superseded: preserved history that has been replaced by another decision.

## Decisions

The first ten entries preserve the historical D-001 through D-010 decisions.

### DEC-001 — Position Reweave as a human-facing AI Memory Control Plane

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Generic archive, search, and portable-memory positions appeared crowded.
- User intent/value protected: Give Reweave a defensible purpose beyond conversation search.
- Intervention: The first strategy pass made memory accuracy, provenance, conflict, and controlled delivery the product wedge.
- Options considered: Generic archive/search, portable cross-AI memory, or human-facing memory governance.
- Decision: Build an AI Memory Control Plane centered on auditing, correction, scoping, and controlled delivery.
- Consequences: The historical roadmap led with Memory Audit validation and deferred everyday capture and delivery.
- Reconsider when: Direct user intent shows that preventing valuable conversational context from evaporating is the stronger primary problem.
- Supersedes: None
- Superseded by: DEC-011

### DEC-002 — Treat the conversation archive as immutable evidence

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Derived memory needed provenance that model output could not silently rewrite.
- User intent/value protected: Keep the user able to challenge a generated memory.
- Intervention: Separate the archive from the controlled derived memory layer.
- Options considered: Mutate source records, keep source immutable, or store only derived summaries.
- Decision: Treat original conversations as immutable evidence and a separate ledger as the controlled layer.
- Consequences: Provenance stayed strong, but the contract did not handle source removal for storage reasons.
- Reconsider when: Users need to remove full source data without losing useful derived context.
- Supersedes: None
- Superseded by: DEC-014

### DEC-003 — Require evidence and approval before memory becomes canonical

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Model extraction can create unsupported inference.
- User intent/value protected: User authority over durable personal memory.
- Intervention: Put every proposed memory through explicit review.
- Options considered: Automatic acceptance, confidence thresholds, or approval for every item.
- Decision: Require evidence and user approval before persistence as canonical memory.
- Consequences: The trust boundary was conservative but made the user the routine Context manager.
- Reconsider when: The user explicitly prioritizes effortless automatic personalization and rejects ordinary approval work.
- Supersedes: None
- Superseded by: DEC-013

### DEC-004 — Separate personal, work, client, and project profiles

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: One universal profile could overshare across contexts.
- User intent/value protected: Prevent personal information from entering work and client use.
- Intervention: Make profiles separate policy containers.
- Options considered: Universal profile, separate profiles, or manual packs.
- Decision: Keep personal, work, client, and project profiles separate.
- Consequences: Scope isolation improved, but strict containers made cross-project discovery and automatic personalization harder.
- Reconsider when: One linked library can preserve strict destination boundaries without making the user file information manually.
- Supersedes: None
- Superseded by: DEC-012

### DEC-005 — Defer automatic injection and broad browser capture

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Browser connectors and invisible delivery create privacy and maintenance risk.
- User intent/value protected: Avoid unreliable or hidden context flow.
- Intervention: Make audit and governance precede capture and delivery.
- Options considered: Early browser capture, provider integrations, or later controlled delivery.
- Decision: Defer browser capture and automatic injection until audit and governance were validated.
- Consequences: The roadmap postponed the lowest-friction everyday loop.
- Reconsider when: Explicit user actions can bound extension access while still making capture and reuse convenient.
- Supersedes: None
- Superseded by: DEC-015

### DEC-006 — Use Weekly Verified Memory Reuse as the north-star metric

- Status: superseded
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Stored-memory count would reward hoarding instead of value.
- User intent/value protected: Measure trustworthy reuse rather than database growth.
- Intervention: Tie success to evidence-backed memory reuse.
- Options considered: Total memories, total conversations, retention, or verified reuse.
- Decision: Use Weekly Verified Memory Reuse as the north-star metric.
- Consequences: The metric fit a governed-memory product but not the owner's chosen dogfooding release model.
- Reconsider when: The product owner rejects fixed quantitative release gates in favor of sustained personal use.
- Supersedes: None
- Superseded by: DEC-019

### DEC-007 — Use privacy-safe templates and interoperability for distribution

- Status: accepted
- Date: 2026-07-15
- Initiated by: Project strategy research
- Context: Raw personal memories are inappropriate viral content.
- User intent/value protected: Product distribution must not depend on exposing private context.
- Intervention: Separate reusable structures and redacted outputs from personal data.
- Options considered: Raw sharing, no sharing, or privacy-safe templates and receipts.
- Decision: Use privacy-safe structures and interoperability rather than raw memory sharing.
- Consequences: Knowledge Graph sharing must be scoped, redacted, previewed, and explicit.
- Reconsider when: A new sharing format can prove equivalent privacy guarantees.
- Supersedes: None
- Superseded by: None

### DEC-008 — Store Phase 0 audit sessions separately

- Status: superseded
- Date: 2026-07-15
- Initiated by: Phase 0 pilot implementation
- Context: Pilot records should not prematurely define the future canonical-memory schema.
- User intent/value protected: Keep validation experiments reversible and separate from the archive.
- Intervention: Create a separate local SQLite store for audit sessions.
- Options considered: Archive tables, future-ledger tables, or separate validation storage.
- Decision: Store Phase 0 audit sessions in a separate local database.
- Consequences: The implemented pilot remained isolated and safe, but its standalone product flow is no longer intended.
- Reconsider when: The pilot remains an active product surface.
- Supersedes: None
- Superseded by: DEC-021

### DEC-009 — Treat LLM audit output as suggestions and human review as findings

- Status: superseded
- Date: 2026-07-15
- Initiated by: Phase 0 pilot implementation
- Context: A research finding must not measure the model's own classification as user truth.
- User intent/value protected: Preserve human authority and valid Phase 0 research.
- Intervention: Require human review of statement kind, evidence verdict, issue tags, and severity.
- Options considered: Model-only audit, assisted human audit, or manual-only audit.
- Decision: Only human-confirmed decisions counted as Phase 0 findings.
- Consequences: This remains correct for the historical research protocol but is too burdensome as the everyday Context product.
- Reconsider when: High-confidence automation, visible provenance, correction learning, and exception-only Review can replace ordinary approval.
- Supersedes: None
- Superseded by: DEC-017

### DEC-010 — Run the first live pilot from a ChatGPT memory summary

- Status: superseded
- Date: 2026-07-15
- Initiated by: Phase 0 pilot planning
- Context: A ChatGPT memory summary was the available participant input.
- User intent/value protected: Start validation with real data without expanding scope.
- Intervention: Defer Claude comparison to a later pilot.
- Options considered: Synthetic data, ChatGPT summary, Claude summary, or cross-provider comparison.
- Decision: Start with one ChatGPT memory summary and later expand to 8–10 participants.
- Consequences: The pilot engineering path was completed, but the external cohort was not run.
- Reconsider when: The product owner changes validation from Memory Audit interviews to personal dogfooding.
- Supersedes: None
- Superseded by: DEC-022

The following entries record the current accepted product direction.

### DEC-011 — Make linked conversational context the product, not memory auditing

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: Heavy users create many valuable AI conversations but cannot absorb or reuse all the insights, decisions, learning, plans, and context they contain.
- User intent/value protected: Prevent useful AI-derived information from evaporating and let later AI work benefit from it without manual context preparation.
- Intervention: The user rejected discrepancy correction as the first product value and explained that a simple downloadable conversation search app was never the reason for Reweave.
- Options considered: Memory Audit control plane, searchable archive, Context Pack tool, or linked Context Library feeding existing web AI.
- Decision: Reweave turns user-selected conversations into a living linked Context Library and supplies relevant context to the web AI the user already uses.
- Consequences: Memory auditing becomes an internal trust function; standalone Reweave Q&A is removed; Context Home becomes the first visible value and web-chat personalization the second.
- Reconsider when: Dogfooding shows that conversational continuity is not naturally useful or a different primary job repeatedly dominates real use.
- Supersedes: DEC-001
- Superseded by: None

### DEC-012 — Use one linked library with progressive disclosure and multiple views

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: One flat context blob wastes tokens, while a strict tree can hide information that belongs in several places.
- User intent/value protected: Keep information in an understandable home with strong links, save tokens, and still find relevant material reliably.
- Intervention: The user proposed a Skills-like structure that reads summaries and follows links only when needed, but explicitly rejected a design that could miss information.
- Options considered: Flat library, strict folders, separate profile databases, or one linked graph with hierarchical views and global retrieval.
- Decision: Use one logical library with Core Self, Personal, Work, Projects, and Topics spaces; allow multi-space links; use progressive disclosure, global keyword and semantic retrieval, graph expansion, and low-confidence full-library fallback.
- Consequences: Context Home, Explorer, direct links, search, filters, and Knowledge Graph are views over the same model. Hierarchy may rank but never exclude globally relevant items.
- Reconsider when: Retrieval evaluation shows that the graph or progressive summaries reduce recall, or the shared model cannot support understandable navigation.
- Supersedes: DEC-004
- Superseded by: None

### DEC-013 — Automate ordinary Context management and learn from corrections

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: A product that repeatedly asks the user to classify, approve, file, and select Context Items will not be used.
- User intent/value protected: The result should feel naturally tailored to the user, as if the Context Home were a document of the user rather than a database they must maintain.
- Intervention: The user selected automatic high-confidence value and tacit-knowledge generation and emphasized that comfort is the product.
- Options considered: Approval for every item, confidence-based automatic use with exception Review, or unrestricted automatic rewriting.
- Decision: Automatically analyze, route, link, deduplicate, personalize, and use high-confidence non-sensitive context; distinguish observed, inferred, and suggested content; send only exceptions to Review; learn from direct correction with history and undo.
- Consequences: Direct correction, current project scope, recent direct statements, older direct statements, and inference form the precedence order. High-confidence inferred values may be used in private contexts without ordinary approval.
- Reconsider when: Confident errors remain frequent, exception detection fails, or users cannot understand and reverse automatic changes.
- Supersedes: DEC-003
- Superseded by: None

### DEC-014 — Preserve scope safety while allowing private cross-space relevance

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The user ranked cross-scope disclosure as the most damaging failure but also wanted highly relevant personal context to improve private AI work automatically.
- User intent/value protected: Get deeply personal results in private use without leaking personal context into work, client, shared, or unknown destinations.
- Intervention: The user chose automatic relevance in private use and strict trust zones for external or shared use.
- Options considered: Universal context, strict isolation everywhere, manual scope choice, or inferred trust zones with conservative shared behavior.
- Decision: Core Self applies safe general preferences broadly; private AI chats may use relevant cross-space context; Work, Client, Shared, and unknown environments use allowed scope only; sensitive inference requires confirmation before external use.
- Consequences: Scope is inferred and correction is remembered. Risky export warns only when needed. Removing a full source does not cascade to derived Context, which keeps compact evidence and is deleted separately.
- Implementation evidence: Explicit Use accepts the private cross-space policy only from canonical
  signed-in ChatGPT and Claude conversation URLs. The local assembler still excludes sensitive,
  inactive, and irrelevant items; non-private destinations still require concrete allowed scopes,
  and shared or unknown browser URLs fail before any page read or Context request.
- Reconsider when: Scope inference causes a disclosure, browser environments cannot be classified safely, or separate deletion creates unacceptable privacy confusion.
- Supersedes: DEC-002
- Superseded by: None

### DEC-015 — Put explicit Save and Use actions at the web boundary

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The user wants low-friction capture and reuse but does not want invisible browser collection or automatic injection.
- User intent/value protected: The user decides when Reweave participates; after that decision the system does the work.
- Intervention: The user chose explicit Save, user-requested Context refresh, and a non-blocking save reminder instead of passive or always-on behavior.
- Options considered: Passive capture, default automatic injection, one explicit boundary action, or manual export and copy.
- Decision: Save reads the current whole ChatGPT or Claude conversation only after a click. Use reads the current chat and drafted request only after a click. Context refresh occurs only on request. Unsaved chats receive a non-blocking reminder and extension badge.
- Consequences: Extension access remains legible; automatic analysis starts after capture; no standalone Ask Reweave is needed.
- Implementation evidence: The production extension reads a complete current chat and non-empty
  draft only after Use, inserts one bounded block without submission or Save, refuses to overwrite a
  concurrently changed draft, and refreshes only after another explicit Use action.
- Reconsider when: First-party provider integrations offer equal control with less friction or explicit actions prevent natural daily use.
- Supersedes: DEC-005
- Superseded by: None

### DEC-016 — Treat the system prompt and retrieval evaluation as product assets

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: Insight quality depends on prompt quality, but frequent full-library LLM calls would be expensive and can compound hallucination.
- User intent/value protected: Produce useful new insight rather than shallow summaries while keeping cost predictable and evidence inspectable.
- Intervention: The user selected automatic batching, local-first routing, purpose presets, evidence-backed synthesis, visible prompt versions, and regression tests.
- Options considered: One universal prompt, fully user-authored prompts, product prompts with additive personal instructions, immediate per-save calls, or scheduled/batched calls.
- Decision: Provide Auto plus Project, Learning, Research/Writing, and Context Handoff modes; label observed, inferred, and suggested output; run local parsing, search, routing, and duplicate detection first; batch remote synthesis; expose prompt versions; protect safety rules from user override.
- Consequences: Every selected conversation receives a brief, but item types are not filled artificially. Failures remain queued and retry. Prompt changes require a source, usefulness, hallucination, injection, and scope-leakage golden set.
- Implementation evidence: The schema-v5 local scheduler atomically claims at most three ready
  source versions, serializes them through one Context worker, computes aggregate input estimates
  from the exact prepared prompt before remote analysis, returns offline work to pending without
  consuming an attempt, and applies durable capped backoff only to transient provider failures.
- Reconsider when: Local preprocessing harms quality, one model call cannot produce reliable structure, or provider capabilities materially change the cost/quality boundary.
- Supersedes: None
- Superseded by: None

### DEC-017 — Retire standalone Memory Audit and Ask Archive experiences

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: Manual Memory Audit requires repeated review, and Ask Archive duplicates the web-chat assistants the user already prefers.
- User intent/value protected: Reweave should manage and supply context, not become another review workflow or general AI chat.
- Intervention: After inspecting the implemented pilot, the user chose to remove the standalone Memory Audit. The user then chose to remove Ask Archive entirely and move questions to web chat with Reweave context.
- Options considered: Keep both as primary features, keep them as advanced tools, reuse internal foundations only, or remove all related code.
- Decision: Remove the user-facing Memory Audit and Ask Archive workflows. Reuse evidence search, citation, untrusted-input, and classification foundations internally where they serve Context extraction, retrieval, and Review.
- Consequences: Search becomes Sources / Evidence Search; Insight Reports become Conversation Briefs and analysis history; the current code is documented as drift until migration is implemented.
- Reconsider when: Dogfooding reveals a frequent evidence question that cannot be served well by web-chat Context use and source navigation.
- Supersedes: DEC-009
- Superseded by: None

### DEC-018 — Keep the core local, BYOK, individual, and open source

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: A managed LLM and required account would improve onboarding but create server cost, billing, privacy, and operational complexity.
- User intent/value protected: Preserve provider choice, local ownership, a clear privacy boundary, and an MIT open-source core.
- Intervention: The user chose BYOK for cost, privacy, and provider freedom despite the additional one-time setup.
- Options considered: Managed LLM, BYOK only, local model only, required cloud account, or local library with optional future services.
- Decision: Ship Windows, Chrome, and Edge first; support ChatGPT and Claude first; keep the library local; use BYOK; keep the local app and extension MIT; require no account for the core product.
- Consequences: Onboarding must discover models, recommend defaults, test connection, and secure credentials. Optional paid encrypted synchronization may be considered later. English is the first UI language.
- Implementation evidence: Automatic queue work resolves only the active connected saved BYOK
  profile at claim time. Queue rows retain no profile ID, credential, or copied source content;
  no-key work remains local and pending until a successful saved-profile connection wakes the
  scheduler.
- Reconsider when: BYOK prevents ordinary use, provider policies block the workflow, or a managed service can preserve the same privacy and open-source contract sustainably.
- Supersedes: None
- Superseded by: None

### DEC-019 — Validate by product-owner dogfooding before Public Beta

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The product owner intends to use Reweave personally until it feels good enough to publish and does not want an external cohort or numerical release gate.
- User intent/value protected: Let real sustained use, not artificial study targets, determine product quality.
- Intervention: The user rejected the proposed 5–10 user validation cohort and fixed preference, relevance, and correction thresholds.
- Options considered: External Phase 0 cohort, fixed quantitative gate, public-first beta, or sustained product-owner dogfooding.
- Decision: Use real personal data and ordinary work for dogfooding, keep metrics local and diagnostic, and publish a Windows and Chrome/Edge Public Beta when the product owner judges the agreed product complete and useful.
- Consequences: The former 8–10 participant Memory Audit gate is retired. GitHub Issues and Discussions are the initial support channels. The v1 scope freeze and encrypted-sync timing remain deferred to public-release preparation.
- Reconsider when: External evidence is required for a commercial, safety, or distribution decision, or personal use cannot represent the intended target workflow.
- Supersedes: DEC-006
- Superseded by: None

### DEC-020 — Split the canonical product record into four documents

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The historical combined document mixes intended behavior, roadmap, observed status, research, and decision history, which makes drift difficult to see.
- User intent/value protected: Future work should reconstruct product intent and current reality without relying on chat history.
- Intervention: The user approved PRODUCT_SPEC.md, ROADMAP.md, PROJECT_STATUS.md, and DECISION_LOG.md as separate sources of truth and delegated low-level implementation decisions to the agent.
- Options considered: Keep one combined document, duplicate it alongside four documents, or migrate to distinct non-duplicating views.
- Decision: Use four canonical documents, preserve the combined document as a superseded historical strategy and source map, and route future agents through AGENTS.md.
- Consequences: Product contract, sequence, status, and rationale have explicit owners; every implementation task must converge affected documents and keep one Next task.
- Reconsider when: The four-document contract creates demonstrable duplication or maintenance failure that a simpler durable structure can solve.
- Supersedes: None
- Superseded by: None

### DEC-021 — Retire the separate Phase 0 audit store with the standalone pilot

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The separate audit database was deliberately safe for the Phase 0 experiment, but the standalone Memory Audit no longer belongs to the intended product.
- User intent/value protected: Preserve useful implementation knowledge without carrying an obsolete pilot store into the Context Library architecture.
- Intervention: The user chose to remove the independent Memory Audit experience after reviewing what it does.
- Options considered: Keep the pilot store as an advanced feature, migrate it into the Context Library, or retire it when the pilot UI is removed.
- Decision: Preserve the pilot and its evidence as repository history, but do not make its separate audit-session store part of the intended Context product.
- Consequences: Reusable evidence and untrusted-input patterns may move into the Context engine; the pilot database may be removed only in a scoped implementation task with migration and deletion safety.
- Reconsider when: Historical audit sessions become valuable user data that must be migrated rather than retired.
- Supersedes: DEC-008
- Superseded by: None

### DEC-022 — Replace the external Memory Audit cohort with product-owner dogfooding

- Status: accepted
- Date: 2026-07-21
- Initiated by: User
- Context: The planned first live ChatGPT memory-summary pilot and later 8–10 participant cohort validate the superseded Memory Audit wedge rather than the accepted Context product.
- User intent/value protected: Spend validation effort on whether the complete product is naturally useful in real daily work.
- Intervention: The user explicitly chose to use the product alone until it feels good enough to publish.
- Options considered: Complete the historical cohort, recruit a new Context cohort, use fixed quantitative gates, or dogfood privately until Public Beta judgment.
- Decision: Do not run the historical Memory Audit cohort as a product gate; validate through sustained product-owner dogfooding.
- Consequences: Historical pilot records remain valid evidence of completed work, but P0 participant counts and discrepancy targets no longer block the roadmap.
- Reconsider when: External validation becomes necessary for a safety, commercial, or distribution decision.
- Supersedes: DEC-010
- Superseded by: None

### DEC-023 — Use Native Messaging as the browser-to-local-app boundary

- Status: accepted
- Date: 2026-07-21
- Initiated by: Agent-owned architecture within accepted TASK-002
- Context: The desktop app binds an unpredictable loopback port, while the extension must discover
  the packaged app without granting ordinary web pages capture access or requesting localhost and
  provider permissions before an explicit user action.
- User intent/value protected: Keep browser access explicit, local, permission-minimal, and
  understandable while supporting both Chrome and Edge reliably.
- Intervention: None; the user delegated low-level implementation decisions, and this choice
  implements the accepted local-first and explicit-boundary contract.
- Options considered: A fixed loopback HTTP port with CORS and extension-origin checks, browser
  Native Messaging with an extension-origin allowlist, or a manual pairing and port workflow.
- Decision: Use Chrome and Edge Native Messaging as the extension boundary. Package a separate
  console host, allow only explicit extension origins in its host manifest, and let that host read
  an atomic short-lived runtime descriptor and authenticate to the app's random loopback port with
  an ephemeral token. Do not give the availability scaffold provider, localhost, or content-script
  access, and do not expose its token or port to the extension.
- Consequences: Browser and Windows registration are required; Chrome and Edge store IDs must both
  be allowlisted when they differ; installer work must own durable registration. Ordinary pages
  cannot invoke the native host, port conflicts remain avoided, stale descriptors fail closed, and
  later explicit Save and Use messages can reuse the same authenticated boundary.
- Reconsider when: Browser distribution or enterprise policy blocks native-host installation,
  installer friction prevents practical dogfooding, or a first-party provider integration offers
  an equally explicit and less privileged local boundary.
- Supersedes: None
- Superseded by: None

### DEC-024 — Grant provider-page access only for an explicit browser action

- Status: accepted
- Date: 2026-07-21
- Initiated by: Agent-owned architecture within accepted TASK-002
- Context: Explicit Save must read the complete active provider conversation after a user action,
  but persistent provider host permissions or always-loaded content scripts would widen the
  browser-access boundary beyond the accepted product contract.
- User intent/value protected: Keep browser collection legible, temporary, and initiated by the
  user while preserving one-click Save in Chrome and Edge.
- Intervention: None; the user delegated low-level implementation decisions, and this choice
  implements DEC-015 and DEC-018.
- Options considered: Persistent provider host permissions with content scripts, optional
  per-provider host permissions, or temporary `activeTab` access with programmatic injection.
- Decision: Use `activeTab` and `scripting` with no provider host permissions and no persistent
  content scripts. Query the active tab and inject the provider adapter only after the popup Save
  button or reserved browser action shortcut is invoked. Fail closed when the URL, sign-in state,
  turn sequence, identity, content, or payload bounds cannot prove a complete conversation.
- Consequences: Popup availability checks cannot inspect provider tabs; access ends with the
  temporary tab grant; provider DOM changes require fixture-backed adapter updates; ChatGPT and
  future Claude Save and Use paths share the same explicit boundary. Automated fixture harnesses
  may need temporary test-only host permission because programmatic button activation does not
  create a browser user gesture, but production permission tests must reject that permission.
- Reconsider when: Browser action semantics change, enterprise policy blocks temporary injection,
  or a first-party provider integration offers equally explicit access with fewer permissions.
- Supersedes: None
- Superseded by: None

### DEC-025 — Keep unsaved reminders inside the explicit tab lifetime

- Status: accepted
- Date: 2026-07-21
- Initiated by: Agent-owned architecture within accepted TASK-002
- Context: DEC-015 requires a non-blocking unsaved-conversation prompt and extension badge,
  while DEC-024 forbids provider host permissions, always-loaded content scripts, and page reads
  before the user explicitly invokes Reweave.
- User intent/value protected: Remind the user after Reweave is invited into a conversation
  without turning the extension into passive browsing or durable activity tracking.
- Intervention: None; the user delegated low-level implementation decisions and requested the
  next documented TASK-002 slice.
- Options considered: Persistent provider permissions with static content scripts, a timer-only
  badge that cannot detect meaningful new work, or an action-injected observer limited to the
  already authorized document.
- Decision: After a successful explicit Save, keep one isolated, page-lifetime reminder
  controller in that document. Observe only provider identity, stable role markers, complete
  message counts, and complete assistant-response counts; do not read or retain message text for
  reminder detection. One new complete assistant response followed by 30 seconds without DOM
  activity is meaningful new content. Show a non-modal prompt and per-tab `SAVE` badge, auto-hide
  the prompt while retaining the badge, and treat dismissal as the new assistant-count baseline.
  Read and validate the whole conversation again only when the user presses the reminder's Save
  button. Keep no reminder data in `chrome.storage` or the local app.
- Consequences: A conversation receives reminders only after its first explicit Reweave action;
  TASK-003 may start the same controller after Use Reweave. Same-tab conversation changes,
  navigation, changed DOM, browser restart, and tab closure clear or abandon reminder state.
  Streaming or incomplete output never triggers a reminder. The toolbar badge may outlive the
  short prompt, but both clear after Save or explicit dismissal.
- Implementation evidence: Deterministic ChatGPT and Claude tests verify structural snapshots
  without content cloning, timing, dismissal, re-arming, explicit re-Save, sender validation,
  streaming and DOM uncertainty, navigation, startup, and app-unavailable behavior. Packaged
  Chrome and Edge flows verified the prompt, badge, dismissal, successful re-Save, failed
  unavailable-app retry without persistence, and complete cleanup against isolated data.
- TASK-003 implementation evidence: Successful Use starts the same page-lifetime controller from
  the current provider identity and complete assistant-count baseline. Failed Context assembly or
  insertion does not start reminder state.
- Reconsider when: Browser action or injected-script lifetimes change, structural provider DOM
  signals become unreliable, or dogfooding shows that a 30-second quiet interval is too early or
  too late.
- Supersedes: None
- Superseded by: None
