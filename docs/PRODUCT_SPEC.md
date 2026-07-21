# Reweave Product Spec

## Document control

- Status: accepted
- Last reviewed: 2026-07-21
- Working language: English
- Product promise: Reweave turns the AI conversations you choose into a living, linked context library, then brings the right context back to the AI you already use.

## Product intent

- Why this exists: Heavy AI users create many valuable web-chat conversations, but the insights, decisions, lessons, open questions, and personal context produced in them are fragmented and gradually disappear from practical use.
- User intent to preserve: Reweave should make accumulated AI conversations feel like an evolving document of the user without requiring the user to become a librarian, prompt engineer, or context manager.
- Priority values: Prevent cross-scope disclosure first; avoid confident mispersonalization second; minimize management work third; preserve retrieval recall fourth; control API cost and latency fifth.
- Non-negotiable tradeoffs: The user explicitly decides when Reweave may read, save, or supply a web chat. After that boundary action, analysis, routing, linking, deduplication, personalization, and recovery should be automatic.
- Reconsider these choices when: Sustained dogfooding shows that the product is not naturally useful, explicit browser actions still create unacceptable friction, supported providers offer a safer first-party integration, or measured retrieval and personalization quality cannot meet the trust contract.

## Product definition

Reweave is a local-first context system for individual multi-AI power users. It converts user-selected ChatGPT and Claude conversations into source-linked Conversation Briefs and Context Items, connects them across personal, work, project, and topic spaces, and supplies relevant context back to the web AI the user already chose.

Reweave is not another general AI chat. It does not answer questions in its own standalone assistant surface. It prepares context, preserves provenance, and helps existing web-chat assistants produce results that better reflect the user's knowledge, values, projects, decisions, and preferred way of working.

The library is one logical system, not one flat document. Information belongs in named spaces and can link across multiple spaces. Hierarchy supports orientation and progressive disclosure; it must never be the only route by which information can be found.

## Users and problems

### Primary user

The initial user is an individual heavy multi-AI user who:

- uses at least two AI assistants and creates many web-chat conversations;
- relies on AI for learning, research, writing, project work, planning, and personal organization;
- wants prior insights and context to improve later work;
- values personalization but does not want to maintain another knowledge-management system;
- is willing to use BYOK for LLM analysis in exchange for provider choice, a clear privacy boundary, and no Reweave-operated inference service.

The initial target is intentionally broad across professions. Developers, founders, researchers, consultants, and other knowledge workers are examples, not separate product editions.

### Problems

- Valuable AI-derived knowledge disappears into a growing list of conversations.
- Users cannot comfortably reconstruct project decisions, lessons, unresolved questions, tasks, or research evidence across many chats.
- Manually preparing context for every new AI chat is repetitive and incomplete.
- A single undifferentiated profile can leak personal information into work, client, or shared outputs.
- Model-generated summaries can turn inference into apparent fact or silently overwrite how the user has changed.
- Folder-only or hierarchy-only organization can save tokens but miss relevant information.
- Export-only ingestion is useful for history but too cumbersome for everyday capture.

### Initial non-users

- teams seeking shared enterprise knowledge management;
- users seeking passive screen or activity recording;
- users primarily seeking a general notes, documents, or web knowledge base;
- users seeking a new general-purpose chat assistant inside Reweave;
- casual users with too little AI-chat history to benefit from continuity.

## Goals and success criteria

### Product goals

1. Make the first visible value an automatically organized Context Home containing meaningful insights, decisions, lessons, open questions, and actions from the user's conversations.
2. Make the second visible value a web-chat result that feels more personally relevant because the user requested Reweave context without manually selecting Context Items.
3. Let the user browse the same connected context through a readable home document, an explorer, direct links, global search, and eventually a Knowledge Graph.
4. Keep context current through automatic linking, versioning, contradiction handling, staleness, user corrections, and quiet background updates.
5. Preserve a strong scope boundary so personal context does not silently enter work, client, or shared results.

### Validation approach

The product owner will dogfood Reweave with real exports and ordinary daily AI work until it becomes naturally useful. External interviews and fixed quantitative release gates are not required before publication.

Local diagnostic measures may include:

- preference between a normal AI result and the same task with Reweave context;
- relevance of automatically retrieved Context Items;
- frequency of context corrections;
- retrieval misses;
- scope and sensitive-data violations;
- analysis latency and BYOK cost.

These measures diagnose problems; they do not replace the product owner's release judgment.

### Unacceptable outcomes

In descending order of harm:

