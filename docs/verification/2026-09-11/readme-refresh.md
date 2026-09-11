# Bilingual README refresh verification

Date: 2026-09-11 KST. Scope: reader documentation and corresponding canonical records.
Application source, frontend assets, extension permissions, and product acceptance are unchanged.

## Reference research and editorial choices

The owner requested welcoming, current English and Korean READMEs, then explicitly asked
to learn from real repositories with substantial GitHub stars. The following repositories
and their actual READMEs were read; counts are GitHub REST snapshots from this date, not
claims that popularity proves documentation quality.

| Reference | Stars at inspection | Relevant pattern used |
| --- | --- | --- |
| [Open WebUI](https://github.com/open-webui/open-webui/blob/main/README.md) | 151,571 | Short product explanation, visible product screenshot, grouped features, runnable installation instructions and troubleshooting. |
| [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm/blob/master/README.md) | 65,895 | Prominent language navigation, product overview, separate user/developer setup and explicit privacy information. |
| [Logseq](https://github.com/logseq/logseq/blob/master/README.md) | 44,861 | Explain why the product exists, orient new readers, and link deeper documentation and contribution guidance. |
| [Khoj](https://github.com/khoj-ai/khoj/blob/master/README.md) | 37,259 | Plain introduction, concrete capabilities, getting-started links and beginner FAQ. |

Reweave's copy is original. It does not borrow their feature, adoption, licensing, platform,
performance, hosted-service or release claims. The repository had zero published GitHub
releases at inspection, so the README leads with source installation and local packaging.
Issues was enabled; Discussions was disabled. The two screenshot files are already tracked
2026-09-10 captures from actual isolated browser QA with synthetic data, visually inspected
again for this refresh. They are not generated mockups or new owner-acceptance evidence.

`README.md` and `README.ko.md` share structure, commands, images, supported capabilities,
data boundaries and remaining limits. UI labels remain recognizable in the Korean version.
Detailed CLI/configuration/API material moves to `docs/DEVELOPMENT.md`. DEC-031 records
the explicit owner language exception without modifying protected AGENTS.md text.

## Fresh checks

| Check | Result |
| --- | --- |
| `uv sync --locked` | Passed against the committed lockfile. |
| `npm ci` | Dependency installation is documented from the existing lockfile; it was not rerun over the already installed frontend dependencies. |
| Markdown audit | All three reader documents parsed successfully; relative files and heading anchors resolved, all 10 image elements had descriptions, and the four PowerShell blocks matched between languages. The scanner visited 77 links/image references; external destinations were not treated as locally validated files. |
| CLI examples | 12 invocations passed: root and eight command help screens, then fixture import, keyword search and stats in a new isolated Library. No provider call or model download. |
| CLI/parser/registration/runtime tests | `pytest tests/test_cli.py tests/test_parsers.py tests/test_native_registration_scripts.py tests/test_runtime_isolation.py -q`: 65 passed, one existing Starlette deprecation warning. |
| Frontend tests | `npm test`: 12 files, 102 tests passed. |
| Python lint | `ruff check src/ tests/`: passed. |
| Frontend production build | `npm run build` from `D:\Projects\Reweave\frontend`: TypeScript and Vite passed; generated tracked assets are unchanged. |
| Clean Windows bundle | `.venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\Reweave.spec`: passed. |
| Packaged functional smoke | Existing `scripts/verify_packaged_runtime.py`: passed; exact results in [packaged report](packaged-readme-smoke.json). |
| Canonical documentation | Installed `manage-project-intent` validator with `--strict full`: passed, zero errors and warnings; TASK-012 remains the only Next task. |
| Patch hygiene | `git diff --check`: passed; AGENTS.md and tracked generated frontend assets are unchanged. |

An initial Vite build from the C: alias failed because Rollup received an absolute
`D:/Projects/Reweave/frontend/index.html` asset name. The same build from the physical
D: checkout succeeded. No product change was needed; the development guide documents
the path-alias constraint.

The fresh bundle contains:

| Executable | Bytes | SHA-256 |
| --- | --- | --- |
| `Reweave.exe` | 17,783,971 | `1deedc8106adca234879ccd9b06a84e7bcb742cd92174fec32c6dd9f5d2d9154` |
| `ReweaveNativeHost.exe` | 2,239,744 | `d4cd82f90cb9b05b207290e80791728a0a04262baa338569b697ea6d1c0dfee6` |

The packaged smoke used a new ignored directory, hidden owned processes, memory-only
credentials and one loopback fake-provider request. Save, no-key queueing, analysis,
exact source evidence, explicit destination-aware Use, unchanged transient draft,
restart persistence, repeated-Save idempotence and descriptor cleanup passed.
Paid provider calls: zero. No owner database, native window, real browser profile,
clipboard, registry registration or embedding-model download was used.

## Acceptance boundary

This is documentation delivery. It does not publish an installer, enable support
services, change the application language, or close any real-owner usefulness/native
acceptance gate. TASK-012 remains the single Next task, and TASK-014 remains open for
its separate public-release requirements. The repository delivery uses a feature PR
to `dev`, a merge commit, then a verified `dev` merge commit into `main`.
