import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookMarked,
  Brain,
  ChevronRight,
  CircleHelp,
  Compass,
  FolderTree,
  History,
  Home,
  Layers3,
  Lightbulb,
  Link2,
  ListTodo,
  LockKeyhole,
  Quote,
  RefreshCw,
  Scale
} from "lucide-react";

export type ContextScope = {
  scope_type: string;
  scope_key: string;
  confidence: number;
  created_at: string;
};

export type ContextEvidence = {
  id: string;
  source_conversation_id: string | null;
  source_message_id: string | null;
  source_record_id: string;
  source_external_id: string | null;
  source_message_record_id: string;
  source_provider: string;
  source_title: string;
  source_message_index: number;
  source_role: string;
  source_timestamp: string | null;
  excerpt: string;
  relationship: string;
  source_available: boolean;
  created_at: string;
};

export type ContextItem = {
  id: string;
  canonical_text: string;
  item_type: string;
  epistemic_kind: string;
  confidence: number;
  sensitivity: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
  last_confirmed_at: string | null;
  stale_at: string | null;
  scopes: ContextScope[];
  evidence: ContextEvidence[];
  versions: Array<{
    version: number;
    canonical_text: string;
    change_reason: string;
    created_at: string;
  }>;
  links: Array<{
    source_item_id: string;
    target_item_id: string;
    relationship: string;
    created_at: string;
  }>;
};

export type ContextBrief = {
  id: string;
  source_conversation_id: string | null;
  source_record_id: string;
  source_provider: string;
  source_title: string;
  source_created_at: string;
  main_subject: string;
  user_goal: string;
  important_outcomes: string[];
  decisions: string[];
  lessons: string[];
  unresolved_questions: string[];
  actions: string[];
  analysis_mode: string;
  analysis_status: string;
  created_at: string;
  updated_at: string;
  context_item_ids: string[];
  item_count: number;
};

export type ContextScopeGroup = {
  key: string;
  label: string;
  kind: string;
  items: ContextItem[];
};

type HomeSection = {
  key: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  itemTypes: string[];
};

export type ContextBriefEntry = {
  id: string;
  text: string;
  sourceTitle: string;
};

const homeSections: HomeSection[] = [
  {
    key: "insights",
    title: "Insights & lessons",
    description: "Useful patterns and concepts carried forward from your conversations.",
    icon: <Lightbulb size={18} />,
    itemTypes: ["insight", "concept", "lesson", "value", "preference", "project_fact"]
  },
  {
    key: "decisions",
    title: "Decisions",
    description: "Choices that should remain visible with their supporting context.",
    icon: <Scale size={18} />,
    itemTypes: ["decision"]
  },
  {
    key: "questions",
    title: "Open questions & follow-up",
    description: "Unresolved threads worth returning to.",
    icon: <CircleHelp size={18} />,
    itemTypes: ["open_question", "follow_up"]
  },
  {
    key: "actions",
    title: "Actions",
    description: "Concrete next steps extracted from active work.",
    icon: <ListTodo size={18} />,
    itemTypes: ["action"]
  }
];

const fixedScopes = [
  { key: "core_self", label: "Core Self", kind: "core_self" },
  { key: "personal", label: "Personal", kind: "personal" },
  { key: "work", label: "Work", kind: "work" }
];

export function buildContextScopeGroups(items: ContextItem[]): ContextScopeGroup[] {
  const groups = new Map<string, ContextScopeGroup>();
  for (const scope of fixedScopes) {
    groups.set(scope.key, { ...scope, items: [] });
  }

  for (const item of items) {
    for (const scope of item.scopes) {
      const key = scope.scope_key ? `${scope.scope_type}:${scope.scope_key}` : scope.scope_type;
      const existing = groups.get(key);
      if (existing) {
        existing.items.push(item);
        continue;
      }
      groups.set(key, {
        key,
        label: scope.scope_key || scopeLabel(scope.scope_type),
        kind: scope.scope_type,
        items: [item]
      });
    }
  }

  return Array.from(groups.values()).sort((left, right) => {
    const kindOrder = ["core_self", "personal", "work", "project", "topic", "destination"];
    const kindDifference = kindOrder.indexOf(left.kind) - kindOrder.indexOf(right.kind);
    return kindDifference || left.label.localeCompare(right.label);
  });
}

