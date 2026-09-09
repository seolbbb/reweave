# Windows beta preparation handoff

Prepared on **2026-09-10**. These are pre-release instructions and decision aids,
not a release announcement, download authorization, or public-readiness claim.

- [Windows beta guide](WINDOWS_BETA_GUIDE.md): installation, browser setup, and the first Save/Use loop.
- [Privacy and support](PRIVACY_AND_SUPPORT.md): local/provider data boundaries and a safe bug-report template.
- [Current implementation and evidence](../PROJECT_STATUS.md): the authoritative moving status.
- [Product contract](../PRODUCT_SPEC.md) and [release roadmap](../ROADMAP.md): acceptance and owner decisions.

## What is prepared

The current delivery path is a per-user Windows installer with an unpacked
Chrome/Edge extension. Native Messaging registration is a separate, explicit
step using the browser's exact extension ID. The installer is unsigned.
No Chrome Web Store or Edge Add-ons publication is claimed by these documents.

Use the [installer instructions](../../packaging/installer/README.md) for the
current build and lifecycle contract, and the [extension instructions](../../extension/README.md)
for browser access and consent behavior. Verify the selected installer against
its own sibling manifest and isolated verification artifact; evidence for an
older build or a synthetic installer does not verify a newly built package.

## Owner decisions and remaining acceptance

| Item | Required outcome before claiming public beta readiness |
| --- | --- |
| Sustained owner dogfooding (TASK-012) | The owner verifies real reuse through Save/Import, approved BYOK analysis, restart, source inspection, correction, and explicit Use. Record outcomes and costs without raw private data. Automated or synthetic tests do not establish usefulness. |
| Public v1 scope freeze (TASK-013) | The owner records which accepted capabilities enter v1 and how later dogfood discoveries are handled. |
| Encrypted synchronization timing (TASK-013) | The owner decides whether to defer sync, use user-managed encrypted backup files, or undertake an account-backed service. Current local backup/restore is not automatic synchronization. |
| Exact Windows build (TASK-014) | Final Python/frontend checks, fresh dual-executable packaging, packaged smoke, and the chosen installer's isolated install/uninstall evidence refer to the same delivered source and assets. See current status for results. |
| Normal installation and browser setup | The owner explicitly exercises normal Windows installation, exact-ID Native Messaging registration, and ordinary Chrome/Edge Save/Use. Isolated lifecycle tests skip real registry/profile changes. |
| Native file saving | Verify actual Windows Save File interaction for backup and graph export. Headless preview or generated-file bytes alone do not establish native dialog behavior. |
| Signing and distribution | The owner chooses a signing identity and publication route, or explicitly accepts an unsigned beta route. No store approval or automatic browser installation is assumed. |
| Support | Keep Issues for reproducible bugs; enable and configure Discussions before advertising it for questions or ideas. Choose a private security-report route before advertising one. |
| Publication | The owner judges the agreed product useful and ready, then separately authorizes distribution/publication. Repository integration is not that decision. |

There is no required external interview cohort or invented numerical release
threshold. The protected scope and sensitive-data boundaries still apply to
every build. Remaining owner choices must be recorded in the canonical product
documents by their owner; this handoff does not resolve them.

## Verified support endpoint snapshot

Read-only GitHub metadata checked on 2026-09-10:

```text
gh repo view seolbbb/reweave --json hasIssuesEnabled,hasDiscussionsEnabled,url
hasIssuesEnabled: true
hasDiscussionsEnabled: false
url: https://github.com/seolbbb/reweave

gh repo view seolbbb/reweave --json isPrivate,url
isPrivate: false
```

[GitHub Issues](https://github.com/seolbbb/reweave/issues) is the verified public
bug-report destination. Discussions is planned but disabled in this snapshot;
these documents do not direct users to an unavailable discussion form. Recheck
these settings before publication. No response-time commitment, private intake,
or external provider-policy guarantee has been established here.
