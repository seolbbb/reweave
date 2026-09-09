import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  AlertTriangle,
  BookMarked,
  Brain,
  ChevronRight,
  CircleHelp,
  Compass,
  ExternalLink,
  FolderTree,
  Layers3,
  Lightbulb,
  Link2,
  ListTodo,
  Loader2,
  LockKeyhole,
  Quote,
  RefreshCw,
  Scale,
} from "lucide-react";
import { ChatUseGuide } from "./ChatUseGuide";
import { ContextManagement, SpacesManager } from "./ContextManagement";
import "./contextGraph.css";

const ContextGraph = lazy(() =>
  import("./ContextGraph").then((module) => ({ default: module.ContextGraph })),
);
const ContextReview = lazy(() =>
  import("./ContextReview").then((module) => ({ default: module.ContextReview })),
);

export type ContextScope = {
  space_id?: string;
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
  source_changed?: boolean;
  created_at: string;
};

export type ContextItem = {
  id: string;
  canonical_text: string;
  item_type: string;
  epistemic_kind: string;
  confidence: number;
  effective_confidence?: number;
  sensitivity: string;
  status: string;
  current_version: number;
  created_at: string;
  updated_at: string;
  last_confirmed_at: string | null;
  stale_at: string | null;
  authority?: string;
  inference_rationale?: string;
  scopes: ContextScope[];
  evidence: ContextEvidence[];
  versions: ContextItemVersion[];
  links: Array<{
    source_item_id: string;
    target_item_id: string;
    relationship: string;
    created_at: string;
  }>;
};

export type ContextItemVersion = {
  version: number;
  canonical_text: string;
  change_reason: string;
  created_at: string;
  item_type?: string;
  epistemic_kind?: string;
  confidence?: number;
  sensitivity?: string;
  status?: string;
  authority?: string;
  inference_rationale?: string;
  scopes?: Array<Pick<ContextScope, "scope_type" | "scope_key" | "confidence">>;
  evidence_ids?: string[];
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

export type EvidenceOpenTarget = {
  conversationId: string;
  messageIndex: number;
};

const homeSections: HomeSection[] = [
  {
    key: "decisions",
    title: "Decisions",
    description:
      "Choices that should remain visible with their supporting context.",
    icon: <Scale size={18} />,
    itemTypes: ["decision"],
  },
  {
    key: "insights",
    title: "Insights & lessons",
    description:
      "Useful patterns and concepts carried forward from your conversations.",
    icon: <Lightbulb size={18} />,
    itemTypes: [
      "insight",
      "concept",
      "lesson",
      "value",
      "preference",
      "project_fact",
    ],
  },
  {
    key: "questions",
    title: "Open questions & follow-up",
    description: "Unresolved threads worth returning to.",
    icon: <CircleHelp size={18} />,
    itemTypes: ["open_question", "follow_up"],
  },
  {
    key: "actions",
    title: "Actions",
    description: "Concrete next steps extracted from active work.",
    icon: <ListTodo size={18} />,
    itemTypes: ["action"],
  },
];

const fixedScopes = [
  { key: "core_self", label: "Core Self", kind: "core_self" },
  { key: "personal", label: "Personal", kind: "personal" },
  { key: "work", label: "Work", kind: "work" },
];

export function buildContextScopeGroups(
  items: ContextItem[],
): ContextScopeGroup[] {
  const groups = new Map<string, ContextScopeGroup>();
  for (const scope of fixedScopes) {
    groups.set(scope.key, { ...scope, items: [] });
  }

  for (const item of items) {
    for (const scope of item.scopes) {
      const key = scope.scope_key
        ? `${scope.scope_type}:${scope.scope_key}`
        : scope.scope_type;
      const existing = groups.get(key);
      if (existing) {
        existing.items.push(item);
        continue;
      }
      groups.set(key, {
        key,
        label: scope.scope_key || scopeLabel(scope.scope_type),
        kind: scope.scope_type,
        items: [item],
      });
    }
  }

  return Array.from(groups.values()).sort((left, right) => {
    const kindOrder = [
      "core_self",
      "personal",
      "work",
      "project",
      "topic",
      "destination",
    ];
    const kindDifference =
      kindOrder.indexOf(left.kind) - kindOrder.indexOf(right.kind);
    return kindDifference || left.label.localeCompare(right.label);
  });
}

export function contextHomeItems(items: ContextItem[], itemTypes: string[]) {
  const accepted = new Set(itemTypes);
  return items.filter(
    (item) => item.status === "active" && accepted.has(item.item_type),
  );
}

export function contextBriefEntries(
  briefs: ContextBrief[],
  sectionKey: string,
) {
  const seen = new Set<string>();
  const entries: ContextBriefEntry[] = [];
  for (const brief of briefs) {
    const values =
      sectionKey === "insights"
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
      entries.push({
        id: `${brief.id}:${sectionKey}:${index}`,
        text,
        sourceTitle: brief.source_title,
      });
    }
  }
  return entries;
}

export function evidenceOpenTarget(
  evidence: ContextEvidence,
): EvidenceOpenTarget | null {
  if (
    !evidence.source_available ||
    !evidence.source_conversation_id ||
    !Number.isInteger(evidence.source_message_index) ||
    evidence.source_message_index < 0
  ) {
    return null;
  }
  return {
    conversationId: evidence.source_conversation_id,
    messageIndex: evidence.source_message_index,
  };
}