1. Personal context is used in the wrong work, project, client, or shared scope.
2. Reweave confidently applies an incorrect value, preference, or fact.
3. The user must repeatedly classify, approve, file, or select ordinary context.
4. Saved information cannot be found when it is relevant.
5. LLM analysis becomes unexpectedly expensive or slow.

## Scope

### In scope

- Windows desktop application.
- Chrome and Edge extension support.
- ChatGPT and Claude web-chat support first.
- Optional ChatGPT and Claude export backfill.
- Explicit whole-conversation Save to Reweave from the current web chat.
- Non-blocking reminders for unsaved conversations.
- User-requested Use Reweave context insertion into a drafted web-chat request.
- Automatic batching, analysis, retry, classification, linking, and deduplication after capture.
- Conversation Briefs for every selected conversation.
- Zero or more source-linked Context Items per conversation.
- One linked Context Library with Core Self, Personal, Work, Projects, and Topics spaces.
- Context Home, Explorer, direct links, global search, filters, and Knowledge Graph views.
- Project decisions, lessons, open questions, actions, follow-up research, reusable concepts, insights, values, preferences, and inferred tacit knowledge.
- Auto, Project, Learning, Research/Writing, and Context Handoff analysis modes.
- Versioned and visible system prompts with additive personal instructions.
- Local encrypted backup and one-file restore.
- Local diagnostic metrics and user-controlled redacted export.
- Redacted, explicitly selected Knowledge Graph sharing.
- English user interface for the first public release.

### Out of scope

- A standalone Ask Reweave or Ask Archive user-facing chat experience.
- A standalone manual Memory Audit experience.
- Passive browser capture, background recording, or OS-wide screen capture.
- Automatic context injection without an explicit Use Reweave request.
- A managed Reweave LLM service or required Reweave account.
- Team workspaces, collaborative editing, or enterprise knowledge management.
- Automatic writes to calendars, task managers, or other external systems.
- A generic PDF, web, note, or document knowledge base.
- A graph-first product in which visual complexity replaces the primary reading and navigation experience.
- Raw context, conversation evidence, or personal graph sharing by default.
- macOS, Gemini, additional web-chat providers, and encrypted cloud synchronization in the initial implementation sequence.

The public v1 scope freeze and whether encrypted synchronization belongs before publication are deliberately deferred to the product owner at the public-release preparation stage.

## User experience

### Onboarding

1. Explain that Reweave stores its library locally and uses the user's chosen BYOK provider for analysis.
2. Offer a whole-export import as the recommended way to build useful historical context quickly.
3. Let the user skip import and begin with new extension-captured conversations.
4. Let the user capture, browse, and search without an API key.
5. Queue analysis until an API key is connected, then start pending work automatically.
6. Discover available provider models, recommend a default, verify the connection, and store the key in the operating-system credential store.
7. Offer installation of the Chrome or Edge extension for everyday Save and Use actions.

### Capture and analysis

- Save to Reweave reads the entire current conversation only after the user presses it.
- Saved conversation content is persisted locally immediately.
- A Conversation Brief is always created after successful analysis.
- Individual Context Items are created only when supported by the conversation; the absence of an atomic item never labels the conversation meaningless.
- The explicit save or selection action is the importance signal. The LLM must not score a selected conversation as unworthy.
- The system waits for an idle interval or useful batch size before remote analysis. Analyze now remains an optional accelerator, not a required step.
- Failed analysis stays in a durable local queue and retries without blocking access to the saved source.

### Initial-export selection

- Imported conversations remain searchable regardless of recommendation state.
- Users can search and filter by source, title, date, topic, and other available metadata.
- Local signals may recommend likely starting points, but recommendations must not hide, discard, or assign low value to other conversations.

### Context Home

Context Home is the primary reading surface. It presents:

- Core Self;
- active projects and topics;
- recent insights and lessons;
- decisions and their reasons;
- open questions and follow-up research;
- actions and commitments;
- a quiet summary of automatic changes with expansion and undo.

### Navigation

- A readable document links to spaces, projects, Context Items, and source evidence.
- Explorer provides folder-like orientation even though an item may link to multiple spaces.
- Global keyword and semantic search remains available from every level.
- Knowledge Graph visualizes relationships after link quality is trustworthy.
- The graph's primary purpose is discovery; viral sharing is secondary and always redacted and explicit.

### Use in web chat

