import { useRef, useState } from "react";
import {
  ArchiveRestore,
  Download,
  Eye,
  EyeOff,
  FileUp,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import "./backupManager.css";

export const MAX_BACKUP_FILE_BYTES = 2 * 1024 ** 3;
export const MIN_BACKUP_PASSWORD_LENGTH = 12;

export type BackupPreview = {
  conversations: number;
  messages: number;
  briefs: number;
  context_items: number;
  versions: number;
  links: number;
  profiles: number;
  created_at: string;
  database_bytes: number;
  requires_reconnect: boolean;
  notice: string;
};

export type RestoreResult = {
  preview: BackupPreview;
  requires_reconnect: boolean;
  notice: string;
  recovery_pending: boolean;
};

export function validBackupPassword(password: string) {
  return Array.from(password).length >= MIN_BACKUP_PASSWORD_LENGTH;
}

export function backupFileProblem(file: Pick<File, "name" | "size"> | null) {
  if (!file) return "Choose an encrypted .reweave backup.";
  if (!file.name.toLowerCase().endsWith(".reweave"))
    return "Choose a .reweave backup file.";
  if (file.size > MAX_BACKUP_FILE_BYTES)
    return "This file exceeds the 2 GiB restore limit.";
  if (file.size === 0)
    return "This backup file is empty. Choose another backup.";
  return "";
}

type OperationError = { message: string; busy: boolean };

export function BackupManager({
  onRestored,
}: {
  onRestored?: (result: RestoreResult) => void | Promise<void>;
}) {
  const [backupPassword, setBackupPassword] = useState("");
  const [backupPasswordAgain, setBackupPasswordAgain] = useState("");
  const [showBackupPassword, setShowBackupPassword] = useState(false);
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupError, setBackupError] = useState<OperationError | null>(null);
  const [backupNotice, setBackupNotice] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [restorePassword, setRestorePassword] = useState("");
  const [showRestorePassword, setShowRestorePassword] = useState(false);
  const [preview, setPreview] = useState<BackupPreview | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [restoreBusy, setRestoreBusy] = useState<"preview" | "restore" | null>(
    null,
  );
  const [restoreError, setRestoreError] = useState<OperationError | null>(null);
  const [restoreNotice, setRestoreNotice] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const restorePasswordInput = useRef<HTMLInputElement>(null);
  const working = backupBusy || restoreBusy !== null;
  const fileProblem = file ? backupFileProblem(file) : "";
  const backupReady =
    validBackupPassword(backupPassword) &&
    backupPassword === backupPasswordAgain;
  const previewReady =
    file !== null &&
    !backupFileProblem(file) &&
    validBackupPassword(restorePassword);

  function clearPreview() {
    setPreview(null);
    setConfirmation("");
    setRestoreError(null);
    setRestoreNotice("");
  }

  function cancelRestore() {
    setFile(null);
    setRestorePassword("");
    setShowRestorePassword(false);
    clearPreview();
    if (fileInput.current) fileInput.current.value = "";
    fileInput.current?.focus();
  }

  async function downloadBackup() {
    if (!backupReady || working) return;
    setBackupBusy(true);
    setBackupError(null);
    setBackupNotice("");
    let objectUrl: string | null = null;
    let anchor: HTMLAnchorElement | null = null;
    try {
      const response = await fetch("/api/archive/encrypted-backup", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: backupPassword }),
      });
      if (!response.ok) throw operationFailure(response.status, "backup");
      const archive = await response.blob();
      objectUrl = URL.createObjectURL(archive);
      anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `Reweave-backup-${new Date().toISOString().slice(0, 10)}.reweave`;
      document.body.append(anchor);
      anchor.click();
      setBackupPassword("");
      setBackupPasswordAgain("");
      setShowBackupPassword(false);
      setBackupNotice(
        "Encrypted backup prepared for download. Keep its password somewhere safe; Reweave cannot recover it.",
      );
    } catch (reason) {
      setBackupError(
        normalizeFailure(
          reason,
          "The backup could not be created. Your library is unchanged. Try again when Reweave is available.",
        ),
      );
    } finally {
      anchor?.remove();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setBackupBusy(false);
    }
  }

  function restoreForm() {
    const form = new FormData();
    if (file) form.append("file", file);
    form.append("password", restorePassword);
    return form;
  }

  async function previewRestore() {
    if (!previewReady || working) return;
    setRestoreBusy("preview");
    setRestoreError(null);
    setRestoreNotice("");
    setPreview(null);
    setConfirmation("");
    try {
      const response = await fetch("/api/archive/encrypted-restore/preview", {
        method: "POST",
        credentials: "same-origin",
        body: restoreForm(),
      });
      if (!response.ok) throw operationFailure(response.status, "preview");
      const result = (await response.json()) as { preview: BackupPreview };
      if (!result.preview || typeof result.preview.conversations !== "number")
        throw new Error("Invalid backup preview");
      setPreview(result.preview);
      window.requestAnimationFrame(() => previewHeading.current?.focus());
    } catch (reason) {
      setRestoreError(
        normalizeFailure(
          reason,
          "This backup could not be previewed. Your current library is unchanged. Check the file and password, then try again.",
        ),
      );
    } finally {
      setRestoreBusy(null);
    }
  }

  async function restore() {
    if (!preview || !previewReady || confirmation !== "RESTORE" || working)
      return;
    setRestoreBusy("restore");
    setRestoreError(null);
    setRestoreNotice("");
    let restored: RestoreResult | null = null;
    try {
      const form = restoreForm();
      form.append("confirmation", "RESTORE");
      const response = await fetch("/api/archive/encrypted-restore", {
        method: "POST",
        credentials: "same-origin",
        body: form,
      });
      if (!response.ok) throw operationFailure(response.status, "restore");
      restored = (await response.json()) as RestoreResult;
      setFile(null);
      setRestorePassword("");
      setShowRestorePassword(false);
      setConfirmation("");
      setPreview(null);
      if (fileInput.current) fileInput.current.value = "";
      setRestoreNotice(
        restored.recovery_pending
          ? "Your backup was restored. Restart Reweave to reopen the restored library, then reconnect provider credentials in Settings."
          : "Your local library was restored. Reconnect provider credentials in Settings before analysis resumes.",
      );
      window.dispatchEvent(
        new Event(
          restored.recovery_pending
            ? "reweave:restart-required"
            : "reweave:context-changed",
        ),
      );
    } catch (reason) {
      setRestoreError(
        normalizeFailure(
          reason,
          "The restore could not be completed. Your selected file and password are kept here so you can review and retry.",
        ),
      );
    } finally {
      setRestoreBusy(null);
    }
    if (restored && !restored.recovery_pending && onRestored) {
      try {
        await onRestored(restored);
      } catch {
        setRestoreNotice(
          "The library was restored, but this view could not refresh. Reopen Home or restart Reweave, then reconnect provider credentials in Settings.",
        );
      }
    }
  }

  return (
    <section className="backupManager" aria-labelledby="backup-manager-title">
      <header className="backupManagerHeader">
        <div>
          <span className="sectionLabel">Keep a recoverable copy</span>
          <h2 id="backup-manager-title">Encrypted backup &amp; restore</h2>
          <p>
            Your backup contains private source conversations and derived
            context, protected by your password. API keys are excluded.
          </p>
        </div>
        <ShieldCheck size={24} aria-hidden="true" />
      </header>
      <div className="backupManagerGrid">
        <article className="backupCard">
          <h3>
            <LockKeyhole size={18} /> Create an encrypted backup
          </h3>
          <p>
            Download one .reweave file with the local library, context history,
            links, and provider settings. Provider secrets are never included.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void downloadBackup();
            }}
          >
            <label>
              Backup password
              <span className="backupSecret">
                <input
                  type={showBackupPassword ? "text" : "password"}
                  minLength={MIN_BACKUP_PASSWORD_LENGTH}
                  autoComplete="new-password"
                  value={backupPassword}
                  onInput={(event) => {
                    setBackupPassword(event.currentTarget.value);
                    setBackupError(null);
                    setBackupNotice("");
                  }}
                  disabled={working}
                  aria-describedby="backup-password-help"
                />
                <button
                  type="button"
                  onClick={() => setShowBackupPassword(!showBackupPassword)}
                  aria-label={
                    showBackupPassword
                      ? "Hide backup password"
                      : "Show backup password"
                  }
                >
                  {showBackupPassword ? (
                    <EyeOff size={17} />
                  ) : (
                    <Eye size={17} />
                  )}
                </button>
              </span>
            </label>
            <label>
              Repeat backup password
              <input
                type={showBackupPassword ? "text" : "password"}
                minLength={MIN_BACKUP_PASSWORD_LENGTH}
                autoComplete="new-password"
                value={backupPasswordAgain}
                onInput={(event) =>
                  setBackupPasswordAgain(event.currentTarget.value)
                }
                disabled={working}
              />
            </label>
            <p id="backup-password-help" className="backupHelp">
              Use at least 12 characters. Reweave does not save this password
              and cannot recover a lost password or decrypt the backup without
              it.
            </p>
            {backupPasswordAgain && backupPasswordAgain !== backupPassword && (
              <p className="backupInlineError">The passwords do not match.</p>
            )}
            <button
              type="submit"
              className="secondaryButton"
              disabled={working || !backupReady}
            >
              {backupBusy ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <Download size={16} />
              )}
              {backupBusy
                ? "Preparing encrypted backup…"
                : backupError?.busy
                  ? "Try backup again"
                  : "Download encrypted backup"}
            </button>
          </form>
          {backupError && (
            <p role="alert" className="contextEvidenceError">
              {backupError.message}
            </p>
          )}
          {backupNotice && (
            <p role="status" className="backupSuccess">
              {backupNotice}
            </p>
          )}
        </article>
        <article className="backupCard">
          <h3>
            <ArchiveRestore size={18} /> Restore an encrypted backup
          </h3>
          <p>
            Preview the backup before changing anything. Restoring replaces your
            current local library. Create a backup first if you want to keep it.
          </p>
          <div className="backupRestoreFields">
            <label className="backupFilePicker">
              <FileUp size={18} /> Choose .reweave backup
              <input
                ref={fileInput}
                type="file"
                accept=".reweave"
                disabled={working}
                onChange={(event) => {
                  setFile(event.currentTarget.files?.[0] ?? null);
                  clearPreview();
                }}
              />
            </label>
            {file && (
              <p className="backupSelectedFile">
                {file.name} · {fileSize(file.size)}
              </p>
            )}
            {fileProblem && (
              <p role="alert" className="backupInlineError">
                {fileProblem}
              </p>
            )}
            <label>
              Restore password
              <span className="backupSecret">
                <input
                  ref={restorePasswordInput}
                  type={showRestorePassword ? "text" : "password"}
                  minLength={MIN_BACKUP_PASSWORD_LENGTH}
                  autoComplete="off"
                  value={restorePassword}
                  onInput={(event) => {
                    setRestorePassword(event.currentTarget.value);
                    clearPreview();
                  }}
                  disabled={working}
                />
                <button
                  type="button"
                  onClick={() => setShowRestorePassword(!showRestorePassword)}
                  aria-label={
                    showRestorePassword
                      ? "Hide restore password"
                      : "Show restore password"
                  }
                >
                  {showRestorePassword ? (
                    <EyeOff size={17} />
                  ) : (
                    <Eye size={17} />
                  )}
                </button>
              </span>
            </label>
            <p className="backupHelp">
              Use the original backup password. Files up to 2 GiB are supported.
              Restored provider profiles need their API keys reconnected.
            </p>
            <div className="buttonRow">
              <button
                type="button"
                className="secondaryButton"
                onClick={() => void previewRestore()}
                disabled={working || !previewReady}
              >
                {restoreBusy === "preview" ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <RefreshCw size={16} />
                )}
                {restoreBusy === "preview"
                  ? "Reading backup…"
                  : restoreError?.busy && !preview
                    ? "Try preview again"
                    : "Preview backup"}
              </button>
              {(file || restorePassword) && (
                <button
                  type="button"
                  className="contextTextButton"
                  onClick={cancelRestore}
                  disabled={working}
                >
                  Cancel restore
                </button>
              )}
            </div>
          </div>
          {preview && (
            <section
              className="backupPreview"
              aria-labelledby="backup-preview-title"
            >
              <h4 id="backup-preview-title" ref={previewHeading} tabIndex={-1}>
                Review this backup
              </h4>
              <p>
                Created {formatBackupDate(preview.created_at)} ·{" "}
                {fileSize(preview.database_bytes)} of library data
              </p>
              <dl>
                {[
                  ["Conversations", preview.conversations],
                  ["Messages", preview.messages],
                  ["Briefs", preview.briefs],
                  ["Context Items", preview.context_items],
                  ["Versions", preview.versions],
                  ["Links", preview.links],
                  ["Provider profiles", preview.profiles],
                ].map(([title, count]) => (
                  <div key={String(title)}>
                    <dt>{title}</dt>
                    <dd>{Number(count).toLocaleString()}</dd>
                  </div>
                ))}
              </dl>
              <p className="backupRestoreWarning">
                This will replace the library currently stored on this device.
                Provider credentials are excluded; reconnect them after
                restoring.
              </p>
              <label>
                Type RESTORE to replace this library
                <input
                  value={confirmation}
                  onInput={(event) =>
                    setConfirmation(event.currentTarget.value)
                  }
                  autoComplete="off"
                  spellCheck={false}
                  disabled={working}
                />
              </label>
              <button
                type="button"
                className="dangerButton"
                onClick={() => void restore()}
                disabled={working || confirmation !== "RESTORE"}
              >
                {restoreBusy === "restore" ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <ArchiveRestore size={16} />
                )}
                {restoreBusy === "restore"
                  ? "Restoring library…"
                  : restoreError?.busy
                    ? "Try restore again"
                    : "Replace library with this backup"}
              </button>
            </section>
          )}
          {restoreError && (
            <div role="alert" className="contextEvidenceError">
              <p>{restoreError.message}</p>
              {!restoreError.busy && (
                <button
                  className="contextTextButton"
                  type="button"
                  onClick={() => restorePasswordInput.current?.focus()}
                >
                  Review file and password
                </button>
              )}
            </div>
          )}
          {restoreNotice && (
            <p role="status" className="backupSuccess">
              {restoreNotice}
            </p>
          )}
        </article>
      </div>
    </section>
  );
}

