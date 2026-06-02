import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Download,
  FileSearch,
  FileUp,
  Lightbulb,
  Loader2,
  Search,
  Settings,
  X
} from "lucide-react";
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
};

type ImportSummary = {
  parsed_conversations: number;
  inserted_conversations: number;
  inserted_messages: number;
  skipped_files: string[];
};

type SettingsState = {
  provider: string;
  model: string;
  apiKey: string;
  baseUrl: string;
  maxContextChars: number;
  temperature: number;
};

const defaultSettings: SettingsState = {
  provider: "openai",
  model: "gpt-4o-mini",
  apiKey: "",
  baseUrl: "",
  maxContextChars: 80000,
  temperature: 0.2
};

function App() {
  const [query, setQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState("");
  const [titleFilter, setTitleFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Search your imported archive.");
  const [importStatus, setImportStatus] = useState("Drop files or choose a .zip/.json export.");

  const selectedResults = useMemo(
    () => results.filter((result) => selectedIds.includes(result.id)),
    [results, selectedIds]
  );

  async function runSearch() {
    if (!query.trim()) {
      setStatus("Enter a search query.");
      return;
    }
    setBusy(true);
    setStatus("Searching...");
    try {
      const params = new URLSearchParams({ q: query, limit: "40" });
      if (providerFilter) params.set("provider", providerFilter);
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

  async function openDetail(id: string) {
    setBusy(true);
    try {
      const response = await fetch(`/api/conversations/${id}`);
      const data = await response.json();
      setDetail(data);
    } finally {
      setBusy(false);
    }
  }

  async function createInsight() {
    if (!selectedIds.length) {
      setStatus("Select at least one conversation.");
      return;
    }
    setBusy(true);
    setStatus("Generating insight report...");
    try {
      const response = await fetch("/api/insights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_ids: selectedIds,
          title: query ? `Insights: ${query}` : "Connected Insights",
          settings: {
            provider: settings.provider,
            model: settings.model,
            api_key: settings.apiKey,
            base_url: settings.baseUrl,
            max_context_chars: settings.maxContextChars,
            temperature: settings.temperature
          }
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "Insight generation failed.");
      setInsight(data);
      setStatus("Insight report generated.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Insight generation failed.");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelection(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
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

        <label>
          Provider
          <select value={providerFilter} onChange={(event) => setProviderFilter(event.target.value)}>
            <option value="">All</option>
            <option value="chatgpt">ChatGPT</option>
            <option value="claude">Claude</option>
          </select>
        </label>

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
        </div>

        <section className="settingsBlock">
          <h2>
            <Settings size={16} />
            LLM Settings
          </h2>
          <label>
            Provider
            <select
              value={settings.provider}
              onChange={(event) => setSettings({ ...settings, provider: event.target.value })}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="gemini">Gemini</option>
              <option value="openai-compatible">OpenAI-compatible</option>
            </select>
          </label>
          <label>
            Model
            <input
              value={settings.model}
              onChange={(event) => setSettings({ ...settings, model: event.target.value })}
            />
          </label>
          <label>
            API key
            <input
              type="password"
              value={settings.apiKey}
              onChange={(event) => setSettings({ ...settings, apiKey: event.target.value })}
            />
          </label>
          <label>
            Base URL
            <input
              value={settings.baseUrl}
              onChange={(event) => setSettings({ ...settings, baseUrl: event.target.value })}
              placeholder="Required for compatible providers"
            />
          </label>
        </section>
      </aside>

      <section className="resultsPane">
        <header className="toolbar">
          <span>{status}</span>
          <span>{results.length} results</span>
        </header>
        <div className="resultList">
          {results.map((result) => (
            <article key={result.id} className="resultRow">
              <label className="checkCell">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(result.id)}
                  onChange={() => toggleSelection(result.id)}
                />
              </label>
              <button className="resultContent" onClick={() => openDetail(result.id)}>
                <div className="resultMeta">
                  <strong>{result.title}</strong>
                  <span>{result.source} - {result.raw_message_count} messages</span>
                </div>
                {result.excerpts.map((excerpt) => (
                  <p key={excerpt.message_id}>
                    <span>[#{excerpt.message_index}] {excerpt.role}</span> {excerpt.excerpt}
                  </p>
                ))}
              </button>
            </article>
          ))}
          {!results.length && <div className="emptyState">No search results yet.</div>}
        </div>
      </section>

      <aside className="selectionPane">
        <section className="selectionHeader">
          <h2>{selectedIds.length} selected</h2>
          <button className="primaryButton" onClick={createInsight} disabled={busy || !selectedIds.length}>
            {busy ? <Loader2 className="spin" size={16} /> : <Lightbulb size={16} />}
            Generate Insight MD
          </button>
        </section>

        <div className="selectedList">
          {selectedResults.map((result) => (
            <div className="selectedItem" key={result.id}>
              <span>{result.title}</span>
              <button onClick={() => toggleSelection(result.id)} aria-label={`Remove ${result.title}`}>
                <X size={14} />
              </button>
            </div>
          ))}
        </div>

        {detail && (
          <section className="detailPanel">
            <h2>{detail.conversation.title}</h2>
            <div className="messageList">
              {detail.messages.slice(0, 24).map((message) => (
                <div className="messageItem" key={message.id}>
                  <b>[{message.index}] {message.role}</b>
                  <p>{message.content}</p>
                </div>
              ))}
            </div>
          </section>
        )}

        {insight && (
          <section className="insightPanel">
            <div className="insightHeader">
              <h2>{insight.title}</h2>
              <button
                onClick={() => navigator.clipboard.writeText(insight.markdown)}
                aria-label="Copy Markdown"
              >
                <Download size={16} />
              </button>
            </div>
            <pre>{insight.markdown}</pre>
          </section>
        )}
      </aside>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : data;
    throw new Error(typeof detail === "string" ? detail : "Request failed.");
  }
  return data as T;
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
