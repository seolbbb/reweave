import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CloudUpload,
  Database,
  Download,
  Eye,
  EyeOff,
  FileText,
  FileUp,
  FolderInput,
  Compass,
  Home,
  KeyRound,
  Library,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Settings,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { MarkdownContent } from "./MarkdownContent";
import { LibraryView, OnboardingWizard } from "./ArchiveManagement";
import { ContextWorkspace } from "./ContextWorkspace";
import { ContextSearch, SourceContextLinks } from "./ContextSearch";
import { ChatUseGuide } from "./ChatUseGuide";
import { AnalysisQueue } from "./AnalysisQueue";
import { useDialogFocus } from "./useDialogFocus";
import { HighlightedText, extractHighlightTerms } from "./textHighlight";

type View =
  | "context"
  | "explore"
  | "library"
  | "search"
  | "import"
  | "settings";
type SearchMode = "auto" | "keyword" | "semantic";

type Excerpt = {
  conversation_id: string;
  message_id: string;
  message_index: number;
  source: string;
  title: string;
  role: string;
  timestamp: string | null;
  excerpt: string;
  match_kind?: string;
  rank_score?: number;
};

type SearchResult = {
  id: string;
  source: string;
  title: string;
  created_at: string;
  updated_at: string | null;
  raw_message_count: number;
  match_count: number;
  excerpts: Excerpt[];
};

type Message = {
  id: string;
  conversation_id: string;
  index: number;
  role: string;
  content: string;
  timestamp: string | null;
};

type ConversationDetail = {
  conversation: SearchResult;
  messages: Message[];
};

type ImportSummary = {
  parsed_conversations: number;
  inserted_conversations: number;
  updated_conversations: number;
  inserted_messages: number;
  updated_messages: number;
  invalidated_embeddings: number;
  skipped_files: string[];
};

type AppPaths = {
  data_dir: string;
  db_path: string;
  memory_audit_db_path: string;
  imports_dir: string;
  extracted_dir: string;
  models_dir: string;
};

type SemanticStatus = {
  model_id: string;
  model_downloaded: boolean;
  indexed_chunks: number;
  total_chunks: number;
  total_messages: number;
  ready: boolean;
};

type BackgroundJob<T> = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  message: string;
  progress: number;
  result: T | null;
  error: string | null;
};

type SourceFacet = {
  source: string;
  conversations: number;
  messages: number;
};

type LLMKey = {
  id: string;
  label: string;
  enabled: boolean;
  priority: number;
  has_secret: boolean;
};

type LLMProfile = {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  default_model: string;
  custom_models: string[];
  keys: LLMKey[];
  connected: boolean;
  masked_key: string;
};

type ModelLoadState = {
  profileId: string;
  status:
    | "idle"
    | "loading"
    | "success"
    | "empty"
    | "invalid-key"
    | "permission"
    | "rate-limit"
    | "network"
    | "error";
  models: string[];
  message: string;
};

const providerDetails: Record<
  string,
  { label: string; keyUrl?: string; keyHelp: string }
> = {
  openai: {
    label: "OpenAI",
    keyUrl: "https://platform.openai.com/api-keys",
    keyHelp: "Create a key in the OpenAI platform.",
  },
  anthropic: {
    label: "Anthropic",
    keyUrl: "https://console.anthropic.com/settings/keys",
    keyHelp: "Create a key in the Anthropic Console.",
  },
  gemini: {
    label: "Google Gemini",
    keyUrl: "https://aistudio.google.com/app/apikey",
    keyHelp: "Create a key in Google AI Studio.",
  },
  openrouter: {
    label: "OpenRouter",
    keyUrl: "https://openrouter.ai/settings/keys",
    keyHelp: "Create a key in OpenRouter.",
  },
  "openai-compatible": {
    label: "OpenAI-compatible",
    keyHelp: "Use the API key and base URL from your provider.",
  },
};

const initialModelLoad: ModelLoadState = {
  profileId: "",
  status: "idle",
  models: [],
  message: "Connect a provider to load available models.",
};

