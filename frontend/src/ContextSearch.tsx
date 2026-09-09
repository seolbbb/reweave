import { useEffect, useState } from "react";
import { ArrowUpRight, RefreshCw } from "lucide-react";
import "./contextSearch.css";

type Hit = {
  item_id: string; summary: string; item_type: string; epistemic_kind: string;
  confidence: number; reasons: string[]; sensitivity?: string; status?: string;
};
type SearchData = { hits: Hit[]; diagnostics: { strategy: string; semantic_available: boolean; fallback_used: boolean } };

export function ContextSearch({ query, onOpenItem }: {query: string; onOpenItem: (id: string) => void}) {
  const [data, setData] = useState<SearchData | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [spaceId, setSpaceId] = useState("");
  const [itemType, setItemType] = useState("");
  const [spaces, setSpaces] = useState<Array<{id: string; name: string; scope_type: string}>>([]);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/context/spaces", {signal: controller.signal})
      .then(async (response) => response.ok ? response.json() : null)
      .then((result) => { if (!controller.signal.aborted && Array.isArray(result?.results)) setSpaces(result.results); })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setData(null); setError("");
    if (!query.trim()) return;
    const controller = new AbortController();
    const parameters = new URLSearchParams({q: query, limit: "100"});
    if (spaceId) parameters.set("space_id", spaceId);
    if (itemType) parameters.set("item_type", itemType);
    fetch(`/api/context/search?${parameters}`, {signal: controller.signal})
      .then(async (response) => {
        if (!response.ok) throw new Error("Context search is temporarily unavailable.");
        return response.json() as Promise<SearchData>;
      }).then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not search Context."); });
    return () => controller.abort();
  }, [query, revision, spaceId, itemType]);
  if (!query.trim()) return null;
  return <section className="contextSearchResults" aria-label="Context search results">
    <header><div><span className="sectionLabel">Across your Context Library</span><h2>Context matches</h2></div>
      {data && <span role="status">{data.hits.length}{data.hits.length === 100 ? "+" : ""} matches</span>}
    </header>
    <div className="contextSearchFilters">
      <label>Context space<select value={spaceId} onChange={(event) => setSpaceId(event.target.value)}><option value="">All spaces</option>{spaces.map((space) => <option key={space.id} value={space.id}>{space.name || space.scope_type.replaceAll("_", " ")}</option>)}</select></label>
      <label>Context type<select value={itemType} onChange={(event) => setItemType(event.target.value)}><option value="">All types</option>{["project_fact", "decision", "lesson", "insight", "concept", "value", "preference", "open_question", "action", "follow_up"].map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>
      {(spaceId || itemType) && <button type="button" className="secondaryButton" onClick={() => {setSpaceId(""); setItemType("");}}>Search all Context</button>}
    </div>
    {error ? <p role="alert">{error} <button type="button" className="secondaryButton" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={16}/> Retry Context search</button></p>
      : !data ? <p role="status">Searching saved context…</p>
        : <>
          <p>{data.diagnostics.semantic_available ? "Local keyword and semantic search" : "Local keyword search · semantic model is not ready"}. Open a match to inspect its sources, connections, and history.</p>
          {data.hits.length === 0 && <p>No Context Items match. Original source matches are listed below; sources without completed analysis still remain searchable.</p>}
          <ul>{data.hits.map((hit) => <li key={hit.item_id}>
            <button type="button" className="contextSearchItem" onClick={() => onOpenItem(hit.item_id)}>
              <span>{hit.summary}</span><ArrowUpRight size={17} aria-hidden="true" />
            </button>
            <p>{hit.item_type.replaceAll("_", " ")} · {hit.epistemic_kind} · {Math.round(hit.confidence * 100)}% confidence
              {hit.sensitivity === "sensitive" ? " · Sensitive: kept local" : ""}{hit.status && hit.status !== "active" ? ` · ${hit.status}` : ""}</p>
            {hit.reasons.length > 0 && <small>{hit.reasons.join(" · ")}</small>}
          </li>)}</ul>
          {data.hits.length === 100 && <p>The first 100 ranked matches are shown. Add an exact identifier or more specific phrase to narrow the full-library search.</p>}
        </>}
  </section>;
}

export function SourceContextLinks({ conversationId, onOpenItem }: { conversationId: string; onOpenItem: (id: string) => void }) {
  const [items, setItems] = useState<Array<{id: string; canonical_text: string; epistemic_kind: string}> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setItems(null); setFailed(false);
    fetch(`/api/context/sources/${encodeURIComponent(conversationId)}`, {signal: controller.signal})
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json(); })
      .then((result) => { if (!controller.signal.aborted) setItems(result.results); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [conversationId]);
  return <details className="sourceContextLinks">
    <summary>Context from this source{items ? ` (${items.length})` : ""}</summary>
    {failed ? <p>Related context could not be loaded. The source remains available below.</p>
      : !items ? <p>Loading related context…</p>
        : items.length === 0 ? <p>No derived Context Items yet. You can queue analysis from Sources.</p>
          : <ul>{items.map((item) => <li key={item.id}><button type="button" onClick={() => onOpenItem(item.id)}>{item.canonical_text} <small>({item.epistemic_kind})</small></button></li>)}</ul>}
  </details>;
}
