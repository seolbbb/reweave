# Reweave Product Strategy, Competitive Rationale, and Delivery Tracker

> Canonical product document. Read and update this file for every repository
> task, as required by `AGENTS.md`.

| Field | Value |
|---|---|
| Strategy version | 1.0 |
| Strategy date | 2026-07-15 |
| Last progress update | 2026-07-15 |
| Product stage | Existing archive/search foundation; memory audit validation next |
| Primary decision | Build a human-facing AI memory governance product, not another conversation search or generic cross-AI memory tool |

## 1. Executive Decision

Reweave should not compete as a generic conversation archive, second brain,
cross-AI search extension, or universal memory synchronization layer. Pieces,
Recall, LLMnesia, OpenMemory, and Supermemory already cover substantial parts
of those categories.

Reweave will instead become a personal **AI Memory Control Plane**:

> See what every AI remembers about you, verify where it came from, decide
> whether it is still true, and control where it is allowed to go.

The strategic shift is from **capturing more memory** to **auditing, correcting,
scoping, and safely delivering memory**.

## 2. Why This Direction Was Selected

### 2.1 Observed market facts

The following are observations from official product pages, documentation,
privacy policies, changelogs, and public issue trackers as of 2026-07-15.

- Pieces positions itself as an on-device long-term memory layer that captures
  workflow context, provides a chronological timeline and time-based retrieval,
  and exposes memory through MCP. It also emphasizes pause, source, and deletion
  controls.
- Recall turns articles, videos, podcasts, PDFs, and notes into summarized cards,
  automatically organizes them, connects related knowledge, resurfaces material,
  and supports quizzes and spaced repetition.
- LLMnesia already supports local cross-platform conversation indexing,
  historical backfill, semantic search, exact-message navigation, portable
  memory, and continuing a conversation in another AI service.
- OpenMemory already offers memory types, project scoping, versioning,
  visibility rules, access logs, MCP delivery, and a browser extension.
- Supermemory describes a shared memory layer that can update, merge,
  contradict, infer, and forget memories.
- Public research on 2,050 ChatGPT memories found meaningful user-agency and
  privacy concerns, including system-created memories, personal data, and
  psychological inference.

### 2.2 Product inference

The market observations imply that these positions are not defensible enough:

- "Search all your AI chats."
- "Move your memory between AI assistants."
- "One memory for every AI."
- "A private second brain for your conversations."
- "Automatic long-term memory."

The remaining high-value gap is human-facing governance:

- There is no obvious user-owned canonical truth when assistants remember
  different versions of the same person or project.
- Users need to distinguish direct statements from AI-generated inferences.
- Memory can become stale, contradictory, overly broad, or sensitive.
- A universal profile can leak personal context into work, client, or project
  conversations.
- Users need provenance, approval, expiry, scope, and an audit trail before
  memory is delivered to another system.

This is a better fit for Reweave because the product already owns the original
conversation evidence, verified source citations, local search, report
generation, archive backup, and local-first trust model.

## 3. Target User and Job to Be Done

### 3.1 Primary target

Heavy multi-AI knowledge workers who:

- use at least two assistants such as ChatGPT, Claude, Gemini, or Cursor;
- have accumulated at least 100 conversations;
- work on long-running projects where decisions and preferences change;
- need continuity but care about privacy, accuracy, and context boundaries;
- include developers, founders, researchers, consultants, and independent
  knowledge workers.

### 3.2 Core job

> When several AI assistants have learned different things about me and my
> projects, help me identify what they think they know, verify it against the
> original conversation, keep only the current truth, and safely reuse the
> right subset in the next interaction.

### 3.3 Not the initial target

- Casual users with very few AI conversations.
- General note-taking and document-authoring users.
- Students primarily seeking flashcards or spaced repetition.
- Teams seeking enterprise knowledge management.
- Users seeking continuous screen recording or employee monitoring.

## 4. Competitive Research and Benchmark Decisions