export function Workspace() {
  const [activeView, setActiveView] = useState<View>("context");
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("auto");
  const [modeUsed, setModeUsed] = useState("keyword");
  const [sourceFilter, setSourceFilter] = useState("");
  const [titleFilter, setTitleFilter] = useState("");
  const [sourceSpaceFilter, setSourceSpaceFilter] = useState("");
  const [sourceTypeFilter, setSourceTypeFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searchSubmitted, setSearchSubmitted] = useState(false);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [openItemId, setOpenItemId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const detailOpener = useRef<HTMLElement | null>(null);
  const [detailMessageIndex, setDetailMessageIndex] = useState<number | null>(
    null,
  );
  const [paths, setPaths] = useState<AppPaths | null>(null);
  const [sourceFacets, setSourceFacets] = useState<SourceFacet[]>([]);
  const [semanticStatus, setSemanticStatus] = useState<SemanticStatus | null>(
    null,
  );
  const [semanticJob, setSemanticJob] =
    useState<BackgroundJob<SemanticStatus> | null>(null);
  const [profiles, setProfiles] = useState<LLMProfile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState("");
  const [model, setModel] = useState("");
  const [modelLoad, setModelLoad] = useState<ModelLoadState>(initialModelLoad);
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [editingKey, setEditingKey] = useState(false);
  const [baseUrlDraft, setBaseUrlDraft] = useState("");
  const [customModelsDraft, setCustomModelsDraft] = useState("");
  const [maxContextChars, setMaxContextChars] = useState(80000);
  const [temperature, setTemperature] = useState(0.2);
  const [importPath, setImportPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [status, setStatus] = useState("Search your imported archive.");
  const [importStatus, setImportStatus] = useState(
    "Drop files or choose a .zip/.json export.",
  );
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const modelRequest = useRef(0);

  const activeProfile = useMemo(
    () =>
      profiles.find((profile) => profile.id === activeProfileId) ?? profiles[0],
    [profiles, activeProfileId],
  );
  const archiveConversationCount = sourceFacets.reduce(
    (total, facet) => total + facet.conversations,
    0,
  );
  const archiveMessageCount = sourceFacets.reduce(
    (total, facet) => total + facet.messages,
    0,
  );
  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (!activeProfile) return;
    setBaseUrlDraft(activeProfile.base_url);
    setCustomModelsDraft(activeProfile.custom_models.join(", "));
    setEditingKey(false);
    setApiKeyDraft("");
    if (activeProfile.default_model) setModel(activeProfile.default_model);
    if (activeProfile.connected) void loadAvailableModels(activeProfile.id);
    else {
      setModelLoad({
        profileId: activeProfile.id,
        status: "idle",
        models: [],
        message: "Connect this provider to load available models.",
      });
    }
  }, [activeProfile?.id, activeProfile?.base_url, activeProfile?.connected]);

  async function loadInitialData() {
    const [, conversationCount] = await Promise.all([
      loadPaths(),
      loadFacets(),
      loadProfiles(),
      loadSemanticStatus(),
    ]);
    if (shouldOpenOnboarding(conversationCount)) setOnboardingOpen(true);
  }

  async function loadSemanticStatus() {
    try {
      setSemanticStatus(await api<SemanticStatus>("/api/semantic/status"));
    } catch {
      setSemanticStatus(null);
    }
  }

  async function loadPaths() {
    try {
      setPaths(await api<AppPaths>("/api/paths"));
    } catch {
      setPaths(null);
    }
  }

  async function loadFacets() {
    try {
      const data = await api<{ sources: SourceFacet[] }>("/api/facets");
      setSourceFacets(data.sources ?? []);
      return (data.sources ?? []).reduce(
        (total, facet) => total + facet.conversations,
        0,
      );
    } catch {
      setSourceFacets([]);
      return null;
    }
  }

  async function loadProfiles() {
    try {
      const data = await api<{
        active_profile_id: string | null;
        profiles: LLMProfile[];
      }>("/api/llm/profiles");
      setProfiles(data.profiles ?? []);
      setActiveProfileId(data.active_profile_id ?? data.profiles[0]?.id ?? "");
    } catch (error) {
      setStatus(messageFrom(error, "Could not load AI profiles."));
    }
  }

  async function loadAvailableModels(profileId: string) {
    const requestId = modelRequest.current + 1;
    modelRequest.current = requestId;
    setModelLoad({
      profileId,
      status: "loading",
      models: modelLoad.profileId === profileId ? modelLoad.models : [],
      message: "Loading available models...",
    });
    try {
      const data = await api<{ models: string[] }>(
        `/api/llm/profiles/${profileId}/models`,
      );
      if (requestId !== modelRequest.current) return;
      const models = Array.from(new Set(data.models ?? []));
      const profile = profiles.find((item) => item.id === profileId);
      const nextModel = chooseModel(
        model,
        profile?.default_model ?? "",
        models,
        profile?.provider ?? "",
      );
      setModel(nextModel);
      setModelLoad({
        profileId,
        status: models.length ? "success" : "empty",
        models,
        message: models.length
          ? `Connected. ${models.length} available models loaded.`
          : "Connected, but the provider returned no models.",
      });
    } catch (error) {
      if (requestId !== modelRequest.current) return;
      setModelLoad({
        profileId,
        status: modelErrorStatus(error instanceof ApiError ? error.status : 0),
        models: [],
        message: messageFrom(error, "Could not load provider models."),
      });
    }
  }

  async function runSearch() {
    if (!query.trim()) {
      setStatus("Enter a search query.");
      return;
    }
    setBusy(true);
    setSearchSubmitted(true);
    setSubmittedQuery(query.trim());
    setStatus("Searching...");
    try {
      const params = new URLSearchParams({
        q: query,
        limit: "40",
        mode: searchMode,
      });
      if (sourceFilter) params.set("provider", sourceFilter);
      if (titleFilter) params.set("title", titleFilter);
      if (sourceSpaceFilter) params.set("space_id", sourceSpaceFilter);
      if (sourceTypeFilter) params.set("item_type", sourceTypeFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const data = await api<{
        results: SearchResult[];
        mode_used: string;
        semantic_status: SemanticStatus;
      }>(`/api/search?${params.toString()}`);
      setResults(data.results ?? []);
      setModeUsed(data.mode_used);
      setSemanticStatus(data.semantic_status);
      setStatus(`${data.results?.length ?? 0} conversations found.`);
    } catch (error) {
      setStatus(messageFrom(error, "Search failed."));
    } finally {
      setBusy(false);
    }
  }

  async function startSemanticIndex(rebuild = false) {
    const queued: BackgroundJob<SemanticStatus> = {
      id: "",
      status: "queued",
      stage: "preparing",
      message: "Preparing the local semantic model",
      progress: 2,
      result: null,
      error: null,
    };
    setSemanticJob(queued);
    try {
      const job = await api<BackgroundJob<SemanticStatus>>(
        "/api/semantic/index/jobs",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rebuild }),
        },
      );
      setSemanticJob(job);
      while (true) {
        await delay(500);
        const update = await api<BackgroundJob<SemanticStatus>>(
          `/api/semantic/index/jobs/${job.id}`,
        );
        setSemanticJob(update);
        if (update.status === "completed") {
          setSemanticStatus(update.result);
          setSemanticJob(null);
          setStatus("Smart search is ready.");
          return;
        }
        if (update.status === "failed")
          throw new Error(update.error || "Smart search setup failed.");
      }
    } catch (error) {
      const message = messageFrom(error, "Smart search setup failed.");
      setSemanticJob({
        ...queued,
        status: "failed",
        stage: "failed",
        message,
        error: message,
      });
      setStatus(message);
      await loadSemanticStatus();
    }
  }

  async function deleteSemanticIndex() {
    if (
      !window.confirm(
        "Remove the local semantic index? The downloaded model will be kept.",
      )
    )
      return;
    try {
      setSemanticStatus(
        await api<SemanticStatus>("/api/semantic/index", { method: "DELETE" }),
      );
      setStatus("Smart search index removed.");
    } catch (error) {
      setStatus(messageFrom(error, "Could not remove the smart search index."));
    }
  }

  async function deleteSemanticModel() {
    if (
      !window.confirm("Remove the local semantic index and downloaded model?")
    )
      return;
    try {
      setSemanticStatus(
        await api<SemanticStatus>("/api/semantic/model", { method: "DELETE" }),
      );
      setStatus("Smart search model and index removed.");
    } catch (error) {
      setStatus(messageFrom(error, "Could not remove the smart search model."));
    }
  }

  async function openDetail(id: string, messageIndex: number | null = null) {
    detailOpener.current = document.activeElement as HTMLElement | null;
    setDetail(null);
    setDetailMessageIndex(messageIndex);
    try {
      setDetail(await api<ConversationDetail>(`/api/conversations/${id}`));
      return true;
    } catch (error) {
      setStatus(messageFrom(error, "Could not open the conversation."));
      setDetailMessageIndex(null);
      return false;
    }
  }

  async function importFiles(
    files: FileList | File[],
  ): Promise<ImportSummary | null> {
    const fileList = Array.from(files);
    if (!fileList.length) return null;
    setBusy(true);
    setImportStatus(
      `Importing ${fileList.length} file${fileList.length === 1 ? "" : "s"}...`,
    );
    try {
      const formData = new FormData();
      fileList.forEach((file) => formData.append("files", file));
      const summary = await api<ImportSummary>("/api/import/upload", {
        method: "POST",
        body: formData,
      });
      setImportStatus(formatImportStatus(summary));
      await Promise.all([loadFacets(), loadSemanticStatus()]);
      return summary;
    } catch (error) {
      setImportStatus(messageFrom(error, "Import failed."));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function importLocalPath() {
    if (!importPath.trim()) {
      setImportStatus("Enter a local file or folder path.");
      return;
    }
    setBusy(true);
    setImportStatus("Importing local path...");
    try {
      const summary = await api<ImportSummary>("/api/import/path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: importPath }),
      });
      setImportStatus(formatImportStatus(summary));
      await Promise.all([loadFacets(), loadSemanticStatus()]);
    } catch (error) {
      setImportStatus(messageFrom(error, "Import failed."));
    } finally {
      setBusy(false);
    }
  }

  async function changeProfile(profileId: string) {
    setActiveProfileId(profileId);
    setModel("");
    await api("/api/llm/profiles/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId }),
    });
  }

  async function connectProvider() {
    if (!activeProfile || !apiKeyDraft.trim()) return;
    if (
      activeProfile.provider === "openai-compatible" &&
      !baseUrlDraft.trim()
    ) {
      setModelLoad({
        profileId: activeProfile.id,
        status: "error",
        models: [],
        message: "Add the provider base URL before connecting.",
      });
      return;
    }
    setSettingsBusy(true);
    try {
      const data = await api<{
        profile: LLMProfile;
        models: string[];
        selected_model: string;
      }>(`/api/llm/profiles/${activeProfile.id}/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKeyDraft,
          base_url: baseUrlDraft,
          custom_models: splitModels(customModelsDraft),
        }),
      });
      setModel(data.selected_model);
      setApiKeyDraft("");
      setEditingKey(false);
      await loadProfiles();
    } catch (error) {
      setModelLoad({
        profileId: activeProfile.id,
        status: modelErrorStatus(error instanceof ApiError ? error.status : 0),
        models: [],
        message: messageFrom(error, "Could not connect the provider."),
      });
    } finally {
      setSettingsBusy(false);
    }
  }

  async function disconnectProvider() {
    if (!activeProfile) return;
    setSettingsBusy(true);
    try {
      await api(`/api/llm/profiles/${activeProfile.id}/connection`, {
        method: "DELETE",
      });
      setModel("");
      await loadProfiles();
    } catch (error) {
      setStatus(messageFrom(error, "Could not remove the connection."));
    } finally {
      setSettingsBusy(false);
    }
  }

  async function saveAdvancedSettings() {
    if (!activeProfile) return;
    setSettingsBusy(true);
    try {
      await api(`/api/llm/profiles/${activeProfile.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: activeProfile.name,
          provider: activeProfile.provider,
          base_url: baseUrlDraft,
          default_model: activeProfile.default_model,
          custom_models: splitModels(customModelsDraft),
        }),
      });
      await loadProfiles();
      setStatus("Advanced AI settings saved.");
    } catch (error) {
      setStatus(messageFrom(error, "Could not save AI settings."));
    } finally {
      setSettingsBusy(false);
    }
  }

  async function saveModel(nextModel: string) {
    setModel(nextModel);
    if (!activeProfile || !nextModel) return;
    try {
      await api(`/api/llm/profiles/${activeProfile.id}/model`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: nextModel }),
      });
    } catch (error) {
      setStatus(messageFrom(error, "Could not save the selected model."));
    }
  }

  function openContextItem(id: string) {
    setOpenItemId(id);
    setDetail(null);
    setActiveView("explore");
  }

  function switchView(view: View) {
    setActiveView(view);
    setDetail(null);
  }

  async function refreshArchiveData() {
    setDetail(null);
    setResults([]);
    await Promise.all([loadFacets(), loadSemanticStatus()]);
  }

  function finishOnboarding(destination: "context" | "import" | "settings") {
    rememberOnboardingComplete();
    setOnboardingOpen(false);
    setActiveView(destination);
  }

  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  return (
    <div className="workspaceShell">
      <a className="skipLink" href="#workspace-content">
        Skip to content
      </a>
      <Navigation
        activeView={activeView}
        conversationCount={archiveConversationCount}
        onNavigate={switchView}
      />
      <main id="workspace-content" className="workspaceMain" tabIndex={-1}>
        <header className="workspaceToolbar">
          <form
            className="globalSearch"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              switchView("search");
              void runSearch();
            }}
          >
            <Search size={18} aria-hidden="true" />
            <label className="srOnly" htmlFor="global-search">
              Search all sources
            </label>
            <input
              id="global-search"
              ref={searchInputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your library…"
            />
            <button
              type="submit"
              aria-label="Search all sources"
              disabled={busy}
            >
              {busy ? <Loader2 className="spin" size={17} /> : "Search"}
            </button>
            <kbd aria-hidden="true">Ctrl K</kbd>
          </form>
          <button
            className="secondaryButton toolbarImport"
            type="button"
            aria-label="Import conversations"
            onClick={() => switchView("import")}
          >
            <CloudUpload size={17} />
            <span>Import conversations</span>
          </button>
        </header>
        <div className="workspaceContent">
          {(activeView === "context" || activeView === "explore") && (
            <>
              <ContextWorkspace
                openItemId={openItemId}
                view={activeView === "explore" ? "explorer" : "home"}
                onViewChange={(view) =>
                  setActiveView(view === "explorer" ? "explore" : "context")
                }
                onOpenImport={() => switchView("import")}
                onOpenSettings={() => switchView("settings")}
                onOpenLibrary={() => switchView("library")}
                activity={
                  <AnalysisQueue
                    onOpenSource={(id) => void openDetail(id)}
                    onOpenSettings={() => setActiveView("settings")}
                  />
                }
                onOpenEvidence={(conversationId, messageIndex) =>
                  openDetail(conversationId, messageIndex)
                }
              />
              {detail && (
                <div
                  className="libraryDrawerBackdrop"
                  role="presentation"
                  onClick={() => setDetail(null)}
                >
                  <aside
                    className="libraryDrawerPanel"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <ConversationDrawer
                      returnFocus={detailOpener}
                      detail={detail}
                      onOpenContextItem={openContextItem}
                      close={() => setDetail(null)}
                      targetIndex={detailMessageIndex}
                      label={
                        detailMessageIndex === null
                          ? "Context evidence"
                          : `Context evidence · message #${detailMessageIndex}`
                      }
                    />
                  </aside>
                </div>
              )}
            </>
          )}
          {activeView === "library" && (
            <>
              <LibraryView
                paths={paths}
                sourceFacets={sourceFacets}
                onOpenConversation={(id) => void openDetail(id)}
                onOpenSettings={() => switchView("settings")}
                onImport={() => setActiveView("import")}
                onArchiveChanged={refreshArchiveData}
              />
              {detail && (
                <div
                  className="libraryDrawerBackdrop"
                  role="presentation"
                  onClick={() => setDetail(null)}
                >
                  <aside
                    className="libraryDrawerPanel"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <ConversationDrawer
                      returnFocus={detailOpener}
                      detail={detail}
                      onOpenContextItem={openContextItem}
                      close={() => setDetail(null)}
                      targetIndex={detailMessageIndex}
                      label="Archived conversation"
                    />
                  </aside>
                </div>
              )}
            </>
          )}
          {activeView === "search" && (
            <SearchView
              submittedQuery={submittedQuery}
              onOpenContextItem={openContextItem}
              hasSearched={searchSubmitted}
              query={query}
              setQuery={setQuery}
              runSearch={runSearch}
              busy={busy}
              status={status}
              results={results}
              searchMode={searchMode}
              setSearchMode={setSearchMode}
              modeUsed={modeUsed}
              semanticStatus={semanticStatus}
              openDetail={openDetail}
              filtersOpen={filtersOpen}
              setFiltersOpen={setFiltersOpen}
              sourceFacets={sourceFacets}
              sourceFilter={sourceFilter}
              setSourceFilter={setSourceFilter}
              titleFilter={titleFilter}
              setTitleFilter={setTitleFilter}
              sourceSpaceFilter={sourceSpaceFilter}
              setSourceSpaceFilter={setSourceSpaceFilter}
              sourceTypeFilter={sourceTypeFilter}
              setSourceTypeFilter={setSourceTypeFilter}
              dateFrom={dateFrom}
              setDateFrom={setDateFrom}
              dateTo={dateTo}
              setDateTo={setDateTo}
              detail={detail}
              detailMessageIndex={detailMessageIndex}
              detailOpener={detailOpener}
              closeDetail={() => setDetail(null)}
            />
          )}
          {activeView === "import" && (
            <ImportView
              paths={paths}
              sourceFacets={sourceFacets}
              conversationCount={archiveConversationCount}
              messageCount={archiveMessageCount}
              importPath={importPath}
              setImportPath={setImportPath}
              importStatus={importStatus}
              busy={busy}
              importFiles={importFiles}
              importLocalPath={importLocalPath}
              showOnboarding={() => setOnboardingOpen(true)}
            />
          )}
          {activeView === "settings" && (
            <SettingsView
              status={status}
              profiles={profiles}
              activeProfile={activeProfile}
              activeProfileId={activeProfileId}
              changeProfile={changeProfile}
              model={model}
              saveModel={saveModel}
              modelLoad={modelLoad}
              reloadModels={() =>
                activeProfile && loadAvailableModels(activeProfile.id)
              }
              apiKeyDraft={apiKeyDraft}
              setApiKeyDraft={setApiKeyDraft}
              showApiKey={showApiKey}
              setShowApiKey={setShowApiKey}
              editingKey={editingKey}
              setEditingKey={setEditingKey}
              connectProvider={connectProvider}
              disconnectProvider={disconnectProvider}
              baseUrlDraft={baseUrlDraft}
              setBaseUrlDraft={setBaseUrlDraft}
              customModelsDraft={customModelsDraft}
              setCustomModelsDraft={setCustomModelsDraft}
              maxContextChars={maxContextChars}
              setMaxContextChars={setMaxContextChars}
              temperature={temperature}
              setTemperature={setTemperature}
              saveAdvancedSettings={saveAdvancedSettings}
              settingsBusy={settingsBusy}
              semanticStatus={semanticStatus}
              semanticJob={semanticJob}
              startSemanticIndex={startSemanticIndex}
              deleteSemanticIndex={deleteSemanticIndex}
              deleteSemanticModel={deleteSemanticModel}
            />
          )}
        </div>
      </main>
      <OnboardingWizard
        open={onboardingOpen}
        busy={busy}
        onImport={importFiles}
        onFinish={finishOnboarding}
      />
    </div>
  );
}