export function contextHomeItems(items: ContextItem[], itemTypes: string[]) {
  const accepted = new Set(itemTypes);
  return items.filter((item) => item.status === "active" && accepted.has(item.item_type));
}

export function contextBriefEntries(briefs: ContextBrief[], sectionKey: string) {
  const seen = new Set<string>();
  const entries: ContextBriefEntry[] = [];
  for (const brief of briefs) {
    const values = sectionKey === "insights"
      ? [...brief.important_outcomes, ...brief.lessons]
      : sectionKey === "decisions"
        ? brief.decisions
        : sectionKey === "questions"
          ? brief.unresolved_questions
          : sectionKey === "actions"
            ? brief.actions
            : [];
    for (const [index, text] of values.entries()) {
      const normalized = text.trim().toLocaleLowerCase();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      entries.push({ id: `${brief.id}:${sectionKey}:${index}`, text, sourceTitle: brief.source_title });
    }
  }
  return entries;
}

export function ContextWorkspace({ onOpenLibrary }: { onOpenLibrary: () => void }) {
  const [view, setView] = useState<"home" | "explorer">("home");
  const [briefs, setBriefs] = useState<ContextBrief[]>([]);
  const [items, setItems] = useState<ContextItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState("");
  const [selectedGroupKey, setSelectedGroupKey] = useState("core_self");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);

  const loadContext = useCallback(async (signal?: AbortSignal) => {
    setStatus("loading");
    setError("");
    try {
      const [briefResponse, itemResponse] = await Promise.all([
        contextApi<{ results: ContextBrief[] }>("/api/context/briefs?limit=50", signal),
        contextApi<{ results: ContextItem[] }>("/api/context/items?limit=200", signal)
      ]);
      if (signal?.aborted) return;
      setBriefs(briefResponse.results ?? []);
      setItems(itemResponse.results ?? []);
      const firstPopulatedGroup = buildContextScopeGroups(itemResponse.results ?? [])
        .find((group) => group.items.length > 0);
      setSelectedGroupKey(firstPopulatedGroup?.key ?? "core_self");
      setSelectedItemId(firstPopulatedGroup?.items[0]?.id ?? null);
      setStatus("ready");
    } catch (reason) {
      if (signal?.aborted) return;
      setStatus("error");
      setError(reason instanceof Error ? reason.message : "Could not load your Context Library.");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadContext(controller.signal);
    return () => controller.abort();
  }, [loadContext]);

  const groups = useMemo(() => buildContextScopeGroups(items), [items]);
  const selectedGroup = groups.find((group) => group.key === selectedGroupKey) ?? groups[0];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  const activeItems = useMemo(() => items.filter((item) => item.status === "active"), [items]);
  const projectAndTopicGroups = groups.filter(
    (group) => (group.kind === "project" || group.kind === "topic") && group.items.length > 0
  );

  function openExplorer(item?: ContextItem) {
    if (item) {
      setSelectedItemId(item.id);
      setSelectedGroupKey(item.scopes[0]?.scope_key
        ? `${item.scopes[0].scope_type}:${item.scopes[0].scope_key}`
        : item.scopes[0]?.scope_type ?? "core_self");
    }
    setView("explorer");
  }

  function selectGroup(group: ContextScopeGroup) {
    setSelectedGroupKey(group.key);
    setSelectedItemId(group.items[0]?.id ?? null);
  }

  return (
    <section className="contextScreen" aria-labelledby="context-title">
      <header className="contextHeader">
        <div>
          <span className="contextEyebrow"><Compass size={15} /> Linked Context Library</span>
          <h1 id="context-title">Context</h1>
          <p>A calm, source-grounded view of what your conversations are helping you build.</p>
        </div>
        {status === "ready" && items.length > 0 && (
          <div className="contextTotals" aria-label="Context Library totals">
            <strong>{activeItems.length}</strong>
            <span>active items from {briefs.length} conversations</span>
          </div>
        )}
      </header>

      <div className="contextViewTabs" role="tablist" aria-label="Context views">
        <button
          type="button"
          role="tab"
          aria-selected={view === "home"}
          className={view === "home" ? "active" : ""}
          onClick={() => setView("home")}
        >
          <Home size={17} /> Home
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "explorer"}
          className={view === "explorer" ? "active" : ""}
          onClick={() => openExplorer()}
        >
          <FolderTree size={17} /> Explorer
        </button>
      </div>

      {status === "loading" && <ContextLoading />}
      {status === "error" && <ContextError message={error} onRetry={loadContext} />}
      {status === "ready" && briefs.length === 0 && items.length === 0 && (
        <ContextEmpty onOpenLibrary={onOpenLibrary} />
      )}
      {status === "ready" && (briefs.length > 0 || items.length > 0) && view === "home" && (
        <ContextHome
          briefs={briefs}
          items={activeItems}
          projectAndTopicGroups={projectAndTopicGroups}
          onOpenExplorer={openExplorer}
        />
      )}
      {status === "ready" && (briefs.length > 0 || items.length > 0) && view === "explorer" && (
        <ContextExplorer
          groups={groups}
          selectedGroup={selectedGroup}
          selectedItem={selectedItem}
          onSelectGroup={selectGroup}
          onSelectItem={(item) => setSelectedItemId(item.id)}
        />
      )}
    </section>
  );
}

