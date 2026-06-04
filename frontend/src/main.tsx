import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Clock3,
  Eye,
  EyeOff,
  FileDown,
  FileSearch,
  FileUp,
  FolderInput,
  KeyRound,
  Lightbulb,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Settings,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import { MarkdownContent, type CitationTarget } from "./MarkdownContent";
import "./styles.css";

type Excerpt = {
  conversation_id: string;
  message_id: string;
  message_index: number;
  source: string;
  title: string;
  role: string;
  timestamp: string | null;
  excerpt: string;
};

export type SearchResult = {
  id: string;
  source: string;
  title: string;
  created_at: string;
  updated_at: string | null;
  raw_message_count: number;
  match_count: number;
  excerpts: Excerpt[];
};

type ConversationDetail = {
  conversation: SearchResult;
  messages: Array<{
    id: string;
    conversation_id: string;
    index: number;
    role: string;
    content: string;
    timestamp: string | null;
  }>;
};

type Insight = {
  id: string;
  title: string;
  selected_conversation_ids: string[];
  provider: string;
  model: string;
  markdown: string;
  created_at: string;
  language?: "ko" | "en";
  performance?: {
    total_ms?: number;
    chunk_count?: number;
    model_call_count?: number;
    context_chars?: number;
  };
};

type InsightJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  message: string;
  progress: number;
  result: Insight | null;
  error: string | null;
};

type ImportSummary = {
  parsed_conversations: number;
  inserted_conversations: number;
  inserted_messages: number;
  skipped_files: string[];
};

