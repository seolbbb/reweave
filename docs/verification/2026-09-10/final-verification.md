# Reading Room implementation verification

Date: 2026-09-10. Scope: the approved full-product implementation, verified in isolation.
This is not real-owner acceptance, a public release, or completion of the overall Goal.

## Repository checks

- Full Python suite after the scope, send-accounting and encrypted-restore counter fixes:
  **535 passed in 248.85 seconds**. The one warning is the existing Starlette/httpx TestClient
  deprecation warning. Command: `.venv/Scripts/python.exe -m pytest -q`.
- Frontend: **102 tests passed in 12 files**; TypeScript check and Vite production build passed.
  Commands from `frontend/`: `npm test -- --run`, `npx --no-install tsc --noEmit`, `npm run build`.
  The delivered entry bundle is `index-zcjdla7V.js`, with `index-COsppU0X.css` and lazy Graph/Review
  bundles. No frontend change followed that build.
- Ruff passed across `src`, `tests` and `scripts`. Focused counter and restore regressions passed
  independently. After the core full suite, **13 isolated PowerShell helper tests passed in 7.65
  seconds** (`tests/test_native_registration_scripts.py`). This distribution-only helper is not
  an input to the PyInstaller executables. Its final bytes are included in the installer manifest.
  Chrome-only/Edge-only removal preserves the other browser's shared connection file; full removal
  deletes only owned registrations/manifest, while foreign paths and redirected files remain.
  Registry operations were mocked and tripwired; only synthetic files were touched.
- Strict-full document validation passed with zero errors/warnings. The fresh-context
  [handoff reconstruction](handoff-reconstruction.md) passed without implementation-blocking
  ambiguity. These validate continuity, not actual model quality or owner value.

The full-suite logs and PyInstaller log are retained locally in `.pytest_cache/` and contain
synthetic test/build output. Repository evidence deliberately omits owner source content and keys.

## Fresh Windows executables

Command: `.venv/Scripts/pyinstaller.exe --noconfirm --clean packaging/Reweave.spec`.
The clean build completed successfully in approximately 89 seconds after the final Python fix.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `dist/Reweave/Reweave.exe` | 17,783,971 | `5d149f730b67ec00ec8af782d0da06de49a7fb40a432862b4bc86360d8392113` |
| `dist/Reweave/ReweaveNativeHost.exe` | 2,239,744 | `ffb7f4d63813312465604f4d67edb51b1ed2c6a68d2e787d91226f2f0c4dfaf9` |

These supersede the earlier preflight/review builds. Never substitute those earlier hashes for
the delivered executables. PyInstaller emitted a Pydantic-v1/Python-3.14 hook warning; the actual
packaged process and Native Host paths below passed, but this does not exercise every third-party
optional embedding provider. No model was downloaded.

## Actual packaged round-trip

Command:

```powershell
.venv\Scripts\python.exe scripts\verify_packaged_runtime.py --data-dir .pytest_cache\packaged-2026-09-10-final --report docs\verification\2026-09-10\packaged-runtime-final.json
```

The real two executables passed authenticated/framed Native Messaging Save; durable no-key queue;
one actual HTTP request to an isolated loopback synthetic provider; complete one-segment analysis;
exact user-source evidence; explicit destination selection and insertion-ready Use; process
shutdown/restart; persistent source, item and destination; repeated unchanged Save; and runtime
descriptor cleanup. The synthetic draft sentinel was not stored. Test processes exited normally.

Machine-readable evidence: [packaged-runtime-final.json](packaged-runtime-final.json).
This proves the package/bridge contract; it does not prove current signed-in provider DOM behavior,
physical insertion in the owner's browser, or useful real-model output.

## Browser and independent review evidence

- [Browser QA](browser-qa-report.md) uses real local HTTP, synthetic records and an isolated
  headless browser. It includes correction conflict/draft preservation, save/undo, space rename/
  merge, bidirectional sources, Review, canonical Graph, sharing redaction, encrypted restore
  and diagnostics. The keyboard source-drawer return-focus defect was fixed and rechecked.
- [Current 1280x720 Home](browser-qa-home-1280-after.png) and
  [current 375x812 Home](browser-qa-home-375-after.png) implement A with shared semantic tokens,
  offline fonts and actual data. The original approved [baseline](../../design/reading-room/baseline-home.png)
  remains available for comparison; source-derived dates reflect each capture date.
- [Extraction review](extraction-code-review.md) and [integration review](integration-code-review.md)
  record reproduced findings, fixes and independent rechecks. No confirmed P1/P2 finding remains
  in those bounded reviews. Golden fixtures test software contracts against supplied responses;
  they do not establish real prompt-injection resistance, synthesis quality or retrieval value.

## Installation and delivery boundary

[Installer verification](installer-verification.md) separates the actual final product installer
from the earlier synthetic compiler/lifecycle probe. The per-user installer and sibling manifest
live under `dist/`. The manifest identifies every embedded file. Isolated install/uninstall
verification does not perform normal-profile registration, create shortcuts or start a UI.
The 50,343,040-byte final installer passed installation, all 720 installed file hashes,
uninstall completion and unrelated-file preservation. SHA-256:
`8a96ee9131788f5b8820ae3f3e6743c32060659cc2cf11d783c42acc15777a57`.

Git delivery follows English functional commits, a PR to `dev`, observed checks, merge commits
into `dev` and then `main`, and fresh local/remote tip observation. Exact final repository tips
are reported with the handoff rather than guessing a self-referential commit ID in this document.
No store upload, public announcement, signing identity or external deployment was authorized.

## Remaining mandatory acceptance

All seventeen scenarios map to [the acceptance matrix](acceptance-matrix.md). TASK-012 and
[the prepared owner round-trip](owner-acceptance.md) remain mandatory:

- Selected real source, approved provider/model/data/call/cost/stop bounds, faithful analysis,
  restart, source inspection and explicit draft-preserving Use; the owner judges reduced repetition.
- A useful non-obvious graph relationship, native backup/PNG/diagnostic file saving, actual 200%
  native zoom, normal installation and current browser-account Save/Use.
- Sustained-use corrections and the owner's later public scope/synchronization/distribution choices.

Headless downloads were canceled even for an independent control, so Blob/PNG bytes are not
claimed as download completion. Equivalent 640x360 reflow passed; ignored headless zoom shortcuts
are not called a native zoom test. Native downloads are enabled in the launcher and its mocked
contract passed, but no owner window was opened.

Across this execution: **zero paid provider calls**, zero owner-data transmissions, no owner
archive inspection, no real keyring/Native Messaging registration, no physical input/clipboard,
and no owner application termination. These boundaries remain in force at handoff.
