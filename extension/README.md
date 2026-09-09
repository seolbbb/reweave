# Reweave browser extension

This Manifest V3 extension checks whether the local Reweave desktop app is available through
the browser's Native Messaging boundary and supports explicit whole-conversation Save plus
draft-only Context use from ChatGPT and Claude. It has no persistent provider host permissions or
content scripts. `activeTab` and `scripting` grant temporary access only after the user opens the
extension and clicks Save or Use Reweave; the popup's availability check never reads the provider
page.

Use Reweave reads the complete current conversation and non-empty draft only after
the click. A supported signed-in URL establishes provider identity. On first use,
confirm the destination: private chats may use relevant normal-sensitivity Context
across spaces; Work, Client, Shared and unknown destinations require an explicit
scope allowlist. Destination corrections are remembered for that provider conversation.

Sensitive material stays local unless a separate preview and one-use confirmation
approve exact current item versions for the current request. Changed drafts, scope
revisions or item versions invalidate consent. Unresolved contradictions remain
excluded. The popup explains used and excluded Context without storing the chat or draft.

The bounded `<reweave_context>` block is added before the unchanged draft. A later
explicit Use replaces it instead of duplicating it, and a concurrent draft edit prevents
insertion. Use never submits, saves or refreshes automatically. Shared URLs, streaming,
incomplete, empty, oversized and changed provider pages fail closed.

After a successful Save, the injected adapter remains active only for that page lifetime. It observes
structural turn and role markers rather than message text. When at least one new complete assistant
response has been present for 30 seconds without page activity, Reweave shows a non-blocking prompt
and a per-tab `SAVE` badge. The prompt auto-hides after 8 seconds while the badge remains. **Not now**
suppresses the reminder until another complete assistant response appears; **Save to Reweave** reads
and sends the whole conversation again as a new explicit action.

Reminder baselines, dismissal, and pending state are memory-only. Reweave does not use extension
storage, static content scripts, or persistent provider access. Navigation, changed provider markup,
browser restart, and uncertain streaming state stop or defer the reminder without saving anything.

For a local unpacked test:

1. Load this directory from `chrome://extensions` or `edge://extensions` with Developer mode.
2. Copy the extension ID shown by the browser.
3. Build the Windows package with `packaging/Reweave.spec`.
4. Run `scripts/register_native_host.ps1 -ExtensionId <id>`.
5. Start `dist/Reweave/Reweave.exe`, open a ChatGPT or Claude conversation, open the extension popup,
   and choose **Use Reweave context** or **Save current conversation**.

On Windows, `Alt+Shift+R` opens the same action popup for keyboard-only use. Browser extension
shortcut settings can remap or clear it.

The popup reports whether the conversation was created, updated, or already unchanged. Invalid,
incomplete, unsupported, unavailable, and oversized captures do not partially write the archive.
If the desktop app is unavailable during Save, reminder Save, or Use, the action remains retryable and
the archive and draft are unchanged.

Run `scripts/unregister_native_host.ps1` after a temporary development registration.
