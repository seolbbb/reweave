# Reweave browser extension scaffold

This Manifest V3 scaffold checks whether the local Reweave desktop app is available through
the browser's Native Messaging boundary. It intentionally has no provider host permissions,
content scripts, or page-reading code. ChatGPT and Claude adapters and the explicit Save and
Use actions belong to later TASK-002 slices.

For a local unpacked test:

1. Load this directory from `chrome://extensions` or `edge://extensions` with Developer mode.
2. Copy the extension ID shown by the browser.
3. Build the Windows package with `packaging/Reweave.spec`.
4. Run `scripts/register_native_host.ps1 -ExtensionId <id>`.
5. Start `dist/Reweave/Reweave.exe`, open the extension popup, and retry the connection.

Run `scripts/unregister_native_host.ps1` after a temporary development registration.