function ContextHome({
  briefs,
  items,
  projectAndTopicGroups,
  onOpenExplorer
}: {
  briefs: ContextBrief[];
  items: ContextItem[];
  projectAndTopicGroups: ContextScopeGroup[];
  onOpenExplorer: (item?: ContextItem) => void;
}) {
  return (
    <div className="contextHome" role="tabpanel">
      <section className="contextNow" aria-labelledby="context-now-title">
        <div className="contextSectionHeading">
          <div>
            <span className="contextEyebrow"><Layers3 size={15} /> Current context</span>
            <h2 id="context-now-title">What is taking shape</h2>
          </div>
          <button className="contextTextButton" type="button" onClick={() => onOpenExplorer()}>
            Browse all context <ChevronRight size={16} />
          </button>
        </div>
        {projectAndTopicGroups.length > 0 && (
          <div className="contextScopeStrip" aria-label="Active projects and topics">
            {projectAndTopicGroups.slice(0, 8).map((group) => (
              <span key={group.key}>
                {group.kind === "project" ? "Project" : "Topic"} · {group.label}
                <b>{group.items.length}</b>
              </span>
            ))}
          </div>
        )}
        <div className="briefGrid">
          {briefs.slice(0, 3).map((brief) => (
            <article className="briefCard" key={brief.id}>
              <div className="briefMeta">
                <span>{formatContextLabel(brief.analysis_mode)}</span>
                <time dateTime={brief.updated_at}>{formatContextDate(brief.updated_at)}</time>
              </div>
              <h3>{brief.main_subject}</h3>
              {brief.user_goal && <p>{brief.user_goal}</p>}
              <footer>
                <BookMarked size={15} />
                <span title={brief.source_title}>{brief.source_title}</span>
                <b>{brief.item_count} items</b>
              </footer>
            </article>
          ))}
        </div>
      </section>

      <div className="contextHomeSections">
        {homeSections.map((section) => {
          const sectionItems = contextHomeItems(items, section.itemTypes);
          const itemTexts = new Set(
            sectionItems.map((item) => item.canonical_text.trim().toLocaleLowerCase())
          );
          const briefEntries = contextBriefEntries(briefs, section.key)
            .filter((entry) => !itemTexts.has(entry.text.trim().toLocaleLowerCase()));
          const sectionCount = sectionItems.length + briefEntries.length;
          return (
            <section className="contextCollection" aria-labelledby={`context-${section.key}`} key={section.key}>
              <div className="contextCollectionHeading">
                <span>{section.icon}</span>
                <div>
                  <h2 id={`context-${section.key}`}>{section.title}</h2>
                  <p>{section.description}</p>
                </div>
                <b>{sectionCount}</b>
              </div>
              {sectionCount > 0 ? (
                <div className="contextCardList">
                  {sectionItems.slice(0, 4).map((item) => (
                    <button className="contextItemCard" type="button" onClick={() => onOpenExplorer(item)} key={item.id}>
                      <span className="contextItemType">{formatContextLabel(item.item_type)}</span>
                      <strong>{item.canonical_text}</strong>
                      <small>
                        {scopeSummary(item)}
                        <ChevronRight size={15} />
                      </small>
                    </button>
                  ))}
                  {briefEntries.slice(0, Math.max(0, 4 - sectionItems.length)).map((entry) => (
                    <article className="contextBriefEntry" key={entry.id}>
                      <span className="contextItemType">Conversation Brief</span>
                      <strong>{entry.text}</strong>
                      <small>{entry.sourceTitle}</small>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="contextCollectionEmpty">Nothing established here yet.</p>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ContextExplorer({
  groups,
  selectedGroup,
  selectedItem,
  onSelectGroup,
  onSelectItem
}: {
  groups: ContextScopeGroup[];
  selectedGroup: ContextScopeGroup;
  selectedItem: ContextItem | null;
  onSelectGroup: (group: ContextScopeGroup) => void;
  onSelectItem: (item: ContextItem) => void;
}) {
  return (
    <div className="contextExplorer" role="tabpanel">
      <aside className="contextScopeRail" aria-label="Context scopes">
        <div className="explorerPaneTitle">
          <FolderTree size={17} />
          <strong>Spaces</strong>
        </div>
        <nav aria-label="Browse Context by scope">
          {groups.map((group) => (
            <button
              type="button"
              className={group.key === selectedGroup.key ? "active" : ""}
              aria-current={group.key === selectedGroup.key ? "page" : undefined}
              onClick={() => onSelectGroup(group)}
              key={group.key}
            >
              <ScopeIcon kind={group.kind} />
              <span>
                <strong>{group.label}</strong>
                <small>{formatContextLabel(group.kind)}</small>
              </span>
              <b>{group.items.length}</b>
            </button>
          ))}
        </nav>
      </aside>

      <section className="contextItemPane" aria-labelledby="context-scope-title">
        <div className="explorerPaneHeading">
          <div>
            <span>{formatContextLabel(selectedGroup.kind)}</span>
            <h2 id="context-scope-title">{selectedGroup.label}</h2>
          </div>
          <b>{selectedGroup.items.length} items</b>
        </div>
        {selectedGroup.items.length > 0 ? (
          <div className="explorerItemList">
            {selectedGroup.items.map((item) => (
              <button
                type="button"
                className={item.id === selectedItem?.id ? "active" : ""}
                aria-pressed={item.id === selectedItem?.id}
                onClick={() => onSelectItem(item)}
                key={item.id}
              >
                <span>{formatContextLabel(item.item_type)}</span>
                <strong>{item.canonical_text}</strong>
                <small>{formatContextDate(item.updated_at)} · {Math.round(item.confidence * 100)}% confidence</small>
              </button>
            ))}
          </div>
        ) : (
          <div className="explorerEmpty">
            <Brain size={24} />
            <h3>No context here yet</h3>
            <p>Reweave keeps this space quiet until a conversation supports something worth carrying forward.</p>
          </div>
        )}
      </section>

      <aside className="contextDetailPane" aria-label="Selected Context Item">
        {selectedItem ? <ContextItemDetail item={selectedItem} /> : (
          <div className="explorerEmpty">
            <Compass size={24} />
            <h3>Select an item</h3>
            <p>Choose a Context Item to see its source, confidence, scope, and history.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

function ContextItemDetail({ item }: { item: ContextItem }) {
  const evidence = item.evidence[0];
  return (
    <article className="contextDetail">
      <header>
        <div className="contextDetailLabels">
          <span>{formatContextLabel(item.item_type)}</span>
          <span>{formatContextLabel(item.epistemic_kind)}</span>
          {item.sensitivity === "sensitive" && <span className="sensitive"><LockKeyhole size={12} /> Sensitive</span>}
        </div>
        <h2>{item.canonical_text}</h2>
        <p>Last updated {formatContextDate(item.updated_at)}</p>
      </header>
      <dl className="contextMetadata">
        <div><dt>Confidence</dt><dd>{Math.round(item.confidence * 100)}%</dd></div>
        <div><dt>Status</dt><dd>{formatContextLabel(item.status)}</dd></div>
        <div><dt>Version</dt><dd>{item.current_version}</dd></div>
      </dl>
      <section>
        <h3><Layers3 size={15} /> Scopes</h3>
        <div className="contextDetailScopes">
          {item.scopes.map((scope) => (
            <span key={`${scope.scope_type}:${scope.scope_key}`}>
              {scope.scope_key || scopeLabel(scope.scope_type)}
            </span>
          ))}
        </div>
      </section>
      <section>
        <h3><Quote size={15} /> Source evidence</h3>
        {evidence ? (
          <figure className="contextEvidence">
            <blockquote>{evidence.excerpt}</blockquote>
            <figcaption>
              <BookMarked size={14} />
              <span>{evidence.source_title}</span>
              <b>{evidence.source_available ? "Source available" : "Snapshot retained"}</b>
            </figcaption>
          </figure>
        ) : <p className="contextDetailMuted">No compact evidence is available.</p>}
        <p className="contextEvidenceNote">Opening the exact source conversation is part of the next delivery slice.</p>
      </section>
      <section>
        <h3><History size={15} /> History & links</h3>
        <p className="contextDetailMuted">
          Version {item.current_version} · {item.links.length} linked item{item.links.length === 1 ? "" : "s"}
        </p>
      </section>
    </article>
  );
}

function ContextLoading() {
  return (
    <div className="contextLoading" role="status" aria-live="polite">
      <RefreshCw className="spin" size={20} />
      <strong>Gathering your Context Library…</strong>
      <span>Loading source-grounded briefs and items from this device.</span>
    </div>
  );
}

function ContextError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="contextStateCard" role="alert">
      <AlertTriangle size={26} />
      <h2>Context could not be loaded</h2>
      <p>{message}</p>
      <button className="secondaryButton" type="button" onClick={() => onRetry()}>
        <RefreshCw size={16} /> Try again
      </button>
    </div>
  );
}

function ContextEmpty({ onOpenLibrary }: { onOpenLibrary: () => void }) {
  return (
    <div className="contextStateCard contextEmptyState">
      <span className="contextEmptyIcon"><Compass size={28} /></span>
      <span className="contextEyebrow">Your Context Library starts quietly</span>
      <h2>Turn one useful conversation into lasting context</h2>
      <p>
        Import or open a conversation in Library, then analyze it. Reweave will keep the brief,
        supported Context Items, and compact source evidence on this device.
      </p>
      <button className="primaryButton" type="button" onClick={onOpenLibrary}>
        <BookMarked size={16} /> Open Library
      </button>
    </div>
  );
}

function ScopeIcon({ kind }: { kind: string }) {
  if (kind === "core_self") return <Brain size={17} />;
  if (kind === "project") return <Layers3 size={17} />;
  if (kind === "topic") return <Lightbulb size={17} />;
  if (kind === "destination") return <Link2 size={17} />;
  return <FolderTree size={17} />;
}

function scopeLabel(value: string) {
  const labels: Record<string, string> = {
    core_self: "Core Self",
    personal: "Personal",
    work: "Work",
    project: "Project",
    topic: "Topic",
    destination: "Destination"
  };
  return labels[value] ?? formatContextLabel(value);
}

function scopeSummary(item: ContextItem) {
  if (!item.scopes.length) return "Unscoped";
  return item.scopes.map((scope) => scope.scope_key || scopeLabel(scope.scope_type)).join(" · ");
}

function formatContextLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatContextDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

async function contextApi<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : data;
    throw new Error(typeof detail === "string" ? detail : "Could not load your Context Library.");
  }
  return data as T;
}
