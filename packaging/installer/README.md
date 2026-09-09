# Windows installation

The installer installs for the current Windows user in
`%LOCALAPPDATA%\Programs\Reweave`. It does not request administrator access,
start Reweave, enable automatic startup, register a browser extension, or change
provider credentials. Start Reweave from its Start menu shortcut when ready.

The package includes `Reweave.exe`, `ReweaveNativeHost.exe`, their Python runtime
and web assets, the unpacked browser extension, Native Messaging registration
scripts, and the license. Reweave's archive/settings directory is separate at
`%LOCALAPPDATA%\Reweave` unless an explicit `REWEAVE_DATA_DIR` is configured.

## Browser extension: an explicit second step

1. Open `chrome://extensions` or `edge://extensions` and enable Developer mode.
2. Choose **Load unpacked** and select the installed `extension` directory.
3. Copy the extension ID displayed by that browser.
4. In PowerShell, run the installed registration script with that exact ID and
   the installed Native Host path (replace the ID and browser below):

```powershell
$install = Join-Path $env:LOCALAPPDATA 'Programs\Reweave'
& (Join-Path $install 'scripts\register_native_host.ps1') `
  -ExtensionId 'YOUR_32_CHARACTER_EXTENSION_ID' -Browser Chrome `
  -HostPath (Join-Path $install 'ReweaveNativeHost.exe')
```

Registration writes the current user's browser Native Messaging registration.
It is never performed by the installer. The bridge uses authenticated local
Native Messaging; the extension does not need a pasted local URL or session
token. Use the extension's visible consent controls for any transfer of context.

Before uninstalling, remove the unpacked extension and, if you registered it,
run `scripts\unregister_native_host.ps1 -Browser Chrome` (or `Edge`/`Both`).
The uninstaller does not silently change browser registration.

## Updates and removal

Close Reweave before updating or uninstalling. An update verifies the previous
installation marker and exact owned-file manifest. It stops before copying if
the directory contains unmarked files that would be overwritten, if an owned
file was modified, or if a path uses a junction or symbolic link.

Use Windows **Installed apps → Reweave → Uninstall**, or `Uninstall.exe`.
Only manifest-listed files whose hashes still match are removed. Modified files
and unrelated files remain. The uninstaller never recursively removes the
installation folder, archive data, provider credentials, or browser profile.
Keep an encrypted backup separately before deleting data inside the app.

An interrupted filesystem write can leave a partial program installation;
user data is stored separately. The installer does not promise a transactional
upgrade. Keep the previous installer and do not manually overwrite modified
files without checking them.

## Repeating the build

First build and verify `packaging\Reweave.spec`. Then, from the repository root:

```powershell
.venv\Scripts\python.exe scripts\build_windows_installer.py --prepare-toolchain
.venv\Scripts\python.exe scripts\build_windows_installer.py
.venv\Scripts\python.exe scripts\build_windows_installer.py --verify-isolated
```

The script downloads the pinned portable NSIS compiler only into the workspace's
ignored `.pytest_cache\installer-toolchain` directory. It checks the archive's
size and SHA-256 before extracting or executing it. The output defaults to
`dist\Reweave-Setup.exe` with a sibling `.manifest.json` containing the installer
hash and every packaged file hash. This provides a repeatable build recipe and
bundle provenance; bit-for-bit reproducibility is not claimed.

## Isolated automated verification

Use `/S /ISOLATED /WORKSPACE=<absolute workspace> /D=<workspace>\.pytest_cache\<test directory>`.
`/D=` must be the final argument. The isolated mode rejects every installation
target outside the explicitly named workspace's `.pytest_cache` directory and
skips all registry and shortcut operations. Use the same `/ISOLATED` and
`/WORKSPACE=` options when running its uninstaller. Automated verification must
never execute a normal installation against an owner's Windows profile.
The builder's `--verify-isolated` option runs the existing output executable,
checks every installed file hash, uninstalls it, and verifies an unrelated
synthetic sentinel remains. It writes a sibling `.verification.json` artifact.

The current executable is not code-signed. Public distribution, a signing
identity, and any store publication require the owner's separate release choice.