type AppPaths = {
  data_dir: string;
  db_path: string;
  imports_dir: string;
  extracted_dir: string;
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

export type LLMProfile = {
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

type LLMProfilesResponse = {
  active_profile_id: string | null;
  profiles: LLMProfile[];
};

type ModelDiscoveryResponse = {
  models: string[];
  validated_key_label: string;
};

type ConnectResponse = {
  profile: LLMProfile;
  models: string[];
  selected_model: string;
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

type ProfileDraft = {
  base_url: string;
  custom_models: string;
};

type SettingsState = {
  profileId: string;
  model: string;
  customModel: string;
  maxContextChars: number;
  temperature: number;
};

const defaultSettings: SettingsState = {
  profileId: "",
  model: "",
  customModel: "",
  maxContextChars: 80000,
  temperature: 0.2
};

const initialModelLoadState: ModelLoadState = {
  profileId: "",
  status: "idle",
  models: [],
  message: "Choose a provider and connect your API key."
};

const customModelValue = "__custom__";
const providerDetails: Record<string, { label: string; keyUrl?: string; keyHelp: string }> = {
  openai: {
    label: "OpenAI",
    keyUrl: "https://platform.openai.com/api-keys",
    keyHelp: "Create a key in the OpenAI platform."
  },
  anthropic: {
    label: "Anthropic",
    keyUrl: "https://console.anthropic.com/settings/keys",
    keyHelp: "Create a key in the Anthropic Console."
  },
  gemini: {
    label: "Google Gemini",
    keyUrl: "https://aistudio.google.com/app/apikey",
    keyHelp: "Create a key in Google AI Studio."
  },
  openrouter: {
    label: "OpenRouter",
    keyUrl: "https://openrouter.ai/settings/keys",
    keyHelp: "Create a key in OpenRouter. The endpoint is configured automatically."
  },
  "openai-compatible": {
    label: "OpenAI-compatible",
    keyHelp: "Use the API key and base URL from your provider."
  }
};

function App() {
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [titleFilter, setTitleFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedById, setSelectedById] = useState<Record<string, SearchResult>>({});
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailMessageIndex, setDetailMessageIndex] = useState<number | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [insightJob, setInsightJob] = useState<InsightJob | null>(null);
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [paths, setPaths] = useState<AppPaths | null>(null);
  const [sourceFacets, setSourceFacets] = useState<SourceFacet[]>([]);
  const [profiles, setProfiles] = useState<LLMProfile[]>([]);
  const [profileDraft, setProfileDraft] = useState<ProfileDraft | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [editingKey, setEditingKey] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [modelLoad, setModelLoad] = useState<ModelLoadState>(initialModelLoadState);
  const [importPath, setImportPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [status, setStatus] = useState("Search your imported archive.");
  const [importStatus, setImportStatus] = useState("Drop files or choose a .zip/.json export.");
  const modelLoadRequest = useRef(0);

  const selectedIds = useMemo(() => Object.keys(selectedById), [selectedById]);
  const selectedResults = useMemo(() => Object.values(selectedById), [selectedById]);
  const insightBusy = insightJob?.status === "queued" || insightJob?.status === "running";
  const reportOpen = Boolean(insight || insightBusy);
  const visibleDetailMessages = useMemo(() => {
    if (!detail) return [];
    if (detailMessageIndex === null) return detail.messages.slice(0, 24);
    return detail.messages.filter(
      (message) => Math.abs(message.index - detailMessageIndex) <= 2
    );
  }, [detail, detailMessageIndex]);
  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.id === settings.profileId) ?? profiles[0],
    [profiles, settings.profileId]
  );
  const providerDetail = providerDetails[activeProfile?.provider ?? "openai"] ?? providerDetails.openai;
  const modelOptions = modelLoad.profileId === activeProfile?.id ? modelLoad.models : [];
  const insightModel = settings.model === customModelValue ? settings.customModel : settings.model;
  const selectedModelUnavailable = isModelUnavailable(
    settings.model,
    modelLoad.status,
    modelOptions
  );
  const showSourceFilter = sourceFacets.length > 1;

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (!activeProfile) return;
    setProfileDraft(profileToDraft(activeProfile));
    setApiKeyDraft("");
    setEditingKey(false);
    setSettings((current) => {
      if (current.profileId === activeProfile.id) return current;
      return {
        ...current,
        profileId: activeProfile.id,
        model: "",
        customModel: ""
      };
    });
  }, [activeProfile]);

  useEffect(() => {
    if (!activeProfile) return;
    if (!activeProfile.connected) {
      modelLoadRequest.current += 1;
      setModelLoad({
        profileId: activeProfile.id,
        status: "idle",
        models: [],
        message: "Paste an API key and connect to load available models."
      });
      return;
    }
    void loadAvailableModels(activeProfile.id);
  }, [activeProfile?.id, activeProfile?.provider, activeProfile?.base_url, activeProfile?.connected]);

  async function loadInitialData() {
    await Promise.all([loadPaths(), loadFacets(), loadProfiles()]);
  }

  async function loadPaths() {
    try {
      const response = await fetch("/api/paths");
      const data = await parseJsonResponse<AppPaths>(response);
      setPaths(data);
    } catch {
      setPaths(null);
    }
  }

  async function loadFacets() {
    try {
      const response = await fetch("/api/facets");
      const data = await parseJsonResponse<{ sources: SourceFacet[] }>(response);
      setSourceFacets(data.sources ?? []);
    } catch {
      setSourceFacets([]);
    }
  }

  async function loadProfiles() {
    try {
      const response = await fetch("/api/llm/profiles");
      const data = await parseJsonResponse<LLMProfilesResponse>(response);
      setProfiles(data.profiles ?? []);
      setSettings((current) => ({
        ...current,
        profileId: data.active_profile_id ?? data.profiles?.[0]?.id ?? current.profileId
      }));
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not load LLM profiles.");
    }
  }

  async function loadAvailableModels(profileId: string) {
    const requestId = modelLoadRequest.current + 1;
    const previousModels = modelLoad.profileId === profileId ? modelLoad.models : [];
    modelLoadRequest.current = requestId;
    setModelLoad({
      profileId,
      status: "loading",
      models: previousModels,
      message: "Loading available models from the provider..."
    });
    try {
      const response = await fetch(`/api/llm/profiles/${profileId}/models`);
      const data = await parseJsonResponse<ModelDiscoveryResponse>(response);
      if (requestId !== modelLoadRequest.current) return;
      const models = Array.from(new Set(data.models ?? []));
      const loadedMessage = `${models.length} available model${models.length === 1 ? "" : "s"} loaded.`;
      setModelLoad({
        profileId,
        status: models.length ? "success" : "empty",
        models,
        message: models.length
          ? `Connected. ${loadedMessage}`
          : "Connected, but the provider returned no models."
      });
      setStatus(models.length ? loadedMessage : "The provider returned no available models.");
      setSettings((current) => {
        if (current.profileId !== profileId || !models.length) return current;
        const profile = profiles.find((item) => item.id === profileId);
        const model = chooseAvailableModel(
          current.model,
          profile?.default_model ?? "",
          models,
          profile?.provider ?? ""
        );
        return { ...current, model };
      });
    } catch (error) {
      if (requestId !== modelLoadRequest.current) return;
      const errorStatus = error instanceof ApiError ? error.status : 0;
      setModelLoad({
        profileId,
        status: modelErrorStatus(errorStatus),
        models: previousModels,
        message: error instanceof Error ? error.message : "Could not load provider models."
      });
      setStatus(error instanceof Error ? error.message : "Could not load provider models.");
    }
  }

  async function runSearch() {
    if (!query.trim()) {
      setStatus("Enter a search query.");
      return;
    }
    setBusy(true);
    setStatus("Searching...");
    try {
      const params = new URLSearchParams({ q: query, limit: "40" });
      if (sourceFilter) params.set("provider", sourceFilter);
      if (titleFilter) params.set("title", titleFilter);
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const response = await fetch(`/api/search?${params.toString()}`);
      const data = await response.json();
      setResults(data.results ?? []);
      setStatus(`${data.results?.length ?? 0} conversations found.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function importFiles(files: FileList | File[]) {
    const fileList = Array.from(files);
    if (!fileList.length) return;

    setBusy(true);
    const importingMessage = `Importing ${fileList.length} file${fileList.length === 1 ? "" : "s"}...`;
    setStatus(importingMessage);
    setImportStatus(importingMessage);
    try {
      const formData = new FormData();
      fileList.forEach((file) => formData.append("files", file));
      const response = await fetch("/api/import/upload", {
        method: "POST",
        body: formData
      });
      const data = await parseJsonResponse<ImportSummary>(response);
      const message = formatImportStatus(data);
      setStatus(message);
      setImportStatus(message);
      await loadFacets();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Import failed.";
      setStatus(message);
      setImportStatus(message);
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
      const response = await fetch("/api/import/path", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: importPath })
      });
      const data = await parseJsonResponse<ImportSummary>(response);
      const message = formatImportStatus(data);
      setStatus(message);
      setImportStatus(message);
      await loadFacets();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Import failed.";
      setStatus(message);
      setImportStatus(message);
    } finally {
      setBusy(false);
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    if (busy) return;
    importFiles(event.dataTransfer.files);
  }

  async function openDetail(id: string, messageIndex: number | null = null) {
    setBusy(true);
    setDetailMessageIndex(messageIndex);
    try {
      const response = await fetch(`/api/conversations/${id}`);
      const data = await parseJsonResponse<ConversationDetail>(response);
      setDetail(data);
    } finally {
      setBusy(false);
    }
  }

  function openCitation(target: CitationTarget) {
    void openDetail(target.conversationId, target.messageIndex);
  }

  async function createInsight() {
    if (!selectedIds.length) {
      setStatus("Select at least one conversation.");
      return;
    }
    if (!activeProfile) {
      setStatus("Select an LLM profile.");
      return;
    }
    if (!insightModel.trim()) {
      setStatus("Select a model.");
      return;
    }
    if (settings.model !== customModelValue && modelLoad.status !== "success") {
      setStatus("Load and validate provider models before generating an insight.");
      return;
    }
    if (selectedModelUnavailable) {
      setStatus("Choose a model that is currently available from the provider.");
      return;
    }
    const initialJob: InsightJob = {
      id: "",
      status: "queued",
      stage: "loading",
      message: "Preparing selected conversations",
      progress: 2,
      result: null,
      error: null
    };
    setInsight(null);
    setInsightJob(initialJob);
    setStatus("Preparing selected conversations...");
    try {
      const response = await fetch("/api/insights/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_ids: selectedIds,
          title: query ? `Insights: ${query}` : "Connected Insights",
          settings: {
            profile_id: activeProfile.id,
            model: insightModel,
            max_context_chars: settings.maxContextChars,
            temperature: settings.temperature
          }
        })
      });
      const job = await parseJsonResponse<InsightJob>(response);
      setInsightJob(job);
      await pollInsightJob(job.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Insight generation failed.";
      setInsightJob({ ...initialJob, status: "failed", stage: "failed", message, error: message });
      setStatus(message);
    }
  }

  async function pollInsightJob(jobId: string) {
    while (true) {
      await delay(500);
      const response = await fetch(`/api/insights/jobs/${jobId}`);
      const job = await parseJsonResponse<InsightJob>(response);
      setInsightJob(job);
      setStatus(job.message);
      if (job.status === "completed" && job.result) {
        setInsight(job.result);
        setStatus("Insight report ready.");
        return;
      }
      if (job.status === "failed") {
        throw new Error(job.error || "Insight generation failed.");
      }
    }
  }

  function downloadInsight() {
    if (!insight) return;
    const blob = new Blob([insight.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${safeFilename(insight.title)}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function toggleSelection(result: SearchResult) {
    setSelectedById((current) => toggleSelectedConversation(current, result));
  }

  function removeSelection(id: string) {
    setSelectedById((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }

  function clearSelections() {
    setSelectedById({});
  }

  async function setActiveProfile(profileId: string) {
    setSettings((current) => ({ ...current, profileId, model: "", customModel: "" }));
    setAdvancedOpen(false);
    await fetch("/api/llm/profiles/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_id: profileId })
    });
  }

  async function saveAdvancedSettings() {
    if (!activeProfile || !profileDraft) return;
    setSettingsBusy(true);
    try {
      const response = await fetch(`/api/llm/profiles/${activeProfile.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: activeProfile.name,
          provider: activeProfile.provider,
          base_url: profileDraft.base_url,
          default_model: activeProfile.default_model,
          custom_models: profileDraft.custom_models
            .split(",")
            .map((model) => model.trim())
            .filter(Boolean)
        })
      });
      await parseJsonResponse<LLMProfile>(response);
      await loadProfiles();
      if (activeProfile.connected) {
        await loadAvailableModels(activeProfile.id);
      }
      setStatus("Advanced AI settings saved.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save AI settings.");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function connectProvider() {
    if (!activeProfile || !profileDraft || !apiKeyDraft.trim()) {
      setModelLoad({
        profileId: activeProfile?.id ?? "",
        status: "invalid-key",
        models: [],
        message: "Paste an API key before connecting."
      });
      return;
    }
    if (activeProfile.provider === "openai-compatible" && !profileDraft.base_url.trim()) {
      setAdvancedOpen(true);
      setModelLoad({
        profileId: activeProfile.id,
        status: "error",
        models: [],
        message: "Add the provider base URL in Advanced settings."
      });
      return;
    }
    const previousModels = activeProfile.connected ? modelOptions : [];
    setSettingsBusy(true);
    setModelLoad({
      profileId: activeProfile.id,
      status: "loading",
      models: previousModels,
      message: `Connecting to ${providerDetail.label}...`
    });
    try {
      const response = await fetch(`/api/llm/profiles/${activeProfile.id}/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKeyDraft,
          base_url: profileDraft.base_url,
          custom_models: profileDraft.custom_models
            .split(",")
            .map((model) => model.trim())
            .filter(Boolean)
        })
      });
      const data = await parseJsonResponse<ConnectResponse>(response);
      setModelLoad({
        profileId: activeProfile.id,
        status: data.models.length ? "success" : "empty",
        models: data.models,
        message: data.models.length
          ? `Connected. ${data.models.length} model${data.models.length === 1 ? "" : "s"} available.`
          : "Connected, but the provider returned no models."
      });
      setSettings((current) => ({ ...current, model: data.selected_model, customModel: "" }));
      setApiKeyDraft("");
      setShowApiKey(false);
      setEditingKey(false);
      await loadProfiles();
      setStatus(`Connected to ${providerDetail.label}.`);
    } catch (error) {
      const errorStatus = error instanceof ApiError ? error.status : 0;
      const message = error instanceof Error ? error.message : "Could not connect to the provider.";
      setModelLoad({
        profileId: activeProfile.id,
        status: modelErrorStatus(errorStatus),
        models: previousModels,
        message
      });
      setStatus(message);
    } finally {
      setSettingsBusy(false);
    }
  }

  async function disconnectProvider() {
    if (!activeProfile) return;
    setSettingsBusy(true);
    try {
      const response = await fetch(`/api/llm/profiles/${activeProfile.id}/connection`, {
        method: "DELETE"
      });
      await parseJsonResponse<{ status: string }>(response);
      setSettings((current) => ({ ...current, model: "", customModel: "" }));
      setModelLoad({
        profileId: activeProfile.id,
        status: "idle",
        models: [],
        message: "Connection removed. Paste an API key to reconnect."
      });
      setEditingKey(false);
      setApiKeyDraft("");
      await loadProfiles();
      setStatus(`${providerDetail.label} connection removed.`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not remove the connection.");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function selectModel(model: string) {
    if (!activeProfile) return;
    setSettings((current) => ({
      ...current,
      model,
      customModel: model === customModelValue ? current.customModel : ""
    }));
    if (!model || model === customModelValue) return;
    try {
      const response = await fetch(`/api/llm/profiles/${activeProfile.id}/model`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model })
      });
      await parseJsonResponse<LLMProfile>(response);
      await loadProfiles();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not save the selected model.");
    }
  }

  return (
    <main className="appShell">
      <aside className="filterPane">
        <div className="brandBlock">
          <FileSearch size={22} />
          <div>
            <h1>Reweave</h1>
            <p>Local AI conversation search</p>
          </div>
        </div>

        <label>
          Search
          <div className="searchBox">
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && runSearch()}
              placeholder="plants, mitochondria, chemical reactions..."
            />
          </div>
        </label>

        <button
          className="secondaryButton compactButton"
          onClick={() => setFiltersOpen((open) => !open)}
          type="button"
        >
          {filtersOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          Filters
        </button>

        {filtersOpen && (
          <section className="advancedFilters">
            {showSourceFilter && (
              <label>
                Source
                <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
                  <option value="">All</option>
                  {sourceFacets.map((facet) => (
                    <option value={facet.source} key={facet.source}>
                      {facet.source} ({facet.conversations})
                    </option>
                  ))}
                </select>
              </label>
            )}

            <label>
              Title contains
              <input value={titleFilter} onChange={(event) => setTitleFilter(event.target.value)} />
            </label>

            <div className="dateGrid">
              <label>
                From
                <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              </label>
              <label>
                To
                <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              </label>
            </div>
          </section>
        )}

        <button className="primaryButton" onClick={runSearch} disabled={busy}>
          {busy ? <Loader2 className="spin" size={16} /> : <Search size={16} />}
          Search
        </button>

        <div className="importBlock">
          <div
            className="importPanel"
            onDrop={handleDrop}
            onDragOver={(event) => event.preventDefault()}
            aria-label="Import exported conversation files"
          >
            <FileUp size={18} />
            <strong>Import exports</strong>
            <span>Drop ChatGPT or Claude .zip/.json files here.</span>
            <label className="filePickerButton">
              <FileUp size={16} />
              Choose Files
              <input
                type="file"
                accept=".zip,.json,application/json,application/zip,application/x-zip-compressed"
                multiple
                onChange={(event) => {
                  const selectedFiles = event.currentTarget.files;
                  if (selectedFiles) importFiles(selectedFiles);
                  event.currentTarget.value = "";
                }}
              />
            </label>
            <p className="importStatus">{importStatus}</p>
          </div>

          <div className="pathImport">
            <label>
              Local path
              <input
                value={importPath}
                onChange={(event) => setImportPath(event.target.value)}
                placeholder="C:\\path\\to\\export.zip or folder"
              />
            </label>
            <button className="secondaryButton" onClick={importLocalPath} disabled={busy}>
              <FolderInput size={16} />
              Import Path
            </button>
            {paths && <p className="pathHint">Imports folder: {paths.imports_dir}</p>}
          </div>
        </div>

        <section className="settingsBlock">
          <div className="settingsTitle">
            <div>
              <h2>
                <Settings size={16} />
                AI connection
              </h2>
              <p>Connect your own provider to generate insights.</p>
            </div>
            {activeProfile?.connected && <span className="connectedBadge">Connected</span>}
          </div>

          <label>
            Provider
            <select
              value={activeProfile?.id ?? ""}
              onChange={(event) => setActiveProfile(event.target.value)}
              disabled={settingsBusy}
            >
              {profiles.map((profile) => (
                <option value={profile.id} key={profile.id}>
                  {providerDetails[profile.provider]?.label ?? profile.name}
                </option>
              ))}
            </select>
          </label>

          {activeProfile?.connected && !editingKey ? (
            <div className="connectedKey">
              <div>
                <span>API key</span>
                <strong>{activeProfile.masked_key}</strong>
                <small>Stored securely in your operating system keyring.</small>
              </div>
              <div className="connectionActions">
                <button
                  className="secondaryButton"
                  type="button"
                  onClick={() => setEditingKey(true)}
                  disabled={settingsBusy}
                >
                  <KeyRound size={15} />
                  Change key
                </button>
                <button
                  className="secondaryButton"
                  type="button"
                  onClick={() => loadAvailableModels(activeProfile.id)}
                  disabled={settingsBusy || modelLoad.status === "loading"}
                >
                  <RefreshCw size={15} />
                  Reconnect
                </button>
                <button
                  className="quietDangerButton"
                  type="button"
                  onClick={disconnectProvider}
                  disabled={settingsBusy}
                >
                  <Trash2 size={15} />
                  Remove
                </button>
              </div>
            </div>
          ) : (
            <div className="connectForm">
              <div className="keyHelp">
                <span>{providerDetail.keyHelp}</span>
                {providerDetail.keyUrl && (
                  <a href={providerDetail.keyUrl} target="_blank" rel="noreferrer">
                    Get an API key
                  </a>
                )}
              </div>
              <div className="secretInput">
                <input
                  type={showApiKey ? "text" : "password"}
                  value={apiKeyDraft}
                  onChange={(event) => setApiKeyDraft(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && connectProvider()}
                  placeholder={`Paste your ${providerDetail.label} API key`}
                  aria-label="API key"
                  autoComplete="new-password"
                  spellCheck={false}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey((show) => !show)}
                  aria-label={showApiKey ? "Hide API key" : "Show API key"}
                >
                  {showApiKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              <div className="connectActions">
                <button
                  className="primaryButton"
                  onClick={connectProvider}
                  disabled={settingsBusy || !apiKeyDraft.trim()}
                  type="button"
                >
                  {settingsBusy ? <Loader2 className="spin" size={16} /> : <KeyRound size={16} />}
                  Connect
                </button>
                {activeProfile?.connected && (
                  <button
                    className="secondaryButton"
                    type="button"
                    onClick={() => {
                      setEditingKey(false);
                      setApiKeyDraft("");
                      void loadAvailableModels(activeProfile.id);
                    }}
                    disabled={settingsBusy}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}

          <div className={`modelStatus ${modelLoad.status}`} role="status">
            {modelLoad.status === "loading" && <Loader2 className="spin" size={15} />}
            {modelLoad.status === "success" && <CheckCircle2 size={15} />}
            {["empty", "invalid-key", "permission", "rate-limit", "network", "error"].includes(
              modelLoad.status
            ) && <AlertCircle size={15} />}
            <span>{modelLoad.message}</span>
          </div>

          {activeProfile?.connected && (
            <section className="modelSetup">
              <div className="sectionHeading">
                <div>
                  <h3>Model</h3>
                  <p>Choose which available model Reweave should use.</p>
                </div>
                <button
                  className="iconButton"
                  onClick={() => loadAvailableModels(activeProfile.id)}
                  disabled={settingsBusy || modelLoad.status === "loading"}
                  aria-label="Refresh available models"
                  title="Refresh available models"
                  type="button"
                >
                  <RefreshCw className={modelLoad.status === "loading" ? "spin" : ""} size={15} />
                </button>
              </div>
              <label>
                Available model
                <select
                  value={settings.model}
                  disabled={modelLoad.status === "loading" || !modelOptions.length}
                  onChange={(event) => selectModel(event.target.value)}
                >
                  {!settings.model && <option value="">Choose a model</option>}
                  {settings.model && !modelOptions.includes(settings.model) && (
                    <option value={settings.model} disabled>
                      {settings.model} ({modelLoad.status === "success" ? "unavailable" : "not validated"})
                    </option>
                  )}
                  {modelOptions.map((model) => (
                    <option value={model} key={model}>
                      {model}
                    </option>
                  ))}
                </select>
              </label>
              {selectedModelUnavailable && (
                <p className="fieldError">
                  This model is no longer available. Choose another model to continue.
                </p>
              )}
            </section>
          )}

          {profileDraft && (
            <details
              className="advancedSettings"
              open={advancedOpen}
              onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
            >
              <summary>Advanced settings</summary>
              <div className="advancedSettingsBody">
                <label>
                  Base URL
                  <input
                    value={profileDraft.base_url}
                    onChange={(event) =>
                      setProfileDraft({ ...profileDraft, base_url: event.target.value })
                    }
                    placeholder={
                      activeProfile?.provider === "openai-compatible"
                        ? "Required for compatible providers"
                        : "Optional provider override"
                    }
                  />
                </label>
                <label>
                  Additional model IDs
                  <input
                    value={profileDraft.custom_models}
                    onChange={(event) =>
                      setProfileDraft({ ...profileDraft, custom_models: event.target.value })
                    }
                    placeholder="Comma-separated"
                  />
                </label>
                <p>
                  Leave these empty unless your provider uses a custom endpoint or does not return
                  every model automatically.
                </p>
                <button
                  className="secondaryButton"
                  onClick={saveAdvancedSettings}
                  disabled={settingsBusy}
                  type="button"
                >
                  <Save size={16} />
                  Save advanced settings
                </button>
              </div>
            </details>
          )}
        </section>
      </aside>

      <section className="resultsPane">
        <header className="toolbar">
          <span>{status}</span>
          {reportOpen && !insightBusy ? (
            <button className="toolbarButton" type="button" onClick={() => setInsight(null)}>
              <ArrowLeft size={15} />
              Back to results
            </button>
          ) : reportOpen ? (
            <span>{selectedIds.length} sources</span>
          ) : (
            <span>{results.length} results</span>
          )}
        </header>
        {reportOpen ? (
          <div className="reportWorkspace">
            {insightBusy && insightJob && (
              <section className="generationCard" aria-live="polite">
                <div className="generationIcon">
                  <Sparkles size={24} />
                </div>
                <div className="generationCopy">
                  <span className="eyebrow">Generating insight</span>
                  <h2>{insightJob.message}</h2>
                  <p>
                    Reweave is analyzing {selectedIds.length} selected conversation
                    {selectedIds.length === 1 ? "" : "s"} and linking findings to their sources.
                  </p>
                  <div
                    className="progressTrack"
                    role="progressbar"
                    aria-valuenow={insightJob.progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <span style={{ width: `${insightJob.progress}%` }} />
                  </div>
                  <div className="progressMeta">
                    <span>{insightJob.stage}</span>
                    <strong>{insightJob.progress}%</strong>
                  </div>
                </div>
              </section>
            )}

            {insight && (
              <>
                <header className="reportHero">
                  <div>
                    <span className="eyebrow">
                      {insight.language === "ko" ? "한국어 인사이트 보고서" : "Insight report"}
                    </span>
                    <h1>{insight.title}</h1>
                    <p>
                      A source-grounded synthesis of {insight.selected_conversation_ids.length}{" "}
                      selected conversation
                      {insight.selected_conversation_ids.length === 1 ? "" : "s"}.
                    </p>
                  </div>
                  <div className="reportActions">
                    <button
                      className="secondaryButton"
                      type="button"
                      onClick={() => navigator.clipboard.writeText(insight.markdown)}
                    >
                      <Clipboard size={16} />
                      Copy Markdown
                    </button>
                    <button className="secondaryButton" type="button" onClick={downloadInsight}>
                      <FileDown size={16} />
                      Download
                    </button>
                  </div>
                </header>
                <div className="reportStats">
                  <span>
                    <BookOpen size={15} />
                    {insight.selected_conversation_ids.length} sources
                  </span>
                  {insight.performance?.chunk_count && (
                    <span>{insight.performance.chunk_count} source groups</span>
                  )}
                  {insight.performance?.total_ms && (
                    <span>
                      <Clock3 size={15} />
                      {(insight.performance.total_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>
                <article className="reportPaper">
                  <MarkdownContent markdown={insight.markdown} onCitation={openCitation} />
                </article>
              </>
            )}
          </div>
        ) : (
          <div className="resultList">
            {results.map((result) => (
              <article key={result.id} className="resultRow">
                <label className="checkCell" aria-label={`Select ${result.title}`}>
                  <input
                    type="checkbox"
                    checked={Boolean(selectedById[result.id])}
                    onChange={() => toggleSelection(result)}
                  />
                </label>
                <div className="resultContent">
                  <button className="resultTitleButton" onClick={() => openDetail(result.id)}>
                    <strong>{result.title}</strong>
                    <span>{result.source} - {result.raw_message_count} messages</span>
                  </button>
                  <div className="excerptList">
                    {result.excerpts.map((excerpt) => (
                      <div className="excerpt" key={excerpt.message_id}>
                        <span className="excerptSource">
                          [#{excerpt.message_index}] {excerpt.role}
                        </span>
                        <MarkdownContent markdown={excerpt.excerpt} compact />
                      </div>
                    ))}
                  </div>
                </div>
              </article>
            ))}
            {!results.length && <div className="emptyState">No search results yet.</div>}
          </div>
        )}
      </section>

      <aside className="selectionPane">
        <section className="selectionHeader">
          <h2>{selectedIds.length} selected</h2>
          <div className="selectionActions">
            <button
              className="primaryButton"
              onClick={createInsight}
              disabled={busy || insightBusy || !selectedIds.length}
            >
              {insightBusy ? <Loader2 className="spin" size={16} /> : <Lightbulb size={16} />}
              {insight ? "Regenerate insight" : "Generate insight"}
            </button>
            <button
              className="secondaryButton"
              onClick={clearSelections}
              disabled={insightBusy || !selectedIds.length}
              type="button"
            >
              <Trash2 size={15} />
              Clear all
            </button>
          </div>
        </section>

        <div className="selectedList">
          {selectedResults.map((result) => (
            <div className="selectedItem" key={result.id}>
              <button className="selectedSource" type="button" onClick={() => openDetail(result.id)}>
                <span>{result.title}</span>
                <small>{result.source} · {result.raw_message_count} messages</small>
              </button>
              <button
                onClick={() => removeSelection(result.id)}
                aria-label={`Remove ${result.title}`}
                disabled={insightBusy}
              >
                <X size={14} />
              </button>
            </div>
          ))}
          {!selectedResults.length && (
            <p className="selectionEmpty">Selected conversations stay here while you keep searching.</p>
          )}
        </div>

        {detail && (
          <section className="detailPanel">
            <div className="detailHeading">
              <div>
                <span className="eyebrow">
                  {detailMessageIndex === null ? "Source preview" : `Supporting message #${detailMessageIndex}`}
                </span>
                <h2>{detail.conversation.title}</h2>
              </div>
              <button
                className="iconButton"
                type="button"
                aria-label="Close source preview"
                onClick={() => setDetail(null)}
              >
                <X size={15} />
              </button>
            </div>
            <div className="messageList">
              {visibleDetailMessages.map((message) => (
                <div
                  className={message.index === detailMessageIndex ? "messageItem targetMessage" : "messageItem"}
                  key={message.id}
                >
                  <b>[{message.index}] {message.role}</b>
                  <MarkdownContent markdown={message.content} compact />
                </div>
              ))}
            </div>
          </section>
        )}
      </aside>
    </main>
  );
}

