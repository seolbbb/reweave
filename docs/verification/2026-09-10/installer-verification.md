# Windows installer verification

## Scope and decision

The installer is a per-user application distribution artifact. NSIS supplies
the executable container and UI; a bounded PowerShell lifecycle validates exact
file ownership and every destination before installation/removal. Isolated QA
skips all registry/shortcut code and permits only explicit workspace cache
targets. It never launches the application or touches a real archive or keyring.

Compiler provenance is recorded in `installer-provenance.md`. This record
separates synthetic lifecycle/compiler evidence from final product-bundle proof.

## Focused verification

Commands, run from the repository root on 2026-09-10:

```powershell
.venv\Scripts\ruff.exe check scripts\build_windows_installer.py tests\test_windows_installer.py
.venv\Scripts\python.exe -m pytest tests\test_windows_installer.py -q
```

Observed: Ruff passed; **35 tests passed in 19.77 seconds**. The only warning was
the existing Starlette/httpx TestClient deprecation warning. Tests used synthetic
files in workspace `.pytest_cache/installer-tests/` and did not use any external
network, real provider, application database, registry mutation, or visible UI.

The tests exercise exact file hashes, modified/unrelated-file preservation,
update replacement/removal, unmarked-directory refusal, overwrite collisions,
corrupt payloads, invalid manifest paths, malformed root aliases, marker/mode
mismatches, real Windows junction rejection, and isolated command tripwires that
throw if registry/shortcut creation is reached.

## Synthetic compiled executable

```powershell
.venv\Scripts\python.exe scripts\build_windows_installer.py --bundle-root .pytest_cache\installer-synthetic-bundle --output .pytest_cache\Reweave-Synthetic-Setup.exe --version 0.1.0-test
.venv\Scripts\python.exe scripts\build_windows_installer.py --verify-isolated --output .pytest_cache\Reweave-Synthetic-Setup.exe
```

The synthetic bundle's two application EXE files contain inert test bytes and
were never executed. Its installer and generated uninstaller are actual NSIS
executables. Final observed synthetic result:

| Check | Result |
| --- | --- |
| Installer SHA-256 | `16196ea98eef85e5a234a30e02cfade7159045353811de8a2039e0e04a038d37` |
| Installer size | 113,703 bytes |
| Installed file hashes verified | 17 |
| Silent isolated installation exit | 0 |
| Silent isolated uninstaller launcher exit | 0 |
| All owned files removed | Yes |
| Unrelated synthetic sentinel retained | Yes |
| Application started | No |

Machine-readable artifacts are the synthetic installer's sibling
`.manifest.json` and `.verification.json` files under ignored `.pytest_cache/`.
An earlier synthetic pass also verified a target directory containing spaces.

## Final product installer

The final product bundle was built and tested on 2026-09-10 with the exact
executables identified in [final-verification.md](final-verification.md). Commands:

```powershell
.venv\Scripts\python.exe scripts\build_windows_installer.py
.venv\Scripts\python.exe scripts\build_windows_installer.py --verify-isolated
```

The resulting artifacts are `dist/Reweave-Setup.exe`, its complete sibling
`.manifest.json`, and its isolated `.verification.json`. The installer embeds both
application executables, runtime/web assets, the extension, explicit Native
Messaging registration/unregistration scripts, installation instructions, and
license.

| Final product check | Observed result |
| --- | --- |
| Installer SHA-256 | `8a96ee9131788f5b8820ae3f3e6743c32060659cc2cf11d783c42acc15777a57` |
| Installer size | 50,343,040 bytes |
| Input payload | 719 files; 165,713,112 bytes |
| Installed file hashes verified | 720, including the generated uninstaller |
| Silent isolated installation exit | 0 |
| Silent isolated uninstaller launcher exit | 0 |
| All owned files removed | Yes |
| Unrelated synthetic sentinel retained | Yes |
| Application started by installer | No |

The verifier waited for the uninstaller child and required exactly the unrelated
sentinel to remain. Evidence: [installer-final.json](installer-final.json).
The final helper also passed 13 isolated PowerShell tests for partial-browser
unregistration, exact key ownership and foreign-manifest preservation; no real
browser registration was changed.

Normal profile installation, visible installer screens, browser registration,
code signing, store distribution, and public publication were not exercised.
