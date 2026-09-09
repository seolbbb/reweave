# Privacy and support for the Windows beta

This is an operational guide to the current local/BYOK design. It does not make
legal, certification, browser-store approval, or third-party retention guarantees.
The [Product Spec](../PRODUCT_SPEC.md) is the product contract; [Project Status](../PROJECT_STATUS.md)
records what has actually been verified.

## What stays local and what is handed to a provider

| Action | Data boundary |
| --- | --- |
| Save or import | Selected conversation content and metadata are stored in the local archive. Save reads the whole current conversation only after your click. |
| Connect a provider | Credentials authorize direct requests to your selected BYOK provider, including connection/model discovery. Keys are kept in the operating-system credential store, outside normal Library data and diagnostic exports. |
| Automatic or explicit analysis | The selected source content is sent directly to the configured BYOK provider. Long sources use complete bounded segments and Brief synthesis. Pending work may start after a key is connected. Reweave does not operate an inference service. |
| Relationship verification | A bounded extra analysis stage can send new claims/evidence and eligible existing normal-sensitivity summaries. Existing summaries must belong to the same source or compatible known scopes; every protective named project/destination route must be grounded before cross-source transmission. Unrelated Personal/Core Self/Work summaries are not authorized by a source prompt. |
| Browse, local retrieval, Review | Archive, Context, links, corrections, and evidence remain in the local Library. Optional semantic retrieval uses an available local model. |
| Use Reweave context | The explicit click gives the local app the current chat and draft for retrieval. Allowed Context is inserted into the selected provider's webpage input. Treat inserted text as available to that webpage; Reweave itself never presses Send. Use does not automatically archive the current chat or persist its draft. |
| Sensitive Context in Use | Excluded by default. A separate local preview approves selected item versions for the exact request/destination using short-lived one-use consent. A changed draft, source, item, or scope can invalidate approval. |
| Graph sharing | Only an explicitly selected, redacted preview is exported after confirmation. Inspect the exact labels/output before sharing; do not add private details yourself. Raw source titles and evidence are not part of that sharing flow. |
| Diagnostics | Counts, queue states, limits, and runtime/schema versions are generated locally. Exporting a diagnostic file is explicit; posting it to support is a separate user action. |
| Backup/restore | One password-encrypted local artifact contains sources, derived Context, evidence, history, queue, and settings. Provider keys are excluded, and restored profiles require reconnection. |

**Local-first does not mean analysis stays on the device.** The sensitive-Context
confirmation applies to material supplied by Use; it does not scrub sensitive
content out of a conversation you selected for BYOK analysis. Choose sources and
providers accordingly. Review your provider's own terms and account settings;
these notes do not promise how another service stores or uses received data.

The working Library is a local SQLite database, not an encrypted-at-rest vault.
Encrypted backup files do not encrypt the live archive. Protect the Windows
device and your data/backup locations, and do not put them in a public shared folder.
There is no required Reweave account or current account-backed synchronization
service. Choosing a third-party sync folder for a backup also involves that service.

## Consent and deletion boundaries

Save and Use are separate actions. Opening the extension for availability does not
read chat text. There is no persistent provider-page content script or passive
screen recording. After a Save, the temporary reminder observes structural turn
markers for that page's lifetime and requires another explicit Save to read content.

A supported ChatGPT or Claude URL establishes site identity, not destination
permission. An explicit Private choice permits relevant normal Context across
spaces. Work, Client, Shared, and uncertain destinations require narrower decisions
and allowed scopes. Source instructions cannot grant these permissions. Generic
accuracy confirmation does not resolve a contradiction or authorize sensitive Use.

Pausing analysis, disconnecting/changing a provider, or closing the app stops later
unsent requests. A request already sent may finish. Visible usage estimates and
local allowances are safeguards, not a promise of exact billing or exactly-once
provider charging after an interrupted response.

Removing a conversation leaves its derived Context, compact evidence excerpts,
and source metadata intact. Delete derived data separately in Library management.
Uninstalling the desktop program does not erase Library data, credentials, browser
profiles, or backup copies. Manage each deliberately; deleting the live copy does
not erase copies you previously exported elsewhere.

## Support destinations

Verified on **2026-09-10**: the repository is public and
[GitHub Issues](https://github.com/seolbbb/reweave/issues) is enabled. Use Issues
for reproducible bugs: a concrete action, expected behavior, and observed failure.

GitHub Discussions is the planned place for usage questions, ideas, and broader
feedback, but it is **disabled in this snapshot**. Do not treat it as an available
support form. Owner enablement and categories remain release-preparation work.
No private support inbox, security submission route, or response-time commitment
is established by these documents.

## Report a bug

Use a synthetic conversation or non-private placeholder example whenever possible.
Do not post raw chat exports, Context text, source evidence, databases, encrypted
backups, backup passwords, API keys, session/bridge tokens, browser profiles, or
unredacted request/console/network logs. Screenshots can expose chat titles,
addresses, paths, drafts, and names; crop or redact them before posting.

Diagnostics exported from Settings intentionally omit source/Context text, names,
identifiers, paths, provider addresses, prompts, and credentials. Preview the file
yourself and attach it only if its remaining counts/settings are acceptable to share.
Diagnostics are optional. Never supply a key so someone else can reproduce a failure.

Copy this template into a new Issue:

```text
Title: [Area] Brief description of the reproducible failure

Build: app version and installer filename/hash, if available
Environment: Windows version; Chrome or Edge version; extension version
Area: installation / Save / analysis / Context / Use / backup / other
Provider: provider and model names only, if relevant; no key or account identifier

Steps using a synthetic example:
1.
2.

Expected behavior:
Observed behavior and visible error category:
Does it happen again after restarting the app? yes / no / not checked
Does it affect the archive, derived Context, or only the current draft?
Approximate time and timezone, if useful:
Optional reviewed redacted diagnostics:

I have removed private conversation content, credentials, tokens, and identifying details.
```

If safe reproduction would require private data, report only generic symptoms and
say that a synthetic reproduction is not yet available. Do not put private content
in an Issue or Discussion while waiting for a private reporting route to be defined.
For a suspected disclosure or security defect, stop the affected action and keep
the evidence locally; any initial public report must avoid secrets and sensitive
reproduction details.
