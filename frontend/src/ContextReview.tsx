import { useCallback, useEffect, useRef, useState } from "react";
import type { ContextItem } from "./ContextWorkspace";
import "./contextReview.css";

type ReviewReason = { code: string; label: string; detail: string };
type ReviewEvent = {
  id: string; item_id: string; item_version: number; action: string;
  created_at: string; undone_at: string | null; resolution: string | null;
};
type RelatedItem = { id: string; version: number; canonical_text: string; relationship: string };
export type ReviewRow = {
  item: ContextItem; reasons: ReviewReason[]; related_items: RelatedItem[];
  effective_confidence: number; review_key: string; state: "open" | "handled"; history: ReviewEvent[];
};
type ReviewResponse = { results: ReviewRow[]; total: number; open_count: number; reason_counts: Record<string, number> };
const reasons = [
  ["sensitive_inference", "Sensitive inference"], ["cross_scope", "Scope boundary"],
  ["low_confidence", "Uncertain personalization"], ["contradiction", "Contradiction"],
  ["changed_decision", "Changed decision"], ["source_changed", "Source changed"],
  ["ambiguous_evidence", "Incomplete evidence"], ["failed_evidence", "Failed analysis"],
] as const;
const eventLabels: Record<string, string> = {
  dismiss: "Hidden for this version", confirm: "Accuracy confirmed", confirm_accuracy: "Accuracy confirmed; relationship still open",
  resolve_link: "Relationship resolved",
};

async function checkedJson(response: Response) {
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Review could not be updated. Try again.");
  return body;
}

