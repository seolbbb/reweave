# Windows installer compiler provenance

Observed on 2026-09-10. No global compiler installation, administrator action,
registry write, browser profile mutation, or application launch was performed.

## Publisher and byte verification

The [official NSIS download page](https://nsis.sourceforge.io/Download) identifies
NSIS 3.12, released on 2026-04-19. Its publisher-hosted
[SourceForge release directory](https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/)
lists the portable `nsis-3.12.zip` archive. The directory's `net.sf.files` metadata
publishes SHA-1 `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1` for that file and a null
SHA-256 value. A publisher-provided SHA-256 or signature was not observed.

The archive was downloaded over HTTPS through SourceForge's official download
URL and its selected `twds.dl.sourceforge.net` mirror. Its SHA-1 matched the
publisher metadata before any compiler execution. The downloaded bytes were then
pinned as follows:

| Property | Observed value |
| --- | --- |
| Archive | `nsis-3.12.zip` |
| Bytes | 2,362,938 |
| SHA-256 | `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f` |
| SHA-1 | `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1` |
| Compiler `/NOCONFIG /VERSION` | `v3.12` |
| Location | Workspace `.pytest_cache/installer-toolchain/` only |

`packaging/installer/toolchain.json` records this pin and provenance. The builder
checks size and SHA-256 before each extraction/execution, rejects archive path
traversal and links, rejects unexpected cached compiler files, and extracts the
trusted archive's compiler/includes/plugins again before use. It invokes
`makensis.exe` with `/NOCONFIG` and no visible process window.

This is a pinned HTTPS/publisher-metadata verification, not a claim that the
compiler or generated installer has a verified code-signing signature.

## Installation boundary

Normal installation is fixed to the current user's
`%LOCALAPPDATA%\Programs\Reweave`. It creates only its own application files,
Windows Installed Apps entry, and optional new Start menu shortcut. There is no
elevation, automatic launch, startup entry, or automatic Native Messaging
registration. Native Messaging registration is a separate explicit command
requiring the actual browser extension ID.

The installer refuses unmarked nonempty targets. A versioned marker and exact
relative-file SHA-256 manifest define file ownership. Existing modified owned
files, unrelated overwrite collisions, unsafe paths, and reparse points stop an
update before target file mutation. Removal validates the entire manifest first,
removes only matching owned files, retains changed/unrelated files, and prunes
only empty directories without recursive deletion. It does not access the
archive data directory or provider credential store.

`/ISOLATED` accepts only a strict descendant of an explicitly supplied workspace's
`.pytest_cache`. It skips all registry and shortcut code. The same mode and
workspace must be supplied to its uninstaller. Automatic verification uses this
mode exclusively.

## Evidence and limits

The focused lifecycle tests execute Windows PowerShell against synthetic files.
They cover path traversal/alias rejection, exact ownership, preflight rejection,
hash corruption, modified/unrelated files, update collisions, malformed removal
manifests, mode/marker mismatches, real junction rejection, and command tripwires
that fail if isolated mode reaches registry or shortcut operations.

A synthetic compiled NSIS executable was silently installed and uninstalled at a
workspace `.pytest_cache` path containing spaces. Installation returned 0; its
marker retained `isolated=1` and the exact intended path. Removal returned 0 and
left only the unrelated synthetic sentinel. No synthetic application executable
was launched.

The final PyInstaller payload and installer verification are recorded separately
in `installer-verification.md` when available. The compiler and synthetic
installer proof do not establish that a final product bundle has been built.

Normal registry/shortcut integration and visible installer UI have not been run
against the owner's Windows profile. Installer upgrades do not offer a database-
style transaction across all program file writes; an OS interruption can leave
a partial program installation, while separately stored user data is retained.
Bit-for-bit installer reproducibility, code signing, public publication, and
store acceptance are not claimed.