export function ContextWorkspace({
  onOpenLibrary,
  onOpenEvidence,
  onOpenImport,
  onOpenSettings,
  view: controlledView,
  onViewChange,
  activity,
  openItemId,
}: {
  onOpenLibrary: () => void;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
  onOpenImport?: () => void;
  onOpenSettings?: () => void;
  view?: "home" | "explorer";
  onViewChange?: (view: "home" | "explorer") => void;
  activity?: ReactNode;
  openItemId?: string | null;
}) {
  const [localView, setLocalView] = useState<"home" | "explorer">("home");
  const [exploreMode, setExploreMode] = useState<"list" | "graph" | "review">("list");
  const view = controlledView ?? localView;
  const [briefs, setBriefs] = useState<ContextBrief[]>([]);
  const [items, setItems] = useState<ContextItem[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [error, setError] = useState("");
  const [selectedGroupKey, setSelectedGroupKey] = useState("all");
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [hasMoreItems, setHasMoreItems] = useState(false);
  const [hasMoreBriefs, setHasMoreBriefs] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageSize = 100;
  const loadedCounts = useRef({ briefs: 0, items: 0 });
  const contextRequest = useRef(0);
  const linkedItemRequest = useRef(0);
  const handledOpenItem = useRef<string | null>(null);

  const loadContext = useCallback(async (signal?: AbortSignal) => {
    const request = ++contextRequest.current;
    setStatus((current) => (current === "ready" ? current : "loading"));
    setError("");
    try {
      const [briefResponse, itemResponse] = await Promise.all([
        refreshLoadedPages<ContextBrief>(
          "briefs",
          loadedCounts.current.briefs,
          pageSize,
          signal,
        ),
        refreshLoadedPages<ContextItem>(
          "items",
          loadedCounts.current.items,
          pageSize,
          signal,
        ),
      ]);
      if (signal?.aborted || request !== contextRequest.current) return;
      loadedCounts.current = {
        briefs: briefResponse.results.length,
        items: itemResponse.results.length,
      };
      setBriefs(briefResponse.results ?? []);
      setItems(itemResponse.results ?? []);
      setHasMoreBriefs(
        briefResponse.has_more ?? briefResponse.results.length === pageSize,
      );
      setHasMoreItems(
        itemResponse.has_more ?? itemResponse.results.length === pageSize,
      );
      setSelectedItemId((id) =>
        itemResponse.results.some((item) => item.id === id)
          ? id
          : (itemResponse.results[0]?.id ?? null),
      );
      setSelectedBriefId((id) =>
        briefResponse.results.some((brief) => brief.id === id)
          ? id
          : (briefResponse.results[0]?.id ?? null),
      );
      setStatus("ready");
    } catch (reason) {
      if (signal?.aborted || request !== contextRequest.current) return;
      setStatus((current) => (current === "ready" ? current : "error"));
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load your Context Library.",
      );
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadContext(controller.signal);
    const refresh = () => void loadContext(controller.signal);
    window.addEventListener("reweave:context-changed", refresh);
    return () => {
      controller.abort();
      window.removeEventListener("reweave:context-changed", refresh);
    };
  }, [loadContext]);

  async function loadMore() {
    const request = contextRequest.current;
    setLoadingMore(true);
    setError("");
    try {
      const [briefPage, itemPage] = await Promise.all([
        hasMoreBriefs
          ? contextApi<{ results: ContextBrief[]; has_more?: boolean }>(
              `/api/context/briefs?limit=${pageSize}&offset=${loadedCounts.current.briefs}`,
            )
          : null,
        hasMoreItems
          ? contextApi<{ results: ContextItem[]; has_more?: boolean }>(
              `/api/context/items?limit=${pageSize}&offset=${loadedCounts.current.items}`,
            )
          : null,
      ]);
      if (request !== contextRequest.current) return;
      if (briefPage) {
        loadedCounts.current.briefs += briefPage.results.length;
        setBriefs((current) => mergeContextPage(current, briefPage.results));
        setHasMoreBriefs(
          briefPage.has_more ?? briefPage.results.length === pageSize,
        );
      }
      if (itemPage) {
        loadedCounts.current.items += itemPage.results.length;
        setItems((current) => mergeContextPage(current, itemPage.results));
        setHasMoreItems(
          itemPage.has_more ?? itemPage.results.length === pageSize,
        );
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not load more context. Try again.",
      );
    } finally {
      setLoadingMore(false);
    }
  }

  const groups = useMemo(
    () => [
      { key: "all", label: "All spaces", kind: "all", items },
      ...buildContextScopeGroups(items),
    ],
    [items],
  );
  const selectedGroup =
    groups.find((group) => group.key === selectedGroupKey) ?? groups[0];
  const selectedItem = items.find((item) => item.id === selectedItemId) ?? null;
  const selectedBrief =
    briefs.find((brief) => brief.id === selectedBriefId) ?? briefs[0] ?? null;
  const activeItems = useMemo(
    () => items.filter((item) => item.status === "active"),
    [items],
  );

  function changeView(next: "home" | "explorer") {
    setLocalView(next);
    onViewChange?.(next);
  }

  function openExplorer(item?: ContextItem, groupKey?: string) {
    setExploreMode("list");
    setSelectedGroupKey(groupKey ?? "all");
    if (item) setSelectedItemId(item.id);
    changeView("explorer");
  }

  function updateItem(updated: ContextItem) {
    setItems((current) => mergeContextPage(current, [updated]));
    setSelectedGroupKey("all");
    setSelectedItemId(updated.id);
  }

  async function openRelatedItem(id: string) {
    const request = ++linkedItemRequest.current;
    try {
      const item =
        items.find((entry) => entry.id === id) ??
        (await contextApi<ContextItem>(
          `/api/context/items/${encodeURIComponent(id)}`,
        ));
      if (request !== linkedItemRequest.current) return false;
      updateItem(item);
      setExploreMode("list");
      changeView("explorer");
      return true;
    } catch {
      return false;
    }
  }

  const openRequestedItem = useRef(openRelatedItem);
  openRequestedItem.current = openRelatedItem;
  useEffect(() => {
    if (!openItemId) {
      handledOpenItem.current = null;
      return;
    }
    if (status !== "ready" || handledOpenItem.current === openItemId) return;
    handledOpenItem.current = openItemId;
    void openRequestedItem.current(openItemId).then((opened) => {
      if (!opened && handledOpenItem.current === openItemId)
        setError(
          "This Context Item could not be opened. Search again or refresh the library.",
        );
    });
  }, [openItemId, status]);

  return (
    <section className="contextScreen" aria-labelledby="context-title">
      <header className="contextHeader">
        <div>
          <h1 id="context-title">
            {view === "home" ? "Context Home" : "Explore your context"}
          </h1>
          <p>
            {view === "home"
              ? "Return to what matters, with its sources close by."
              : "Find an idea, follow its connections, and read the evidence."}
          </p>
        </div>
        <button
          type="button"
          className="contextTextButton"
          onClick={() => void loadContext()}
          disabled={status === "loading"}
          aria-label="Refresh Context Library"
        >
          <RefreshCw size={17} /> Refresh
        </button>
      </header>
      {view === "explorer" && (
        <div
          className="contextExploreViews"
          role="group"
          aria-label="Explore view"
        >
          <button
            type="button"
            aria-pressed={exploreMode === "list"}
            onClick={() => setExploreMode("list")}
          >
            List &amp; sources
          </button>
          <button
            type="button"
            aria-pressed={exploreMode === "graph"}
            onClick={() => setExploreMode("graph")}
          >
            Graph
          </button>
          <button type="button" aria-pressed={exploreMode === "review"}
            onClick={() => setExploreMode("review")}>Review exceptions</button>
        </div>
      )}
      {status === "ready" && error && (
        <p className="contextEvidenceError" role="alert">
          {error} Your previously loaded context is still available. Use Refresh
          to try again.
        </p>
      )}
      {status === "loading" && <ContextLoading />}
      {status === "error" && (
        <ContextError message={error} onRetry={loadContext} />
      )}
      {status === "ready" &&
        briefs.length === 0 &&
        items.length === 0 &&
        !(view === "explorer" && exploreMode !== "list") && (
          <ContextEmpty
            onOpenLibrary={onOpenLibrary}
            onOpenImport={onOpenImport}
            onOpenSettings={onOpenSettings}
          />
        )}
      {status === "ready" &&
        (briefs.length > 0 || items.length > 0) &&
        view === "home" && (
          <ContextHome
            briefs={briefs}
            brief={selectedBrief}
            items={activeItems}
            groups={groups}
            onSelectBrief={setSelectedBriefId}
            onOpenExplorer={openExplorer}
            onOpenEvidence={onOpenEvidence}
            onOpenSettings={onOpenSettings}
          />
        )}
      {status === "ready" &&
        (briefs.length > 0 || items.length > 0) &&
        view === "explorer" &&
        exploreMode === "list" && (
          <ContextExplorer
            briefs={briefs}
            items={items}
            groups={groups}
            selectedGroup={selectedGroup}
            selectedItem={selectedItem}
            onItemUpdated={updateItem}
            onOpenRelated={openRelatedItem}
            onSelectGroup={(group) => {
              setSelectedGroupKey(group.key);
              setSelectedItemId(group.items[0]?.id ?? null);
            }}
            onSelectItem={(item) => setSelectedItemId(item.id)}
            onOpenEvidence={onOpenEvidence}
          />
        )}
      {status === "ready" && view === "explorer" && exploreMode === "graph" && (
        <Suspense fallback={<ContextLoading />}>
          <ContextGraph onOpenItem={openRelatedItem} />
        </Suspense>
      )}
      {status === "ready" && view === "explorer" && exploreMode === "review" && (
        <Suspense fallback={<ContextLoading />}>
          <ContextReview onOpenItem={(id) => { void openRelatedItem(id); }}
            onLibraryDeleted={() => { void loadContext(); }} />
        </Suspense>
      )}
      {activity && <div className="contextActivity">{activity}</div>}
      {status === "ready" &&
        !(view === "explorer" && exploreMode !== "list") &&
        (hasMoreItems || hasMoreBriefs) && (
          <div className="contextPagination">
            <p>
              {items.length} items and {briefs.length} briefs loaded. More are
              available in your library.
            </p>
            <button
              type="button"
              className="secondaryButton"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? (
                <Loader2 className="spin" size={16} />
              ) : (
                <ChevronRight size={16} />
              )}{" "}
              {loadingMore ? "Loading…" : "Load more context"}
            </button>
          </div>
        )}
    </section>
  );
}