function Navigation({
  activeView,
  conversationCount,
  onNavigate,
}: {
  activeView: View;
  conversationCount: number;
  onNavigate: (view: View) => void;
}) {
  const items: Array<{ view: View; label: string; icon: React.ReactNode }> = [
    { view: "context", label: "Home", icon: <Home size={19} /> },
    { view: "explore", label: "Explore", icon: <Compass size={19} /> },
    { view: "library", label: "Sources", icon: <Library size={19} /> },
  ];
  return (
    <aside className="navigationPane">
      <button
        className="wordmark"
        type="button"
        onClick={() => onNavigate("context")}
        aria-label="Reweave Home"
      >
        <span>
          <BookOpen size={22} />
        </span>
        <strong>Reweave</strong>
      </button>
      <nav aria-label="Primary navigation">
        {items.map((item) => (
          <button
            className={activeView === item.view ? "navItem active" : "navItem"}
            type="button"
            onClick={() => onNavigate(item.view)}
            aria-current={activeView === item.view ? "page" : undefined}
            key={item.view}
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="navigationFooter">
        <button
          className={activeView === "settings" ? "navItem active" : "navItem"}
          type="button"
          onClick={() => onNavigate("settings")}
          aria-current={activeView === "settings" ? "page" : undefined}
        >
          <Settings size={19} />
          <span>Settings</span>
        </button>
        <div className="archiveStatus">
          <span>
            <Database size={15} /> Local library
          </span>
          <small>
            {conversationCount.toLocaleString()} saved conversations
          </small>
        </div>
      </div>
    </aside>
  );
}

type SearchViewProps = {
  sourceSpaceFilter: string;
  setSourceSpaceFilter: (value: string) => void;
  sourceTypeFilter: string;
  setSourceTypeFilter: (value: string) => void;
  submittedQuery: string;
  onOpenContextItem: (id: string) => void;
  hasSearched: boolean;
  query: string;
  setQuery: (value: string) => void;
  runSearch: () => void;
  busy: boolean;
  status: string;
  results: SearchResult[];
  searchMode: SearchMode;
  setSearchMode: (value: SearchMode) => void;
  modeUsed: string;
  semanticStatus: SemanticStatus | null;
  openDetail: (id: string, index?: number | null) => void;
  filtersOpen: boolean;
  setFiltersOpen: (value: boolean) => void;
  sourceFacets: SourceFacet[];
  sourceFilter: string;
  setSourceFilter: (value: string) => void;
  titleFilter: string;
  setTitleFilter: (value: string) => void;
  dateFrom: string;
  setDateFrom: (value: string) => void;
  dateTo: string;
  setDateTo: (value: string) => void;
  detail: ConversationDetail | null;
  detailMessageIndex: number | null;
  detailOpener: React.RefObject<HTMLElement | null>;
  closeDetail: () => void;
};

function SearchView(props: SearchViewProps) {
  const [spaces, setSpaces] = useState<Array<{id: string; name: string; scope_type: string}>>([]);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/context/spaces", {signal: controller.signal})
      .then(async (response) => response.ok ? response.json() : null)
      .then((result) => { if (!controller.signal.aborted && Array.isArray(result?.results)) setSpaces(result.results); })
      .catch(() => undefined);
    return () => controller.abort();
  }, []);
  const highlightTerms = useMemo(
    () => extractHighlightTerms(props.query),
    [props.query],
  );
  return (
    <section className="searchScreen readingSearch">
      <div className="searchWorkspace">
        <header className="pageHeader searchPageHeader">
          <span className="sectionLabel">Your local library</span>
          <h1>Search your library</h1>
          <p>
            Find saved context and original conversations, with their exact source excerpts.
            Search works without an API key.
          </p>
        </header>
        <ContextSearch query={props.submittedQuery} onOpenItem={props.onOpenContextItem} />
        <h2>Original source matches</h2>
        <div className="searchControls">
          <div className="filterRow">
            <label className="modePicker">
              <span>Mode</span>
              <select
                aria-label="Search mode"
                value={props.searchMode}
                onChange={(event) =>
                  props.setSearchMode(event.target.value as SearchMode)
                }
              >
                <option value="auto">Auto</option>
                <option value="keyword">Keyword</option>
                <option value="semantic">Semantic</option>
              </select>
            </label>
            <button
              className={props.filtersOpen ? "filterChip active" : "filterChip"}
              type="button"
              aria-expanded={props.filtersOpen}
              onClick={() => props.setFiltersOpen(!props.filtersOpen)}
            >
              <SlidersHorizontal size={15} /> Filters <ChevronDown size={14} />
            </button>
            <button
              className="secondaryButton"
              type="button"
              onClick={props.runSearch}
              disabled={props.busy || !props.query.trim()}
            >
              <Search size={16} /> Apply search
            </button>
            <span className="resultCount" role="status">
              {props.status}
            </span>
          </div>
          {props.filtersOpen && (
            <div className="filterPanel">
              <label>Associated project or topic<select value={props.sourceSpaceFilter}
                onChange={(event) => props.setSourceSpaceFilter(event.target.value)}>
                <option value="">All spaces</option>{spaces.filter((space) => ["project", "topic", "destination"].includes(space.scope_type)).map((space) => <option key={space.id} value={space.id}>{space.name}</option>)}
              </select></label>
              <label>Derived Context type<select value={props.sourceTypeFilter}
                onChange={(event) => props.setSourceTypeFilter(event.target.value)}>
                <option value="">All types</option>{["project_fact", "decision", "lesson", "insight", "concept", "value", "preference", "open_question", "action", "follow_up"].map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
              </select></label>
              <label>
                Source
                <select
                  value={props.sourceFilter}
                  onChange={(event) =>
                    props.setSourceFilter(event.target.value)
                  }
                >
                  <option value="">All sources</option>
                  {props.sourceFacets.map((facet) => (
                    <option value={facet.source} key={facet.source}>
                      {facet.source} ({facet.conversations})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Title contains
                <input
                  value={props.titleFilter}
                  onChange={(event) => props.setTitleFilter(event.target.value)}
                />
              </label>
              <label>
                From
                <input
                  type="date"
                  value={props.dateFrom}
                  onChange={(event) => props.setDateFrom(event.target.value)}
                />
              </label>
              <label>
                To
                <input
                  type="date"
                  value={props.dateTo}
                  onChange={(event) => props.setDateTo(event.target.value)}
                />
              </label>
            </div>
          )}
        </div>
        <div className="searchContent" aria-busy={props.busy}>
          <div className="resultList">
            {props.results.map((result) => (
              <article className="resultRow" key={result.id}>
                <BookOpen size={20} aria-hidden="true" />
                <div className="resultBody">
                  <button
                    type="button"
                    className="searchResultTitle"
                    onClick={() => props.openDetail(result.id)}
                  >
                    <HighlightedText
                      text={result.title}
                      terms={highlightTerms}
                    />
                  </button>
                  <p className="searchResultMeta">
                    {result.source} · {formatDate(result.created_at)} ·{" "}
                    {result.raw_message_count} messages
                  </p>
                  <div className="excerptList">
                    {result.excerpts.slice(0, 2).map((excerpt) => (
                      <div className="excerpt" key={excerpt.message_id}>
                        <MarkdownContent
                          markdown={excerpt.excerpt}
                          compact
                          highlightTerms={highlightTerms}
                        />
                        <button
                          type="button"
                          className="contextTextButton"
                          onClick={() =>
                            props.openDetail(result.id, excerpt.message_index)
                          }
                        >
                          View source message #{excerpt.message_index}
                          <ChevronRight size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </article>
            ))}
          </div>
          {!props.results.length && (
            <div className="emptyState">
              <Search size={28} />
              <h2>
                {props.busy
                  ? "Searching your sources…"
                  : props.hasSearched
                    ? "No matching sources"
                    : "Find something worth returning to"}
              </h2>
              <p>
                {props.hasSearched
                  ? "Try a shorter phrase or broaden the source and date filters."
                  : "Use the search field above to find ideas, decisions, or phrases across your saved conversations."}
              </p>
            </div>
          )}
          {props.results.length >= 40 && (
            <p className="searchResultLimit">
              Showing the first {props.results.length} matching sources. Narrow
              the search or use date filters to find another part of your
              archive.
            </p>
          )}
        </div>
      </div>
      {props.detail && (
        <div
          className="libraryDrawerBackdrop"
          role="presentation"
          onClick={props.closeDetail}
        >
          <aside
            className="libraryDrawerPanel"
            onClick={(event) => event.stopPropagation()}
          >
            <ConversationDrawer
              returnFocus={props.detailOpener}
              detail={props.detail}
              onOpenContextItem={props.onOpenContextItem}
              targetIndex={props.detailMessageIndex}
              close={props.closeDetail}
              label="Source preview"
              highlightTerms={highlightTerms}
            />
          </aside>
        </div>
      )}
    </section>
  );
}

function ConversationDrawer({
  detail,
  targetIndex,
  close,
  label,
  highlightTerms = [],
  onOpenContextItem,
  returnFocus,
}: {
  detail: ConversationDetail;
  targetIndex: number | null;
  close: () => void;
  label: string;
  highlightTerms?: string[];
  onOpenContextItem?: (id: string) => void;
  returnFocus?: React.RefObject<HTMLElement | null>;
}) {
  const [viewMode, setViewMode] = useState<"all" | "context">(
    targetIndex === null ? "all" : "context",
  );
  const targetRef = useRef<HTMLElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(dialogRef, close, returnFocus);
  const canShowContext = targetIndex !== null;
  const messages = useMemo(
    () =>
      viewMode === "context" && targetIndex !== null
        ? detail.messages.filter(
            (message) => Math.abs(message.index - targetIndex) <= 2,
          )
        : detail.messages,
    [detail.messages, targetIndex, viewMode],
  );

  useEffect(() => {
    setViewMode(targetIndex === null ? "all" : "context");
  }, [detail.conversation.id, targetIndex]);

  useEffect(() => {
    if (targetIndex === null) return;
    window.requestAnimationFrame(() => {
      targetRef.current?.scrollIntoView({ block: "center" });
    });
  }, [detail.conversation.id, targetIndex, viewMode]);

  function jumpToTarget() {
    if (targetIndex === null) return;
    if (viewMode !== "all") {
      setViewMode("all");
      return;
    }
    targetRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  return (
    <section
      ref={dialogRef}
      className="conversationDrawer"
      role="dialog"
      aria-modal="true"
      aria-label={label}
      tabIndex={-1}
    >
      <header className="conversationDrawerHeader">
        <div>
          <span className="sectionLabel">{label}</span>
          <h2 title={detail.conversation.title}>{detail.conversation.title}</h2>
          <p>
            {detail.conversation.source} /{" "}
            {detail.conversation.raw_message_count} messages /{" "}
            {formatDate(detail.conversation.created_at)}
          </p>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close conversation drawer"
        >
          <X size={17} />
        </button>
      </header>
      {onOpenContextItem && <SourceContextLinks conversationId={detail.conversation.id} onOpenItem={onOpenContextItem} />}
      {canShowContext && (
        <div
          className="drawerControls"
          role="group"
          aria-label="Conversation view"
        >
          <button
            className={viewMode === "context" ? "active" : ""}
            type="button"
            onClick={() => setViewMode("context")}
          >
            Context around #{targetIndex}
          </button>
          <button
            className={viewMode === "all" ? "active" : ""}
            type="button"
            onClick={() => setViewMode("all")}
          >
            All messages
          </button>
          <button type="button" onClick={jumpToTarget}>
            Jump to #{targetIndex}
          </button>
        </div>
      )}
      <div className="messageList drawerMessageList">
        {messages.map((message) => (
          <article
            className={
              message.index === targetIndex
                ? "messageItem target"
                : "messageItem"
            }
            ref={message.index === targetIndex ? targetRef : undefined}
            key={message.id}
          >
            <header>
              <strong>{message.role}</strong>
              <small>#{message.index}</small>
            </header>
            <MarkdownContent
              markdown={message.content}
              variant="conversation"
              highlightTerms={highlightTerms}
            />
          </article>
        ))}
      </div>
    </section>
  );
}

function ImportView({
  paths,
  sourceFacets,
  conversationCount,
  messageCount,
  importPath,
  setImportPath,
  importStatus,
  busy,
  importFiles,
  importLocalPath,
  showOnboarding,
}: {
  paths: AppPaths | null;
  sourceFacets: SourceFacet[];
  conversationCount: number;
  messageCount: number;
  importPath: string;
  setImportPath: (value: string) => void;
  importStatus: string;
  busy: boolean;
  importFiles: (files: FileList | File[]) => void;
  importLocalPath: () => void;
  showOnboarding: () => void;
}) {
  return (
    <section className="singlePage">
      <header className="pageHeader importHeader">
        <div>
          <span className="sectionLabel">Local archive</span>
          <h1>Import conversations</h1>
          <p>
            Add ChatGPT or Claude exports. Reweave keeps your searchable archive
            on this device.
          </p>
        </div>
        <button
          className="secondaryButton"
          type="button"
          onClick={showOnboarding}
        >
          <BookOpen size={16} /> Export guide
        </button>
      </header>
      <div className="statsGrid">
        <div>
          <Database size={20} />
          <span>
            <strong>{conversationCount.toLocaleString()}</strong>
            <small>Conversations</small>
          </span>
        </div>
        <div>
          <FileText size={20} />
          <span>
            <strong>{messageCount.toLocaleString()}</strong>
            <small>Messages</small>
          </span>
        </div>
        {sourceFacets.map((facet) => (
          <div key={facet.source}>
            <Library size={20} />
            <span>
              <strong>{facet.conversations.toLocaleString()}</strong>
              <small>{facet.source}</small>
            </span>
          </div>
        ))}
      </div>
      <div className="importGrid">
        <div
          className="dropZone"
          onDrop={(event) => {
            event.preventDefault();
            if (!busy) importFiles(event.dataTransfer.files);
          }}
          onDragOver={(event) => event.preventDefault()}
        >
          <span>
            <FileUp size={28} />
          </span>
          <h2>Drop export files here</h2>
          <p>Choose one or more .zip or .json exports.</p>
          <label className="primaryButton filePicker">
            <CloudUpload size={17} /> Choose files
            <input
              type="file"
              accept=".zip,.json,application/json,application/zip,application/x-zip-compressed"
              multiple
              onChange={(event) => {
                if (event.currentTarget.files)
                  importFiles(event.currentTarget.files);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>
        <div className="importPathCard">
          <FolderInput size={24} />
          <h2>Import a local path</h2>
          <p>
            Use a folder, JSON file, or zip path already available on this
            device.
          </p>
          <label>
            Local path
            <input
              value={importPath}
              onChange={(event) => setImportPath(event.target.value)}
              placeholder="C:\\path\\to\\export.zip"
            />
          </label>
          <button
            className="secondaryButton"
            type="button"
            onClick={importLocalPath}
            disabled={busy}
          >
            <FolderInput size={16} /> Import path
          </button>
        </div>
      </div>
      <div className="statusNotice" role="status">
        <CheckCircle2 size={17} />
        <span>{importStatus}</span>
      </div>
      {paths && (
        <div className="pathDetails">
          <strong>Archive database</strong>
          <span>{paths.db_path}</span>
          <strong>Imports folder</strong>
          <span>{paths.imports_dir}</span>
        </div>
      )}
    </section>
  );
}

type SettingsProps = {
  status: string;
  profiles: LLMProfile[];
  activeProfile?: LLMProfile;
  activeProfileId: string;
  changeProfile: (id: string) => void;
  model: string;
  saveModel: (model: string) => void;
  modelLoad: ModelLoadState;
  reloadModels: () => void;
  apiKeyDraft: string;
  setApiKeyDraft: (value: string) => void;
  showApiKey: boolean;
  setShowApiKey: (value: boolean) => void;
  editingKey: boolean;
  setEditingKey: (value: boolean) => void;
  connectProvider: () => void;
  disconnectProvider: () => void;
  baseUrlDraft: string;
  setBaseUrlDraft: (value: string) => void;
  customModelsDraft: string;
  setCustomModelsDraft: (value: string) => void;
  maxContextChars: number;
  setMaxContextChars: (value: number) => void;
  temperature: number;
  setTemperature: (value: number) => void;
  saveAdvancedSettings: () => void;
  settingsBusy: boolean;
  semanticStatus: SemanticStatus | null;
  semanticJob: BackgroundJob<SemanticStatus> | null;
  startSemanticIndex: (rebuild?: boolean) => void;
  deleteSemanticIndex: () => void;
  deleteSemanticModel: () => void;
};

function SettingsView(props: SettingsProps) {
  const detail =
    providerDetails[props.activeProfile?.provider ?? "openai"] ??
    providerDetails.openai;
  const connected = props.activeProfile?.connected;
  return (
    <section className="singlePage settingsPage">
      <header className="pageHeader">
        <span className="sectionLabel">Bring your own model</span>
        <h1>AI connection</h1>
        <p>
          Capture, browsing, and search stay available without a provider.
          Connect one when you want source-grounded Context analysis.
        </p>
      </header>
      {props.status !== "Search your imported archive." && (
        <p className="statusNotice" role="status">
          {props.status}
        </p>
      )}
      <ChatUseGuide />
      <div className="settingsLayout">
        <section className="settingsSection">
          <header>
            <div>
              <h2>Provider connection</h2>
              <p>
                API keys stay in your operating-system credential store. A
                successful saved connection starts pending Context analysis
                automatically.
              </p>
            </div>
            {connected && (
              <span className="connectedBadge">
                <Check size={13} /> Connected
              </span>
            )}
          </header>
          <label>
            Provider
            <select
              value={props.activeProfileId}
              onChange={(event) => props.changeProfile(event.target.value)}
            >
              {props.profiles.map((profile) => (
                <option value={profile.id} key={profile.id}>
                  {providerDetails[profile.provider]?.label ?? profile.name}
                </option>
              ))}
            </select>
          </label>
          {connected && !props.editingKey ? (
            <div className="connectedKey">
              <span>
                <KeyRound size={18} />
                <span>
                  <strong>{props.activeProfile?.masked_key}</strong>
                  <small>
                    Stored securely in your operating system keyring.
                  </small>
                </span>
              </span>
              <div>
                <button
                  className="secondaryButton"
                  type="button"
                  onClick={() => props.setEditingKey(true)}
                >
                  Change key
                </button>
                <button
                  className="dangerButton"
                  type="button"
                  onClick={props.disconnectProvider}
                >
                  Remove
                </button>
              </div>
            </div>
          ) : (
            <div className="connectionForm">
              <p>
                {detail.keyHelp}{" "}
                {detail.keyUrl && (
                  <a href={detail.keyUrl} target="_blank" rel="noreferrer">
                    Get an API key
                  </a>
                )}
              </p>
              <div className="secretInput">
                <input
                  type={props.showApiKey ? "text" : "password"}
                  value={props.apiKeyDraft}
                  onChange={(event) => props.setApiKeyDraft(event.target.value)}
                  placeholder={`Paste your ${detail.label} API key`}
                  aria-label="API key"
                />
                <button
                  type="button"
                  onClick={() => props.setShowApiKey(!props.showApiKey)}
                  aria-label={
                    props.showApiKey ? "Hide API key" : "Show API key"
                  }
                >
                  {props.showApiKey ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              <div className="buttonRow">
                <button
                  className="primaryButton"
                  type="button"
                  onClick={props.connectProvider}
                  disabled={props.settingsBusy || !props.apiKeyDraft.trim()}
                >
                  <KeyRound size={16} /> Connect
                </button>
                {connected && (
                  <button
                    className="secondaryButton"
                    type="button"
                    onClick={() => props.setEditingKey(false)}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}
          <div className={`modelStatus ${props.modelLoad.status}`}>
            {props.modelLoad.status === "loading" ? (
              <Loader2 className="spin" size={16} />
            ) : props.modelLoad.status === "success" ? (
              <CheckCircle2 size={16} />
            ) : (
              <AlertCircle size={16} />
            )}
            <span>{props.modelLoad.message}</span>
          </div>
        </section>
        <section className="settingsSection">
          <header>
            <div>
              <h2>Context analysis model</h2>
              <p>Choose the model used for source-grounded Context analysis.</p>
            </div>
            <button
              className="iconButton"
              type="button"
              onClick={props.reloadModels}
              aria-label="Refresh models"
            >
              <RefreshCw size={17} />
            </button>
          </header>
          <label>
            Available model
            <select
              value={props.model}
              onChange={(event) => props.saveModel(event.target.value)}
              disabled={!props.modelLoad.models.length}
            >
              <option value="">Choose a model</option>
              {props.modelLoad.models.map((item) => (
                <option value={item} key={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <div className="twoColumnFields">
            <label>
              Context characters
              <input
                type="number"
                min={1000}
                value={props.maxContextChars}
                onChange={(event) =>
                  props.setMaxContextChars(Number(event.target.value))
                }
              />
            </label>
            <label>
              Temperature
              <input
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={props.temperature}
                onChange={(event) =>
                  props.setTemperature(Number(event.target.value))
                }
              />
            </label>
          </div>
        </section>
        <section className="settingsSection full smartSearchCard">
          <header>
            <div>
              <h2>Smart search</h2>
              <p>
                Optional local meaning search for Korean and English. Nothing is
                uploaded.
              </p>
            </div>
            {props.semanticStatus?.ready && (
              <span className="connectedBadge">
                <Check size={13} /> Ready
              </span>
            )}
          </header>
          <div className="smartSearchDetails">
            <div>
              <strong>
                {props.semanticStatus?.model_downloaded
                  ? "Multilingual model installed"
                  : "Model not downloaded"}
              </strong>
              <p>
                Reweave downloads about 220 MB only after you enable this
                feature, then stores message embeddings and searches them
                locally.
              </p>
            </div>
            <dl>
              <div>
                <dt>Indexed chunks</dt>
                <dd>
                  {props.semanticStatus?.indexed_chunks.toLocaleString() ?? "0"}
                </dd>
              </div>
              <div>
                <dt>Archive messages</dt>
                <dd>
                  {props.semanticStatus?.total_messages.toLocaleString() ?? "0"}
                </dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd>Multilingual MiniLM</dd>
              </div>
            </dl>
          </div>
          {props.semanticJob && (
            <div className="smartProgress" aria-live="polite">
              <strong>{props.semanticJob.message}</strong>
              <div className="progressTrack">
                <span style={{ width: `${props.semanticJob.progress}%` }} />
              </div>
              <div className="progressMeta">
                <span>{props.semanticJob.stage}</span>
                <span>{props.semanticJob.progress}%</span>
              </div>
            </div>
          )}
          <div className="buttonRow">
            {!props.semanticStatus?.ready ? (
              <button
                className="primaryButton"
                type="button"
                onClick={() => props.startSemanticIndex(false)}
                disabled={Boolean(props.semanticJob)}
              >
                <Download size={16} /> Download model &amp; index archive
              </button>
            ) : (
              <button
                className="secondaryButton"
                type="button"
                onClick={() => props.startSemanticIndex(true)}
                disabled={Boolean(props.semanticJob)}
              >
                <RefreshCw size={16} /> Rebuild index
              </button>
            )}
            {Boolean(props.semanticStatus?.indexed_chunks) && (
              <button
                className="secondaryButton"
                type="button"
                onClick={props.deleteSemanticIndex}
                disabled={Boolean(props.semanticJob)}
              >
                <Trash2 size={16} /> Remove index
              </button>
            )}
            {props.semanticStatus?.model_downloaded && (
              <button
                className="dangerButton"
                type="button"
                onClick={props.deleteSemanticModel}
                disabled={Boolean(props.semanticJob)}
              >
                <Trash2 size={16} /> Remove model
              </button>
            )}
          </div>
        </section>
        <section className="settingsSection full">
          <header><div><h2>Local diagnostics</h2><p>Download a support report containing counts and runtime versions. Conversation content, Context text, names, personal paths, and credentials are excluded.</p></div></header>
          <a className="secondaryButton" href="/api/diagnostics/export" download="reweave-diagnostics.json"><Download size={16}/> Download redacted diagnostics</a>
        </section>
        <section className="settingsSection full">
          <header>
            <div>
              <h2>Advanced provider settings</h2>
              <p>
                Only needed for compatible endpoints or models not returned
                automatically.
              </p>
            </div>
          </header>
          <div className="twoColumnFields">
            <label>
              Base URL
              <input
                value={props.baseUrlDraft}
                onChange={(event) => props.setBaseUrlDraft(event.target.value)}
                placeholder="Optional provider endpoint"
              />
            </label>
            <label>
              Additional model IDs
              <input
                value={props.customModelsDraft}
                onChange={(event) =>
                  props.setCustomModelsDraft(event.target.value)
                }
                placeholder="Comma-separated"
              />
            </label>
          </div>
          <button
            className="secondaryButton alignedButton"
            type="button"
            onClick={props.saveAdvancedSettings}
            disabled={props.settingsBusy}
          >
            <Save size={16} /> Save advanced settings
          </button>
        </section>
      </div>
    </section>
  );
}

async function api<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? data.detail
        : data;
    throw new ApiError(
      typeof detail === "string" ? detail : "Request failed.",
      response.status,
    );
  }
  return data as T;
}

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function messageFrom(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function formatImportStatus(summary: ImportSummary) {
  const updates =
    summary.updated_conversations || summary.updated_messages
      ? ` Updated ${summary.updated_conversations} conversations and ${summary.updated_messages} messages.`
      : "";
  const invalidated = summary.invalidated_embeddings
    ? ` ${summary.invalidated_embeddings} smart-search chunks will be refreshed.`
    : "";
  return `Imported ${summary.inserted_conversations} new conversations and ${summary.inserted_messages} new messages from ${summary.parsed_conversations} parsed conversations.${updates}${invalidated}${summary.skipped_files.length ? ` ${summary.skipped_files.length} files skipped.` : ""}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(date);
}

function splitModels(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function modelErrorStatus(status: number): ModelLoadState["status"] {
  if (status === 401) return "invalid-key";
  if (status === 403) return "permission";
  if (status === 429) return "rate-limit";
  if (status === 0 || status === 502) return "network";
  return "error";
}

function chooseModel(
  current: string,
  saved: string,
  models: string[],
  provider: string,
) {
  if (models.includes(current)) return current;
  if (models.includes(saved)) return saved;
  const preference =
    provider === "anthropic"
      ? "sonnet"
      : provider === "gemini"
        ? "flash"
        : "mini";
  return (
    models.find((item) => item.toLocaleLowerCase().includes(preference)) ??
    models[0] ??
    ""
  );
}

type OnboardingStorage = Pick<Storage, "getItem" | "setItem">;

export const ONBOARDING_STORAGE_KEY = "reweave:onboarding-complete:v1";

export function hasCompletedOnboarding(storage?: OnboardingStorage) {
  try {
    return (
      (storage ?? window.localStorage).getItem(ONBOARDING_STORAGE_KEY) ===
      "true"
    );
  } catch {
    return false;
  }
}

export function shouldOpenOnboarding(
  conversationCount: number | null,
  storage?: OnboardingStorage,
) {
  return conversationCount === 0 && !hasCompletedOnboarding(storage);
}

export function rememberOnboardingComplete(storage?: OnboardingStorage) {
  try {
    (storage ?? window.localStorage).setItem(ONBOARDING_STORAGE_KEY, "true");
  } catch {
    // Onboarding still works when storage is unavailable in a restricted webview.
  }
}
