# Extraction and reconciliation review — 2026-09-10

## Scope and evidence boundary

Reviewed the current uncommitted `codex/reading-room-product` implementation against
`PRODUCT_SPEC.md`, `PROJECT_STATUS.md`, `ROADMAP.md`, and DEC-026 through DEC-029.
Primary files were `context_extraction.py`, `context_chunking.py`, `context_matching.py`,
the reconciliation and evidence paths in `context_library.py`, and the versioned extraction
fixtures/tests. The additional provider-attempt review covered `llm.py` and
`analysis_policy.py`.

The review initially made no product changes. After the three initial findings were reproduced,
the implementation owner assigned the two scope fixes to the Context foundation implementer
and the bounded provider-attempt fix to this reviewer. Only that last assignment superseded
the read-only product-code boundary. Independent synthetic rechecks of the scope fixes passed.
All probes used temporary libraries and synthetic adapters or intercepted HTTP. No provider
request, owner source data, model download, browser, clipboard, registry, or desktop interaction
was used. Full-suite, executable-build, installer, and packaged-runtime evidence belongs to
the root delivery record and is not claimed here.

## Confirmed findings and resolution

### P1 — One grounded route authorized another ungrounded protective route

Original evidence: `src/reweave/context_matching.py:93-103` used
`grounded_named_route |= any(...)`. The cross-source gate at original lines 121–124 checked
that at least one named project/destination occurred in cited user evidence, while accepting
additional high-confidence model-provided project/destination routes.

Reproduction: an existing normal item had routes `Atlas` and `Secret`. A new source mentioned
only `Atlas`, and the synthetic model added `Secret` to the extracted item's scopes. Candidate
preparation included the existing `Secret`-scoped summary in its outbound payload:

```json
{"case":"unguarded_second_route","private_summary_transmitted":true,"pairs":1}
```

Impact: untrusted model output could widen the content sent during relationship analysis,
contrary to the requirement that every protective route be supported.

Resolution: `context_matching.py:81-103` now records each named route's grounding;
`context_matching.py:122-129` requires a nonempty set with every member grounded. Current
scope compatibility and sensitivity restrictions remain in place. The independent original
probe now returns:

```json
{"case":"unguarded_second_route","private_summary_transmitted":false,"pairs":0}
```

Status: resolved in the reviewed working tree. Golden regressions cover multiple projects,
project plus destination, and both allowed and denied routes.

### P2 — Historical extraction identity bypassed current corrected scope

Original evidence: `src/reweave/context_library.py:1175-1179` accepted a stored extraction
identity without checking the target's current routes. The legacy fallback at original
lines 1218–1235 also accepted a historical route match for any user-corrected item, regardless
of whether the new source was the source whose correction was being preserved.

Reproduction: an item originally extracted as `Generic repeated decision.` in `Atlas` was
corrected by the owner to `Secret project owner correction.` in `Secret`. A different source
then produced the original wording in `Atlas`. Reconciliation returned the corrected `Secret`
item and attached the new `Atlas` source evidence to it:

```json
{"case":"stale_identity","reused_corrected_target":true,"returned_scopes":[["project","Secret"]]}
```

Impact: a different source could inherit another source's correction and protective scope,
producing incorrect canonical context and cross-scope provenance.

Resolution: `context_library.py:1180-1186` now validates current routes, type, and epistemic
kind unless preserving a user correction associated with this same source. The legacy
fallback at lines 1195–1254 applies the same distinction and preserves same-source correction
precedence when a different source populated the global identity after migration. The
independent original probe now returns:

```json
{"case":"stale_identity","reused_corrected_target":false,"returned_scopes":[["project","Atlas"]],"new_source_attached_to_corrected_target":false}
```

Status: resolved in the reviewed working tree. Regressions exercise indexed and legacy paths,
scope/type/kind corrections, repeated cross-source extraction, and same-source preservation.

### P2 — Source and invocation limits counted stages instead of actual key attempts

Original evidence: `context_chunking.py:662-675` reserved one provider call per generation
callback, while `llm.py:141-151` could send one request per enabled credential. Daily usage
reservations in `analysis_policy.py` correctly reserved the credential ceiling, but the
eight-call invocation and 256-call source limits did not. A real `FailoverLLMProvider` with
synthetic adapters, one timeout, and one success reproduced:

```json
{"case":"credential_attempt_accounting","actual_provider_attempts":2,"coverage_provider_calls":1}
```

Additionally, a later-key permission/allowance denial refunded the entire stage at original
`context_chunking.py:679-687` and `555-563`, despite an earlier key having been sent.

Resolution: `llm.py:15-34` adds an execution-local send recorder, separate from repeatedly
executed permission guards. OpenAI-compatible, Anthropic, and Gemini adapters record once
immediately before HTTP (`llm.py:203`, `261`, `325`). Failover uses one generation-boundary
fallback for custom/test adapters that do not report their own sends (`llm.py:172-174`).
`context_chunking.py:502-551` atomically reserves each actual send, enforces the source limit
before transmission, and retains earlier reservations if a later key is denied. The runner's
invocation counter is shared with relationship verification. The existing extraction limits
of seven source-stage attempts plus the eighth relationship slot, and 255 source attempts
plus the 256th relationship slot, remain within the accepted ceilings. Uninstrumented
synthetic callbacks retain the existing one-attempt behavior; a pre-send denial counts zero.
Daily worst-case reservations remain unchanged and conservative.