class BackupOperationError extends Error {
  constructor(public information: OperationError) {
    super(information.message);
  }
}
function operationFailure(
  status: number,
  operation: "backup" | "preview" | "restore",
) {
  if (status === 409)
    return new BackupOperationError({
      busy: true,
      message:
        "Reweave is busy with another operation. Wait for analysis or import to finish, then try again. Your input is kept.",
    });
  if (status === 413)
    return new BackupOperationError({
      busy: false,
      message:
        "This backup exceeds the 2 GiB restore limit. Choose a smaller backup.",
    });
  if (status === 400)
    return new BackupOperationError({
      busy: false,
      message:
        operation === "backup"
          ? "This backup could not be created. Check that the password has at least 12 characters and try again."
          : "The file or password could not be verified. Check that this is an intact .reweave backup and enter its original password.",
    });
  return new BackupOperationError({
    busy: false,
    message:
      operation === "backup"
        ? "The encrypted backup could not be prepared. Check that Reweave is available and try again."
        : "Reweave could not complete this operation. Keep your backup file, check the app is available, and try again.",
  });
}
function normalizeFailure(reason: unknown, fallback: string): OperationError {
  return reason instanceof BackupOperationError
    ? reason.information
    : { message: fallback, busy: false };
}
function fileSize(bytes: number) {
  return bytes >= 1024 ** 3
    ? `${(bytes / 1024 ** 3).toFixed(2)} GiB`
    : bytes >= 1024 ** 2
      ? `${(bytes / 1024 ** 2).toFixed(1)} MiB`
      : `${Math.ceil(bytes / 1024)} KiB`;
}
function formatBackupDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("en-US");
}