### 4.1 Pieces

**Observed product loop**

1. Install PiecesOS and enable long-term memory.
2. Passively capture workflow context from approved sources.
3. Browse a chronological workstream or ask time-based questions.
4. Reuse the retrieved context through integrations and MCP.

**Benchmark**

- Low-effort capture and retrieval.
- Visible pause and source controls.
- Deletion by time, source, and data type.
- Time-based questions and timeline navigation.
- Memory available inside the user's current work tool.
- Clear local-first privacy communication.

**Do not copy**

- OS-wide screen and activity capture.
- The broad promise to remember everything.
- A multi-component dependency chain before the core value is proven.

**Reason**

Continuous capture expands privacy risk, platform complexity, and connector
maintenance before Reweave has validated its unique value.

### 4.2 Recall

**Observed product loop**

1. Save an article, video, PDF, podcast, or note.
2. Receive an immediate summary card.
3. Let automatic tags and connections organize it.
4. Retrieve, chat with, resurface, quiz, and review it later.

**Benchmark**

- Immediate value after a single capture action.
- One canonical card per saved source.
- Automatic organization that does not require manual filing.
- A closed loop from capture to retrieval and repeated use.
- Clear feature packaging and use-case language.
- API and MCP as distribution surfaces.

**Do not copy**

- A broad personal knowledge management product.
- A graph-first interface.
- Generic web and PDF ingestion as the main wedge.
- Learning quizzes before a learning audience is validated.

**Reason**

Recall already has a mature content-to-knowledge loop. Reweave should use the
same activation quality for conversation-derived memories without becoming a
general content library.

### 4.3 LLMnesia

**Observed product loop**

1. Install the extension.
2. Import and backfill existing conversations.
3. Index new conversations locally while the user browses.
4. Search with a keyboard shortcut and jump to the exact message.
5. Continue a summarized conversation in another AI service.
6. Save or transfer portable memory.

**Benchmark**

- Fast activation with a setup checklist.
- Automatic backfill, deduplication, and original-date preservation.
- Progress, pause, cancel, and resume for long imports.
- Search embedded in the current workflow.
- Simple Off, On, and Auto controls.
- A low-friction cross-AI handoff.

**Do not copy**

- Competing on the number of supported AI platforms.
- Competing primarily on search speed.
- Treating portable memory alone as the product distinction.
- Depending on fragile page structures before governance is validated.

**Reason**

LLMnesia already offers portable cross-AI memory and local semantic search.
Reweave must solve the trust and control problem that comes before delivery.

### 4.4 OpenMemory and Supermemory

**Benchmark**

- Typed memories.
- Project scope and visibility rules.
- Version history and access logs.
- Merge, update, contradiction, and forgetting semantics.
- MCP as a controlled delivery channel.

**Reweave distinction**

- Designed for end users rather than developer infrastructure.
- Every approved memory is anchored to original message evidence.
- Direct statements and AI inferences are visibly different.
- Sensitive inference and oversharing are first-class review cases.
- Users compare what different assistants remember side by side.
- Users preview exactly what will be sent before it is sent.
- Work, personal, client, and project identities remain separate.

## 5. Ranked User Problems

| Rank | Problem | Severity | Frequency | Confidence | Product leverage |
|---:|---|---|---|---|---|
| 1 | No user-owned canonical memory exists across assistants | High | High | High | Very high |
| 2 | Stale, wrong, sensitive, or inferred memories are difficult to detect | High | Medium | Medium-high | Very high |
| 3 | Work, personal, client, and project contexts can be mixed | High | Medium | Medium | High |
| 4 | Users cannot reliably see why a memory exists | High | Medium | High | Very high |
| 5 | Historical conversation retrieval is inconvenient | Medium | High | High | Low because the category is crowded |
| 6 | Capture and MCP connectors can become unreliable | Medium | Medium | Medium | Medium |

## 6. Product Principles