1. The user writes a normal request in ChatGPT or Claude.
2. The user presses Use Reweave.
3. Reweave evaluates the chat so far and the drafted request.
4. Relevant allowed Context Items are retrieved and assembled within a context budget.
5. The extension adds the context to the web-chat input.
6. Reweave does not refresh context again unless the user requests it.
7. A later request uses the full current chat plus the new draft and replaces or extends the supplied context without duplicating prior material.

Reweave does not automatically save that web chat. After meaningful new content or inactivity, a small non-blocking Save to Reweave prompt appears. If missed, the extension badge records the reminder. Dismissing the prompt suppresses it until substantial new content exists.

### Corrections

- A direct user correction updates the current result and the related long-term Context Item.
- The update is versioned and offers a quiet undo.
- Conflict precedence is: explicit user correction, current project scope, recent direct statement, older direct statement, then LLM inference.
- Historical versions and their sources remain inspectable.

## Functional requirements

### Conversation Brief

Every analyzed selected conversation produces a faithful brief covering:

- main subject and user goal;
- important outcomes;
- decisions and reasons;
- useful lessons or insights;
- unresolved questions;
- actions and follow-up research;
- source identity and analysis version.

### Context Item

Each item must support:

- stable ID and canonical text;
- type: insight, concept, value, preference, decision, lesson, project fact, open question, action, or follow-up;
- epistemic kind: observed, inferred, or suggested;
- source conversation and compact evidence references;
- confidence, sensitivity, and current status;
- Core Self, Personal, Work, Project, Topic, and destination scopes;
- links to related items and spaces;
- created, last confirmed, updated, and optional stale timestamps;
- version and change history.

### Analysis contract

- Auto mode looks for all supported item types but never fills a category merely to satisfy a schema.
- Purpose presets change emphasis without weakening source, scope, or safety rules.
- The model may produce new source-grounded connections and interpretations only when it labels observed facts, inferences, and suggestions distinctly.
- Archived conversation content is untrusted data, never system instruction.
- The prompt is versioned and visible.
- Advanced users may add personal analysis instructions, but cannot override evidence, prompt-injection, sensitivity, or scope rules.

### Linking and deduplication

- Exact semantic duplicates attach new evidence to the existing item.
- Meaningful expansion, changed decisions, and contradictions create reviewable version or merge events instead of silently rewriting history.
- The system proposes spaces and links automatically.
- Users may rename, merge, or correct a space without having to organize ordinary captures.

### Progressive retrieval

Retrieval follows progressive disclosure:

1. read compact space and route summaries;
2. inspect candidate item summaries;
3. load full top-ranked items;
4. load source evidence only when needed.

The hierarchy is a ranking signal, not a search boundary. Every item remains in a global keyword and semantic index. Candidate results expand through graph links. Low-confidence retrieval broadens to the full allowed library. The product exposes why an item was used and supports a Search all fallback.

### Personalization

- Core Self may contain generally applicable values, reasoning preferences, writing style, preferred structure, and explanation depth.
- Personal details such as health, relationships, family, finances, and schedules stay in Personal rather than Core Self.
- Values and tacit knowledge may be inferred and stored automatically in a dedicated visible area with sources, rationale, confidence, timestamps, and contradictions.
- High-confidence, non-sensitive inferred context may be used automatically in private environments.
- Repeated edits and direct corrections may update presentation preferences automatically with history and undo.

### Scope and destination trust

- Reweave infers Personal, Work, Project, Client, and Shared scope from the current conversation and known links.
- A user correction to an inferred scope is remembered.
- Private AI chats may automatically use highly relevant cross-space context, subject to sensitivity rules.
- Work, client, and shared environments use only explicitly allowed scope.
- Unknown environments are treated as Work or Shared.
- Sensitive inferred content may be stored locally but requires separate confirmation before external AI use.
- External export shows a warning only when sensitive or cross-scope material is present.

### Review

Review is an exception surface, not a daily approval inbox. It contains:

- sensitive inferred content;
- cross-scope risk;
- low-confidence personalization;
- contradictions that cannot be safely versioned;
- materially changed decisions;
- failed or ambiguous evidence links.

Standalone Memory Audit sessions are not part of the intended user experience. Useful evidence and classification foundations may be reused internally.

### Source and evidence search

Sources / Evidence Search supports:

- global keyword and semantic search;
- source, date, title, project, topic, and type filters;
- conversation and message inspection;
- Context-to-source and source-to-Context navigation.

The user-facing Ask Archive question feature is removed. Retrieval and citation components may be reused internally for Context selection and provenance.

### Data lifecycle

