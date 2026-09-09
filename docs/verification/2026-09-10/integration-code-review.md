# Reading Room integration code review

Date: 2026-09-10 KST. Review scope: analysis policy and queue scheduling, web maintenance integration, encrypted transfer endpoints, source filtering, diagnostics, and their runtime ownership boundaries. Review used synthetic fixtures, memory-only credentials, and local tests. No live provider, native window, browser profile, clipboard, or registry access was used.

The initial review was read-only. The parent subsequently authorized this reviewer to fix archive identity matching and direct CLI ownership; the parent fixed provider guards, restore accounting, application ownership, and shutdown. Historical reproduction artifacts remain unchanged. All four confirmed findings below have been corrected and independently rechecked within this scope. This is not an executable-build, release, real-data extraction-quality, or whole-product completion claim.

## Findings and disposition

### R1 — P1: Disconnected provider credentials remained usable by unsent jobs

Initial locations: `src/reweave/context_scheduler.py:90–100` and `src/reweave/web.py:1424–1429` in the reviewed pre-fix state. The scheduler resolved one saved provider before claiming three jobs and retained that provider's credential tuple for every later job. Disconnect removed persisted keys but did not invalidate this captured runtime. A disconnect or provider change during the first request therefore allowed later unsent sources, chunks, or failover attempts to use the previous credentials. This violated the user's provider-choice boundary in Product Spec Safety, privacy, and data.

Reproduction: resolve a connected synthetic runtime; claim three fixture jobs; mark that connection disconnected during the first submission. The runtime was resolved once and all three submissions used the old provider, including two while disconnected. See [original evidence](integration-review-repros.json).

Correction: the scheduler now re-resolves the runtime for each claimed job (`context_scheduler.py:95–120`); the saved-provider guard validates the profile, credentials, and required active profile before transmission (`web.py:2231`). Failover checks the guard before each key. `BudgetedProvider` checks it before reserving allowance (`analysis_policy.py:143`). A superseded claim is skipped before deferral, preventing concurrent recapture from stranding later claims.

Recheck: only the first job was submitted; later runtime resolutions returned disconnected. A synthetic first-key 429 that disconnects the profile prevented the second key and a subsequent call, without an additional reservation. See [recheck evidence](integration-review-recheck.json) and `tests/test_provider_connection_guard.py`. Already transmitted HTTP requests cannot be recalled; the fix prevents subsequent transmissions.

### R2 — P2: Restoring a backup rewound the current day's safe allowance

Initial location: `src/reweave/encrypted_backup.py:203–229`, especially the database replacement; the ledger consumed by `analysis_policy.py:104` was replaced by its historical backup value. Requiring provider reconnection delayed the next request but did not preserve attempts already consumed that day. This broke the user-visible safe-limit requirement in Product Spec Nonfunctional requirements.

Reproduction: set a daily attempt limit of two, back up at usage zero, reserve two attempts, then restore. Usage became zero and another two attempts were accepted on the same UTC day. No remote request was made. See [original evidence](integration-review-repros.json).

Correction: `_commit_restore` reads the current UTC day's usage and merges the per-counter maximum into the staged database before its atomic commit (`encrypted_backup.py:206–225`). This preserves the local current-day high-water mark while retaining a higher backed-up reservation.

Recheck: restored attempts remained two, tokens remained 2,000, and a new reservation was rejected. See [recheck evidence](integration-review-recheck.json) and `test_restore_preserves_current_day_usage_high_water_mark` in `tests/test_encrypted_backup.py`.

### R3 — P1: Library replacement was exclusive only inside one application instance

Initial locations: `src/reweave/maintenance.py:16–58`, `desktop.py:33–76`, and `web.py:335–351` in the reviewed pre-fix state. Each app had an independent maintenance gate. Normal launch created another runtime without reserving the library before restore recovery and cleanup. Two owners could therefore race database replacement or recovery.

Reproduction: create two real application instances against one synthetic database; hold an active operation in A; restore through B. B returned 200 and A continued serving. See [original multi-app evidence](integration-review-multi-app.json).

The first ownership fix exposed a shutdown gap: the launcher released its lock while a context worker remained alive because executor shutdown did not wait. Through actual `desktop.running_app`, the server exited in 0.208 seconds, another owner acquired the lock, and the old worker subsequently completed a synthetic write. See [original shutdown evidence](integration-review-shutdown.json).

The same review found direct CLI commands bypassed the new owner lock. With that lock held, `reweave import --db` returned zero and inserted two conversations. See [original CLI evidence](integration-review-cli-owner.json). Read commands also construct stores that perform schema initialization, so they require the same boundary.

Correction: `library_lock.py` holds an OS lock before application construction; desktop and CLI app launchers retain it through shutdown. `web.py:360` waits for running executors after marking shutdown, and `InterruptibleProvider` prevents subsequent requests. `desktop.py:87` waits for the actual server shutdown instead of releasing ownership after its former short deadline. Direct import/search/index/ask/show/stats/export commands now acquire the same lock before constructing a store using the signature-preserving wrapper in `cli.py:35`; desktop and app do not acquire it twice.

