import { useEffect, useId, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  History,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import type {
  ContextItem,
  ContextItemVersion,
  ContextScope,
} from "./ContextWorkspace";
import "./contextManagement.css";

const itemTypes = [
  "insight",
  "concept",
  "value",
  "preference",
  "decision",
  "lesson",
  "project_fact",
  "open_question",
  "action",
  "follow_up",
];
const kinds = ["observed", "inferred", "suggested"];
const statuses = ["active", "superseded", "stale", "archived"];
const scopeTypes = [
  "core_self",
  "personal",
  "work",
  "project",
  "topic",
  "destination",
];
const namedScopes = new Set(["project", "topic", "destination"]);

export type CorrectionDraft = {
  canonical_text: string;
  item_type: string;
  epistemic_kind: string;
  sensitivity: string;
  status: string;
  inference_rationale: string;
  confidence: number;
  scopes: Array<Pick<ContextScope, "scope_type" | "scope_key" | "confidence">>;
  change_reason: string;
};

export function correctionDraft(item: ContextItem): CorrectionDraft {
  return {
    canonical_text: item.canonical_text,
    item_type: item.item_type,
    epistemic_kind: item.epistemic_kind,
    sensitivity: item.sensitivity,
    status: item.status,
    inference_rationale: item.inference_rationale ?? "",
    confidence: item.confidence,
    scopes: item.scopes.map(({ scope_type, scope_key, confidence }) => ({
      scope_type,
      scope_key,
      confidence,
    })),
    change_reason: "",
  };
}

export function correctionPatch(
  original: ContextItem,
  draft: CorrectionDraft,
  expectedVersion: number,
) {
  const base = correctionDraft(original);
  const changes: Record<string, unknown> = {
    expected_version: expectedVersion,
    change_reason: draft.change_reason.trim(),
  };
  for (const field of [
    "canonical_text",
    "item_type",
    "epistemic_kind",
    "sensitivity",
    "status",
    "inference_rationale",
    "confidence",
    "scopes",
  ] as const) {
    if (JSON.stringify(base[field]) !== JSON.stringify(draft[field]))
      changes[field] = draft[field];
  }
  return changes;
}

function label(value: string) {
  if (value === "core_self") return "Core Self";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function Choice({
  title,
  value,
  choices,
  onChange,
}: {
  title: string;
  value: string;
  choices: string[];
  onChange: (value: string) => void;
}) {
  const options = choices.includes(value) ? choices : [value, ...choices];
  return (
    <label>
      {title}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((choice) => (
          <option key={choice} value={choice}>
            {label(choice)}
          </option>
        ))}
      </select>
    </label>
  );
}

function announceChange() {
  window.dispatchEvent(new Event("reweave:context-changed"));
}

export function ContextManagement({
  item,
  onUpdated,
}: {
  item: ContextItem;
  onUpdated: (item: ContextItem) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [original, setOriginal] = useState(item);
  const [draft, setDraft] = useState(() => correctionDraft(item));
  const [expectedVersion, setExpectedVersion] = useState(item.current_version);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [currentSaved, setCurrentSaved] = useState<ContextItem | null>(null);
  const [notice, setNotice] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<{
    version: number;
    expectedVersion: number;
  } | null>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const editorId = useId();

  useEffect(() => {
    if (editing) editorRef.current?.focus();
  }, [editing]);

  function startEdit() {
    setOriginal(item);
    setDraft(correctionDraft(item));
    setExpectedVersion(item.current_version);
    setEditing(true);
    setError("");
    setConflict(false);
    setCurrentSaved(null);
    setNotice("");
    setRestoreTarget(null);
  }

  function edit<K extends keyof CorrectionDraft>(
    key: K,
    value: CorrectionDraft[K],
  ) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function changeScope(
    index: number,
    field: "scope_type" | "scope_key",
    value: string,
  ) {
    edit(
      "scopes",
      draft.scopes.map((scope, position) =>
        position !== index
          ? scope
          : {
              ...scope,
              [field]: value,
              ...(field === "scope_type" && !namedScopes.has(value)
                ? { scope_key: "" }
                : {}),
            },
      ),
    );
  }

  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await managementApi<ContextItem>(
        `/api/context/items/${encodeURIComponent(item.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify(
            correctionPatch(original, draft, expectedVersion),
          ),
        },
      );
      onUpdated(updated);
      setEditing(false);
      setConflict(false);
      setCurrentSaved(null);
      setNotice(
        `Correction saved as version ${updated.current_version}. Your source evidence is preserved.`,
      );
      announceChange();
    } catch (reason) {
      setConflict(reason instanceof ManagementError && reason.status === 409);
      setError(
        reason instanceof ManagementError && reason.status === 409
          ? "This item changed while you were editing. Your draft is kept. Refresh the saved version, review it below, then save your edits."
          : message(
              reason,
              "Your correction could not be saved. Your draft is kept.",
            ),
      );
    } finally {
      setBusy(false);
    }
  }

  async function refreshCurrent() {
    setBusy(true);
    try {
      const current = await managementApi<ContextItem>(
        `/api/context/items/${encodeURIComponent(item.id)}`,
      );
      onUpdated(current);
      setCurrentSaved(current);
      setExpectedVersion(current.current_version);
      setConflict(false);
      setError("");
      setNotice(
        `Saved version ${current.current_version} loaded. Your draft is unchanged. Review both before saving.`,
      );
      setRestoreTarget(null);
    } catch (reason) {
      setError(
        message(
          reason,
          "The saved version could not be refreshed. Your draft is kept.",
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  async function restore() {
    if (!restoreTarget) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await managementApi<ContextItem>(
        `/api/context/items/${encodeURIComponent(item.id)}/undo`,
        {
          method: "POST",
          body: JSON.stringify({
            version: restoreTarget.version,
            expected_version: restoreTarget.expectedVersion,
          }),
        },
      );
      onUpdated(updated);
      setRestoreTarget(null);
      setNotice(
        `Version ${restoreTarget.version} restored as new version ${updated.current_version}.`,
      );
      announceChange();
    } catch (reason) {
      setConflict(reason instanceof ManagementError && reason.status === 409);
      setError(
        reason instanceof ManagementError && reason.status === 409
          ? "This item changed before the restore. Refresh it and review the version again."
          : message(
              reason,
              "The version could not be restored. Your current item is unchanged.",
            ),
      );
    } finally {
      setBusy(false);
    }
  }

  const patch = correctionPatch(original, draft, expectedVersion);
  const changed = Object.keys(patch).length > 2;
  const scopesValid = draft.scopes.every(
    (scope) => !namedScopes.has(scope.scope_type) || scope.scope_key.trim(),
  );
  const versions = [...item.versions].sort(
    (left, right) => right.version - left.version,
  );
  return (
    <section
      className="contextManagement"
      aria-label="Correct context and inspect history"
    >
      <div className="contextManagementHeading">
        <h3>
          <Pencil size={16} /> Your corrections
        </h3>
        {!editing && (
          <button type="button" className="secondaryButton" onClick={startEdit}>
            <Pencil size={15} /> Correct this item
          </button>
        )}
      </div>
      <p className="contextDetailMuted">
        {item.authority === "user"
          ? "You corrected this item. Analysis will preserve your edits."
          : "Correct the wording or where it belongs. The original evidence remains attached."}
      </p>
      {editing && (
        <form
          className="contextEditor"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          aria-labelledby={`${editorId}-title`}
        >
          <h4 id={`${editorId}-title`}>Correct version {expectedVersion}</h4>
          <label>
            Context text
            <textarea
              ref={editorRef}
              rows={5}
              required
              value={draft.canonical_text}
              onChange={(event) => edit("canonical_text", event.target.value)}
            />
          </label>
          <div className="contextEditorGrid">
            <Choice
              title="Type"
              value={draft.item_type}
              choices={itemTypes}
              onChange={(value) => edit("item_type", value)}
            />
            <Choice
              title="How it is known"
              value={draft.epistemic_kind}
              choices={kinds}
              onChange={(value) => edit("epistemic_kind", value)}
            />
            <Choice
              title="Sensitivity"
              value={draft.sensitivity}
              choices={["normal", "sensitive"]}
              onChange={(value) => edit("sensitivity", value)}
            />
            <Choice
              title="State"
              value={draft.status}
              choices={statuses}
              onChange={(value) => edit("status", value)}
            />
          </div>
          <p className="contextDetailMuted">
            Observed is directly supported by the source. Inferred is an
            interpretation; suggested is a proposed action. Sensitive context
            remains subject to stricter use boundaries.
          </p>
          {(draft.epistemic_kind === "inferred" ||
            draft.inference_rationale) && (
            <label>
              Reason for the inference
              <textarea
                rows={3}
                maxLength={4000}
                value={draft.inference_rationale}
                onChange={(event) =>
                  edit("inference_rationale", event.target.value)
                }
              />
              <span className="contextDetailMuted">
                Explain how the source supports this interpretation. This is
                separate from the source quotation.
              </span>
            </label>
          )}
          <fieldset className="scopeEditor">
            <legend>Spaces this item belongs to</legend>
            <p className="contextDetailMuted">
              One item may belong to several spaces. Named spaces also determine
              where context can be used.
            </p>
            {draft.scopes.map((scope, index) => (
              <div className="scopeEditorRow" key={index}>
                <Choice
                  title={`Space ${index + 1}`}
                  value={scope.scope_type}
                  choices={scopeTypes}
                  onChange={(value) => changeScope(index, "scope_type", value)}
                />
                {namedScopes.has(scope.scope_type) && (
                  <label>
                    Space name
                    <input
                      required
                      value={scope.scope_key}
                      onChange={(event) =>
                        changeScope(index, "scope_key", event.target.value)
                      }
                    />
                  </label>
                )}
                <button
                  type="button"
                  className="iconButton"
                  aria-label={`Remove space ${index + 1}`}
                  onClick={() =>
                    edit(
                      "scopes",
                      draft.scopes.filter((_, position) => position !== index),
                    )
                  }
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
            <button
              type="button"
              className="contextTextButton"
              onClick={() =>
                edit("scopes", [
                  ...draft.scopes,
                  { scope_type: "project", scope_key: "", confidence: 1 },
                ])
              }
            >
              <Plus size={16} /> Add space
            </button>
          </fieldset>
          <label>
            Why this changed
            <input
              required
              value={draft.change_reason}
              onChange={(event) => edit("change_reason", event.target.value)}
              placeholder="What should the history remember?"
            />
          </label>
          {currentSaved && (
            <div className="currentSavedVersion">
              <strong>
                Current saved version {currentSaved.current_version}
              </strong>
              <p>{currentSaved.canonical_text}</p>
              <p>
                {label(currentSaved.epistemic_kind)} ·{" "}
                {label(currentSaved.sensitivity)} · {label(currentSaved.status)}
              </p>
              <p>
                Spaces:{" "}
                {currentSaved.scopes
                  .map((scope) => scope.scope_key || label(scope.scope_type))
                  .join(", ") || "None"}
              </p>
              <p className="contextDetailMuted">
                Saving applies only fields you changed in this editor to the
                saved version above.
              </p>
            </div>
          )}
          <div className="buttonRow">
            <button
              type="submit"
              className="primaryButton"
              disabled={
                busy ||
                conflict ||
                !changed ||
                !draft.canonical_text.trim() ||
                !draft.change_reason.trim() ||
                !scopesValid
              }
            >
              {busy ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <Save size={16} />
              )}{" "}
              Save correction
            </button>
            <button
              type="button"
              className="secondaryButton"
              disabled={busy}
              onClick={() => {
                setEditing(false);
                setError("");
                setConflict(false);
                setNotice("");
              }}
            >
              Cancel edit
            </button>
          </div>
        </form>
      )}
      {error && (
        <div className="contextEvidenceError" role="alert">
          <p>{error}</p>
          {conflict && (
            <button
              className="secondaryButton"
              type="button"
              onClick={() => void refreshCurrent()}
              disabled={busy}
            >
              <RefreshCw size={16} /> Refresh saved item
              {editing ? " (keep draft)" : ""}
            </button>
          )}
        </div>
      )}
      {notice && (
        <p className="contextMutationNotice" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      <details className="contextVersionHistory">
        <summary>
          <History size={16} /> History · {versions.length} recorded version
          {versions.length === 1 ? "" : "s"}
          <ChevronDown size={15} />
        </summary>
        {versions.length ? (
          versions.map((version) => (
            <VersionRecord
              version={version}
              currentVersion={item.current_version}
              key={version.version}
              disabled={busy || editing || conflict}
              onRestore={() => {
                setError("");
                setConflict(false);
                setRestoreTarget({
                  version: version.version,
                  expectedVersion: item.current_version,
                });
              }}
            />
          ))
        ) : (
          <p className="contextDetailMuted">
            No version snapshots are available for this item.
          </p>
        )}
        {restoreTarget && (
          <div className="restoreConfirmation">
            <h4>Restore version {restoreTarget.version}?</h4>
            <p>
              This creates a new current version from that recorded text,
              classification, and spaces. Existing history stays available.
            </p>
            <div className="buttonRow">
              <button
                type="button"
                className="primaryButton"
                onClick={() => void restore()}
                disabled={busy || conflict}
              >
                <RotateCcw size={16} /> Confirm restore
              </button>
              <button
                type="button"
                className="secondaryButton"
                onClick={() => setRestoreTarget(null)}
                disabled={busy}
              >
                Keep current version
              </button>
            </div>
          </div>
        )}
      </details>
    </section>
  );
}

function VersionRecord({
  version,
  currentVersion,
  disabled,
  onRestore,
}: {
  version: ContextItemVersion;
  currentVersion: number;
  disabled: boolean;
  onRestore: () => void;
}) {
  return (
    <article className="contextVersion">
      <header>
        <strong>
          Version {version.version}
          {version.version === currentVersion ? " · Current" : ""}
        </strong>
        <time dateTime={version.created_at}>
          {new Date(version.created_at).toLocaleString("en-US")}
        </time>
      </header>
      <p>{version.canonical_text}</p>
      <p className="contextDetailMuted">{version.change_reason}</p>
      {version.item_type && (
        <p className="contextVersionMeta">
          {label(version.item_type)} · {label(version.epistemic_kind ?? "")} ·{" "}
          {label(version.sensitivity ?? "")} · {label(version.status ?? "")}
        </p>
      )}
      {version.inference_rationale && (
        <p className="versionRationale">
          Inference: {version.inference_rationale}
        </p>
      )}
      {version.scopes && (
        <p className="contextDetailMuted">
          Spaces:{" "}
          {version.scopes
            .map((scope) => scope.scope_key || label(scope.scope_type))
            .join(", ") || "None"}
        </p>
      )}
      {version.evidence_ids && (
        <p className="contextDetailMuted">
          {version.evidence_ids.length} recorded evidence reference
          {version.evidence_ids.length === 1 ? "" : "s"}
        </p>
      )}
      {version.version !== currentVersion && (
        <button
          type="button"
          className="contextTextButton"
          disabled={disabled}
          onClick={onRestore}
        >
          <RotateCcw size={15} /> Restore version {version.version}
        </button>
      )}
    </article>
  );
}

export type ContextSpace = {
  id: string;
  scope_type: string;
  name: string;
  aliases: string[];
  revision: number;
  corrected: boolean;
  merged_into: string | null;
};

export function SpacesManager() {
  const [open, setOpen] = useState(false);
  const [spaces, setSpaces] = useState<ContextSpace[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [name, setName] = useState("");
  const [targetId, setTargetId] = useState("");
  const [expectedRevision, setExpectedRevision] = useState(0);
  const [confirmingMerge, setConfirmingMerge] = useState<{
    source: ContextSpace;
    target: ContextSpace;
  } | null>(null);
  const active = spaces.filter(
    (space) => !space.merged_into && namedScopes.has(space.scope_type),
  );
  const source = active.find((space) => space.id === sourceId);
  const target = active.find((space) => space.id === targetId);

  async function refresh() {
    setBusy(true);
    setError("");
    try {
      const data = await managementApi<{ results: ContextSpace[] }>(
        "/api/context/spaces",
      );
      setSpaces(data.results);
      setConfirmingMerge(null);
      const current = data.results.find((space) => space.id === sourceId);
      if (current) setExpectedRevision(current.revision);
    } catch (reason) {
      setError(message(reason, "Spaces could not be loaded. Try again."));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (open) void refresh();
  }, [open]);

  function select(space: ContextSpace) {
    setSourceId(space.id);
    setName(space.name);
    setExpectedRevision(space.revision);
    setTargetId("");
    setConfirmingMerge(null);
    setError("");
    setNotice("");
  }

  async function rename() {
    if (!source) return;
    setBusy(true);
    setError("");
    try {
      const updated = await managementApi<ContextSpace>(
        `/api/context/spaces/${encodeURIComponent(source.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            name: name.trim(),
            expected_revision: expectedRevision,
          }),
        },
      );
      setSpaces((current) =>
        current.map((space) => (space.id === updated.id ? updated : space)),
      );
      setExpectedRevision(updated.revision);
      setName(updated.name);
      setNotice(`Renamed to ${updated.name}. Previous names remain aliases.`);
      announceChange();
    } catch (reason) {
      setError(
        reason instanceof ManagementError && reason.status === 409
          ? "This space changed elsewhere. Refresh spaces, review its current name, then retry. Your name draft is kept."
          : message(reason, "The space could not be renamed."),
      );
    } finally {
      setBusy(false);
    }
  }

  async function merge() {
    if (!confirmingMerge) return;
    setBusy(true);
    setError("");
    const plan = confirmingMerge;
    try {
      await managementApi<ContextSpace>(
        `/api/context/spaces/${encodeURIComponent(plan.source.id)}/merge`,
        {
          method: "POST",
          body: JSON.stringify({
            target_id: plan.target.id,
            expected_source_revision: plan.source.revision,
            expected_target_revision: plan.target.revision,
          }),
        },
      );
      setSourceId("");
      setConfirmingMerge(null);
      setTargetId("");
      setNotice(`Merged ${plan.source.name} into ${plan.target.name}.`);
      announceChange();
      await refresh();
    } catch (reason) {
      setError(
        reason instanceof ManagementError && reason.status === 409
          ? "One of these spaces changed. Refresh spaces and review a new merge preview."
          : message(reason, "The spaces could not be merged."),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="spacesManager">
      <button
        type="button"
        className="contextTextButton"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Pencil size={15} /> Manage spaces
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="spacesManagerBody">
          <div className="contextManagementHeading">
            <div>
              <h3>Names and shared spaces</h3>
              <p className="contextDetailMuted">
                Rename or combine named projects, topics, and destinations. Core
                Self, Personal, and Work stay available as fixed spaces.
              </p>
            </div>
            <button
              type="button"
              className="iconButton"
              aria-label="Refresh spaces (keep name draft)"
              onClick={() => void refresh()}
              disabled={busy}
            >
              <RefreshCw size={16} />
            </button>
          </div>
          {active.length > 0 ? (
            <label>
              Named space
              <select
                value={sourceId}
                onChange={(event) => {
                  const space = active.find(
                    (entry) => entry.id === event.target.value,
                  );
                  if (space) select(space);
                }}
              >
                <option value="">Choose a space to edit</option>
                {active.map((space) => (
                  <option key={space.id} value={space.id}>
                    {label(space.scope_type)} · {space.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="contextDetailMuted">
              {busy
                ? "Loading spaces…"
                : "No named spaces yet. Context analysis or an item correction can establish one."}
            </p>
          )}
          {source && (
            <div className="spaceEditor">
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void rename();
                }}
              >
                <p className="contextDetailMuted">
                  Current saved name: {source.name} · Revision {source.revision}
                </p>
                <label>
                  Space name
                  <input
                    required
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </label>
                {source.aliases.length > 0 && (
                  <p className="contextDetailMuted">
                    Also known as: {source.aliases.join(", ")}
                  </p>
                )}
                <button
                  className="secondaryButton"
                  type="submit"
                  disabled={busy || !name.trim() || name.trim() === source.name}
                >
                  <Save size={15} /> Save name
                </button>
              </form>
              <details className="spaceMerge">
                <summary>
                  Combine with another {label(source.scope_type).toLowerCase()}
                </summary>
                <label>
                  Keep this destination space
                  <select
                    value={targetId}
                    onChange={(event) => {
                      setTargetId(event.target.value);
                      setConfirmingMerge(null);
                    }}
                  >
                    <option value="">Choose destination</option>
                    {active
                      .filter(
                        (space) =>
                          space.id !== source.id &&
                          space.scope_type === source.scope_type,
                      )
                      .map((space) => (
                        <option key={space.id} value={space.id}>
                          {space.name}
                        </option>
                      ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={busy || !target}
                  onClick={() => {
                    if (target) setConfirmingMerge({ source, target });
                  }}
                >
                  Preview merge
                </button>
                {confirmingMerge && (
                  <div className="restoreConfirmation">
                    <h4>
                      {confirmingMerge.source.name} →{" "}
                      {confirmingMerge.target.name}
                    </h4>
                    <p>
                      Every Context Item in {confirmingMerge.source.name} will
                      also belong to {confirmingMerge.target.name}. This changes
                      where those items can be found and used. Previous names
                      remain aliases.
                    </p>
                    <div className="buttonRow">
                      <button
                        type="button"
                        className="primaryButton"
                        onClick={() => void merge()}
                        disabled={busy}
                      >
                        Confirm merge
                      </button>
                      <button
                        type="button"
                        className="secondaryButton"
                        onClick={() => setConfirmingMerge(null)}
                        disabled={busy}
                      >
                        Cancel merge
                      </button>
                    </div>
                  </div>
                )}
              </details>
            </div>
          )}
          {error && (
            <p className="contextEvidenceError" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="contextMutationNotice" role="status">
              {notice}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

class ManagementError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
function message(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}
async function managementApi<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok)
    throw new ManagementError(
      data && typeof data.detail === "string"
        ? data.detail
        : "The change could not be saved. Check the fields and try again.",
      response.status,
    );
  return data as T;
}
