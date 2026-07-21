import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  BookOpen,
  CalendarDays,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Clock3,
  CloudUpload,
  Database,
  Download,
  Eye,
  EyeOff,
  FileText,
  FileUp,
  FolderInput,
  Compass,
  KeyRound,
  Library,
  Loader2,
  RefreshCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import {
  MarkdownContent,
  extractMarkdownHeadings,
  type CitationTarget,
  type MarkdownHeading
} from "./MarkdownContent";
import { LibraryView, OnboardingWizard } from "./ArchiveManagement";
import { MemoryAuditView, type AuditLLMSettings } from "./MemoryAudit";
import { ContextWorkspace } from "./ContextWorkspace";
import { HighlightedText, extractHighlightTerms } from "./textHighlight";

type View = "context" | "library" | "audit" | "search" | "reports" | "import" | "settings";
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

type InsightSummary = {
  id: string;
  title: string;
  selected_conversation_ids: string[];
  provider: string;
  model: string;
  created_at: string;
};

type Insight = InsightSummary & {
  markdown: string;
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

type ArchiveAnswer = {
  question: string;
  markdown: string;
  mode_used: string;
  language: "ko" | "en";
  sources: Excerpt[];
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
    keyHelp: "Create a key in OpenRouter."
  },
  "openai-compatible": {
    label: "OpenAI-compatible",
    keyHelp: "Use the API key and base URL from your provider."
  }
};

const initialModelLoad: ModelLoadState = {
  profileId: "",
  status: "idle",
  models: [],
  message: "Connect a provider to load available models."
};