1. **Evidence before memory.** Every approved memory must point to one or more
   original messages.
2. **Proposal before persistence.** AI-generated memories enter an inbox and do
   not become canonical without approval.
3. **Direct statement is not inference.** The interface must distinguish what
   the user said from what a model inferred.
4. **Scope before sharing.** A memory must have an allowed profile, project, or
   destination before delivery.
5. **Preview before injection.** Users see the exact context package before an
   assistant or MCP client receives it.
6. **One person can have many contexts.** Work, personal, client, and project
   profiles remain separate.
7. **Forgetting is a feature.** Expiry, supersession, deletion, and denial are
   first-class actions.
8. **Local evidence is the source of truth.** The archive remains locally owned,
   searchable, backupable, and exportable.
9. **Automation handles organization; people retain authority.** Users should
   review decisions, not manually maintain another PKM hierarchy.
10. **No metric should reward hoarding.** The number of stored memories is not a
    success metric.

## 7. Core Product Model

### 7.1 Canonical Memory Ledger

The ledger is the user-owned source of truth derived from the immutable
conversation evidence layer.

Each memory record should include at least:

- stable memory ID;
- canonical text;
- type: identity, preference, project fact, decision, constraint, reusable
  asset, or open loop;
- origin: direct statement or model inference;
- one or more conversation and message references;
- status: proposed, approved, current, superseded, contradicted, blocked, or
  expired;
- confidence and sensitivity;
- allowed profile, project, and destination scopes;
- created, last confirmed, and optional expiry timestamps;
- version and change history.

An approved memory without evidence is invalid.

### 7.2 Memory Inbox

Proposed memories are grouped into actionable review queues:

- **New**: no matching canonical memory exists.
- **Changed**: evidence suggests an approved memory should be updated.
- **Contradicted**: two pieces of evidence disagree.
- **Sensitive**: the content or inference may be private or risky.
- **Stale**: the memory has not been reconfirmed within its policy window.

The primary actions are approve, edit, reject, supersede, expire, and block.

### 7.3 Assistant Comparison

Compare imported ChatGPT, Claude, Gemini, LLMnesia, or other assistant memory
summaries against the canonical ledger. Show missing, divergent, stale,
unsupported, and overshared items.

The initial implementation should support pasted or exported memory summaries.
Direct provider writes are not required for the MVP.

### 7.4 Context Profiles and Policies

Users create separate profiles such as:

- Personal;
- Work;
- Client A;
- Reweave;
- Job Search;
- another specific project.

Each profile defines allowed memory types, explicit memories, denied sensitive
categories, destination assistants, expiry policy, and context budget.

### 7.5 Evidence-backed Memory Pack

Export an approved, scoped snapshot in Markdown and JSON containing:

- selected memory content;
- profile and destination;
- evidence references;
- last confirmation date;
- version and snapshot identifier;
- excluded categories and policy metadata.

Open Memory Protocol compatibility can be added after the internal model is
stable.

### 7.6 Delivery Preview and Audit Log

Before sending a context pack, show exactly what the destination will receive.
After delivery, record the snapshot, destination, time, access method, and
result. MCP must read approved and scoped memory only.

## 8. Intended Product Flow

```text
Import AI conversations or memory summaries
    -> extract memory proposals
    -> classify New / Changed / Contradicted / Sensitive / Stale
    -> open original message evidence
    -> approve, edit, reject, supersede, or expire
    -> assign a personal, work, client, or project scope
    -> preview the destination context pack
    -> export or deliver through controlled MCP
    -> retain an access and change record
```

## 9. Information Architecture

