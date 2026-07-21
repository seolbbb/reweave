# Reweave browser extension

This Manifest V3 extension checks whether the local Reweave desktop app is available through
the browser's Native Messaging boundary and supports explicit whole-conversation Save from
ChatGPT and Claude. It has no persistent provider host permissions or content scripts. `activeTab` and
`scripting` grant temporary access only after the user opens the extension and clicks Save;
the popup's availability check never reads the provider page.

For a local unpacked test:

1. Load this directory from `chrome://extensions` or `edge://extensions` with Developer mode.
2. Copy the extension ID shown by the browser.
3. Build the Windows package with `packaging/Reweave.spec`.
4. Run `scripts/register_native_host.ps1 -ExtensionId <id>`.
5. Start `dist/Reweave/Reweave.exe`, open a ChatGPT or Claude conversation, open the extension popup,
   and choose **Save current conversation**.

On Windows, `Alt+Shift+R` opens the same action popup for keyboard-only use. Browser extension
shortcut settings can remap or clear it.

The popup reports whether the conversation was created, updated, or already unchanged. Invalid,
incomplete, unsupported, unavailable, and oversized captures do not partially write the archive.
Reminders and Use Reweave remain later TASK-002 work.

Run `scripts/unregister_native_host.ps1` after a temporary development registration.