Status: implemented and passing focused verification. The Context foundation implementer
independently read the frozen send-boundary/counter change and found no blocker in double-count
avoidance, partial denial retention, or shared limits; its independent run of the ten new cap
tests passed in 3.96 seconds. The adjacent same-run restore finding below has also been fixed
and independently rechecked. The root's full-suite/build/package loop remains a delivery
responsibility, not additional model quality evidence.

### P2 — Restoring an older partial backup rewinds the same run's attempt ceiling

Original evidence: `encrypted_backup.py:202-226` preserves the current day's `analysis_usage`
high-water counters, but does not preserve `context_chunk_runs.provider_calls` before replacing
the live database at line 248. The chunk run key includes the original source, fingerprint,
configuration, generation, partition size, and segment fingerprints; restoring the older
partial run leaves that identity unchanged.

Reproduction used intercepted real OpenAI-compatible adapter calls and a synthetic daily
allowance of 1,000 attempts. The source's first failed attempt was backed up, the same run
then reached 256 failed attempts and correctly blocked further transmission. Restoring the
older partial artifact and explicitly resuming the synthetic provider produced:

```json
{"same_run_key":true,"generation":1,"backup_calls":1,"before_restore_calls":256,"blocked_at_256":true,"after_restore_calls":1,"restore_itself_sent_requests":false,"restored_active_profile":null,"restored_enabled_key_references":[false],"actual_synthetic_attempts_after_explicit_resume":257,"stored_calls_after_resume":2,"daily_reserved_after_resume":257}
```

Impact is bounded to a resumed unchanged analysis run after restore. This is not a new
explicit reanalysis generation. It is also not an automatic or unauthorized provider send:
restore unset the active profile, disabled every key reference, and made no request. An
explicit reconnect/resume is necessary. The independent daily allowance still applies, but
does not preserve the source's lifetime ceiling across days or a higher configured allowance.

Smallest recommended correction: before database replacement, merge the maximum current and
staged `provider_calls` for matching `run_key` values. Keep the backup's source/checkpoint
content and progress; do not transfer budget between different configurations or explicit
generations. Add an older-partial same-run restore regression and a distinct-generation
control. No generic rollback prevention or unrelated data merging is proposed.

Resolution: the root implementer's `encrypted_backup.py:218-232` streams live
`provider_calls` and `run_key` into matching staged rows with `MAX(provider_calls, ?)`,
before the staged transaction commits and the atomic database replacement occurs. It does
not import checkpoint content, insert unrelated runs, or change another generation's budget.
The parameterized regression at `tests/test_encrypted_backup.py:134-206` covers both current
and backup high-water directions, exact checkpoint preservation, a blocked same-run follow-up,
and an independent generation's allowed follow-up.

The reviewer independently reran the original intercepted HTTP probe against the correction:

```json
{"same_run_key":true,"backup_calls":1,"before_restore_calls":256,"after_restore_calls":256,"same_run_attempt_257_blocked":true,"same_run_actual_synthetic_attempts":256,"restored_active_profile":null,"restored_enabled_key_references":[false],"new_generation_separate_run_key":true,"new_generation_calls":1,"total_actual_attempts_including_new_generation":257}
```

Status: resolved and independently verified in the current working tree. The final extra
attempt belongs only to explicit generation 2; generation 1 remains blocked at 256. This
reviewer made no production changes for the restore follow-up. No confirmed P1/P2 finding
from this bounded extraction/cap review remains open.

## Executed verification

- `.venv\Scripts\python.exe -m pytest -q tests/test_context_attempt_limits.py tests/test_context_chunking.py tests/test_analysis_policy.py tests/test_provider_connection_guard.py`
  — 41 passed in 14.29 seconds; one existing Starlette/httpx deprecation warning.
- `.venv\Scripts\python.exe -m pytest -q tests/test_context_extraction_golden.py tests/test_context_extraction.py`
  — 62 passed in 25.14 seconds; the same existing warning.
- Ruff on `llm.py`, `context_chunking.py`, and `test_context_attempt_limits.py` — passed.
- Scoped `git diff --check` — passed; Git reported only the existing line-ending conversion notice.
- Both original privacy probes rerun independently in fresh temporary databases — passed,
  with the exact post-fix results above.
- Original same-run restore probe rerun independently with intercepted HTTP — passed; the
  same run stays at 256 and explicit generation 2 starts with its own first attempt.

The new send-limit tests cover all three HTTP adapters, failing and successful keys counted
once, the shared eight-send source/relationship invocation ceiling, durable denial of
attempt 257, first-key allowance/disconnection denial with zero sends, later-key denial
without refunding prior sends, and checkpoint reuse after restart. HTTP was intercepted;
no real provider call was made.

## Other reviewed protections and claim limits

- `partition_messages` preserves original characters and source offsets rather than removing
  the conversation middle. Segment normalization checks evidence against the actual piece;
  checkpoint validation checks message identity, role, timestamp, and exact excerpt again.
- The final extraction transaction rechecks the source fingerprint before persisting a Brief
  and reconciling items. Versioned semantic candidates are revalidated at commit, and the
  regression verifies that a concurrent user correction prevents stale evidence attachment.
- Interrupted source/synthesis work cannot commit a complete Brief. Successful source and
  relationship checkpoints survive retries; a crash after a provider send but before a
  checkpoint may require another attempt and does not promise exactly-once billing.
- The versioned golden fixtures supply expected model responses. They test normalization,
  routing, matching-result validation, persistence, and synthetic flow behavior. They do not
  establish actual prompt-injection resistance, extraction accuracy, semantic judgment,
  useful synthesis, or reduced repeated explanation from a real model. Those claims remain
  subject to the explicitly approved, bounded real-data TASK-012 acceptance.