Recheck: `tests/test_library_lock.py` rejected a second supported launcher before database/runtime writes and verified ownership during worker shutdown. The actual launcher waited 3.012 seconds for the synthetic worker and returned with no worker still running; see [shutdown recheck](integration-review-shutdown-recheck.json). CLI import now exits one with zero imported conversations while another owner holds the lock; see [CLI recheck](integration-review-cli-owner-recheck.json). Parameterized CLI tests verify all seven commands are blocked before constructors or output writes, the lock spans index/ask work, and command errors release it.

### R4 — P1: Timestamp fallback merged distinct exported conversation identities

The foundation reviewer identified this additional archive issue and the parent assigned its fix to this reviewer. Initial location: `src/reweave/archive.py:663–674`. If explicit source-ID lookup missed, provider plus creation timestamp selected the first row regardless of its different explicit identity. Importing two unrelated exports with equal timestamps overwrote source metadata and message positions. An export omitting an ID could also erase a previously established source ID.

Correction: `_insert_conversation` (`archive.py:644`) keeps explicit provider/source IDs authoritative. Timestamp fallback requires at least one missing identity and one unambiguous candidate. Existing explicit IDs survive later exports that omit them. An incompatible legacy internal-ID collision receives a new archive ID, then remains stable through explicit source-ID lookup on reimport. No existing archive rows were rewritten by this code change.

Recheck: six new archive regressions cover Claude and ChatGPT same-timestamp/same-title exports with distinct IDs, missing-to-known identity upgrades, later missing-ID exports, ambiguous timestamp matches, and legacy internal-ID collisions. Distinct explicit exports retain two conversations and all six fixture messages. Existing fixture idempotency, updates, capture, parser, and golden extraction tests pass. Previously conflated data is not automatically separable; this fix prevents further conflation and permits distinct explicit identities to be imported again.

## Other inspected boundaries

- The same-instance maintenance gate reserves executor work before submission and releases canceled futures. Backup/restore holds its exclusive lease through database replacement and post-restore reinitialization. Committed restore cleanup failures report success with restart required and block further API operations rather than misreporting rollback.
- `LocalOriginMiddleware` rejects untrusted Hosts, mismatched Origins/ports, duplicate trust headers, and cross-site browser requests before upload parsing. Origin-less local tools remain an explicit supported boundary; this is not authentication against arbitrary local processes. Rejected-body tests verify the application and body receiver are not called.
- Source project/type predicates are parameterized and applied before keyword/semantic ranking. Filter regression tests cover all search modes. No additional correctness defect was found in `source_filters.py`.
- Diagnostics use an explicit allowlist of counts, runtime versions, and non-secret flags. Source/context text, names, IDs, paths, provider addresses, prompts, and credentials are excluded. Browser QA separately inspected the JSON attachment.
- Source deletion uses foreign-key cascades for checkpoint runs, while derived evidence retains compact source metadata. Extraction revalidates the source fingerprint inside the final transaction. Partial invocation and allowance pauses remain pending with durable checkpoints; a completed checkpoint run is not itself a completed Brief. These paths were inspected and covered by the focused checkpoint/deletion tests; no live in-flight provider deletion test was performed.
- The parent independently corrected pywebview's default download-disabled setting. The browser QA report retains the distinction between that desktop configuration defect, unresolved headless download cancellation, and untested Windows Save-dialog completion.

## Verification evidence

| Command / check | Result |
| --- | --- |
| `pytest tests/test_backup_api.py tests/test_local_origin.py tests/test_semantic.py tests/test_context_chunking.py -q` | 85 passed, 10.93 seconds |
| `pytest tests/test_analysis_policy.py tests/test_context_scheduler.py tests/test_provider_connection_guard.py tests/test_library_lock.py tests/test_encrypted_backup.py -q` | 47 passed, 74.68 seconds |
| `pytest tests/test_archive.py tests/test_archive_management.py tests/test_parsers.py tests/test_extension_bridge.py tests/test_conversation_capture.py -q` | 85 passed, 7.40 seconds |
| `pytest tests/test_context_extraction_golden.py -q` | 31 passed, 11.12 seconds |
| `pytest tests/test_cli.py tests/test_library_lock.py -q` | 17 passed, 2.38 seconds |
| Ruff check/format for owned archive, CLI, tests, and `scripts/qa_full_reading_room.py`; helper compilation | Passed |

An earlier combined run had one golden assertion failure because the concurrent matching change normalized trailing whitespace; the foundation owner corrected the expected normalized text, and the complete golden file then passed. Test runs report the existing Starlette TestClient deprecation warning. All reproduction processes and the owned headless runtime exited normally; only synthetic scratch files remain under the ignored QA directory. No product files outside the subsequently assigned archive/CLI scope were changed by this review.
