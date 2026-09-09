# Product scope audit — 2026-09-10

## Scope and evidence boundary

Read-only audit of the full accepted Product Spec, focused on missing user value and functional
risk beyond the separately implemented encrypted backup and exception Review work. Read the
Product Spec, Project Status, Roadmap, and relevant decisions in their required order. The
single recorded Next task remains TASK-005; DEC-026 authorizes later isolated implementation
while retaining real-use acceptance.

Observed checkout: `codex/reading-room-product`, HEAD
`2303357a736b12312f02d657f288530d10a5ad64`, with concurrent uncommitted implementation. References
below describe this working tree at audit time, not that historical commit. Other agents are
fixing findings; retain this original observation and add verification of any resolution.

Evidence used: current code, test bodies, file inventory, canonical records, and three direct
Python probes using synthetic in-memory objects. The probes made no provider call, downloaded
no model, read no owner data, and opened no browser. Existing tests are identified as coverage,
not asserted to have passed from their prose. Root-owned full tests, fresh executable build,
and current headless browser verification were still in progress during this audit.

## Prioritized code findings

### P1 — Explicit reanalysis can silently reuse the old result

`frontend/src/AnalysisQueue.tsx:60` sends `reanalyze: true`; `src/reweave/web.py:774` requeues the
existing source job, and `src/reweave/context_library.py:482` clears queue completion. However,
`src/reweave/context_extraction.py:124` identifies analysis only by prompt version, mode, and
personal-instruction hash. Lines 135–141 immediately return the existing complete Brief when
the source fingerprint matches. Neither the queue worker at `src/reweave/web.py:682` nor the
extraction function carries a force/new-analysis-revision flag. Changing provider or model
does not invalidate that result.

Concrete probe: an unchanged synthetic source with a complete Brief, a different requested
model, and a counting fake provider returned:

```json
{"requested_model":"different-better-model","reused_existing":true,"provider_calls":0}
```

Impact: a user cannot refresh a poor extraction by selecting a better model and explicitly
reanalyzing the same source. Automatic idempotence is useful but currently also consumes the
explicit refresh action. Fix with durable explicit-reanalysis identity while preserving repeat
Save/import reuse and the existing correction/history protections. Regression must prove a
new explicit attempt invokes the newly selected model exactly once and survives restart.

### P1 — Semantic deduplication and automatic contradiction classification are absent

The extraction normalizer keys items by type, epistemic kind, and case/whitespace-normalized
text (`src/reweave/context_extraction.py:294`). Persistence identity also hashes normalized
text and exact routes (`src/reweave/context_library.py:1545`). There is no semantic-equivalence
decision in this path. Different paraphrases therefore become separate items.

The only automatically constructed relationships in reconciliation are `source_update` for
same-source reanalysis with overlapping evidence (`src/reweave/context_library.py:1284`) and
`shared_evidence` for identical source excerpts (`src/reweave/context_library.py:1582`). The
extraction output has no item-relationship field. Evidence relationships such as `contradicts`
are not converted into contradictions between canonical items. Two different conversations
can establish opposing active decisions without creating the link required by Review or the
retriever's contradiction guard.

`tests/test_context_linking.py` covers exact duplicates, source updates, and history; retrieval
golden fixtures manually seed relationship edges. Those tests do not demonstrate automatic
semantic duplicate/expansion/contradiction detection. This is a missing engine stage, not a
missing graph drawing. Acceptance 8 and automatic linking/personalization remain incomplete.

Fix must distinguish equivalent paraphrases from expansion, changed decisions, and negation;
preserve scope and user authority; attach new evidence to true duplicates; and create explicit
versioned relationships for disagreements. A new source has no independent trusted project
association in `ArchivedConversation`; only prior derived Context scopes provide associations.
Do not send unrelated private candidate text to an analysis provider merely because new source
text or model output names its scope. The reconciliation owner has been informed of this boundary.

### P1 — Long sources lose middle content but are marked fully analyzed

`src/reweave/context_extraction.py:637` removes the middle of every message longer than 8,000
characters. `_source_payload` at line 584 then alternates first/last messages within the overall
input limit and discards messages that do not fit. `omitted_message_count` is sent to the model
but is not persisted in the Brief, queue completion, or result. The full source fingerprint is
stored and the Brief becomes `complete` at line 200. No chunk continuation or later coverage
pass exists in this path; unchanged analysis is then reused.