export function mergeContextPage<T extends { id: string }>(
  current: T[],
  next: T[],
) {
  const records = new Map(current.map((record) => [record.id, record]));
  for (const record of next) records.set(record.id, record);
  return [...records.values()];
}

export function ContextHome({
  briefs,
  brief,
  items,
  groups,
  onSelectBrief,
  onOpenExplorer,
  onOpenEvidence,
  onOpenSettings,
}: {
  briefs: ContextBrief[];
  brief: ContextBrief | null;
  items: ContextItem[];
  groups: ContextScopeGroup[];
  onSelectBrief: (id: string) => void;
  onOpenExplorer: (item?: ContextItem, groupKey?: string) => void;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
  onOpenSettings?: () => void;
}) {
  const relatedItems = brief
    ? items.filter((item) => brief.context_item_ids.includes(item.id))
    : items;
  const relatedGroups = groups.filter(
    (group) =>
      group.kind !== "all" &&
      group.items.some((item) => relatedItems.includes(item)),
  );
  const coreSelf = items.filter((item) =>
    item.scopes.some((scope) => scope.scope_type === "core_self"),
  );
  return (
    <div className="contextHome">
      <div className="contextReadingColumn">
        {briefs.length > 1 && (
          <label className="briefPicker">
            Continue reading
            <select
              value={brief?.id ?? ""}
              onChange={(event) => onSelectBrief(event.target.value)}
            >
              {briefs.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.source_title} · {formatContextDate(entry.updated_at)}
                </option>
              ))}
            </select>
          </label>
        )}
        <article className="readingDocument">
          {brief ? (
            <>
              <div className="readingSourceHeader">
                <div>
                  <span className="contextEyebrow">Conversation Brief</span>
                  <p>
                    {brief.source_title} ·{" "}
                    {formatContextLabel(brief.source_provider)} ·{" "}
                    {formatContextDate(brief.updated_at)}
                  </p>
                </div>
                <BriefSource brief={brief} onOpenEvidence={onOpenEvidence} />
              </div>
              <h2 className="readingTitle">{brief.main_subject}</h2>
              {brief.user_goal && (
                <p className="readingGoal">{brief.user_goal}</p>
              )}
              {relatedGroups.length > 0 && (
                <div className="contextScopeStrip" aria-label="Related spaces">
                  {relatedGroups.map((group) => (
                    <button
                      key={group.key}
                      type="button"
                      onClick={() => onOpenExplorer(undefined, group.key)}
                    >
                      {group.label}
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              )}
              {brief.item_count === 0 && (
                <p className="briefOnlyNote">
                  This conversation has a useful Brief without separate Context
                  Items. Its source and outcomes remain available.
                </p>
              )}
            </>
          ) : (
            <>
              <span className="contextEyebrow">Connected ideas</span>
              <h2 className="readingTitle">What you are carrying forward</h2>
              <p className="readingGoal">
                Your saved context stays readable even when its original
                conversation is no longer in the archive.
              </p>
            </>
          )}
          {homeSections.slice(0, 2).map((section) => (
            <ReadingSection
              key={section.key}
              section={section}
              items={contextHomeItems(relatedItems, section.itemTypes)}
              brief={brief}
              onOpenExplorer={onOpenExplorer}
              onOpenEvidence={onOpenEvidence}
            />
          ))}
          <ChatUseGuide onOpenSettings={onOpenSettings} />
        </article>
        {coreSelf.length > 0 && (
          <section className="coreSelfSection">
            <div className="contextSectionHeading">
              <h2>
                <Brain size={19} /> Core Self
              </h2>
              <button
                type="button"
                className="contextTextButton"
                onClick={() => onOpenExplorer(undefined, "core_self")}
              >
                Read all <ChevronRight size={15} />
              </button>
            </div>
            <p className="contextDetailMuted">
              Values and preferences with evidence you can inspect.
            </p>
            <div>
              {coreSelf.slice(0, 2).map((item) => (
                <ContextReadingItem
                  key={item.id}
                  item={item}
                  onOpen={() => onOpenExplorer(item)}
                />
              ))}
            </div>
          </section>
        )}
      </div>
      <aside className="contextCompanion" aria-label="Companion context">
        {homeSections.slice(2).map((section) => (
          <ReadingSection
            key={section.key}
            section={section}
            items={contextHomeItems(relatedItems, section.itemTypes)}
            brief={brief}
            onOpenExplorer={onOpenExplorer}
            onOpenEvidence={onOpenEvidence}
          />
        ))}
        <section className="relatedContext">
          <h2>Related context</h2>
          {relatedGroups.length ? (
            relatedGroups.map((group) => (
              <button
                className="relatedContextLink"
                type="button"
                key={group.key}
                onClick={() => onOpenExplorer(undefined, group.key)}
              >
                <ScopeIcon kind={group.kind} />
                <span>{group.label}</span>
                <ChevronRight size={15} />
              </button>
            ))
          ) : (
            <p>
              No related space has been established for this conversation yet.
            </p>
          )}
          <button
            type="button"
            className="contextTextButton"
            onClick={() => onOpenExplorer()}
          >
            Explore the library <ChevronRight size={15} />
          </button>
        </section>
        {brief && (
          <section className="readingSourceDetails">
            <h2>Source details</h2>
            <p>
              <BookMarked size={17} />
              {brief.source_title}
            </p>
            <p>
              {formatContextLabel(brief.source_provider)} ·{" "}
              {formatContextDate(brief.source_created_at)}
            </p>
            <BriefSource brief={brief} onOpenEvidence={onOpenEvidence} />
          </section>
        )}
      </aside>
    </div>
  );
}

function ContextReadingItem({
  item,
  onOpen,
}: {
  item: ContextItem;
  onOpen: () => void;
}) {
  return (
    <div className="contextReadingItem">
      <div className="contextDetailLabels">
        <span>{formatContextLabel(item.item_type)}</span>
        <span className={item.epistemic_kind === "inferred" ? "inferred" : ""}>
          {formatContextLabel(item.epistemic_kind)}
        </span>
        {item.sensitivity === "sensitive" && (
          <span className="sensitive">Sensitive</span>
        )}
      </div>
      <p>{item.canonical_text}</p>
      <button type="button" className="contextTextButton" onClick={onOpen}>
        <Link2 size={15} /> Read context &amp; sources{" "}
        <ChevronRight size={15} />
      </button>
    </div>
  );
}

function ReadingSection({
  section,
  items,
  brief,
  onOpenExplorer,
  onOpenEvidence,
}: {
  section: HomeSection;
  items: ContextItem[];
  brief: ContextBrief | null;
  onOpenExplorer: (item?: ContextItem) => void;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
}) {
  const itemTexts = new Set(
    items.map((item) => item.canonical_text.trim().toLocaleLowerCase()),
  );
  const entries = contextBriefEntries(brief ? [brief] : [], section.key).filter(
    (entry) => !itemTexts.has(entry.text.trim().toLocaleLowerCase()),
  );
  if (!items.length && !entries.length)
    return (
      <section className="readingSection quietSection">
        <h2>
          {section.icon}
          {section.title}
        </h2>
        <p>Nothing established in this conversation yet.</p>
      </section>
    );
  return (
    <section className="readingSection">
      <h2>
        {section.icon}
        {section.title}
      </h2>
      {items.map((item) => (
        <ContextReadingItem
          key={item.id}
          item={item}
          onOpen={() => onOpenExplorer(item)}
        />
      ))}
      {items.length > 0 && entries.length > 0 ? (
        <details className="briefSupportingDetails">
          <summary>More from the Conversation Brief ({entries.length})</summary>
          {entries.map((entry) => (
            <div className="contextReadingItem" key={entry.id}>
              <span className="contextBriefLabel">
                From the Conversation Brief
              </span>
              <p>{entry.text}</p>
              {brief && (
                <BriefSource brief={brief} onOpenEvidence={onOpenEvidence} />
              )}
            </div>
          ))}
        </details>
      ) : (
        <>
          {entries.map((entry) => (
            <div className="contextReadingItem" key={entry.id}>
              <span className="contextBriefLabel">
                From the Conversation Brief
              </span>
              <p>{entry.text}</p>
              {brief && (
                <BriefSource brief={brief} onOpenEvidence={onOpenEvidence} />
              )}
            </div>
          ))}
        </>
      )}
    </section>
  );
}

function BriefSource({
  brief,
  onOpenEvidence,
}: {
  brief: ContextBrief;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
}) {
  const [error, setError] = useState(false);
  const [opening, setOpening] = useState(false);
  async function open() {
    if (!brief.source_conversation_id) return;
    setOpening(true);
    setError(false);
    try {
      setError(!(await onOpenEvidence(brief.source_conversation_id, 0)));
    } catch {
      setError(true);
    } finally {
      setOpening(false);
    }
  }
  return (
    <div className="briefSource">
      {brief.source_conversation_id ? (
        <button
          type="button"
          className="contextTextButton"
          onClick={() => void open()}
          disabled={opening}
          aria-label={`View source ${brief.source_title}`}
        >
          <Link2 size={15} />
          {opening ? "Opening…" : "View source"}
          <ExternalLink size={14} />
        </button>
      ) : (
        <p className="contextDetailMuted">
          Original source removed · Brief retained
        </p>
      )}
      {error && (
        <p role="alert" className="contextEvidenceError">
          Source could not be opened. This saved Brief is still available.
        </p>
      )}
    </div>
  );
}

export function ContextExplorer({
  briefs,
  items,
  groups,
  selectedGroup,
  selectedItem,
  onSelectGroup,
  onSelectItem,
  onOpenEvidence,
  onItemUpdated,
  onOpenRelated,
}: {
  briefs: ContextBrief[];
  items: ContextItem[];
  groups: ContextScopeGroup[];
  selectedGroup: ContextScopeGroup;
  selectedItem: ContextItem | null;
  onItemUpdated?: (item: ContextItem) => void;
  onOpenRelated?: (id: string) => Promise<boolean>;
  onSelectGroup: (group: ContextScopeGroup) => void;
  onSelectItem: (item: ContextItem) => void;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
}) {
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [showBriefs, setShowBriefs] = useState(items.length === 0);
  const [briefId, setBriefId] = useState<string | null>(briefs[0]?.id ?? null);
  const filteredItems = selectedGroup.items.filter(
    (item) =>
      (!kind || item.item_type === kind) &&
      `${item.canonical_text} ${item.evidence.map((entry) => entry.source_title).join(" ")}`
        .toLocaleLowerCase()
        .includes(query.toLocaleLowerCase()),
  );
  const filteredBriefs = briefs.filter((brief) =>
    `${brief.main_subject} ${brief.source_title} ${brief.user_goal}`
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase()),
  );
  const selectedBrief =
    filteredBriefs.find((brief) => brief.id === briefId) ?? filteredBriefs[0];
  const visibleItem =
    filteredItems.find((item) => item.id === selectedItem?.id) ??
    filteredItems[0];
  return (
    <div className="contextExplorer">
      <div className="explorerFilters">
        <label>
          Find in loaded context
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="An idea or source title"
          />
        </label>
        {!showBriefs && (
          <>
            <label>
              Space
              <select
                value={selectedGroup.key}
                onChange={(event) => {
                  const group = groups.find(
                    (entry) => entry.key === event.target.value,
                  );
                  if (group) onSelectGroup(group);
                }}
              >
                {groups.map((group) => (
                  <option key={group.key} value={group.key}>
                    {group.label} ({group.items.length})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="">All types</option>
                {[...new Set(items.map((item) => item.item_type))]
                  .sort()
                  .map((type) => (
                    <option value={type} key={type}>
                      {formatContextLabel(type)}
                    </option>
                  ))}
              </select>
            </label>
          </>
        )}
        <div
          className="explorerViewPicker"
          role="group"
          aria-label="Explore content"
        >
          <button
            type="button"
            aria-pressed={!showBriefs}
            onClick={() => setShowBriefs(false)}
          >
            Context Items
          </button>
          <button
            type="button"
            aria-pressed={showBriefs}
            onClick={() => setShowBriefs(true)}
          >
            Briefs
          </button>
        </div>
      </div>
      <div className="explorerManagement">
        <SpacesManager />
      </div>
      <section
        className="contextItemPane"
        aria-label={showBriefs ? "Conversation Briefs" : "Context Items"}
      >
        <div className="explorerPaneHeading">
          <h2>{showBriefs ? "Conversation Briefs" : selectedGroup.label}</h2>
          <span>
            {showBriefs ? filteredBriefs.length : filteredItems.length} shown
          </span>
        </div>
        <div className="explorerItemList">
          {showBriefs
            ? filteredBriefs.map((brief) => (
                <button
                  type="button"
                  key={brief.id}
                  aria-pressed={selectedBrief?.id === brief.id}
                  onClick={() => setBriefId(brief.id)}
                >
                  <span>Conversation Brief</span>
                  <strong>{brief.main_subject}</strong>
                  <small>{brief.source_title}</small>
                </button>
              ))
            : filteredItems.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  aria-pressed={visibleItem?.id === item.id}
                  onClick={() => onSelectItem(item)}
                >
                  <span>
                    {formatContextLabel(item.item_type)} ·{" "}
                    {formatContextLabel(item.epistemic_kind)}
                  </span>
                  <strong>{item.canonical_text}</strong>
                  <small>
                    {scopeSummary(item)} · {formatContextDate(item.updated_at)}
                  </small>
                </button>
              ))}
        </div>
        {(showBriefs
          ? filteredBriefs.length === 0
          : filteredItems.length === 0) && (
          <div className="explorerEmpty">
            <Compass size={24} />
            <h3>No matching context</h3>
            <p>
              Try another type or space, clear the filter, or search all
              original sources above.
            </p>
          </div>
        )}
      </section>
      <section className="contextDetailPane" aria-label="Selected context">
        {showBriefs ? (
          selectedBrief ? (
            <article className="contextDetail">
              <header>
                <span className="contextEyebrow">Conversation Brief</span>
                <h2>{selectedBrief.main_subject}</h2>
                <p className="readingGoal">{selectedBrief.user_goal}</p>
                <BriefSource
                  brief={selectedBrief}
                  onOpenEvidence={onOpenEvidence}
                />
              </header>
              {homeSections.map((section) => (
                <ReadingSection
                  key={section.key}
                  section={section}
                  brief={selectedBrief}
                  items={[]}
                  onOpenExplorer={() => setShowBriefs(false)}
                  onOpenEvidence={onOpenEvidence}
                />
              ))}
              {selectedBrief.item_count === 0 && (
                <p className="briefOnlyNote">
                  No separate Context Items were needed. This Brief remains
                  useful and searchable.
                </p>
              )}
            </article>
          ) : (
            <div className="explorerEmpty">
              <h3>No Brief selected</h3>
              <p>
                Conversation Briefs become available after successful analysis.
              </p>
            </div>
          )
        ) : visibleItem ? (
          <ContextItemDetail
            item={visibleItem}
            onOpenEvidence={onOpenEvidence}
            onUpdated={onItemUpdated}
            relatedItems={items}
            onOpenRelated={onOpenRelated}
            key={visibleItem.id}
          />
        ) : (
          <div className="explorerEmpty">
            <Compass size={24} />
            <h3>Select an item</h3>
            <p>Read its full text, source, scope, and history here.</p>
          </div>
        )}
      </section>
    </div>
  );
}

export function ContextItemDetail({
  item: suppliedItem,
  onOpenEvidence,
  onUpdated,
  relatedItems = [],
  onOpenRelated,
}: {
  item: ContextItem;
  onUpdated?: (item: ContextItem) => void;
  relatedItems?: ContextItem[];
  onOpenRelated?: (id: string) => Promise<boolean>;
  onOpenEvidence: (
    conversationId: string,
    messageIndex: number,
  ) => Promise<boolean>;
}) {
  const [openingEvidenceId, setOpeningEvidenceId] = useState<string | null>(
    null,
  );
  const [openError, setOpenError] = useState("");
  const [item, setItem] = useState(suppliedItem);
  const [linkError, setLinkError] = useState("");
  useEffect(() => setItem(suppliedItem), [suppliedItem]);

  async function openEvidence(evidence: ContextEvidence) {
    const target = evidenceOpenTarget(evidence);
    if (!target) return;
    setOpeningEvidenceId(evidence.id);
    setOpenError("");
    try {
      const opened = await onOpenEvidence(
        target.conversationId,
        target.messageIndex,
      );
      if (opened) return;
      setOpenError(
        "The original conversation could not be opened. Its compact evidence remains available here.",
      );
    } catch {
      setOpenError(
        "The original conversation could not be opened. Its compact evidence remains available here.",
      );
    } finally {
      setOpeningEvidenceId(null);
    }
  }

  return (
    <article className="contextDetail">
      <header>
        <div className="contextDetailLabels">
          <span>{formatContextLabel(item.item_type)}</span>
          <span
            className={item.epistemic_kind === "inferred" ? "inferred" : ""}
          >
            {formatContextLabel(item.epistemic_kind)}
          </span>
          {item.sensitivity === "sensitive" && (
            <span className="sensitive">
              <LockKeyhole size={12} /> Sensitive
            </span>
          )}
        </div>
        <h2>{item.canonical_text}</h2>
        <p>Last updated {formatContextDate(item.updated_at)}</p>
      </header>
      {item.epistemic_kind === "inferred" && (
        <section className="inferenceRationale">
          <h3>Why this was inferred</h3>
          <p>
            {item.inference_rationale ||
              "No interpretation rationale was recorded for this item. Inspect the source and correct it if needed."}
          </p>
          <p className="contextDetailMuted">
            An interpretation of the source, not a direct quotation.
          </p>
        </section>
      )}
      <dl className="contextMetadata">
        <div>
          <dt>
            {item.effective_confidence === undefined
              ? "Confidence"
              : "Current confidence"}
          </dt>
          <dd>
            {Math.round((item.effective_confidence ?? item.confidence) * 100)}%
            {item.effective_confidence !== undefined &&
              ` (recorded ${Math.round(item.confidence * 100)}%)`}
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{formatContextLabel(item.status)}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{item.current_version}</dd>
        </div>
      </dl>
      <section>
        <h3>
          <Layers3 size={15} /> Scopes
        </h3>
        <div className="contextDetailScopes">
          {item.scopes.map((scope) => (
            <span key={`${scope.scope_type}:${scope.scope_key}`}>
              {scope.scope_key || scopeLabel(scope.scope_type)}
            </span>
          ))}
        </div>
      </section>
      <section>
        <h3>
          <Quote size={15} /> Source evidence
        </h3>
        {item.evidence.length > 0 ? (
          <div className="contextEvidenceList">
            {item.evidence.map((evidence) => {
              const target = evidenceOpenTarget(evidence);
              const opening = openingEvidenceId === evidence.id;
              return (
                <figure className="contextEvidence" key={evidence.id}>
                  {evidence.source_changed && (
                    <p className="sourceChangedNotice">
                      Source changed since analysis · Original evidence snapshot
                      retained below.
                    </p>
                  )}
                  <blockquote>{evidence.excerpt}</blockquote>
                  <figcaption>
                    <BookMarked size={14} />
                    <span>{evidence.source_title}</span>
                    <b className={target ? "available" : "retained"}>
                      {target ? "Source available" : "Snapshot retained"}
                    </b>
                  </figcaption>
                  {target ? (
                    <button
                      className="contextEvidenceAction"
                      type="button"
                      onClick={() => void openEvidence(evidence)}
                      disabled={openingEvidenceId !== null}
                      aria-label={`Open source message ${target.messageIndex} in ${evidence.source_title}`}
                    >
                      {opening ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <ExternalLink size={16} />
                      )}
                      {opening
                        ? "Opening source…"
                        : `Open source message #${target.messageIndex}`}
                      {!opening && <ChevronRight size={15} />}
                    </button>
                  ) : (
                    <div className="contextEvidenceFallback">
                      <BookMarked size={16} />
                      <span>
                        <strong>Original conversation unavailable</strong>
                        <small>
                          Compact evidence is retained on this device.
                        </small>
                      </span>
                    </div>
                  )}
                </figure>
              );
            })}
          </div>
        ) : (
          <p className="contextDetailMuted">
            No compact evidence is available.
          </p>
        )}
        {openError && (
          <p className="contextEvidenceError" role="alert">
            {openError}
          </p>
        )}
      </section>
      <ContextManagement
        item={item}
        onUpdated={(updated) => {
          setItem(updated);
          onUpdated?.(updated);
        }}
      />
      <RelationshipHistory itemId={item.id} version={item.current_version} />
      {item.links.length > 0 && (
        <section className="contextRelatedLinks">
          <h3>
            <Link2 size={15} /> Linked context
          </h3>
          {item.links.map((link, index) => {
            const id =
              link.source_item_id === item.id
                ? link.target_item_id
                : link.source_item_id;
            const target = relatedItems.find((entry) => entry.id === id);
            return (
              <button
                type="button"
                className="relatedContextLink"
                key={`${id}:${link.relationship}:${index}`}
                disabled={!onOpenRelated}
                onClick={async () => {
                  setLinkError("");
                  try {
                    if (!(await onOpenRelated?.(id)))
                      setLinkError(
                        "This related item could not be opened. Your current context is still available.",
                      );
                  } catch {
                    setLinkError(
                      "This related item could not be opened. Your current context is still available.",
                    );
                  }
                }}
              >
                <span>
                  <small>{formatContextLabel(link.relationship)}</small>
                  <strong>
                    {target?.canonical_text ?? "Read related context"}
                  </strong>
                </span>
                <ChevronRight size={15} />
              </button>
            );
          })}
          {linkError && (
            <p className="contextEvidenceError" role="alert">
              {linkError}
            </p>
          )}
        </section>
      )}
    </article>
  );
}