| Area | Purpose | Existing Reweave foundation |
|---|---|---|
| Home / Memory Health | Show stale, contradicted, sensitive, unsupported, and overshared memory | Archive and insight summaries |
| Inbox | Review proposed and changed memories | Selected-conversation insight generation |
| Ledger | Manage canonical approved memories | SQLite archive and report persistence |
| Compare | Compare assistant memories with the ledger | Multi-source import and search |
| Profiles | Control work, personal, client, project, and destination scope | New capability |
| Evidence | Search and inspect original conversations | FTS5, hybrid search, and source drawer |
| Activity | Review memory changes, exports, and MCP access | New capability |
| Sources | Import, backup, restore, and delete archives | Existing import and archive management |

Search becomes **Evidence Search**, not the primary product promise. Reports
become **Memory Audits**. The existing source drawer becomes an evidence drawer.

## 10. Value, Convenience, and Distribution

### 10.1 User value

The product answers:

> What does each AI think it knows about me, why does it believe that, is it
> still true, and is it safe to use here?

This is more defensible than conversation retrieval because it combines trust,
accuracy, context safety, and user control.

### 10.2 Convenience

- Detect likely memory problems immediately after import.
- Open the exact supporting message without a separate search.
- Reduce review to approve, edit, reject, supersede, expire, or block.
- Reuse project profiles instead of rewriting context for every chat.
- Preview the exact payload instead of trusting invisible auto-injection.
- Keep extraction local by default, with explicit BYOK scope when a remote model
  is selected.

### 10.3 Privacy-safe distribution and viral loops

Personal memories should not become social content. Distribution should come
from reusable structures and interoperability:

- redacted AI Memory Health result cards;
- memory-profile templates for developers, founders, researchers, and
  consultants;
- project handoff Context Packs;
- verification receipts showing that an answer used approved memory;
- MCP and Open Memory Protocol interoperability;
- shareable policy templates without the user's personal values.

Raw memory, evidence, and sensitive findings must never be shared by default.

## 11. Roadmap

### Phase 0: Problem Validation and Taxonomy

**Target duration:** 2 weeks

**Goal:** Prove that memory accuracy, provenance, conflict, and oversharing are
important enough to support a dedicated product.

**Deliverables**

- Interview 8-10 target users who use at least two AI assistants.
- Ask participants to inspect or export what ChatGPT and Claude remember.
- Collect at least 50 real examples of stale, wrong, conflicting, unsupported,
  sensitive, or overshared memory.
- Define the memory taxonomy, sensitivity taxonomy, and privacy threat model.
- Test whether users understand direct statement versus model inference.
- Prototype a read-only audit using the existing archive before adding delivery.

**Gate**

- At least 60% of participants find one meaningful discrepancy or unsafe memory.
- Participants can answer "what does each AI know and why?" using the prototype.
- The team identifies a repeatable problem beyond isolated edge cases.

### Phase 1: Memory Audit MVP

**Target duration:** 4-6 weeks after Phase 0 passes

**Goal:** Deliver the first unique value without automatic memory injection.

**Deliverables**

- Import ChatGPT and Claude archives plus pasted or exported memory summaries.
- Add the Canonical Memory Ledger schema.
- Extract memory proposals from user-selected conversations.
- Add New, Changed, Contradicted, Sensitive, and Stale queues.
- Label direct statements and model inferences.
- Show exact source-message citations.
- Support approve, edit, reject, and expire.
- Add ChatGPT versus Claude versus Reweave comparison.

**Gate**

- Median time to first corrected discrepancy is under 10 minutes.
- Every approved memory has valid evidence.
- At least 60% of useful proposals are approved or corrected rather than simply
  discarded.
- Users return to resolve a second audit batch.

### Phase 2: Memory Governance

**Target duration:** 4-6 weeks after Phase 1 passes

**Goal:** Make memory safe and maintainable over time.

**Deliverables**

- Add version history, supersession, contradiction, expiry, and blocking.
- Add sensitivity review and unsupported-inference warnings.
- Add work, personal, client, and project profiles.
- Add destination allow and deny rules.
- Add Memory Health for stale, contradicted, unsupported, and overshared items.
- Export evidence-backed Memory Packs in Markdown and JSON.
- Add backup and restore coverage for ledger and policy data.