- Removing an original conversation does not automatically delete derived Context Items.
- Context Items retain compact evidence excerpts and source metadata sufficient to explain their origin after the full source is removed.
- Derived Context is deleted separately from Library management.
- Stale context is not automatically deleted. Confidence decays and newer direct evidence or correction can supersede it.
- Encrypted versioned backups are written to a user-selected folder.
- The complete local library can be restored or moved from one backup artifact.

## Safety, privacy, and data

- The conversation archive, Context Library, links, activity state, and backups are local by default.
- Reweave does not operate a cloud inference service.
- BYOK requests go directly to the provider selected by the user.
- Only content required for the current batch or analysis is sent.
- API keys are stored in the operating-system credential store and never in normal application data or exported diagnostics.
- Extension access is explicit: Save reads the current conversation; Use reads the current chat and drafted request.
- No passive browsing, background screen capture, or invisible context injection is permitted.
- Conversation content and imported prompts are always untrusted data.
- Sensitive inference is stored separately and cannot leave the device without an explicit confirmation.
- Shared graph exports are generated from user-selected scope, remove personal content by default, and require preview and confirmation.
- Local diagnostics exclude raw conversation and Context content. Any redacted diagnostic export is user initiated.

## Non-functional requirements

- Platform: Windows desktop, Chrome, and Edge first.
- Provider sites: ChatGPT and Claude first.
- Interface language: English first.
- Offline behavior: capture, browsing, search, and queued work remain available without an LLM connection; remote analysis waits safely.
- Cost behavior: prefer local parsing, search, routing, and duplicate detection; use strong remote models for synthesis; show estimated use and enforce a user-visible safe limit.
- Durability: capture completes before analysis; queued work survives restart; repeat import and save are idempotent.
- Retrieval quality: hierarchy cannot exclude globally relevant items; retrieval evaluation must include cross-space cases and hard exact-identifier queries.
- Prompt quality: prompt revisions require a versioned golden set covering extraction correctness, source grounding, useful synthesis, hallucination, prompt injection, and scope leakage.
- Explainability: used context, excluded sensitive context, source evidence, automatic changes, and undo history remain inspectable without interrupting normal work.
- Accessibility: all core Save, Use, search, navigation, review, backup, restore, and correction flows must be keyboard accessible and meet the repository's chosen accessibility gate.
- Packaging: every implementation task must produce and smoke-test the required Windows executable before completion.

## Acceptance criteria

The intended product is acceptable only when all applicable scenarios pass:

1. A user may skip whole-export import and begin with a newly saved web chat.
2. The onboarding path recommends whole-export backfill without making it mandatory.
3. A user without an API key can capture, browse, and search; queued analysis starts after connection.
4. Save to Reweave persists a whole current ChatGPT or Claude conversation locally before analysis.
5. Automatic batching creates a Conversation Brief and source-linked Context Items without ordinary manual classification.
6. Context Home and Explorer present the same linked data and allow navigation to compact evidence.
7. Global search finds relevant content even when it lives outside the initially predicted hierarchy.
8. Exact duplicates gain evidence without creating noise; contradictions and material changes remain versioned.
9. A correction updates long-term context, preserves history, and can be undone.
10. Use Reweave supplies relevant allowed context only after the user requests it.
11. A private request may use relevant cross-space context, while Work, Client, Shared, unknown, and sensitive cases obey their stricter boundaries.
12. Failed LLM analysis survives restart and retries without losing the captured source.
13. Removing a full source leaves derived context intact; deleting derived context remains a separate explicit action.
14. Encrypted backup and restore preserve sources, Context Items, links, versions, scopes, and settings except protected API-key material.
15. Knowledge Graph uses the same underlying links as Home and Explorer, and shared output is redacted, scoped, previewed, and explicit.
16. No standalone Ask Reweave, Ask Archive, or Memory Audit workflow remains in the intended primary product.
17. The product owner can dogfood the completed flow without needing an external validation cohort or fixed quantitative release gate.

## Open questions

### Deferred: public v1 scope freeze

- State: deferred
- Owner: Product owner
- Reopen when: Preparing the public beta.
- Decision needed: Freeze the agreed pre-public feature set or allow additional dogfood discoveries into v1.

### Deferred: encrypted synchronization timing

- State: deferred
- Owner: Product owner
- Reopen when: Preparing the public beta after local dogfooding has established core usefulness.
- Decision needed: Keep synchronization post-release, include an account-backed encrypted service before release, or rely on encrypted backups in a user-controlled sync folder.
