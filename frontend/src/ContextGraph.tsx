import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpRight,
  Download,
  Focus,
  Loader2,
  Network,
  RefreshCw,
  Share2,
  ShieldCheck,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import "./contextGraph.css";

export type GraphNode = {
  id: string;
  kind: "item" | "space";
  label: string;
  item_type?: string;
  epistemic_kind?: string;
  sensitivity?: string;
  scope_type?: string;
  item_count?: number;
};
export type GraphEdge = {
  source: string;
  target: string;
  relationship: string;
};
export type GraphSpace = { id: string; name: string; scope_type: string };
export type ContextGraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_items: number;
  shown_items: number;
  truncated: boolean;
  spaces: GraphSpace[];
};
type PositionedNode = GraphNode & { x: number; y: number };
type SharePreview = {
  preview_token: string;
  svg: string;
  node_count: number;
  edge_count: number;
  excluded_count: number;
  warnings: string[];
  expires_in_seconds: number;
};
const shareScopeTypes = new Set(["project", "topic", "work", "destination"]);

export function rawSpaceId(nodeId: string) {
  return nodeId.startsWith("space:") ? nodeId.slice(6) : nodeId;
}

export function layoutContextGraph(nodes: GraphNode[], edges: GraphEdge[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const spaces = nodes
    .filter((node) => node.kind === "space")
    .sort((a, b) => a.id.localeCompare(b.id));
  const groups = new Map<string, GraphNode[]>(
    spaces.map((space) => [space.id, []]),
  );
  groups.set("", []);
  const memberships = new Map<string, string[]>();
  for (const edge of edges) {
    const source = byId.get(edge.source);
    const target = byId.get(edge.target);
    const item =
      source?.kind === "item"
        ? source
        : target?.kind === "item"
          ? target
          : null;
    const space =
      source?.kind === "space"
        ? source
        : target?.kind === "space"
          ? target
          : null;
    if (item && space)
      memberships.set(item.id, [...(memberships.get(item.id) ?? []), space.id]);
  }
  for (const item of nodes
    .filter((node) => node.kind === "item")
    .sort((a, b) => a.id.localeCompare(b.id))) {
    const owner = (memberships.get(item.id) ?? []).sort()[0] ?? "";
    groups.get(owner)?.push(item);
  }
  const positioned: PositionedNode[] = [];
  let y = 36;
  for (const [spaceId, items] of groups) {
    if (!spaceId && !items.length) continue;
    const rows = Math.max(1, Math.ceil(items.length / 3));
    const height = rows * 100 + 28;
    const space = byId.get(spaceId);
    if (space) positioned.push({ ...space, x: 130, y: y + height / 2 });
    for (const [index, item] of items.entries())
      positioned.push({
        ...item,
        x: 390 + (index % 3) * 230,
        y: y + 48 + Math.floor(index / 3) * 100,
      });
    y += height + 32;
  }
  return { nodes: positioned, width: 1000, height: Math.max(250, y) };
}

export function graphSharePayload(
  spaceIds: string[],
  labels: Record<string, string>,
) {
  return {
    space_ids: [...new Set(spaceIds)],
    labels: Object.fromEntries(
      Object.entries(labels)
        .filter(([, value]) => value.trim())
        .map(([id, value]) => [id, value.trim()]),
    ),
  };
}

function readable(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function nodeLines(value: string) {
  const words = value.trim().split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    if ((line + " " + word).trim().length > 23 && line) {
      lines.push(line);
      line = "";
    }
    line = line ? `${line} ${word}` : word.slice(0, 25);
    if (lines.length === 2) break;
  }
  if (line && lines.length < 3) lines.push(line);
  if (lines.join(" ").length < value.length && lines.length)
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, 22)}…`;
  return lines;
}

export function ContextGraph({
  onOpenItem,
}: {
  onOpenItem: (id: string) => Promise<boolean> | boolean;
}) {
  const [graph, setGraph] = useState<ContextGraphData | null>(null);
  const [spaceId, setSpaceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [zoom, setZoom] = useState(1);
  const [query, setQuery] = useState("");
  const request = useRef(0);
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const current = ++request.current;
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ limit: "200" });
        if (spaceId) params.set("space_id", spaceId);
        const data = await graphApi<ContextGraphData>(
          `/api/context/graph?${params}`,
          { signal },
        );
        if (signal?.aborted || current !== request.current) return;
        setGraph(data);
        setSelectedId((id) =>
          data.nodes.some((node) => node.id === id) ? id : "",
        );
      } catch (reason) {
        if (!signal?.aborted && current === request.current)
          setError(
            reason instanceof Error
              ? reason.message
              : "The graph could not be loaded. Try again.",
          );
      } finally {
        if (!signal?.aborted && current === request.current) setLoading(false);
      }
    },
    [spaceId],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const refresh = () => void load(controller.signal);
    window.addEventListener("reweave:context-changed", refresh);
    return () => {
      controller.abort();
      window.removeEventListener("reweave:context-changed", refresh);
    };
  }, [load]);
  const layout = useMemo(
    () => layoutContextGraph(graph?.nodes ?? [], graph?.edges ?? []),
    [graph],
  );
  const positions = new Map(layout.nodes.map((node) => [node.id, node]));
  const selected = graph?.nodes.find((node) => node.id === selectedId);
  const visibleList =
    graph?.nodes.filter((node) =>
      node.label.toLocaleLowerCase().includes(query.toLocaleLowerCase()),
    ) ?? [];
  const selectedEdges =
    graph?.edges.filter(
      (edge) => edge.source === selectedId || edge.target === selectedId,
    ) ?? [];

  function activate(node: GraphNode) {
    if (node.kind === "space") {
      setSpaceId(rawSpaceId(node.id));
      setZoom(1);
    } else setSelectedId(node.id);
  }
  async function openSelected() {
    if (!selected || selected.kind !== "item") return;
    try {
      if (!(await onOpenItem(selected.id)))
        setError(
          "This Context Item could not be opened. The graph remains available.",
        );
    } catch {
      setError(
        "This Context Item could not be opened. Try again from the item list.",
      );
    }
  }

  return (
    <section className="contextGraph" aria-label="Explore the Context Graph">
      <div className="graphToolbar">
        <label>
          Graph space
          <select
            value={spaceId}
            onChange={(event) => {
              setSpaceId(event.target.value);
              setZoom(1);
            }}
          >
            <option value="">All spaces</option>
            {graph?.spaces.map((space) => (
              <option key={space.id} value={space.id}>
                {readable(space.scope_type)} · {space.name}
              </option>
            ))}
          </select>
        </label>
        <div className="graphZoom" role="group" aria-label="Graph zoom">
          <button
            type="button"
            className="iconButton"
            aria-label="Zoom out graph"
            disabled={zoom <= 0.5}
            onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}
          >
            <ZoomOut size={17} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="iconButton"
            aria-label="Zoom in graph"
            disabled={zoom >= 2}
            onClick={() => setZoom((value) => Math.min(2, value + 0.25))}
          >
            <ZoomIn size={17} />
          </button>
          <button
            type="button"
            className="secondaryButton"
            onClick={() => setZoom(1)}
          >
            <Focus size={16} /> Reset
          </button>
          <button
            type="button"
            className="iconButton"
            aria-label="Refresh graph"
            onClick={() => void load()}
            disabled={loading}
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>
      <p className="graphExplanation">
        Space lines show membership. Other lines show recorded relationships
        between Context Items. Select an item to inspect its connections and
        sources.
      </p>
      {graph?.truncated && (
        <p className="graphSubsetNotice" role="status">
          Showing {graph.shown_items} of {graph.total_items} items in this
          graph. Choose a space to narrow the view; Explore's list and Search
          remain available for the rest.
        </p>
      )}
      {error && (
        <p className="contextEvidenceError" role="alert">
          {error}
        </p>
      )}
      {loading && (
        <p role="status" className="graphLoading">
          <Loader2 className="spin" size={18} /> Loading recorded connections…
        </p>
      )}
      {graph && graph.nodes.length > 0 ? (
        <>
          <div
            className="graphCanvas"
            aria-busy={loading}
            tabIndex={0}
            aria-label="Scrollable Context Graph"
          >
            <svg
              role="group"
              aria-label="Local Context Graph nodes"
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              style={{ width: `${zoom * 100}%`, minWidth: `${1000 * zoom}px` }}
            >
              <title>Your recorded context and spaces</title>
              <desc>
                Space nodes filter the graph. Item nodes select context for
                inspection. The same nodes and relationships are available in
                the list below.
              </desc>
              <g className="graphEdges" aria-hidden="true">
                {graph.edges.map((edge, index) => {
                  const start = positions.get(edge.source);
                  const end = positions.get(edge.target);
                  if (!start || !end) return null;
                  const active =
                    edge.source === selectedId || edge.target === selectedId;
                  return (
                    <g
                      key={`${edge.source}:${edge.target}:${edge.relationship}:${index}`}
                      className={active ? "selected" : ""}
                    >
                      <path
                        d={`M ${start.x} ${start.y} C ${(start.x + end.x) / 2} ${start.y}, ${(start.x + end.x) / 2} ${end.y}, ${end.x} ${end.y}`}
                      />
                      <title>{readable(edge.relationship)}</title>
                    </g>
                  );
                })}
              </g>
              <g className="graphNodes">
                {layout.nodes.map((node) => (
                  <g
                    key={node.id}
                    className={`graphNode ${node.kind}${node.id === selectedId ? " selected" : ""}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`${node.kind === "space" ? "Filter space" : "Inspect item"}: ${node.label}`}
                    onClick={() => activate(node)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        activate(node);
                      }
                    }}
                  >
                    <title>{node.label}</title>
                    <rect
                      x={node.x - 100}
                      y={node.y - 38}
                      width={200}
                      height={76}
                      rx={8}
                    />
                    <text
                      className="graphNodeKind"
                      x={node.x - 88}
                      y={node.y - 22}
                    >
                      {readable(
                        node.kind === "space"
                          ? (node.scope_type ?? "space")
                          : (node.item_type ?? "context"),
                      )}
                    </text>
                    <text x={node.x - 88} y={node.y - 4}>
                      {nodeLines(node.label).map((line, index) => (
                        <tspan key={index} x={node.x - 88} dy={index ? 17 : 0}>
                          {line}
                        </tspan>
                      ))}
                    </text>
                  </g>
                ))}
              </g>
            </svg>
          </div>
          {selected && (
            <section
              className="graphSelection"
              aria-label="Selected graph item"
            >
              <div>
                <span className="contextEyebrow">
                  {readable(selected.item_type ?? selected.kind)}
                  {selected.epistemic_kind
                    ? ` · ${readable(selected.epistemic_kind)}`
                    : ""}
                  {selected.sensitivity === "sensitive" ? " · Sensitive" : ""}
                </span>
                <h3>{selected.label}</h3>
                <button
                  type="button"
                  className="contextTextButton"
                  onClick={() => void openSelected()}
                >
                  Read context &amp; sources <ArrowUpRight size={15} />
                </button>
              </div>
              <div>
                <h4>Recorded relationships</h4>
                {selectedEdges.length ? (
                  <ul>
                    {selectedEdges.map((edge, index) => {
                      const otherId =
                        edge.source === selectedId ? edge.target : edge.source;
                      const other = graph.nodes.find(
                        (node) => node.id === otherId,
                      );
                      return (
                        <li key={`${otherId}:${index}`}>
                          <span>{readable(edge.relationship)}</span>
                          {other ? (
                            <button
                              type="button"
                              className="contextTextButton"
                              onClick={() => activate(other)}
                            >
                              {other.label}
                            </button>
                          ) : (
                            <span>Related context unavailable</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p>No direct relationships recorded yet.</p>
                )}
              </div>
            </section>
          )}
          <details className="graphAccessibleList" open>
            <summary>
              Browse graph nodes as a list ({graph.nodes.length})
            </summary>
            <label>
              Find in graph
              <input
                value={query}
                onInput={(event) => setQuery(event.currentTarget.value)}
                placeholder="An item or space name"
              />
            </label>
            <div className="graphNodeList">
              {visibleList.map((node) => (
                <button
                  type="button"
                  key={node.id}
                  className={selectedId === node.id ? "selected" : ""}
                  onClick={() => activate(node)}
                >
                  <span>
                    {node.kind === "space"
                      ? "Space"
                      : readable(node.item_type ?? "item")}
                  </span>
                  <strong>{node.label}</strong>
                  <small>
                    {node.kind === "space"
                      ? "Filter to this space"
                      : "Inspect connections"}
                  </small>
                </button>
              ))}
            </div>
            {!visibleList.length && (
              <p>No nodes match this phrase in the loaded graph.</p>
            )}
          </details>
        </>
      ) : (
        !loading && (
          <div className="graphEmpty">
            <Network size={28} />
            <h3>No recorded connections here yet</h3>
            <p>
              Save and analyze a conversation, or choose another space. Graph
              uses the same Context Items and source links as Explore.
            </p>
          </div>
        )
      )}
      {graph && <GraphSharing graph={graph} />}
    </section>
  );
}

export function GraphSharing({ graph }: { graph: ContextGraphData }) {
  const [open, setOpen] = useState(false);
  const [spaceIds, setSpaceIds] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<SharePreview | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewRendered, setPreviewRendered] = useState(false);
  const [expiresAt, setExpiresAt] = useState(0);
  const [busy, setBusy] = useState<"preview" | "export" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const revision = useRef(0);
  const previewRequest = useRef<AbortController | null>(null);
  const previewButton = useRef<HTMLButtonElement>(null);
  const shareButton = useRef<HTMLButtonElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null);
  const allowedSpaces = graph.spaces.filter((space) =>
    shareScopeTypes.has(space.scope_type),
  );
  const selectedIds = new Set(spaceIds);
  const membership = new Map<string, Set<string>>();
  for (const edge of graph.edges) {
    const spaceNode = edge.source.startsWith("space:")
      ? edge.source
      : edge.target.startsWith("space:")
        ? edge.target
        : null;
    const itemId = edge.source.startsWith("space:") ? edge.target : edge.source;
    if (spaceNode)
      membership.set(
        itemId,
        new Set([...(membership.get(itemId) ?? []), rawSpaceId(spaceNode)]),
      );
  }
  const labelNodes = graph.nodes.filter((node) =>
    node.kind === "space"
      ? selectedIds.has(rawSpaceId(node.id))
      : node.sensitivity !== "sensitive" &&
        [...(membership.get(node.id) ?? [])].some((id) => selectedIds.has(id)),
  );

  function invalidate() {
    revision.current += 1;
    previewRequest.current?.abort();
    setPreview(null);
    setPreviewRendered(false);
    setExpiresAt(0);
    setBusy(null);
    setError("");
    setNotice("");
  }
  useEffect(() => {
    invalidate();
    setSpaceIds((current) =>
      current.filter((id) =>
        graph.spaces.some(
          (space) => space.id === id && shareScopeTypes.has(space.scope_type),
        ),
      ),
    );
  }, [graph]);
  useEffect(() => {
    if (!preview) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(
      new Blob([preview.svg], { type: "image/svg+xml" }),
    );
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [preview]);
  useEffect(() => () => previewRequest.current?.abort(), []);
  useEffect(() => {
    if (error && !busy) previewButton.current?.focus();
  }, [error, busy]);
  useEffect(() => {
    if (!preview || !expiresAt) return;
    const timer = window.setTimeout(
      () => {
        setPreview(null);
        setPreviewRendered(false);
        setNotice(
          "This preview expired. Prepare a new preview before exporting.",
        );
      },
      Math.max(0, expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [preview, expiresAt]);

  async function createPreview() {
    if (!spaceIds.length || busy) return;
    invalidate();
    const current = revision.current;
    const controller = new AbortController();
    previewRequest.current = controller;
    setBusy("preview");
    try {
      const payload = graphSharePayload(
        spaceIds,
        Object.fromEntries(
          labelNodes
            .filter((node) => labels[node.id]?.trim())
            .map((node) => [node.id, labels[node.id]]),
        ),
      );
      const result = await graphApi<SharePreview>(
        "/api/context/graph/share/preview",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        },
      );
      if (current !== revision.current || controller.signal.aborted) return;
      inspectShareSvg(result.svg);
      setPreview(result);
      setExpiresAt(Date.now() + result.expires_in_seconds * 1000);
    } catch (reason) {
      if (current === revision.current && !controller.signal.aborted) {
        setError(
          reason instanceof Error
            ? reason.message
            : "The share preview could not be prepared. Try again.",
        );
        previewButton.current?.focus();
      }
    } finally {
      if (current === revision.current) setBusy(null);
    }
  }

  async function exportPreview() {
    if (!preview || !previewRendered || busy) return;
    if (Date.now() >= expiresAt) {
      invalidate();
      setError("This preview expired. Prepare a new preview before exporting.");
      previewButton.current?.focus();
      return;
    }
    setBusy("export");
    setError("");
    const approved = preview;
    const current = revision.current;
    try {
      const response = await fetch("/api/context/graph/share/export", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preview_token: approved.preview_token,
          confirmation: "EXPORT",
        }),
      });
      if (!response.ok)
        throw new Error(
          response.status === 409 || response.status === 410
            ? "This preview is expired or already used. Prepare a new preview."
            : "The graph could not be exported. Prepare a new preview and try again.",
        );
      const svg = await response.text();
      if (current !== revision.current) return;
      if (svg !== approved.svg)
        throw new Error(
          "The export did not match the preview. Prepare a new preview before sharing.",
        );
      const png = await shareSvgToPng(svg);
      if (current !== revision.current) return;
      const url = URL.createObjectURL(png);
      const anchor = document.createElement("a");
      try {
        anchor.href = url;
        anchor.download = `Reweave-shared-graph-${new Date().toISOString().slice(0, 10)}.png`;
        document.body.append(anchor);
        anchor.click();
      } finally {
        anchor.remove();
        URL.revokeObjectURL(url);
      }
      setPreview(null);
      setPreviewRendered(false);
      setNotice(
        "The approved redacted graph was prepared as a PNG download. Nothing was published or sent to another service.",
      );
    } catch (reason) {
      if (current === revision.current) {
        setPreview(null);
        setPreviewRendered(false);
        setError(
          reason instanceof Error
            ? reason.message
            : "The PNG could not be created. Prepare a new preview and try again.",
        );
        previewButton.current?.focus();
      }
    } finally {
      if (current === revision.current) setBusy(null);
    }
  }

  function cancel() {
    invalidate();
    setSpaceIds([]);
    setLabels({});
    shareButton.current?.focus();
  }

  return (
    <section className="graphSharing">
      <button
        ref={shareButton}
        type="button"
        className="secondaryButton"
        aria-expanded={open}
        disabled={busy === "export"}
        onClick={() => {
          if (open) cancel();
          setOpen(!open);
        }}
      >
        <Share2 size={16} /> Share a redacted graph
      </button>
      {open && (
        <div className="graphSharingBody">
          <div className="graphShareIntro">
            <ShieldCheck size={22} />
            <div>
              <h3>Choose what may leave this library</h3>
              <p>
                Original names, source text, and evidence are removed by
                default. The preview uses generic labels such as Project 1 and
                Decision 1. Personal, Core Self, sensitive, and disallowed
                cross-scope context is excluded.
              </p>
            </div>
          </div>
          <fieldset className="graphShareScopes">
            <legend>Spaces to include</legend>
            {allowedSpaces.length ? (
              allowedSpaces.map((space) => (
                <label key={space.id}>
                  <input
                    type="checkbox"
                    checked={spaceIds.includes(space.id)}
                    disabled={busy === "export"}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      invalidate();
                      setSpaceIds((current) =>
                        checked
                          ? [...current, space.id]
                          : current.filter((id) => id !== space.id),
                      );
                    }}
                  />
                  <span>
                    {readable(space.scope_type)} · {space.name}
                  </span>
                </label>
              ))
            ) : (
              <p>
                No eligible work, project, topic, or destination spaces are
                available.
              </p>
            )}
          </fieldset>
          {spaceIds.length > 1 && (
            <p className="graphShareWarning">
              This preview combines several selected spaces. Review cross-space
              relationships before exporting.
            </p>
          )}
          {labelNodes.length > 0 && (
            <details className="publicLabelEditor">
              <summary>Optional public labels · start from blank</summary>
              <p>
                Type new public wording only if generic labels are not enough.
                Your written labels can reveal details; do not include private
                context. The server may exclude nodes whose other scopes are not
                allowed.
              </p>
              {labelNodes.map((node) => (
                <label key={node.id}>
                  <span>
                    {node.label}
                    <small>
                      Local reference only; never copied automatically
                    </small>
                  </span>
                  <input
                    value={labels[node.id] ?? ""}
                    onInput={(event) => {
                      const value = event.currentTarget.value;
                      invalidate();
                      setLabels((current) => ({
                        ...current,
                        [node.id]: value,
                      }));
                    }}
                    maxLength={80}
                    placeholder="New public label (optional)"
                    disabled={busy === "export"}
                    aria-label={`Public label for ${node.label}`}
                  />
                </label>
              ))}
            </details>
          )}
          {Object.values(labels).some((value) => value.trim()) && (
            <p className="graphShareWarning">
              Your written public labels will be visible in the exported image.
              Check them in the preview.
            </p>
          )}
          <div className="buttonRow">
            <button
              ref={previewButton}
              type="button"
              className="secondaryButton"
              onClick={() => void createPreview()}
              disabled={!spaceIds.length || busy !== null}
            >
              {busy === "preview" ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <RefreshCw size={16} />
              )}
              {busy === "preview"
                ? "Preparing preview…"
                : "Preview redacted graph"}
            </button>
            <button
              type="button"
              className="contextTextButton"
              onClick={cancel}
              disabled={busy === "export"}
            >
              <X size={15} /> Cancel sharing
            </button>
          </div>
          {error && (
            <p className="contextEvidenceError" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="graphShareNotice" role="status">
              {notice}
            </p>
          )}
          {preview && previewUrl && (
            <section
              className="graphSharePreview"
              aria-label="Exact redacted graph preview"
            >
              <h3 ref={previewHeading} tabIndex={-1}>
                Review the exact image
              </h3>
              <p>
                {preview.node_count} nodes · {preview.edge_count} relationships
                · Excluded: {preview.excluded_count}. Preview expires in{" "}
                {Math.ceil(preview.expires_in_seconds / 60)} minutes.
              </p>
              {preview.warnings.length > 0 && (
                <ul className="graphShareWarnings">
                  {preview.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              )}
              <img
                src={previewUrl}
                alt={`Redacted graph preview with ${preview.node_count} nodes and ${preview.edge_count} relationships`}
                onLoad={() => {
                  setPreviewRendered(true);
                  previewHeading.current?.focus();
                }}
                onError={() => {
                  invalidate();
                  setError(
                    "The preview image could not be displayed. Prepare a new preview before exporting.",
                  );
                  previewButton.current?.focus();
                }}
              />
              <button
                type="button"
                className="primaryButton"
                onClick={() => void exportPreview()}
                disabled={!previewRendered || busy !== null}
              >
                {busy === "export" ? (
                  <Loader2 className="spin" size={16} />
                ) : (
                  <Download size={16} />
                )}
                {busy === "export"
                  ? "Creating PNG…"
                  : "Export this preview as PNG"}
              </button>
            </section>
          )}
        </div>
      )}
    </section>
  );
}