function RelationshipHistory({ itemId, version }: { itemId: string; version: number }) {
  type Match = {
    id: string; relationship: string; confidence: number; rationale: string;
    evidence_excerpt: string; source_version: number; target_version: number;
    created_at: string;
  };
  const [open, setOpen] = useState(false);
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setMatches(null); setError("");
    void contextApi<{ results: Match[] }>(
      `/api/context/items/${encodeURIComponent(itemId)}/matches`, controller.signal,
    ).then((data) => { if (!controller.signal.aborted) setMatches(data.results); })
      .catch(() => { if (!controller.signal.aborted) setError("Could not load relationship history. Close and reopen to retry."); });
    return () => controller.abort();
  }, [itemId, version, open]);
  return <details className="contextRelatedLinks" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Why Context was connected</summary>
    {error && <p role="alert">{error}</p>}
    {!error && matches === null && open && <p role="status">Loading relationship history…</p>}
    {matches?.length === 0 && <p>No semantic matching event is recorded for this item.</p>}
    {matches?.map((match) => <section key={match.id}>
      <h4>{formatContextLabel(match.relationship)} · {Math.round(match.confidence * 100)}% confidence</h4>
      <p>{match.rationale}</p>
      <blockquote>{match.evidence_excerpt}</blockquote>
      <small>Compared versions {match.source_version} and {match.target_version} · {formatContextDate(match.created_at)}. Later corrections remain in item history.</small>
    </section>)}
  </details>;
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