**Gate**

- More than 50% of active testers create at least two profiles.
- More than 70% of detected contradictions reach an explicit resolution.
- No approved memory lacks evidence.
- Users can safely create a work pack without personal memory leakage.

### Phase 3: Controlled Delivery

**Target duration:** 4-6 weeks after Phase 2 passes

**Goal:** Reuse approved memory without surrendering control.

**Deliverables**

- Add a Context Pack builder and token or character budget.
- Preview exactly what an assistant will receive.
- Add read-only local MCP access to approved, scoped memory.
- Add access logs and delivery receipts.
- Add an audited "Continue in another AI" handoff.
- Allow immediate revocation of a profile or destination.

**Gate**

- Weekly use of approved memory packs or MCP context is measurable.
- No destination receives memory outside its allowed scope in testing.
- Users understand and trust the preview and receipt.
- Reuse saves meaningful setup time without increasing corrections.

### Phase 4: Capture, Interoperability, and Distribution

**Start only after controlled delivery demonstrates retention.**

**Potential deliverables**

- Explicit Save to Reweave browser extension; no passive screen capture.
- Gemini, Perplexity, and other memory-summary imports.
- Open Memory Protocol import and export.
- Optional local extraction model.
- Profile and policy template gallery.
- Redacted Memory Health sharing.
- Scheduled memory audits.

## 12. Explicit Non-goals

Do not build these before the relevant strategy decision is deliberately
superseded:

- OS-wide screen capture.
- A generic web, PDF, and note knowledge base.
- A graph-first personal knowledge management interface.
- Spaced repetition and quizzes.
- A race to support the largest number of AI platforms.
- Invisible automatic injection without preview and logging.
- One universal identity profile that mixes work and personal context.
- Social sharing of raw memory or conversation evidence.
- Direct writes into every provider before the audit and governance loop is
  validated.

## 13. Metrics

### North-star metric

**Weekly Verified Memory Reuse**: the number of approved memories reused through
a profile, context pack, or controlled integration while retaining valid source
evidence.

### Activation

- The user identifies and resolves at least one real discrepancy within 10
  minutes of completing an import.

### Quality and trust guardrails

- Approved memories with valid evidence: 100%.
- Destination deliveries outside allowed scope: 0.
- User correction rate for extracted memories.
- Contradiction resolution rate.
- Sensitive inferences caught before approval.
- Stale memories reviewed or expired.
- Preview-to-delivery conversion.
- Four-week retention among activated users.

### Metrics not to optimize

- Total memories stored.
- Total conversations captured.
- Total assistant integrations without active usage.
- Time spent in the product.

## 14. Risks and Open Questions

| Risk or question | Current response |
|---|---|
| Users may not perceive incorrect memories as urgent | Validate with real memory comparisons before building delivery |
| Extraction can create new unsupported inference | Require provenance, inference labels, and approval |
| Sensitive memories may be exposed during review | Keep evidence local, minimize previews, and add sensitivity controls |
| Provider memory exports may be incomplete | Start with pasted summaries and archive-derived comparison |
| Browser and provider connectors are fragile | Defer broad automatic capture until after retention is proven |
| Profiles may feel complex | Start with Personal, Work, and one Project template |
| Memory standards may change | Stabilize the internal ledger before mapping to external protocols |
| Local models may increase package size and complexity | Keep them optional and validate value before default bundling |

## 15. Research Confidence and Limitations

- Official documentation, product pages, privacy policies, changelogs, pricing,
  and public issues were prioritized.
- The products were not evaluated through long-term authenticated use in this
  research pass.
- Current Pieces individual pricing was not included because a sufficiently
  reliable current source was not established.
- LLMnesia feature claims are based primarily on its official pages and
  changelog; independent adoption and retention evidence is weak.
- A GitHub issue or feature request proves that a problem occurred, not how
  frequently it affects the full user base.