export function inspectShareSvg(svg: string) {
  if (/<!DOCTYPE|<!ENTITY/i.test(svg))
    throw new Error("The preview includes unsupported external content.");
  const document = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = document.documentElement;
  if (root.localName !== "svg" || document.querySelector("parsererror"))
    throw new Error("The preview is not a valid SVG image.");
  for (const element of [root, ...Array.from(root.querySelectorAll("*"))]) {
    if (
      [
        "script",
        "foreignobject",
        "image",
        "use",
        "iframe",
        "a",
        "animate",
        "animatetransform",
        "set",
      ].includes(element.localName.toLowerCase())
    )
      throw new Error("The preview includes unsupported external content.");
    for (const attribute of Array.from(element.attributes)) {
      if (
        /^on/i.test(attribute.name) ||
        (/href$/i.test(attribute.name) && !attribute.value.startsWith("#"))
      )
        throw new Error("The preview includes unsupported external content.");
      if (externalStyleReference(attribute.value))
        throw new Error("The preview includes external style references.");
    }
    if (
      element.localName === "style" &&
      externalStyleReference(element.textContent ?? "")
    )
      throw new Error("The preview includes external style references.");
  }
  const box = (root.getAttribute("viewBox") ?? "").split(/[\s,]+/).map(Number);
  const width = Number.parseFloat(root.getAttribute("width") ?? "") || box[2];
  const height = Number.parseFloat(root.getAttribute("height") ?? "") || box[3];
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0 ||
    width * height > 32_000_000
  )
    throw new Error(
      "The graph is too large to export as one PNG. Select fewer spaces and preview again.",
    );
  return { width: Math.ceil(width), height: Math.ceil(height) };
}

function externalStyleReference(value: string) {
  if (/@import/i.test(value)) return true;
  return [...value.matchAll(/url\(([^)]*)\)/gi)].some(
    (match) =>
      !match[1]
        .trim()
        .replace(/^['"]|['"]$/g, "")
        .startsWith("#"),
  );
}

export async function shareSvgToPng(svg: string): Promise<Blob> {
  const { width, height } = inspectShareSvg(svg);
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () =>
        reject(
          new Error(
            "The approved image could not be rendered. Prepare a new preview and try again.",
          ),
        );
      image.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context)
      throw new Error(
        "PNG export is unavailable in this window. Reopen Reweave and try again.",
      );
    context.drawImage(image, 0, 0, width, height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) =>
          blob
            ? resolve(blob)
            : reject(
                new Error(
                  "The PNG could not be created. Prepare a new preview.",
                ),
              ),
        "image/png",
      ),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function graphApi<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "The graph request could not be completed. Refine your selection and try again.",
    );
  return data as T;
}