Concrete default-budget probe:

```json
{"long_source_total":40,"sent_messages":9,"omitted_messages":31,"individual_message_compacted":true}
```

Impact: the middle decisions or lessons in an ordinary long chat can never become Context, while
the UI says the source is ready to read. Bounded input is appropriate; silent permanent coverage
loss conflicts with faithful Conversation Briefs and full selected-conversation analysis.
Persist coverage and perform bounded resumable chunk analysis/synthesis within the existing
allowance. Do not call a partial source completely analyzed. Tests should place the only decisive
fact in an omitted middle turn and in the middle of a long individual message.

### P2 — Intra-response deduplication merges separate protective scopes

The normalizer's dedup key omits scopes, and `_merge_items` unconditionally unions them at
`src/reweave/context_extraction.py:510`. This occurs before the persistence layer's more careful
scope-aware identity check.

Concrete probe with equal text and separate Client A / Client B project scopes:

```json
{"raw_distinct_project_items":2,"normalized_items":1,"merged_project_keys":["Client A","Client B"]}
```

The current retriever requires all protective routes, so this observation establishes identity
conflation and blocked single-client recall, not a demonstrated disclosure. Preserve distinct
scope-bound items during normalization; do not rely on the later persistence guard to recover
the original two identities. Cover different projects, Personal/Work, and sensitivity mismatch.

### P2 — Source project/topic/type filtering is not implemented

`/api/library` and `/api/search` (`src/reweave/web.py:821` and line 850) accept source/provider,
title, and date filters. They have no project, topic, Context type, or linked-space constraint.
`frontend/src/ContextSearch.tsx` adds space/type controls only to the separate Context-result
panel. `frontend/src/Workspace.tsx:1041` renders it separately from original-source results;
those controls do not filter the sources below it.

The source-to-Context navigation component exists and is valuable, but the accepted Sources /
Evidence Search filter contract is not met. Add join-backed source filtering using canonical
Context associations; include explicit unanalyzed/no-associated-context handling so optional
filters do not permanently hide imported sources. Verify combinations with provider/title/date,
pagination, changed/merged spaces, and source-to-item navigation.

### P2 — Automatic analysis has a maximum batch size but no idle/batch readiness gate

Every capture/import wakes the scheduler immediately (`src/reweave/web.py:788`, line 1220).
`ContextAnalysisScheduler._run_once_guarded` immediately claims up to three ready jobs
(`src/reweave/context_scheduler.py:85`), and fresh queue rows have no readiness delay.
The 30-second poll is a fallback wake interval, not a minimum idle interval. One newly saved
source may therefore invoke the provider immediately while successive saves replace it.

This misses the explicit idle-interval-or-useful-batch requirement and can waste bounded daily
allowance on transient source versions. Add a durable debounce/readiness timestamp or equivalent
batch threshold, retaining an explicit Analyze now bypass and capped retry semantics. Test one
fresh capture, several quick updates, enough queued sources, restart, and manual acceleration.

## Acceptance preparation gaps

### Versioned extraction quality evaluation is missing

The current prompt is `context-extraction-v2`. `tests/test_context_extraction.py` has meaningful
normalizer/persistence tests, including prompt rules, Core Self restrictions and inferred
rationale, but feeds canned `FakeJsonProvider` output. The only versioned golden corpus found
under `tests/fixtures` / `tests/evaluation` is for retrieval. It does not evaluate whether an
analysis model produces faithful extraction, useful synthesis, tacit interpretation, or resists
source injection. The Product Spec explicitly requires this corpus when revising prompts.

Prepare versioned source/expected-evidence cases and an opt-in bounded evaluation runner. Cases
must include ordinary useful insights, zero justified items, inferred values/tacit knowledge,
contradiction, paraphrase/negation, long-source coverage, multilingual evidence, injection, and
scope leakage. Preparing the corpus/runner is code work; executing paid model-quality evaluation
requires the later approved data/model/call/cost/stop boundary. Synthetic normalizer tests must
not be reported as measured real synthesis quality.

Core Self and rationale presentation exist in `ContextWorkspace.tsx:786` and line 1329. Current
extraction sees one conversation, and Core Self eligibility requires two supporting user
messages in that conversation. No separate cross-conversation or repeated-edit preference
synthesis job was found. Do not claim such learning from persistence/reconciliation alone;
validate the intended automatic personalization outcome in the extraction-quality work.