- The roadmap gates are product hypotheses, not established benchmarks. They
  must be replaced with observed baseline data as validation proceeds.

## 16. Current Delivery Tracker

Update this table whenever a roadmap deliverable changes. Add specific task
detail to the Task Work Log below.

| ID | Workstream | Status | Owner | Current milestone | Evidence / next gate | Last updated |
|---|---|---|---|---|---|---|
| F0 | Existing archive and search foundation | Complete | Project | Local ChatGPT/Claude archive, FTS5 and optional hybrid search, cited Ask Archive, insights, backup/restore | Existing repository implementation and tests | 2026-07-15 |
| P0 | Problem validation and taxonomy | In progress | Project | Engineering pilot complete; run the first live audit with the user's ChatGPT memory summary | Complete 8-10 target-user audits; 60% find a meaningful discrepancy; collect 50 cases | 2026-07-15 |
| P1 | Memory Audit MVP | Not started | Unassigned | Blocked on P0 gate | First correction under 10 minutes; evidence coverage 100% | 2026-07-15 |
| P2 | Memory governance | Not started | Unassigned | Blocked on P1 gate | Two-profile adoption and contradiction-resolution targets | 2026-07-15 |
| P3 | Controlled delivery | Not started | Unassigned | Blocked on P2 gate | Weekly verified reuse and zero scope violations | 2026-07-15 |
| P4 | Capture and interoperability | Deferred | Unassigned | Revisit after P3 retention evidence | Connector maintenance justified by active usage | 2026-07-15 |

## 17. Task Work Log

Every repository task must add or update an entry here. Do not delete completed,
cancelled, or superseded entries.

| Date | Task | Roadmap link | Status | Scope and decisions | Validation evidence |
|---|---|---|---|---|---|
| 2026-07-21 | Integrate completed work through `dev` into `main` | Maintenance / Other | Complete | Preserved the onboarding/archive-management commit and Phase 0 memory-audit pilot as separate history; expanded and merged PR #10 into `dev` with a merge commit, then merged the verified `dev` tree into `main` with a merge commit; no new product scope | Ruff passed; 110 Python and 19 frontend tests passed; TypeScript and production frontend build passed; fresh PyInstaller build created `dist/Reweave/Reweave.exe`; 8-second executable startup smoke passed; PR #10 merged as `c3041c4`; `dev` merged and pushed to `main` as `b17db95`; `main` and `dev` tree hashes matched |
| 2026-07-15 | Complete the Phase 0 one-person memory-audit engineering pilot | P0 | Complete | Supersedes the earlier implementation entry: added a separate local validation store, human-confirmed LLM assistance, evidence review, redacted exports, and English research materials; the first live pilot still uses a ChatGPT memory summary; P1 ledger and delivery remain out of scope | Ruff and TypeScript passed; 110 Python and 19 frontend tests passed; production frontend build passed; synthetic browser flow covered manual creation, no-evidence review, save, completion, and redacted JSON export with no browser errors; fresh PyInstaller build produced `dist/Reweave/Reweave.exe` and startup smoke passed; P0 remains In progress pending the real-user gates |
| 2026-07-15 | Build the Phase 0 one-person memory-audit pilot | P0 | In progress | Add a separate local validation store, human-confirmed LLM assistance, evidence review, redacted exports, and English research materials; first live pilot uses a ChatGPT memory summary; P1 ledger and delivery remain out of scope | Implementation, automated tests, executable build, and pilot evidence pending |
| 2026-07-15 | Preserve product strategy and require permanent progress tracking | Maintenance / Other | Complete | Created this canonical strategy, research, rationale, roadmap, tracker, and decision log; updated `AGENTS.md` so every future task maintains it | Documentation reviewed; no runtime files changed, so executable build was not required |

## 18. Decision Log