function ContextError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="contextStateCard" role="alert">
      <AlertTriangle size={26} />
      <h2>Context could not be loaded</h2>
      <p>{message}</p>
      <button
        className="secondaryButton"
        type="button"
        onClick={() => onRetry()}
      >
        <RefreshCw size={16} /> Try again
      </button>
    </div>
  );
}

function ContextEmpty({
  onOpenLibrary,
  onOpenImport,
  onOpenSettings,
}: {
  onOpenLibrary: () => void;
  onOpenImport?: () => void;
  onOpenSettings?: () => void;
}) {
  return (
    <div className="contextStateCard contextEmptyState">
      <span className="contextEmptyIcon">
        <Compass size={28} />
      </span>
      <span className="contextEyebrow">
        A place for what you want to remember
      </span>
      <h2>Begin with one useful conversation</h2>
      <p>
        Import an export, or explicitly Save a conversation with the Reweave
        extension. Sources stay on this device and remain searchable without an
        API key.
      </p>
      <p>
        When you connect an analysis provider, saved conversations can become
        source-linked Briefs. No separate Context Items is a valid result.
      </p>
      <div className="buttonRow">
        <button
          className="primaryButton"
          type="button"
          onClick={onOpenImport ?? onOpenLibrary}
        >
          <BookMarked size={16} /> Import conversations
        </button>
        <button
          className="secondaryButton"
          type="button"
          onClick={onOpenLibrary}
        >
          View saved sources
        </button>
      </div>
      <ChatUseGuide onOpenSettings={onOpenSettings} />
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
    destination: "Destination",
  };
  return labels[value] ?? formatContextLabel(value);
}

function scopeSummary(item: ContextItem) {
  if (!item.scopes.length) return "Unscoped";
  return item.scopes
    .map((scope) => scope.scope_key || scopeLabel(scope.scope_type))
    .join(" · ");
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
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(date);
}

async function refreshLoadedPages<T extends { id: string }>(
  collection: "briefs" | "items",
  loaded: number,
  pageSize: number,
  signal?: AbortSignal,
) {
  let results: T[] = [];
  let hasMore = false;
  for (
    let offset = 0;
    offset < Math.max(pageSize, loaded);
    offset += pageSize
  ) {
    const page = await contextApi<{ results: T[]; has_more?: boolean }>(
      `/api/context/${collection}?limit=${pageSize}&offset=${offset}`,
      signal,
    );
    results = mergeContextPage(results, page.results);
    hasMore = page.has_more ?? page.results.length === pageSize;
    if (!hasMore) break;
  }
  return { results, has_more: hasMore };
}

async function contextApi<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? data.detail
        : data;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "Could not load your Context Library.",
    );
  }
  return data as T;
}