if (typeof document !== "undefined") {
  const rootElement = document.getElementById("root");
  if (rootElement) {
    createRoot(rootElement).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>
    );
  }
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : data;
    throw new ApiError(typeof detail === "string" ? detail : "Request failed.", response.status);
  }
  return data as T;
}

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function formatImportStatus(summary: ImportSummary) {
  const skipped = summary.skipped_files.length
    ? ` ${summary.skipped_files.length} file${summary.skipped_files.length === 1 ? "" : "s"} skipped.`
    : "";
  return (
    `Imported ${summary.inserted_conversations} new conversations and ` +
    `${summary.inserted_messages} messages from ${summary.parsed_conversations} parsed conversations.` +
    skipped
  );
}

function delay(milliseconds: number) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function safeFilename(value: string) {
  const filename = value.trim().replace(/[<>:"/\\|?*\u0000-\u001f]+/g, "-");
  return filename || "reweave-insight";
}

export function isModelUnavailable(
  model: string,
  status: ModelLoadState["status"],
  availableModels: string[]
) {
  return Boolean(
    model &&
      model !== customModelValue &&
      status === "success" &&
      !availableModels.includes(model)
  );
}

export function selectConversation(
  current: Record<string, SearchResult>,
  result: SearchResult
) {
  return { ...current, [result.id]: result };
}

export function toggleSelectedConversation(
  current: Record<string, SearchResult>,
  result: SearchResult
) {
  if (current[result.id]) {
    const next = { ...current };
    delete next[result.id];
    return next;
  }
  return selectConversation(current, result);
}

function profileToDraft(profile: LLMProfile): ProfileDraft {
  return {
    base_url: profile.base_url,
    custom_models: profile.custom_models.join(", ")
  };
}

export function modelErrorStatus(status: number): ModelLoadState["status"] {
  if (status === 401) return "invalid-key";
  if (status === 403) return "permission";
  if (status === 429) return "rate-limit";
  if (status === 0 || status === 502) return "network";
  return "error";
}

export function chooseAvailableModel(
  current: string,
  saved: string,
  models: string[],
  provider: string
) {
  if (models.includes(current)) return current;
  if (models.includes(saved)) return saved;

  const preferences: Record<string, string[]> = {
    openai: ["mini"],
    anthropic: ["sonnet"],
    gemini: ["flash"]
  };
  const excluded = ["audio", "embedding", "image", "realtime", "transcribe", "tts"];
  const usable = models.filter(
    (model) => !excluded.some((term) => model.toLocaleLowerCase().includes(term))
  );
  for (const preference of preferences[provider] ?? []) {
    const match = usable.find((model) => model.toLocaleLowerCase().includes(preference));
    if (match) return match;
  }
  return usable[0] ?? models[0] ?? "";
}