export function ContextReview({ onOpenItem, onLibraryDeleted }: {
  onOpenItem: (itemId: string) => void;
  onLibraryDeleted?: () => void;
}) {
  const [state, setState] = useState<"open" | "handled">("open");
  const [reason, setReason] = useState("");
  const [offset, setOffset] = useState(0);
  const [generation, setGeneration] = useState(0);
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [restartRequired, setRestartRequired] = useState(false);
  const activeRequest = useRef(false);
  const refresh = useCallback(() => setGeneration(value => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ state, limit: "50", offset: String(offset) });
    if (reason) query.set("reason", reason);
    fetch(`/api/context/review?${query}`, { signal: controller.signal })
      .then(checkedJson).then((result: ReviewResponse) => {
        if (!controller.signal.aborted) setData(result);
      }).catch(cause => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Review could not be loaded.");
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [state, reason, offset, generation]);

  async function perform(path: string, body: unknown, success: string) {
    if (activeRequest.current || restartRequired) return;
    activeRequest.current = true;
    setPending(true); setError(""); setNotice("");
    try {
      await checkedJson(await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
      setNotice(success);
      refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Review could not be updated.");
    } finally { activeRequest.current = false; setPending(false); }
  }

  function reviewAction(row: ReviewRow, action: "confirm" | "dismiss") {
    void perform(`/api/context/review/items/${encodeURIComponent(row.item.id)}/${action}`,
      { expected_version: row.item.current_version, review_key: row.review_key },
      action === "confirm" ? "Accuracy confirmed with a new version. External-use permissions are unchanged." : "This version is hidden from Review. Its data and permissions are unchanged.");
  }

  function resolve(row: ReviewRow, related: RelatedItem, resolution: string) {
    void perform(`/api/context/review/items/${encodeURIComponent(row.item.id)}/resolve`, {
      expected_version: row.item.current_version, review_key: row.review_key,
      related_item_id: related.id, related_version: related.version, relationship: related.relationship, resolution,
    }, "Relationship choice recorded. Both items and their versions are preserved.");
  }

  async function deleteLibrary() {
    if (confirmation !== "DELETE LIBRARY" || activeRequest.current || restartRequired) return;
    activeRequest.current = true;
    setPending(true); setError(""); setNotice("");
    try {
      const result = await checkedJson(await fetch("/api/context/library", {
        method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmation }),
      }));
      setConfirmation("");
      setData({ results: [], total: 0, open_count: 0, reason_counts: {} });
      setNotice(`${result.deleted.items} items and ${result.deleted.briefs} briefs deleted. ${result.notice}`);
      setRestartRequired(Boolean(result.restart_required));
      if (!result.restart_required) {
        try { onLibraryDeleted?.(); } catch { setNotice("Library deletion completed. Refresh the page to update other views."); }
        refresh();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Library deletion could not be completed.");
    } finally { activeRequest.current = false; setPending(false); }
  }

  const disabled = pending || restartRequired;
  return <section className="contextReview" aria-label="Context Review">
    <header className="contextReviewHeading">
      <div><p className="contextReviewEyebrow">Library care</p><h2>Review</h2>
        <p>Check sensitive inferences, uncertain personalization, and changed evidence. Ordinary items need no approval.</p></div>
      <button type="button" className="secondaryButton" onClick={refresh} disabled={disabled || loading}>Refresh</button>
    </header>
    <p className="contextReviewBoundary">Confirming accuracy or hiding an exception does not authorize sharing it with another app.</p>
    <div className="contextReviewFilters">
      <label>Show<select value={state} disabled={disabled} onChange={event => { setState(event.target.value as "open" | "handled"); setOffset(0); }}>
        <option value="open">Needs attention{data ? ` (${data.open_count})` : ""}</option><option value="handled">Handled and history</option>
      </select></label>
      <label>Reason<select value={reason} disabled={disabled} onChange={event => { setReason(event.target.value); setOffset(0); }}>
        <option value="">All reasons</option>{reasons.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
      </select></label>
    </div>
    {error && <p className="contextReviewError" role="alert">{error}</p>}
    {notice && <p className="contextReviewNotice" role="status">{notice}</p>}
    {loading ? <p role="status">Loading exceptions…</p> : !error && data?.results.length === 0 ?
      <p className="contextReviewEmpty">{state === "open" ? "No exceptions need your attention in this view." : "No handled exceptions in this view."}</p> : null}
    <div className="contextReviewList" aria-busy={loading || pending}>
      {!loading && data?.results.map(row => <article className="contextReviewItem" key={row.item.id}>
        <div className="contextReviewItemHeading"><h3>{row.item.canonical_text}</h3>
          <span>Version {row.item.current_version} · Effective confidence {Math.round(row.effective_confidence * 100)}%</span></div>
        <ul className="contextReviewReasons">{row.reasons.map(entry => <li key={entry.code}><strong>{entry.label}</strong><p>{entry.detail}</p></li>)}</ul>
        {row.related_items.map(related => <div className="contextReviewRelationship" key={`${related.id}:${related.relationship}`}>
          <p><strong>Linked record, version {related.version}</strong></p><p>{related.canonical_text}</p>
          <div className="buttonRow">
            <button type="button" className="secondaryButton" disabled={disabled} onClick={() => onOpenItem(related.id)}>Open linked item</button>
            <button type="button" className="secondaryButton" disabled={disabled} onClick={() => resolve(row, related, "keep_both")}>Keep both as valid</button>
            <button type="button" className="secondaryButton" disabled={disabled} onClick={() => resolve(row, related, "prefer_this")}>Prefer this item</button>
            <button type="button" className="secondaryButton" disabled={disabled} onClick={() => resolve(row, related, "prefer_other")}>Prefer linked item</button>
          </div>
        </div>)}
        <div className="buttonRow">
          <button type="button" className="secondaryButton" onClick={() => onOpenItem(row.item.id)}>Read evidence or correct</button>
          {row.state === "open" && <>
            <button type="button" className="primaryButton" disabled={disabled} onClick={() => reviewAction(row, "confirm")}>Confirm accuracy</button>
            <button type="button" className="secondaryButton" disabled={disabled} onClick={() => reviewAction(row, "dismiss")}>Hide this version</button>
          </>}
        </div>
        {row.history.length > 0 && <details className="contextReviewHistory"><summary>Review history ({row.history.length})</summary>
          <ol>{row.history.map(event => <li key={event.id}>
            <span>{eventLabels[event.action] ?? event.action} · Version {event.item_version}
              {event.resolution ? ` · ${event.resolution.replaceAll("_", " ")}` : ""}{event.undone_at ? " · Undone" : ""}</span>
            <time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString()}</time>
            {!event.undone_at && event.item_id === row.item.id && <button type="button" className="secondaryButton" disabled={disabled || (event.action.startsWith("confirm") && event.item_version !== row.item.current_version)}
              onClick={() => void perform(`/api/context/review/events/${encodeURIComponent(event.id)}/undo`, { expected_version: row.item.current_version }, "Review action undone. Item history is preserved.")}>Undo review action</button>}
          </li>)}</ol>
        </details>}
      </article>)}
    </div>
    {data && data.total > 50 && <nav className="contextReviewPagination" aria-label="Review pages">
      <button type="button" className="secondaryButton" disabled={disabled || loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 50))}>Previous</button>
      <span>{offset + 1}–{Math.min(offset + 50, data.total)} of {data.total}</span>
      <button type="button" className="secondaryButton" disabled={disabled || loading || offset + 50 >= data.total} onClick={() => setOffset(value => value + 50)}>Next</button>
    </nav>}
    <details className="contextReviewDanger"><summary>Delete derived Library</summary>
      <p>This permanently removes Context items, their evidence and version history, briefs, spaces, review records, and queued analyses.</p>
      <p>Raw source conversations, provider credentials, destination preferences, and usage records stay on this device. To keep a recoverable copy, create an encrypted backup first.</p>
      <label htmlFor="delete-derived-library">Type <strong>DELETE LIBRARY</strong> to confirm</label>
      <input id="delete-derived-library" autoComplete="off" spellCheck={false} value={confirmation} disabled={disabled}
        onInput={event => setConfirmation(event.currentTarget.value)} />
      <button type="button" className="dangerButton" disabled={disabled || confirmation !== "DELETE LIBRARY"} onClick={() => void deleteLibrary()}>Delete Library</button>
    </details>
  </section>;
}
