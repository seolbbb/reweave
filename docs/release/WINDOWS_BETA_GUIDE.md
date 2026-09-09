# Windows local beta guide

This guide is for an owner-approved local build. It does not identify a published
release or authorize downloading an installer from an unverified third party.
See [beta preparation status](README.md) and [privacy and support](PRIVACY_AND_SUPPORT.md).

## Install the desktop app

Use the installer supplied with the exact reviewed build. The default build
artifact is `dist\Reweave-Setup.exe`; its sibling manifest records its SHA-256
and bundled-file hashes. The current installer is **not code-signed**. If the
origin or integrity of a file is uncertain, stop and obtain the verified build;
this guide does not instruct you to bypass Windows security controls.

The installer places program files in `%LOCALAPPDATA%\Programs\Reweave` for the
current Windows user. It does not request administrator access, launch Reweave,
enable startup, connect an API key, or register a browser extension. Start the
app from its Start menu shortcut when ready.

The archive and settings normally live separately in `%LOCALAPPDATA%\Reweave`.
An explicitly configured `REWEAVE_DATA_DIR` changes that data location. Keep
your chosen data location consistent when starting the app and registering the
browser bridge. Working Library files are local data, not encrypted backups.

## Connect Chrome or Edge explicitly

1. Open `chrome://extensions` or `edge://extensions` and enable Developer mode.
2. Choose **Load unpacked** and select
   `%LOCALAPPDATA%\Programs\Reweave\extension`.
3. Copy that browser's displayed 32-character extension ID.
4. Run the installed registration script in PowerShell with the exact ID:

```powershell
$install = Join-Path $env:LOCALAPPDATA 'Programs\Reweave'
& (Join-Path $install 'scripts\register_native_host.ps1') `
  -ExtensionId 'YOUR_32_CHARACTER_EXTENSION_ID' -Browser Chrome `
  -HostPath (Join-Path $install 'ReweaveNativeHost.exe')
```

Choose `-Browser Edge` for Edge. If using both browsers with different extension
IDs, register both exact IDs together because the script writes one shared
allowlist manifest:

```powershell
& (Join-Path $install 'scripts\register_native_host.ps1') `
  -ExtensionId @('YOUR_CHROME_EXTENSION_ID', 'YOUR_EDGE_EXTENSION_ID') -Browser Both `
  -HostPath (Join-Path $install 'ReweaveNativeHost.exe')
```

Replace every placeholder before running a command. Registration changes only
the current user's selected browser Native Messaging registration; the installer
does not run it for you. Do not paste an app session token, API key, or local URL
into the extension. Start Reweave and open the extension popup to check availability.
`Alt+Shift+R` opens the same popup; browser shortcut settings can change it.

This is an unpacked-extension workflow, not a Chrome Web Store or Edge Add-ons
installation. Supported chat sites are ChatGPT and Claude.

## Complete one Save and Use loop

1. Start with a conversation you intentionally want in your Library. Export
   backfill is optional; you can begin with a new browser conversation.
2. In a complete ChatGPT or Claude conversation, open the extension and choose
   **Save current conversation**. This reads and saves the whole current chat
   locally. The popup reports created, updated, or unchanged.
3. Without an API key, saved sources remain available and analysis waits. When
   you connect a BYOK provider, pending analysis may start automatically. Review
   the [transmission boundaries](PRIVACY_AND_SUPPORT.md) before connecting it.
4. Inspect the Conversation Brief, Context Items, and their source evidence.
   Zero extracted items can be a valid result. Check inferred claims and correct
   mistaken content or scope; a correction retains version history and undo.
5. Write a non-empty request in a ChatGPT or Claude chat, then choose
   **Use Reweave context**. On first use, explicitly choose the destination.
   Private permits relevant normal-sensitivity context across spaces; Work,
   Client, and Shared require selected allowed scopes. Unknown destinations wait
   for your choice. A supported site URL alone never grants private access.
6. After saving a destination choice, retry Use explicitly. Reweave remembers
   that provider conversation's choice. Sensitive Context needs a separate local
   preview, selection, and short-lived one-use confirmation for this request.
7. Inspect the context added before your draft. Reweave does not submit it.
   A changed draft prevents insertion. A later explicit Use replaces the prior
   Reweave block rather than duplicating it.

Use does not save the current chat. Save it separately when appropriate. After
an explicit Save, a page-lifetime reminder may offer another Save when a new
assistant response is complete and the page is quiet. A reminder never saves
conversation text by itself.

## If something stops

| What you see | Local next step |
| --- | --- |
| Desktop unavailable | Start Reweave; confirm the installed Native Host path, selected browser, and exact extension ID. Retry the explicit action. |
| Streaming, incomplete, unsupported, or changed page | Wait for completion and reopen the popup on the intended supported conversation. Do not force a partial capture. |
| Analysis pending | Check the saved provider connection, analysis pause, visible allowance, and next retry time. A saved source is not lost when analysis waits. |
| Analysis partial | Completed source segments remain checkpointed. Retry when the app allows it; a hard limit is an explicit stop, not a completed Brief. |
| Destination or consent changed | Review the current destination/scopes or sensitive preview, then retry. Old approval does not authorize a changed request. |
| Draft changed or no relevant allowed Context | Keep the draft; inspect the explanation and correct relevant Context locally if needed. The app should not force unrelated material into it. |
| Library busy | Close the other Reweave app/CLI owner and allow in-flight work to finish. Do not run competing writers against the same Library. |

For reproducible failures, use the [safe report template](PRIVACY_AND_SUPPORT.md#report-a-bug).

## Backup, updates, and removal

Create a password-encrypted `.reweave` backup from Settings and keep it in a
location you control. It contains private Library data even though the file is
encrypted; do not attach it to a support issue. Restore replaces local Library
state, validates the backup, and disconnects restored provider profiles. Reconnect
a provider deliberately when you want analysis to resume.

Close Reweave before updating or uninstalling. The installer checks its owned-file
manifest and can refuse a modified or unmarked installation. Keep the previous
installer; interrupted program-file replacement is not promised to be transactional.

Before uninstalling, remove the unpacked browser extension and explicitly unregister
the bridge if you registered it:

```powershell
$install = Join-Path $env:LOCALAPPDATA 'Programs\Reweave'
& (Join-Path $install 'scripts\unregister_native_host.ps1') -Browser Both
```

For full removal, `Both` clears owned browser registrations and the owned shared
manifest. To disconnect only Chrome or Edge, select that browser instead: the
shared manifest remains while the other browser still references it. Registrations
pointing elsewhere and unrecognized or foreign manifests are preserved.
Then use Windows **Installed apps → Reweave
→ Uninstall**. Uninstall removes unchanged owned program files; it preserves
modified/unrelated files, Library data, provider credentials, and browser profiles.
Use the app's separate source, derived-Library, and provider controls when you want
to remove those records. Removing a source does not remove its derived Context or
retained evidence excerpts.