export function Workspace() {
  const [activeView, setActiveView] = useState<View>("context");
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("auto");
  const [modeUsed, setModeUsed] = useState("keyword");
  const [sourceFilter, setSourceFilter] = useState("");
  const [titleFilter, setTitleFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedById, setSelectedById] = useState<Record<string, SearchResult>>({});
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailMessageIndex, setDetailMessageIndex] = useState<number | null>(null);
  const [reports, setReports] = useState<InsightSummary[]>([]);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [insightJob, setInsightJob] = useState<InsightJob | null>(null);
  const [archiveAnswer, setArchiveAnswer] = useState<ArchiveAnswer | null>(null);
  const [answerJob, setAnswerJob] = useState<BackgroundJob<ArchiveAnswer> | null>(null);
  const [reportSources, setReportSources] = useState<Record<string, SearchResult>>({});
  const [paths, setPaths] = useState<AppPaths | null>(null);
  const [sourceFacets, setSourceFacets] = useState<SourceFacet[]>([]);
  const [semanticStatus, setSemanticStatus] = useState<SemanticStatus | null>(null);
  const [semanticJob, setSemanticJob] = useState<BackgroundJob<SemanticStatus> | null>(null);
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
  const [importStatus, setImportStatus] = useState("Drop files or choose a .zip/.json export.");
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const modelRequest = useRef(0);

  const selectedResults = useMemo(() => Object.values(selectedById), [selectedById]);
  const selectedIds = useMemo(() => Object.keys(selectedById), [selectedById]);
  const insightBusy = insightJob?.status === "queued" || insightJob?.status === "running";
  const answerBusy = answerJob?.status === "queued" || answerJob?.status === "running";
  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.id === activeProfileId) ?? profiles[0],
    [profiles, activeProfileId]
  );
  const reportSourceList = useMemo(
    () =>
      insight?.selected_conversation_ids
        .map((id) => reportSources[id])
        .filter((source): source is SearchResult => Boolean(source)) ?? [],
    [insight, reportSources]
  );
  const archiveConversationCount = sourceFacets.reduce((total, facet) => total + facet.conversations, 0);
  const archiveMessageCount = sourceFacets.reduce((total, facet) => total + facet.messages, 0);
  const modelReady = activeProfile?.connected && modelLoad.status === "success" && Boolean(model);
  const auditLLMSettings: AuditLLMSettings | null = activeProfile && model
    ? {
        profile_id: activeProfile.id,
        model,
        max_context_chars: maxContextChars,
        temperature
      }
    : null;

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
        message: "Connect this provider to load available models."
      });
    }
  }, [activeProfile?.id, activeProfile?.base_url, activeProfile?.connected]);

  async function loadInitialData() {
    const [, conversationCount] = await Promise.all([
      loadPaths(),
      loadFacets(),
      loadProfiles(),
      loadReports(),
      loadSemanticStatus()
    ]);
    if (conversationCount === 0 && !hasCompletedOnboarding()) setOnboardingOpen(true);
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
      return (data.sources ?? []).reduce((total, facet) => total + facet.conversations, 0);
    } catch {
      setSourceFacets([]);
      return null;
    }
  }

  async function loadProfiles() {
    try {
      const data = await api<{ active_profile_id: string | null; profiles: LLMProfile[] }>(
        "/api/llm/profiles"
      );
      setProfiles(data.profiles ?? []);
      setActiveProfileId(data.active_profile_id ?? data.profiles[0]?.id ?? "");
    } catch (error) {
      setStatus(messageFrom(error, "Could not load AI profiles."));
    }
  }

  async function loadReports(openFirst = false) {
    try {
      const data = await api<{ results: InsightSummary[] }>("/api/insights");
      setReports(data.results ?? []);
      if (openFirst && data.results?.[0]) await openReport(data.results[0].id);
    } catch (error) {
      setStatus(messageFrom(error, "Could not load saved reports."));
    }
  }

  async function loadAvailableModels(profileId: string) {
    const requestId = modelRequest.current + 1;
    modelRequest.current = requestId;
    setModelLoad({
      profileId,
      status: "loading",
      models: modelLoad.profileId === profileId ? modelLoad.models : [],
      message: "Loading available models..."
    });
    try {
      const data = await api<{ models: string[] }>(`/api/llm/profiles/${profileId}/models`);
      if (requestId !== modelRequest.current) return;
      const models = Array.from(new Set(data.models ?? []));
      const profile = profiles.find((item) => item.id === profileId);
      const nextModel = chooseModel(model, profile?.default_model ?? "", models, profile?.provider ?? "");
      setModel(nextModel);
      setModelLoad({
        profileId,
        status: models.length ? "success" : "empty",
        models,
        message: models.length
          ? `Connected. ${models.length} available models loaded.`
          : "Connected, but the provider returned no models."
      });
    } catch (error) {
      if (requestId !== modelRequest.current) return;
      setModelLoad({
        profileId,
        status: modelErrorStatus(error instanceof ApiError ? error.status : 0),
        models: [],
        message: messageFrom(error, "Could not load provider models.")
      });
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
      const params = new URLSearchParams({ q: query, limit: "40", mode: searchMode });
      if (sourceFilter) params.set("provider", sourceFilter);
      if (titleFilter) params.set("title", titleFilter);
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
      setArchiveAnswer(null);
      setStatus(`${data.results?.length ?? 0} conversations found.`);
    } catch (error) {
      setStatus(messageFrom(error, "Search failed."));
    } finally {
      setBusy(false);
    }
  }

  async function askArchive() {
    if (!query.trim()) {
      setStatus("Enter a question for your archive.");
      return;
    }
    if (!activeProfile || !modelReady) {
      setStatus("Connect an AI provider and choose an available model in Settings.");
      return;
    }
    const queued: BackgroundJob<ArchiveAnswer> = {
      id: "",
      status: "queued",
      stage: "searching",
      message: "Searching your local archive",
      progress: 2,
      result: null,
      error: null
    };
    setArchiveAnswer(null);
    setAnswerJob(queued);
    setStatus(queued.message);
    try {
      const job = await api<BackgroundJob<ArchiveAnswer>>("/api/archive-answers/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: query,
          mode: searchMode,
          provider: sourceFilter || null,
          title: titleFilter || null,
          date_from: dateFrom || null,
          date_to: dateTo || null,
          settings: {
            profile_id: activeProfile.id,
            model,
            max_context_chars: maxContextChars,
            temperature
          }
        })
      });
      setAnswerJob(job);
      await pollAnswerJob(job.id);
    } catch (error) {
      const message = messageFrom(error, "Archive answer failed.");
      setAnswerJob({ ...queued, status: "failed", stage: "failed", message, error: message });
      setStatus(message);
    }
  }

  async function pollAnswerJob(jobId: string) {
    while (true) {
      await delay(500);
      const job = await api<BackgroundJob<ArchiveAnswer>>(`/api/archive-answers/jobs/${jobId}`);
      setAnswerJob(job);
      setStatus(job.message);
      if (job.status === "completed" && job.result) {
        setArchiveAnswer(job.result);
        setModeUsed(job.result.mode_used);
        setAnswerJob(null);
        setStatus(`Answer grounded in ${job.result.sources.length} archive sources.`);
        return;
      }
      if (job.status === "failed") throw new Error(job.error || "Archive answer failed.");
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
      error: null
    };
    setSemanticJob(queued);
    try {
      const job = await api<BackgroundJob<SemanticStatus>>("/api/semantic/index/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rebuild })
      });
      setSemanticJob(job);
      while (true) {
        await delay(500);
        const update = await api<BackgroundJob<SemanticStatus>>(`/api/semantic/index/jobs/${job.id}`);
        setSemanticJob(update);
        if (update.status === "completed") {
          setSemanticStatus(update.result);
          setSemanticJob(null);
          setStatus("Smart search is ready.");
          return;
        }
        if (update.status === "failed") throw new Error(update.error || "Smart search setup failed.");
      }
    } catch (error) {
      const message = messageFrom(error, "Smart search setup failed.");
      setSemanticJob({ ...queued, status: "failed", stage: "failed", message, error: message });
      setStatus(message);
      await loadSemanticStatus();
    }
  }

  async function deleteSemanticIndex() {
    if (!window.confirm("Remove the local semantic index? The downloaded model will be kept.")) return;
    try {
      setSemanticStatus(await api<SemanticStatus>("/api/semantic/index", { method: "DELETE" }));
      setStatus("Smart search index removed.");
    } catch (error) {
      setStatus(messageFrom(error, "Could not remove the smart search index."));
    }
  }

  async function deleteSemanticModel() {
    if (!window.confirm("Remove the local semantic index and downloaded model?")) return;
    try {
      setSemanticStatus(await api<SemanticStatus>("/api/semantic/model", { method: "DELETE" }));
      setStatus("Smart search model and index removed.");
    } catch (error) {
      setStatus(messageFrom(error, "Could not remove the smart search model."));
    }
  }

  async function openDetail(id: string, messageIndex: number | null = null) {
    setDetailMessageIndex(messageIndex);
    try {
      setDetail(await api<ConversationDetail>(`/api/conversations/${id}`));
    } catch (error) {
      setStatus(messageFrom(error, "Could not open the conversation."));
    }
  }

  async function openReport(id: string) {
    setActiveView("reports");
    setDetail(null);
    try {
      const report = await api<Insight>(`/api/insights/${id}`);
      setInsight(report);
      const sources = await loadReportSources(report.selected_conversation_ids);
      setSelectedById(sources);
    } catch (error) {
      setStatus(messageFrom(error, "Could not open the report."));
    }
  }

  async function loadReportSources(ids: string[]) {
    const entries = await Promise.all(
      ids.map(async (id) => {
        try {
          const source = await api<ConversationDetail>(`/api/conversations/${id}`);
          return [id, source.conversation] as const;
        } catch {
          return null;
        }
      })
    );
    const sources = Object.fromEntries(
      entries.filter((entry): entry is readonly [string, SearchResult] => Boolean(entry))
    );
    setReportSources(sources);
    return sources;
  }

  function openCitation(target: CitationTarget) {
    void openDetail(target.conversationId, target.messageIndex);
  }

  async function createInsight() {
    if (!selectedIds.length) {
      setStatus("Select at least one conversation.");
      return;
    }
    if (!activeProfile || !modelReady) {
      setStatus("Connect an AI provider and choose an available model in Settings.");
      return;
    }
    const queued: InsightJob = {
      id: "",
      status: "queued",
      stage: "loading",
      message: "Preparing selected conversations",
      progress: 2,
      result: null,
      error: null
    };
    setInsight(null);
    setInsightJob(queued);
    setActiveView("reports");
    try {
      const job = await api<InsightJob>("/api/insights/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_ids: selectedIds,
          title: query ? `Insights: ${query}` : "Connected Insights",
          settings: {
            profile_id: activeProfile.id,
            model,
            max_context_chars: maxContextChars,
            temperature
          }
        })
      });
      setInsightJob(job);
      await pollInsightJob(job.id);
    } catch (error) {
      const message = messageFrom(error, "Insight generation failed.");
      setInsightJob({ ...queued, status: "failed", stage: "failed", message, error: message });
      setStatus(message);
    }
  }

  async function pollInsightJob(jobId: string) {
    while (true) {
      await delay(500);
      const job = await api<InsightJob>(`/api/insights/jobs/${jobId}`);
      setInsightJob(job);
      setStatus(job.message);
      if (job.status === "completed" && job.result) {
        setInsight(job.result);
        setInsightJob(null);
        await Promise.all([loadReports(), loadReportSources(job.result.selected_conversation_ids)]);
        return;
      }
      if (job.status === "failed") throw new Error(job.error || "Insight generation failed.");
    }
  }

  async function importFiles(files: FileList | File[]): Promise<ImportSummary | null> {
    const fileList = Array.from(files);
    if (!fileList.length) return null;
    setBusy(true);
    setImportStatus(`Importing ${fileList.length} file${fileList.length === 1 ? "" : "s"}...`);
    try {
      const formData = new FormData();
      fileList.forEach((file) => formData.append("files", file));
      const summary = await api<ImportSummary>("/api/import/upload", { method: "POST", body: formData });
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
        body: JSON.stringify({ path: importPath })
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
      body: JSON.stringify({ profile_id: profileId })
    });
  }

  async function connectProvider() {
    if (!activeProfile || !apiKeyDraft.trim()) return;
    if (activeProfile.provider === "openai-compatible" && !baseUrlDraft.trim()) {
      setModelLoad({
        profileId: activeProfile.id,
        status: "error",
        models: [],
        message: "Add the provider base URL before connecting."
      });
      return;
    }
    setSettingsBusy(true);
    try {
      const data = await api<{ profile: LLMProfile; models: string[]; selected_model: string }>(
        `/api/llm/profiles/${activeProfile.id}/connect`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: apiKeyDraft,
            base_url: baseUrlDraft,
            custom_models: splitModels(customModelsDraft)
          })
        }
      );
      setModel(data.selected_model);
      setApiKeyDraft("");
      setEditingKey(false);
      await loadProfiles();
    } catch (error) {
      setModelLoad({
        profileId: activeProfile.id,
        status: modelErrorStatus(error instanceof ApiError ? error.status : 0),
        models: [],
        message: messageFrom(error, "Could not connect the provider.")
      });
    } finally {
      setSettingsBusy(false);
    }
  }

  async function disconnectProvider() {
    if (!activeProfile) return;
    setSettingsBusy(true);
    try {
      await api(`/api/llm/profiles/${activeProfile.id}/connection`, { method: "DELETE" });
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
          custom_models: splitModels(customModelsDraft)
        })
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
        body: JSON.stringify({ model: nextModel })
      });
    } catch (error) {
      setStatus(messageFrom(error, "Could not save the selected model."));
    }
  }

  function toggleSelection(result: SearchResult) {
    setSelectedById((current) => {
      const next = { ...current };
      if (next[result.id]) delete next[result.id];
      else next[result.id] = result;
      return next;
    });
  }

  function downloadInsight() {
    if (!insight) return;
    const url = URL.createObjectURL(new Blob([insight.markdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${safeFilename(insight.title)}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function switchView(view: View) {
    setActiveView(view);
    if (view !== "reports") setInsightJob(null);
    if (view === "reports" && !insight && reports[0]) void openReport(reports[0].id);
  }

  async function refreshArchiveData() {
    setDetail(null);
    setResults([]);
    setSelectedById({});
    setArchiveAnswer(null);
    setInsight(null);
    await Promise.all([loadFacets(), loadReports(), loadSemanticStatus()]);
  }

  function finishOnboarding(destination: "library" | "search") {
    rememberOnboardingComplete();
    setOnboardingOpen(false);
    setActiveView(destination);
  }

  function dismissOnboarding() {
    rememberOnboardingComplete();
    setOnboardingOpen(false);
    setActiveView("import");
  }

  return (
    <main className="workspaceShell">
      <Navigation
        activeView={activeView}
        reportCount={reports.length}
        conversationCount={archiveConversationCount}
        onNavigate={switchView}
      />
      {activeView === "context" && (
        <ContextWorkspace onOpenLibrary={() => setActiveView("library")} />
      )}
      {activeView === "library" && (
        <>
          <LibraryView
            paths={paths}
            sourceFacets={sourceFacets}
            onOpenConversation={(id) => void openDetail(id)}
            onImport={() => setActiveView("import")}
            onArchiveChanged={refreshArchiveData}
          />
          {detail && (
            <div className="libraryDrawerBackdrop" role="presentation" onClick={() => setDetail(null)}>
              <aside className="libraryDrawerPanel" onClick={(event) => event.stopPropagation()}>
                <ConversationDrawer
                  detail={detail}
                  close={() => setDetail(null)}
                  targetIndex={detailMessageIndex}
                  label="Archived conversation"
                />
              </aside>
            </div>
          )}
        </>
      )}
      {activeView === "audit" && (
        <>
          <MemoryAuditView
            modelReady={Boolean(modelReady)}
            llmSettings={auditLLMSettings}
            onOpenEvidence={(conversationId, messageIndex) => void openDetail(conversationId, messageIndex)}
            onOpenSettings={() => setActiveView("settings")}
          />
          {detail && (
            <div className="libraryDrawerBackdrop" role="presentation" onClick={() => setDetail(null)}>
              <aside className="libraryDrawerPanel" onClick={(event) => event.stopPropagation()}>
                <ConversationDrawer
                  detail={detail}
                  close={() => setDetail(null)}
                  targetIndex={detailMessageIndex}
                  label="Audit evidence"
                />
              </aside>
            </div>
          )}
        </>
      )}
      {activeView === "search" && (
        <SearchView
          query={query}
          setQuery={setQuery}
          runSearch={runSearch}
          askArchive={askArchive}
          busy={busy}
          answerBusy={answerBusy}
          status={status}
          results={results}
          searchMode={searchMode}
          setSearchMode={setSearchMode}
          modeUsed={modeUsed}
          semanticStatus={semanticStatus}
          archiveAnswer={archiveAnswer}
          answerJob={answerJob}
          openCitation={openCitation}
          selectedById={selectedById}
          toggleSelection={toggleSelection}
          openDetail={openDetail}
          filtersOpen={filtersOpen}
          setFiltersOpen={setFiltersOpen}
          sourceFacets={sourceFacets}
          sourceFilter={sourceFilter}
          setSourceFilter={setSourceFilter}
          titleFilter={titleFilter}
          setTitleFilter={setTitleFilter}
          dateFrom={dateFrom}
          setDateFrom={setDateFrom}
          dateTo={dateTo}
          setDateTo={setDateTo}
          selectedResults={selectedResults}
          clearSelections={() => setSelectedById({})}
          removeSelection={(id) =>
            setSelectedById((current) => {
              const next = { ...current };
              delete next[id];
              return next;
            })
          }
          createInsight={createInsight}
          modelReady={Boolean(modelReady)}
          activeProfile={activeProfile}
          model={model}
          detail={detail}
          detailMessageIndex={detailMessageIndex}
          closeDetail={() => setDetail(null)}
        />
      )}
      {activeView === "reports" && (
        <ReportsView
          reports={reports}
          insight={insight}
          insightJob={insightJob}
          reportSources={reportSourceList}
          detail={detail}
          detailMessageIndex={detailMessageIndex}
          openReport={openReport}
          openDetail={openDetail}
          closeDetail={() => setDetail(null)}
          openCitation={openCitation}
          backToSearch={() => setActiveView("search")}
          regenerate={createInsight}
          downloadInsight={downloadInsight}
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
          profiles={profiles}
          activeProfile={activeProfile}
          activeProfileId={activeProfileId}
          changeProfile={changeProfile}
          model={model}
          saveModel={saveModel}
          modelLoad={modelLoad}
          reloadModels={() => activeProfile && loadAvailableModels(activeProfile.id)}
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
      <OnboardingWizard
        open={onboardingOpen}
        busy={busy}
        onImport={importFiles}
        onFinish={finishOnboarding}
        onDismiss={dismissOnboarding}
      />
    </main>
  );
}

function Navigation({
  activeView,
  reportCount,
  conversationCount,
  onNavigate
}: {
  activeView: View;
  reportCount: number;
  conversationCount: number;
  onNavigate: (view: View) => void;
}) {
  const items: Array<{ view: View; label: string; icon: React.ReactNode }> = [
    { view: "context", label: "Context", icon: <Compass size={19} /> },
    { view: "library", label: "Library", icon: <Library size={19} /> },
    { view: "audit", label: "Audit", icon: <ShieldCheck size={19} /> },
    { view: "search", label: "Search", icon: <Search size={19} /> },
    { view: "reports", label: "Reports", icon: <FileText size={19} /> },
    { view: "import", label: "Import", icon: <CloudUpload size={19} /> },
    { view: "settings", label: "Settings", icon: <Settings size={19} /> }
  ];
  return (
    <aside className="navigationPane">
      <button className="wordmark" type="button" onClick={() => onNavigate("context")}>
        <span>R</span>
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
            {item.view === "reports" && reportCount > 0 && <b>{reportCount}</b>}
          </button>
        ))}
      </nav>
      <div className="archiveStatus">
        <span><i /> Local archive</span>
        <small>{conversationCount.toLocaleString()} conversations</small>
      </div>
    </aside>
  );
}

type SearchViewProps = {
  query: string;
  setQuery: (value: string) => void;
  runSearch: () => void;
  askArchive: () => void;
  busy: boolean;
  answerBusy: boolean;
  status: string;
  results: SearchResult[];
  searchMode: SearchMode;
  setSearchMode: (value: SearchMode) => void;
  modeUsed: string;
  semanticStatus: SemanticStatus | null;
  archiveAnswer: ArchiveAnswer | null;
  answerJob: BackgroundJob<ArchiveAnswer> | null;
  openCitation: (target: CitationTarget) => void;
  selectedById: Record<string, SearchResult>;
  toggleSelection: (result: SearchResult) => void;
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
  selectedResults: SearchResult[];
  clearSelections: () => void;
  removeSelection: (id: string) => void;
  createInsight: () => void;
  modelReady: boolean;
  activeProfile?: LLMProfile;
  model: string;
  detail: ConversationDetail | null;
  detailMessageIndex: number | null;
  closeDetail: () => void;
};

function SearchView(props: SearchViewProps) {
  const highlightTerms = useMemo(() => extractHighlightTerms(props.query), [props.query]);

  return (
    <section className="searchScreen">
      <div className="searchWorkspace">
        <header className="pageHeader searchPageHeader">
          <div>
            <span className="sectionLabel">Local conversation library</span>
            <h1>Search your archive</h1>
            <p>Find ideas across every imported ChatGPT and Claude conversation.</p>
          </div>
        </header>
        <div className="searchControls">
          <div className="searchInput">
            <div className="searchField">
              <Search size={19} aria-hidden="true" />
              <input
                aria-label="Search archive"
                value={props.query}
                onChange={(event) => props.setQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && props.runSearch()}
                placeholder="Search topics, phrases, or ideas"
              />
              {props.query && (
                <button type="button" onClick={() => props.setQuery("")} aria-label="Clear search">
                  <X size={17} />
                </button>
              )}
            </div>
            <div className="searchActions">
              <button className="searchSubmit" type="button" onClick={props.runSearch} disabled={props.busy}>
                {props.busy ? <Loader2 className="spin" size={17} /> : <Search size={17} />}
                Search
              </button>
              <button
                className="askSubmit"
                type="button"
                onClick={props.askArchive}
                disabled={props.answerBusy}
              >
                {props.answerBusy ? <Loader2 className="spin" size={17} /> : <Sparkles size={17} />}
                Ask archive
              </button>
            </div>
          </div>
          <div className="filterRow">
            <label className="modePicker">
              <span>Mode</span>
              <select
                aria-label="Search mode"
                value={props.searchMode}
                onChange={(event) => props.setSearchMode(event.target.value as SearchMode)}
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
            <span className="filterChip static"><Database size={15} /> {props.sourceFilter || "All sources"}</span>
            {(props.dateFrom || props.dateTo) && (
              <span className="filterChip static"><CalendarDays size={15} /> Date range</span>
            )}
            <span className={props.semanticStatus?.ready ? "filterChip static smartReady" : "filterChip static"}>
              <Sparkles size={14} /> {props.semanticStatus?.ready ? `Smart ready · ${props.modeUsed}` : "Keyword ready"}
            </span>
            <span className="resultCount">{props.status}</span>
          </div>
          {props.filtersOpen && (
            <div className="filterPanel">
              <label>
                Source
                <select value={props.sourceFilter} onChange={(event) => props.setSourceFilter(event.target.value)}>
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
                <input value={props.titleFilter} onChange={(event) => props.setTitleFilter(event.target.value)} />
              </label>
              <label>
                From
                <input type="date" value={props.dateFrom} onChange={(event) => props.setDateFrom(event.target.value)} />
              </label>
              <label>
                To
                <input type="date" value={props.dateTo} onChange={(event) => props.setDateTo(event.target.value)} />
              </label>
            </div>
          )}
        </div>
        <div className="searchContent">
        {props.answerJob && (
          <section className="archiveAnswer progressAnswer" aria-live="polite">
            <div className="answerHeading">
              <span className="answerIcon"><Sparkles size={19} /></span>
              <div><span className="sectionLabel">Ask Archive</span><h2>{props.answerJob.message}</h2></div>
            </div>
            <div className="progressTrack"><span style={{ width: `${props.answerJob.progress}%` }} /></div>
            <div className="progressMeta"><span>{props.answerJob.stage}</span><span>{props.answerJob.progress}%</span></div>
          </section>
        )}
        {props.archiveAnswer && (
          <article className="archiveAnswer">
            <header className="answerHeading">
              <span className="answerIcon"><BookOpen size={19} /></span>
              <div>
                <span className="sectionLabel">Archive answer · {props.archiveAnswer.mode_used}</span>
                <h2>{props.archiveAnswer.question}</h2>
                <p>{props.archiveAnswer.sources.length} verified source messages</p>
              </div>
            </header>
            <div className="answerDocument">
              <MarkdownContent markdown={props.archiveAnswer.markdown} onCitation={props.openCitation} />
            </div>
          </article>
        )}
        <div className="resultList">
          {props.results.map((result) => (
            <article className={props.selectedById[result.id] ? "resultRow selected" : "resultRow"} key={result.id}>
              <label className="resultCheck" aria-label={`Select ${result.title}`}>
                <input
                  type="checkbox"
                  checked={Boolean(props.selectedById[result.id])}
                  onChange={() => props.toggleSelection(result)}
                />
              </label>
              <button className="providerMark" type="button" onClick={() => props.openDetail(result.id)}>
                {result.source === "chatgpt" ? "G" : "AI"}
              </button>
              <button className="resultBody" type="button" onClick={() => props.openDetail(result.id)}>
                <span className="resultHeading">
                  <strong><HighlightedText text={result.title} terms={highlightTerms} /></strong>
                  <small>{result.source} · {formatDate(result.created_at)} · {result.raw_message_count} messages</small>
                </span>
                <span className="excerptList">
                  {result.excerpts.slice(0, 2).map((excerpt) => (
                    <span className="excerpt" key={excerpt.message_id}>
                      <MarkdownContent markdown={excerpt.excerpt} compact highlightTerms={highlightTerms} />
                    </span>
                  ))}
                </span>
              </button>
              <button className="rowAction" type="button" onClick={() => props.openDetail(result.id)} aria-label={`Open ${result.title}`}>
                <FileText size={17} />
              </button>
            </article>
          ))}
          {!props.results.length && (
            <div className="emptyState">
              <Library size={30} />
              <h2>Search your conversation library</h2>
              <p>Matching conversations and source excerpts will appear here.</p>
            </div>
          )}
        </div>
        </div>
      </div>
      <aside className={props.detail ? "sourceRail drawerOpen" : "sourceRail"}>
        {props.detail ? (
          <ConversationDrawer
            detail={props.detail}
            targetIndex={props.detailMessageIndex}
            close={props.closeDetail}
            label="Source preview"
            highlightTerms={highlightTerms}
          />
        ) : (
          <>
        <div className="railHeader">
          <div>
            <h2>Sources for insight</h2>
            <p>{props.selectedResults.length} selected</p>
          </div>
          {props.selectedResults.length > 0 && (
            <button className="textButton" type="button" onClick={props.clearSelections}>Clear</button>
          )}
        </div>
        <div className="selectedSources">
          {props.selectedResults.map((result) => (
            <div className="selectedSource" key={result.id}>
              <button className="sourceOpen" type="button" onClick={() => props.openDetail(result.id)} title={result.title}>
                <span className="providerMark small">{result.source === "chatgpt" ? "G" : "AI"}</span>
                <span><strong>{result.title}</strong><small>{result.source} · {result.raw_message_count} messages</small></span>
              </button>
              <button type="button" onClick={() => props.removeSelection(result.id)} aria-label={`Remove ${result.title}`}>
                <X size={15} />
              </button>
            </div>
          ))}
          {!props.selectedResults.length && (
            <div className="railEmpty">
              <Sparkles size={22} />
              <p>Select conversations to build a source-grounded insight report.</p>
            </div>
          )}
        </div>
        <button className="primaryButton generateButton" type="button" onClick={props.createInsight} disabled={!props.selectedResults.length}>
          <Sparkles size={17} /> Generate insight
        </button>
        <div className={props.modelReady ? "modelReady ready" : "modelReady"}>
          <i /> {props.modelReady ? "Model ready" : "Configure model in Settings"}
          {props.modelReady && <span>{providerDetails[props.activeProfile?.provider ?? ""]?.label} · {props.model}</span>}
        </div>
          </>
        )}
      </aside>
    </section>
  );
}

function ReportsView({
  reports,
  insight,
  insightJob,
  reportSources,
  detail,
  detailMessageIndex,
  openReport,
  openDetail,
  closeDetail,
  openCitation,
  backToSearch,
  regenerate,
  downloadInsight
}: {
  reports: InsightSummary[];
  insight: Insight | null;
  insightJob: InsightJob | null;
  reportSources: SearchResult[];
  detail: ConversationDetail | null;
  detailMessageIndex: number | null;
  openReport: (id: string) => void;
  openDetail: (id: string) => void;
  closeDetail: () => void;
  openCitation: (target: CitationTarget) => void;
  backToSearch: () => void;
  regenerate: () => void;
  downloadInsight: () => void;
}) {
  const reportCanvasRef = useRef<HTMLDivElement | null>(null);
  const markdownOutline = useMemo(
    () => extractMarkdownHeadings(insight?.markdown ?? ""),
    [insight?.markdown]
  );
  const outlineItems = useMemo<MarkdownHeading[]>(
    () =>
      markdownOutline.length || !insight
        ? markdownOutline
        : [{ id: "report-top", level: 1, text: insight.title }],
    [insight, markdownOutline]
  );
  const [activeOutlineId, setActiveOutlineId] = useState("");

  const updateActiveOutline = useCallback(() => {
    const root = reportCanvasRef.current;
    if (!root || !outlineItems.length) return;

    const rootTop = root.getBoundingClientRect().top;
    const isAtBottom = root.scrollTop + root.clientHeight >= root.scrollHeight - 2;
    if (isAtBottom) {
      const bottomId = outlineItems[outlineItems.length - 1].id;
      setActiveOutlineId((current) => (current === bottomId ? current : bottomId));
      return;
    }

    let nextActiveId = outlineItems[0].id;

    for (const item of outlineItems) {
      const element = document.getElementById(item.id);
      if (!element) continue;
      const distanceFromCanvasTop = element.getBoundingClientRect().top - rootTop;
      if (distanceFromCanvasTop <= 96) nextActiveId = item.id;
      else break;
    }

    setActiveOutlineId((current) => (current === nextActiveId ? current : nextActiveId));
  }, [outlineItems]);

  useEffect(() => {
    setActiveOutlineId(outlineItems[0]?.id ?? "");
    const frame = window.requestAnimationFrame(updateActiveOutline);
    return () => window.cancelAnimationFrame(frame);
  }, [insight?.id, outlineItems, updateActiveOutline]);

  function scrollToOutlineItem(id: string) {
    setActiveOutlineId(id);
    const root = reportCanvasRef.current;
    const element = document.getElementById(id);
    if (!root || !element) return;
    const rootTop = root.getBoundingClientRect().top;
    const elementTop = element.getBoundingClientRect().top;
    const nextTop = root.scrollTop + elementTop - rootTop - 24;
    root.scrollTo({
      top: nextTop,
      behavior: "smooth"
    });
    window.setTimeout(() => {
      if (Math.abs(root.scrollTop - nextTop) > 4) root.scrollTop = nextTop;
    }, 160);
  }

  return (
    <section className="reportsScreen">
      <header className="reportToolbar">
        <strong>Reports{insight ? ` / ${insight.title}` : ""}</strong>
        <div>
          <button className="secondaryButton" type="button" onClick={backToSearch}><ArrowLeft size={16} /> Back to search</button>
          {insight && <button className="secondaryButton" type="button" onClick={regenerate}><RefreshCw size={16} /> Regenerate</button>}
          {insight && (
            <button className="secondaryButton" type="button" onClick={() => navigator.clipboard.writeText(insight.markdown)}>
              <Clipboard size={16} /> Copy Markdown
            </button>
          )}
          {insight && <button className="primaryButton" type="button" onClick={downloadInsight}><Download size={16} /> Download</button>}
        </div>
      </header>
      <aside className="reportIndex">
        <h2>Report outline</h2>
        <nav aria-label="Report outline">
          {outlineItems.map((section) => (
            <button
              className={activeOutlineId === section.id ? `active depth-${section.level}` : `depth-${section.level}`}
              type="button"
              onClick={() => scrollToOutlineItem(section.id)}
              aria-current={activeOutlineId === section.id ? "location" : undefined}
              key={section.id}
            >
              {section.text}
            </button>
          ))}
          {!outlineItems.length && <p>No outline available.</p>}
        </nav>
        <div className="recentReports">
          <h2>Recent reports</h2>
          {reports.slice(0, 5).map((report) => (
            <button className={insight?.id === report.id ? "active" : ""} type="button" onClick={() => openReport(report.id)} key={report.id}>
              <FileText size={16} />
              <span><strong>{report.title}</strong><small>{formatDate(report.created_at)}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
          {!reports.length && <p>No saved reports yet.</p>}
        </div>
      </aside>
      <div className="reportCanvas" ref={reportCanvasRef} onScroll={updateActiveOutline}>
        {insightJob && (
          <section className="generationCard" aria-live="polite">
            <span className="generationIcon"><Sparkles size={23} /></span>
            <div>
              <span className="sectionLabel">Generating insight</span>
              <h1>{insightJob.message}</h1>
              <p>Reweave is analyzing the selected conversations and linking every finding to its source.</p>
              <div className="progressTrack" role="progressbar" aria-valuenow={insightJob.progress} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${insightJob.progress}%` }} />
              </div>
              <div className="progressMeta"><span>{insightJob.stage}</span><strong>{insightJob.progress}%</strong></div>
            </div>
          </section>
        )}
        {!insightJob && insight && (
          <article className="reportPaper" id="report-top">
            <header className="reportHero">
              <span className="sectionLabel">Source-grounded insight report</span>
              <h1>{insight.title}</h1>
              <div className="reportMeta">
                <span><BookOpen size={15} /> {insight.selected_conversation_ids.length} sources</span>
                <span><CalendarDays size={15} /> {formatDate(insight.created_at)}</span>
                <span><Sparkles size={15} /> {insight.model}</span>
                {insight.performance?.total_ms && <span><Clock3 size={15} /> {(insight.performance.total_ms / 1000).toFixed(1)}s</span>}
              </div>
            </header>
            <MarkdownContent markdown={insight.markdown} onCitation={openCitation} />
          </article>
        )}
        {!insightJob && !insight && (
          <div className="emptyState reportEmpty">
            <FileText size={32} />
            <h2>Open a saved report</h2>
            <p>Select a recent report or return to Search to generate one.</p>
          </div>
        )}
      </div>
      <aside className={detail ? "reportSources drawerOpen" : "reportSources"}>
        {detail ? (
          <ConversationDrawer
            detail={detail}
            targetIndex={detailMessageIndex}
            close={closeDetail}
            label={detailMessageIndex === null ? "Source conversation" : `Supporting message #${detailMessageIndex}`}
          />
        ) : (
          <>
        <div className="railHeader"><div><h2>Report sources</h2><p>{reportSources.length} sources</p></div></div>
        <div className="reportSourceList">
          {reportSources.map((source) => (
                <button
                  type="button"
                  onClick={() => openDetail(source.id)}
                  title={source.title}
                  key={source.id}
                >
              <span className="providerMark small">{source.source === "chatgpt" ? "G" : "AI"}</span>
              <span><strong>{source.title}</strong><small>{source.source} · {source.raw_message_count} messages</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
          </>
        )}
      </aside>
    </section>
  );
}

function ConversationDrawer({
  detail,
  targetIndex,
  close,
  label,
  highlightTerms = []
}: {
  detail: ConversationDetail;
  targetIndex: number | null;
  close: () => void;
  label: string;
  highlightTerms?: string[];
}) {
  const [viewMode, setViewMode] = useState<"all" | "context">(targetIndex === null ? "all" : "context");
  const targetRef = useRef<HTMLElement | null>(null);
  const canShowContext = targetIndex !== null;
  const messages = useMemo(
    () =>
      viewMode === "context" && targetIndex !== null
        ? detail.messages.filter((message) => Math.abs(message.index - targetIndex) <= 2)
        : detail.messages,
    [detail.messages, targetIndex, viewMode]
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
    <section className="conversationDrawer" aria-label={label}>
      <header className="conversationDrawerHeader">
        <div>
          <span className="sectionLabel">{label}</span>
          <h2 title={detail.conversation.title}>{detail.conversation.title}</h2>
          <p>
            {detail.conversation.source} / {detail.conversation.raw_message_count} messages / {formatDate(detail.conversation.created_at)}
          </p>
        </div>
        <button type="button" onClick={close} aria-label="Close conversation drawer"><X size={17} /></button>
      </header>
      {canShowContext && (
        <div className="drawerControls" role="group" aria-label="Conversation view">
          <button className={viewMode === "context" ? "active" : ""} type="button" onClick={() => setViewMode("context")}>
            Context around #{targetIndex}
          </button>
          <button className={viewMode === "all" ? "active" : ""} type="button" onClick={() => setViewMode("all")}>
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
            className={message.index === targetIndex ? "messageItem target" : "messageItem"}
            ref={message.index === targetIndex ? targetRef : undefined}
            key={message.id}
          >
            <header><strong>{message.role}</strong><small>#{message.index}</small></header>
            <MarkdownContent markdown={message.content} variant="conversation" highlightTerms={highlightTerms} />
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
  showOnboarding
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
          <p>Add ChatGPT or Claude exports. Reweave keeps your searchable archive on this device.</p>
        </div>
        <button className="secondaryButton" type="button" onClick={showOnboarding}>
          <BookOpen size={16} /> Export guide
        </button>
      </header>
      <div className="statsGrid">
        <div><Database size={20} /><span><strong>{conversationCount.toLocaleString()}</strong><small>Conversations</small></span></div>
        <div><FileText size={20} /><span><strong>{messageCount.toLocaleString()}</strong><small>Messages</small></span></div>
        {sourceFacets.map((facet) => (
          <div key={facet.source}><Library size={20} /><span><strong>{facet.conversations.toLocaleString()}</strong><small>{facet.source}</small></span></div>
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
          <span><FileUp size={28} /></span>
          <h2>Drop export files here</h2>
          <p>Choose one or more .zip or .json exports.</p>
          <label className="primaryButton filePicker">
            <CloudUpload size={17} /> Choose files
            <input
              type="file"
              accept=".zip,.json,application/json,application/zip,application/x-zip-compressed"
              multiple
              onChange={(event) => {
                if (event.currentTarget.files) importFiles(event.currentTarget.files);
                event.currentTarget.value = "";
              }}
            />
          </label>
        </div>
        <div className="importPathCard">
          <FolderInput size={24} />
          <h2>Import a local path</h2>
          <p>Use a folder, JSON file, or zip path already available on this device.</p>
          <label>Local path<input value={importPath} onChange={(event) => setImportPath(event.target.value)} placeholder="C:\\path\\to\\export.zip" /></label>
          <button className="secondaryButton" type="button" onClick={importLocalPath} disabled={busy}><FolderInput size={16} /> Import path</button>
        </div>
      </div>
      <div className="statusNotice" role="status"><CheckCircle2 size={17} /><span>{importStatus}</span></div>
      {paths && <div className="pathDetails"><strong>Archive database</strong><span>{paths.db_path}</span><strong>Imports folder</strong><span>{paths.imports_dir}</span></div>}
    </section>
  );
}

type SettingsProps = {
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
  const detail = providerDetails[props.activeProfile?.provider ?? "openai"] ?? providerDetails.openai;
  const connected = props.activeProfile?.connected;
  return (
    <section className="singlePage settingsPage">
      <header className="pageHeader">
        <span className="sectionLabel">Bring your own model</span>
        <h1>AI connection</h1>
        <p>Local search stays on this device. Connect a provider only for Ask Archive or insight reports.</p>
      </header>
      <div className="settingsLayout">
        <section className="settingsSection">
          <header><div><h2>Provider connection</h2><p>API keys stay in your operating system keyring.</p></div>{connected && <span className="connectedBadge"><Check size={13} /> Connected</span>}</header>
          <label>Provider<select value={props.activeProfileId} onChange={(event) => props.changeProfile(event.target.value)}>{props.profiles.map((profile) => <option value={profile.id} key={profile.id}>{providerDetails[profile.provider]?.label ?? profile.name}</option>)}</select></label>
          {connected && !props.editingKey ? (
            <div className="connectedKey">
              <span><KeyRound size={18} /><span><strong>{props.activeProfile?.masked_key}</strong><small>Stored securely in your operating system keyring.</small></span></span>
              <div>
                <button className="secondaryButton" type="button" onClick={() => props.setEditingKey(true)}>Change key</button>
                <button className="dangerButton" type="button" onClick={props.disconnectProvider}>Remove</button>
              </div>
            </div>
          ) : (
            <div className="connectionForm">
              <p>{detail.keyHelp} {detail.keyUrl && <a href={detail.keyUrl} target="_blank" rel="noreferrer">Get an API key</a>}</p>
              <div className="secretInput">
                <input type={props.showApiKey ? "text" : "password"} value={props.apiKeyDraft} onChange={(event) => props.setApiKeyDraft(event.target.value)} placeholder={`Paste your ${detail.label} API key`} aria-label="API key" />
                <button type="button" onClick={() => props.setShowApiKey(!props.showApiKey)} aria-label={props.showApiKey ? "Hide API key" : "Show API key"}>{props.showApiKey ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
              <div className="buttonRow"><button className="primaryButton" type="button" onClick={props.connectProvider} disabled={props.settingsBusy || !props.apiKeyDraft.trim()}><KeyRound size={16} /> Connect</button>{connected && <button className="secondaryButton" type="button" onClick={() => props.setEditingKey(false)}>Cancel</button>}</div>
            </div>
          )}
          <div className={`modelStatus ${props.modelLoad.status}`}>
            {props.modelLoad.status === "loading" ? <Loader2 className="spin" size={16} /> : props.modelLoad.status === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{props.modelLoad.message}</span>
          </div>
        </section>
        <section className="settingsSection">
          <header><div><h2>Insight model</h2><p>Choose the model used for source-grounded reports.</p></div><button className="iconButton" type="button" onClick={props.reloadModels} aria-label="Refresh models"><RefreshCw size={17} /></button></header>
          <label>Available model<select value={props.model} onChange={(event) => props.saveModel(event.target.value)} disabled={!props.modelLoad.models.length}><option value="">Choose a model</option>{props.modelLoad.models.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
          <div className="twoColumnFields">
            <label>Context characters<input type="number" min={1000} value={props.maxContextChars} onChange={(event) => props.setMaxContextChars(Number(event.target.value))} /></label>
            <label>Temperature<input type="number" min={0} max={2} step={0.1} value={props.temperature} onChange={(event) => props.setTemperature(Number(event.target.value))} /></label>
          </div>
        </section>
        <section className="settingsSection full smartSearchCard">
          <header>
            <div>
              <h2>Smart search</h2>
              <p>Optional local meaning search for Korean and English. Nothing is uploaded.</p>
            </div>
            {props.semanticStatus?.ready && <span className="connectedBadge"><Check size={13} /> Ready</span>}
          </header>
          <div className="smartSearchDetails">
            <div>
              <strong>{props.semanticStatus?.model_downloaded ? "Multilingual model installed" : "Model not downloaded"}</strong>
              <p>
                Reweave downloads about 220 MB only after you enable this feature, then stores message
                embeddings and searches them locally.
              </p>
            </div>
            <dl>
              <div><dt>Indexed chunks</dt><dd>{props.semanticStatus?.indexed_chunks.toLocaleString() ?? "0"}</dd></div>
              <div><dt>Archive messages</dt><dd>{props.semanticStatus?.total_messages.toLocaleString() ?? "0"}</dd></div>
              <div><dt>Model</dt><dd>Multilingual MiniLM</dd></div>
            </dl>
          </div>
          {props.semanticJob && (
            <div className="smartProgress" aria-live="polite">
              <strong>{props.semanticJob.message}</strong>
              <div className="progressTrack"><span style={{ width: `${props.semanticJob.progress}%` }} /></div>
              <div className="progressMeta"><span>{props.semanticJob.stage}</span><span>{props.semanticJob.progress}%</span></div>
            </div>
          )}
          <div className="buttonRow">
            {!props.semanticStatus?.ready ? (
              <button className="primaryButton" type="button" onClick={() => props.startSemanticIndex(false)} disabled={Boolean(props.semanticJob)}>
                <Download size={16} /> Download model &amp; index archive
              </button>
            ) : (
              <button className="secondaryButton" type="button" onClick={() => props.startSemanticIndex(true)} disabled={Boolean(props.semanticJob)}>
                <RefreshCw size={16} /> Rebuild index
              </button>
            )}
            {Boolean(props.semanticStatus?.indexed_chunks) && (
              <button className="secondaryButton" type="button" onClick={props.deleteSemanticIndex} disabled={Boolean(props.semanticJob)}>
                <Trash2 size={16} /> Remove index
              </button>
            )}
            {props.semanticStatus?.model_downloaded && (
              <button className="dangerButton" type="button" onClick={props.deleteSemanticModel} disabled={Boolean(props.semanticJob)}>
                <Trash2 size={16} /> Remove model
              </button>
            )}
          </div>
        </section>
        <section className="settingsSection full">
          <header><div><h2>Advanced provider settings</h2><p>Only needed for compatible endpoints or models not returned automatically.</p></div></header>
          <div className="twoColumnFields"><label>Base URL<input value={props.baseUrlDraft} onChange={(event) => props.setBaseUrlDraft(event.target.value)} placeholder="Optional provider endpoint" /></label><label>Additional model IDs<input value={props.customModelsDraft} onChange={(event) => props.setCustomModelsDraft(event.target.value)} placeholder="Comma-separated" /></label></div>
          <button className="secondaryButton alignedButton" type="button" onClick={props.saveAdvancedSettings} disabled={props.settingsBusy}><Save size={16} /> Save advanced settings</button>
        </section>
      </div>
    </section>
  );
}

async function api<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
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
    this.status = status;
  }
}

function messageFrom(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function formatImportStatus(summary: ImportSummary) {
  const updates = summary.updated_conversations || summary.updated_messages
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
    : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function splitModels(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function safeFilename(value: string) {
  return value.trim().replace(/[<>:"/\\|?*\u0000-\u001f]+/g, "-") || "reweave-insight";
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

function chooseModel(current: string, saved: string, models: string[], provider: string) {
  if (models.includes(current)) return current;
  if (models.includes(saved)) return saved;
  const preference = provider === "anthropic" ? "sonnet" : provider === "gemini" ? "flash" : "mini";
  return models.find((item) => item.toLocaleLowerCase().includes(preference)) ?? models[0] ?? "";
}

function hasCompletedOnboarding() {
  try {
    return window.localStorage.getItem("reweave:onboarding-complete:v1") === "true";
  } catch {
    return false;
  }
}

function rememberOnboardingComplete() {
  try {
    window.localStorage.setItem("reweave:onboarding-complete:v1", "true");
  } catch {
    // Onboarding still works when storage is unavailable in a restricted webview.
  }
}