### Public-beta installation and distribution are unprepared

`packaging/` contains only the desktop/native-host entry points and `Reweave.spec`, producing a
PyInstaller folder. `extension/README.md:30` requires Developer mode, manually copying an
extension ID, a local build, and `register_native_host.ps1`. No installer source, install/update/
uninstall lifecycle verification, store submission package, or distribution-specific privacy /
support asset set was found. The extension README also retains superseded URL-implies-private
copy at line 11; current trust controls require explicit destination intent.

TASK-014 cannot be completed by a successful executable build. Installer and release-asset
preparation can proceed locally. Real Windows registration, existing browser profiles, store
publication/IDs, signing decisions, and public release remain separately controlled operations.

## Accepted-flow coverage map

| Spec acceptance | Current implementation/test evidence inspected | Remaining qualification |
|---|---|---|
| 1–3: optional backfill, no-key use, later connection | Onboarding and Import in `Workspace.tsx`; enqueue-on-import routes; profile-connect scheduler wake; `tests/test_context_api.py`, queue/scheduler tests | Fresh root-owned browser/full-suite evidence pending; idle readiness gap above |
| 4: explicit whole-chat Save before analysis | Capture/Native Messaging code and ChatGPT/Claude fixture suites | Real current-provider DOM/account run is an owner acceptance gate |
| 5: automatic Brief + supported items | `context_extraction.py`, `context_scheduler.py`, extraction and queue tests | Long-source coverage, real synthesis evaluation, and idle readiness incomplete |
| 6: Home/Explore/evidence share linked data | `ContextWorkspace.tsx`, management/linking tests, paired Reading Room artifacts present | Current visual QA belongs to the UI agent; no new visual pass claimed here |
| 7: cross-hierarchy search | Global Context retriever, keyword/semantic path, versioned retrieval corpus | Source filters incomplete; actual embedding/model relevance remains unmeasured here |
| 8: dedup, contradictions, material changes | Exact-text reconciliation, source updates, immutable versions | Semantic equivalence and cross-source disagreement classification absent |
| 9: correction + undo | Atomic revision/space methods and `test_context_linking.py`, management tests | Explicit reanalysis currently cannot refresh unchanged-source extraction |
| 10–11: explicit allowed Use and strict trust | Current trust, assembly, extension confirmation implementation; foundation agent hardens resolution lookup | Latest focused/full checks owned by foundation/root; real-use relevance not established |
| 12: durable failed analysis retry | Durable queue, startup recovery, backoff and bounded allowance implementation | Do not equate retry scheduling with idle batching or full-source coverage |
| 13: separate source/derived deletion | Source snapshots and separate exclusive Library deletion | Direct delegated integration test observed deletion + restart preserving sources |
| 14: encrypted one-artifact restore | Separate encrypted-backup work includes Review/Trust tables | Delegated focused backup tests passed; final package/restoration smoke owned by root |
| 15: canonical Graph and explicit redacted share | `context_graph.py`, Graph UI/tests present | Graph discovery value depends on the missing semantic link stage and later dogfooding |
| 16: remove standalone Ask/Audit product | Primary `Workspace.tsx` navigation contains Home/Explore/Sources; legacy APIs/data preserved | Old Project Status drift bullets and extension README need final documentation reconciliation |
| 17: owner decides real usefulness | DEC-026 and TASK-012 retain the mandatory owner loop | Not satisfied by synthetic tests, screenshots, or packaging |

## Owner-controlled final gates

- Select the real conversation(s), provider/model, call/cost ceiling, and stop rule before the
  first paid/data-transmitting acceptance run. Prove Save/Import → analysis → restart → evidence
  inspection → explicit Use, then assess whether repeated explanation actually decreased.
- Resolve public v1 scope freeze and encrypted-synchronization timing at TASK-013. They are not
  reasons to stop the remaining authorized local implementation.
- Authorize any real installation/registry/browser-profile/store operation only after concrete
  installation and distribution artifacts are prepared. A build is not installation evidence.

## Verification handoff

The three numeric probe outputs above were observed directly in this audit. No full-suite,
model-quality, packaged runtime, owner-use, or public-distribution success is claimed here.
Re-audit corrected code and regression tests against these same cases before closing findings.