| ID | Date | Decision | Reason | Status / supersedes |
|---|---|---|---|---|
| D-001 | 2026-07-15 | Position Reweave as a human-facing AI Memory Control Plane | Generic archive, search, and portable-memory positions are already crowded | Active |
| D-002 | 2026-07-15 | Treat the conversation archive as immutable evidence and the ledger as a controlled derived layer | Preserves provenance and lets users challenge or replace model-generated memory | Active |
| D-003 | 2026-07-15 | Require evidence and user approval before a proposed memory becomes canonical | Addresses unsupported inference and user-agency risk | Active |
| D-004 | 2026-07-15 | Separate personal, work, client, and project profiles | Prevents a universal profile from oversharing context | Active |
| D-005 | 2026-07-15 | Defer automatic injection and broad browser capture until audit and governance are validated | Reduces privacy, reliability, and connector risk | Active |
| D-006 | 2026-07-15 | Make Weekly Verified Memory Reuse the north-star metric | Rewards trustworthy reuse instead of memory hoarding | Active |
| D-007 | 2026-07-15 | Use privacy-safe templates and interoperability for distribution | Raw personal memory is inappropriate as viral content | Active |
| D-008 | 2026-07-15 | Store Phase 0 audit sessions in a separate local SQLite validation database | Prevents validation records from prematurely fixing the Phase 1 canonical-ledger schema or mutating the conversation archive | Active |
| D-009 | 2026-07-15 | Treat LLM extraction, search, and classification output as suggestions; only human-confirmed decisions count as findings | Keeps problem validation separate from model quality and preserves user authority | Active |
| D-010 | 2026-07-15 | Run the first live pilot with a ChatGPT memory summary and defer Claude comparison to a later pilot | Matches currently available participant data without changing the broader Phase 0 gate | Active |

## 19. Source Map

### Pieces

- [Pieces documentation](https://docs.pieces.app/)
- [Pieces product preview](https://preview.pieces.app/)
- [Pieces AI Memory Assistant](https://pieces.app/features/long-term-memory/ai-memory-assistant)
- [Pieces security](https://pieces.app/legal/security)
- [PiecesOS quick menu and long-term-memory controls](https://docs.pieces.app/products/core-dependencies/pieces-os/quick-menu)
- [Pieces backup, restore, and enrichment controls](https://docs.pieces.app/features/back-up-and-restore)
- [Public MCP context retrieval issue](https://github.com/pieces-app/support/issues/747)

### Recall

- [Recall product overview](https://www.recall.it/about)
- [Recall pricing and packaging](https://www.recall.it/pricing)
- [Recall documentation](https://docs.recall.it/)
- [Active recall and spaced repetition](https://www.recall.it/active-recall-and-spaced-repetition)
- [Recall FAQ](https://www.recall.it/faq)
- [Recall 2.0 release notes](https://feedback.recall.it/changelog/recall-release-notes-april-14-2026-recall-20)
- [Recall changelog](https://feedback.recall.it/changelog)
- [Export original files feature request](https://feedback.recall.it/feature-requests/p/export-with-files)

### LLMnesia

- [LLMnesia product page](https://www.llmnesia.com/)
- [LLMnesia changelog](https://www.llmnesia.com/changelog)
- [LLMnesia privacy policy](https://www.llmnesia.com/privacy-policy)
- [LLMnesia use cases](https://www.llmnesia.com/use-cases)

### Adjacent memory systems and standards

- [OpenMemory](https://mem0.ai/openmemory)
- [OpenMemory browser extension](https://mem0.ai/blog/introducing-the-openmemory-chrome-extension)
- [Supermemory personal product](https://supermemory.ai/personal/)
- [Supermemory platform](https://supermemory.ai/)
- [Lumi](https://www.llmmemory.ai/)
- [Open Memory Protocol specification](https://openmemoryprotocol.com/spec/)

### Research

- [Algorithmic Self-Portrait: An Empirical Study of ChatGPT User Memory](https://arxiv.org/abs/2602.01450)
- [Memory governance survey](https://arxiv.org/abs/2604.16548)
