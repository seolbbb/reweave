import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  CloudUpload,
  DatabaseBackup,
  ExternalLink,
  FileUp,
  FolderOpen,
  HardDrive,
  KeyRound,
  Loader2,
  MessageSquareText,
  Puzzle,
  Search,
  ShieldCheck,
  Trash2
} from "lucide-react";
import "./archiveManagement.css";
import { AnalysisQueue, queueConversation } from "./AnalysisQueue";
import { BackupManager } from "./BackupManager";

export type ArchiveConversation = {
  id: string;
  source: string;
  title: string;
  created_at: string;
  updated_at: string | null;
  raw_message_count: number;
  preview: string;
};

export type ArchivePage = {
  results: ArchiveConversation[];
  total: number;
  offset: number;
  limit: number;
};

export type ArchivePaths = {
  data_dir: string;
  db_path: string;
  imports_dir: string;
  extracted_dir: string;
  models_dir: string;
};

export type ArchiveFacet = {
  source: string;
  conversations: number;
  messages: number;
};

export type ImportResult = {
  parsed_conversations: number;
  inserted_conversations: number;
  updated_conversations: number;
  inserted_messages: number;
  updated_messages: number;
  invalidated_embeddings: number;
  skipped_files: string[];
};

type DeletionResult = {
  conversations: number;
  messages: number;
  embeddings: number;
  reports: number;
};

type LibraryViewProps = {
  paths: ArchivePaths | null;
  sourceFacets: ArchiveFacet[];
  onOpenConversation: (id: string) => void;
  onImport: () => void;
  onArchiveChanged: () => Promise<void>;
  onOpenSettings?: () => void;
};

export function LibraryView({
  paths,
  sourceFacets,
  onOpenConversation,
  onImport,
  onArchiveChanged,
  onOpenSettings
}: LibraryViewProps) {
  const [page, setPage] = useState<ArchivePage>({ results: [], total: 0, offset: 0, limit: 50 });
  const [source, setSource] = useState("");
  const [title, setTitle] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sort, setSort] = useState("newest");
  const [offset, setOffset] = useState(0);
  const requestSequence = useRef(0);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("Browse every conversation without knowing what to search for.");
  const [managementBusy, setManagementBusy] = useState(false);

  const loadLibrary = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    try {
      const params = new URLSearchParams({ sort, limit: "50", offset: String(offset) });
      if (source) params.set("source", source);
      if (title.trim()) params.set("title", title.trim());
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const response = await request<ArchivePage>(`/api/library?${params.toString()}`);
      if (sequence !== requestSequence.current) return;
      if (offset > 0 && offset >= response.total) {
        setOffset(Math.max(0, Math.floor((response.total - 1) / 50) * 50));
        return;
      }
      setPage(response);
      setNotice(
        response.total
          ? `${response.total.toLocaleString()} conversations match this view.`
          : "No conversations match these filters."
      );
    } catch (error) {
      if (sequence !== requestSequence.current) return;
      setNotice(errorMessage(error, "Could not load the conversation library."));
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [source, title, dateFrom, dateTo, sort, offset]);

  useEffect(() => {
    void loadLibrary();
  }, [loadLibrary]);

  async function removeConversation(conversation: ArchiveConversation) {
    if (
      !window.confirm(
        `Permanently delete the original “${conversation.title}” and its messages, search index, local embeddings, and related reports? Derived Context Items, history, and compact evidence stay in your Context Library. This source deletion cannot be undone.`
      )
    ) return;
    setManagementBusy(true);
    try {
      const result = await request<DeletionResult>(`/api/conversations/${conversation.id}`, {
        method: "DELETE"
      });
      setNotice(deletionNotice(result));
      await Promise.all([loadLibrary(), onArchiveChanged()]);
    } catch (error) {
      setNotice(errorMessage(error, "Could not delete the conversation."));
    } finally {
      setManagementBusy(false);
    }
  }

  async function removeSource(sourceName: string) {
    const count = sourceFacets.find((facet) => facet.source === sourceName)?.conversations ?? 0;
    if (
      !window.confirm(
        `Permanently delete all ${count.toLocaleString()} ${sourceName} source conversations and related reports? Derived Context Items and compact evidence remain. This source deletion cannot be undone.`
      )
    ) return;
    setManagementBusy(true);
    try {
      const result = await request<DeletionResult>(`/api/archive/sources/${sourceName}`, {
        method: "DELETE"
      });
      setNotice(deletionNotice(result));
      await Promise.all([loadLibrary(), onArchiveChanged()]);
    } catch (error) {
      setNotice(errorMessage(error, `Could not delete ${sourceName} conversations.`));
    } finally {
      setManagementBusy(false);
    }
  }

  async function analyzeConversation(conversation: ArchiveConversation) {
    setManagementBusy(true);
    try {
      await queueConversation(conversation.id);
      setNotice(`“${conversation.title}” is in the durable analysis queue. Without a key it stays saved until you connect a provider.`);
    } catch (error) {
      setNotice(errorMessage(error, "Could not queue this source for analysis."));
    } finally { setManagementBusy(false); }
  }

  return (
    <section className="singlePage libraryPage">
      <header className="pageHeader libraryHeader">
        <div>
          <span className="sectionLabel">Your local archive</span>
          <h1>Sources</h1>
          <p>Browse by date or service, open the original thread, and control what remains stored.</p>
        </div>
        <button className="primaryButton" type="button" onClick={onImport}>
          <CloudUpload size={16} /> Import conversations
        </button>
      </header>

      <div className="privacyBanner">
        <ShieldCheck size={21} />
        <div>
          <strong>Stored on this device</strong>
          <span>
            Search and browsing stay local. Imported and explicitly saved conversations are queued for your selected AI provider, within your analysis allowance.
          </span>
        </div>
        <small title={paths?.db_path}>{paths?.db_path ?? "Loading archive location..."}</small>
      </div>

      <form
        className="libraryFilters"
        onSubmit={(event) => {
          event.preventDefault();
          void loadLibrary();
        }}
      >
        <label>
          <span>Title</span>
          <input value={title} onChange={(event) => { setTitle(event.target.value); setOffset(0); }} placeholder="Filter conversation titles" />
        </label>
        <label>
          <span>Service</span>
          <select value={source} onChange={(event) => { setSource(event.target.value); setOffset(0); }}>
            <option value="">All services</option>
            <option value="chatgpt">ChatGPT</option>
            <option value="claude">Claude</option>
          </select>
        </label>
        <label>
          <span>From</span>
          <input type="date" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setOffset(0); }} />
        </label>
        <label>
          <span>To</span>
          <input type="date" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setOffset(0); }} />
        </label>
        <label>
          <span>Sort</span>
          <select value={sort} onChange={(event) => { setSort(event.target.value); setOffset(0); }}>
            <option value="newest">Recently updated</option>
            <option value="oldest">Oldest first</option>
            <option value="messages">Most messages</option>
            <option value="title">Title</option>
          </select>
        </label>
        <button className="secondaryButton" type="submit"><Search size={16} /> Apply</button>
      </form>

      <div className="libraryNotice" role="status">
        {loading ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
        <span>{notice}</span>
      </div>

      <div className="conversationLibrary" aria-busy={loading}>
        {!loading && page.results.length === 0 && (
          <div className="libraryEmpty">
            <FolderOpen size={32} />
            <h2>{sourceFacets.length ? "No matching conversations" : "Your archive is ready for its first import"}</h2>
            <p>{sourceFacets.length ? "Try clearing one or more filters." : "Import a ChatGPT or Claude export to start browsing."}</p>
            {!sourceFacets.length && <button className="primaryButton" type="button" onClick={onImport}>Import now</button>}
          </div>
        )}
        {page.results.map((conversation) => (
          <article className="libraryConversation" key={conversation.id}>
            <button className="libraryConversationMain" type="button" onClick={() => onOpenConversation(conversation.id)}>
              <span className={`sourceMark ${conversation.source}`}>{conversation.source === "chatgpt" ? "C" : "A"}</span>
              <span className="libraryConversationCopy">
                <span className="libraryConversationMeta">
                  <b>{conversation.source}</b>
                  <span><CalendarDays size={13} /> {formatDate(conversation.updated_at || conversation.created_at)}</span>
                  <span><MessageSquareText size={13} /> {conversation.raw_message_count.toLocaleString()} messages</span>
                </span>
                <strong>{conversation.title}</strong>
                <p>{conversation.preview || "No text preview is available."}</p>
              </span>
              <ArrowRight size={17} />
            </button>
            <button className="secondaryButton libraryAnalyze" type="button" disabled={managementBusy}
              onClick={() => void analyzeConversation(conversation)} aria-label={`Analyze ${conversation.title}`}>
              Analyze
            </button>
            <button
              className="libraryDelete"
              type="button"
              onClick={() => void removeConversation(conversation)}
              aria-label={`Delete ${conversation.title}`}
              disabled={managementBusy}
            >
              <Trash2 size={16} />
            </button>
          </article>
        ))}
      </div>

      {page.total > 50 && <nav className="libraryPagination" aria-label="Source pages">
        <button className="secondaryButton" type="button" disabled={loading || offset === 0}
          onClick={() => setOffset((value) => Math.max(0, value - 50))}><ArrowLeft size={16} /> Previous</button>
        <span>{offset + 1}–{Math.min(offset + page.results.length, page.total)} of {page.total.toLocaleString()} sources</span>
        <button className="secondaryButton" type="button" disabled={loading || offset + page.results.length >= page.total}
          onClick={() => setOffset((value) => value + 50)}>Next <ArrowRight size={16} /></button>
      </nav>}

      <AnalysisQueue onOpenSource={onOpenConversation} onOpenSettings={onOpenSettings} />

      <section className="archiveManagementPanel">
        <header>
          <div>
            <span className="sectionLabel">Archive controls</span>
            <h2>Backup, restore, or remove data</h2>
          </div>
          {managementBusy && <Loader2 className="spin" size={18} />}
        </header>
        <div className="archiveManagementGrid">
          <BackupManager onRestored={async () => { await Promise.all([loadLibrary(), onArchiveChanged()]); }} />
          <div className="managementCard dangerManagement">
            <Trash2 size={21} />
            <h3>Delete by service</h3>
            <p>Removes original conversations, indexes, embeddings, and related reports. Derived Context Items, history, and compact evidence remain.</p>
            <div>
              {sourceFacets.map((facet) => (
                <button
                  className="dangerButton"
                  type="button"
                  disabled={managementBusy}
                  onClick={() => void removeSource(facet.source)}
                  key={facet.source}
                >
                  Delete {facet.source} ({facet.conversations})
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}

type OnboardingWizardProps = {
  open: boolean;
  busy: boolean;
  onImport: (files: FileList | File[]) => Promise<ImportResult | null>;
  onFinish: (destination: "context" | "import" | "settings") => void;
};

export function OnboardingWizard({
  open,
  busy,
  onImport,
  onFinish
}: OnboardingWizardProps) {
  const [step, setStep] = useState(0);
  const [provider, setProvider] = useState<"chatgpt" | "claude">("chatgpt");
  const [summary, setSummary] = useState<ImportResult | null>(null);
  const [message, setMessage] = useState("Choose the export ZIP or JSON file when it is ready.");
  const titleRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!open) return;
    setStep(0);
    setProvider("chatgpt");
    setSummary(null);
    setMessage("Choose the export ZIP or JSON file when it is ready.");
  }, [open]);

  useEffect(() => {
    if (open) titleRef.current?.focus();
  }, [open, step]);

  if (!open) return null;

  async function importOnboardingFiles(files: FileList | File[]) {
    setMessage("Importing and indexing your conversations locally...");
    const result = await onImport(files);
    if (!result) {
      setMessage("The import did not finish. Check the Import screen status and try again.");
      return;
    }
    setSummary(result);
    setStep(4);
  }

  const steps = ["Welcome", "Backfill", "Export", "Import", "Start"];

  return (
    <div className="onboardingBackdrop" role="presentation">
      <section className="onboardingDialog" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
        <aside className="onboardingRail">
          <span className="onboardingLogo">R</span>
          <div>
            {steps.map((label, index) => (
              <span
                className={index === step ? "active" : index < step ? "complete" : ""}
                aria-current={index === step ? "step" : undefined}
                key={label}
              >
                <i>{index < step ? "✓" : index + 1}</i>{label}
              </span>
            ))}
          </div>
          <small>Import is recommended, never required.</small>
        </aside>

        <div className="onboardingContent">
          {step === 0 && (
            <div className="onboardingStep">
              <span className="onboardingIcon"><HardDrive size={26} /></span>
              <span className="sectionLabel">Welcome to Reweave</span>
              <h1 id="onboarding-title" ref={titleRef} tabIndex={-1}>Start a Context Library on your terms.</h1>
              <p>
                Reweave keeps conversations you explicitly save or import on this computer. A historical
                export builds useful context faster, but you can begin with new conversations instead.
              </p>
              <div className="onboardingPromises">
                <span><ShieldCheck size={18} /><b>Local by default</b><small>Capture, browsing, and search stay available without an API key.</small></span>
                <span><DatabaseBackup size={18} /><b>Optional history</b><small>Import ChatGPT or Claude exports when a faster backfill is useful.</small></span>
                <span><Puzzle size={18} /><b>Explicit browser actions</b><small>The extension reads a chat only after you choose Save or Use.</small></span>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="onboardingStep">
              <span className="sectionLabel">Recommended, not required</span>
              <h1 id="onboarding-title" ref={titleRef} tabIndex={-1}>Bring history forward for faster initial value.</h1>
              <p>
                A whole export gives Reweave more prior conversations to browse and search immediately.
                Skip it if you would rather build the library from new, explicitly saved chats.
              </p>
              <div className="onboardingRecommendation">
                <FileUp size={22} />
                <span>
                  <b>Recommended: import an export</b>
                  <small>Request or import a ChatGPT or Claude ZIP/JSON file. You can return to Import later.</small>
                </span>
              </div>
              <button className="onboardingInlineAction" type="button" onClick={() => setStep(4)}>
                <Puzzle size={18} />
                <span><b>Start with new conversations</b><small>Continue to the extension setup without importing.</small></span>
                <ArrowRight size={17} />
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="onboardingStep">
              <span className="sectionLabel">Optional backfill · Request your export</span>
              <h1 id="onboarding-title" ref={titleRef} tabIndex={-1}>Export from your AI service</h1>
              <div className="providerTabs" role="tablist" aria-label="Export service">
                <button className={provider === "chatgpt" ? "active" : ""} type="button" role="tab" aria-selected={provider === "chatgpt"} onClick={() => setProvider("chatgpt")}>ChatGPT</button>
                <button className={provider === "claude" ? "active" : ""} type="button" role="tab" aria-selected={provider === "claude"} onClick={() => setProvider("claude")}>Claude</button>
              </div>
              {provider === "chatgpt" ? (
                <ExportGuide
                  steps={["Open your profile menu and choose Settings.", "Open Data controls, then select Export data.", "Confirm the export and download the ZIP from the email or SMS you receive."]}
                  note="The download link expires after 24 hours. Delivery can take up to 7 days."
                  href="https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data"
                />
              ) : (
                <ExportGuide
                  steps={["Open your initials menu and choose Settings.", "Open Privacy, then select Export data.", "Download the export from the email sent to your Claude account address."]}
                  note="Export requests are available on the web app and Claude Desktop, not mobile. The link expires after 24 hours."
                  href="https://support.anthropic.com/en/articles/9450526-how-can-i-export-my-claude-data"
                />
              )}
              <button className="textButton onboardingSkipLink" type="button" onClick={() => setStep(4)}>
                Continue without waiting for an export <ArrowRight size={15} />
              </button>
            </div>
          )}

          {step === 3 && (
            <div className="onboardingStep">
              <span className="sectionLabel">Optional backfill · Import locally</span>
              <h1 id="onboarding-title" ref={titleRef} tabIndex={-1}>Import the downloaded file</h1>
              <p>You can use the full ZIP as downloaded. Reweave extracts supported conversation JSON temporarily and removes the temporary files after import.</p>
              <label className={`onboardingDrop ${busy ? "busy" : ""}`}>
                {busy ? <Loader2 className="spin" size={30} /> : <FileUp size={30} />}
                <b>{busy ? "Importing your archive..." : "Choose ZIP or JSON files"}</b>
                <span>Files are processed on this device.</span>
                <input
                  type="file"
                  accept=".zip,.json,application/json,application/zip,application/x-zip-compressed"
                  multiple
                  disabled={busy}
                  onChange={(event) => {
                    if (event.currentTarget.files) void importOnboardingFiles(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                />
              </label>
              <div className="onboardingStatus" role="status">{message}</div>
            </div>
          )}

          {step === 4 && (
            <div className="onboardingStep onboardingComplete">
              <span className="onboardingIcon success"><CheckCircle2 size={28} /></span>
              <span className="sectionLabel">Ready for everyday capture</span>
              <h1 id="onboarding-title" ref={titleRef} tabIndex={-1}>
                {summary ? "Your history is imported. Add new conversations as you go." : "Start with new conversations—no export or API key required."}
              </h1>
              {summary ? (
                <p>
                  Imported {summary.inserted_conversations.toLocaleString()} new conversations and {summary.inserted_messages.toLocaleString()} messages.
                </p>
              ) : (
                <p>Open Context now, then add history later or capture a supported web chat with the extension.</p>
              )}
              <div className="onboardingStartGrid">
                <article>
                  <Search size={19} />
                  <span><b>Use local features now</b><small>Explicit saves persist locally. Context, Library, and Search remain available without a key while analysis waits.</small></span>
                </article>
                <article>
                  <KeyRound size={19} />
                  <span><b>Connect analysis when ready</b><small>Settings stores the key in the operating-system credential store. A successful saved connection starts queued Context analysis automatically.</small></span>
                </article>
                <article>
                  <Puzzle size={19} />
                  <span>
                    <b>Add the current Chrome or Edge extension</b>
                    <small>
                      This development build does not install it automatically. Load the repository&apos;s <code>extension</code> folder unpacked, then register the included Native Messaging host as described in the setup guide.
                    </small>
                    <a href="https://github.com/seolbbb/reweave/tree/main/extension" target="_blank" rel="noreferrer">
                      Open current extension setup <ExternalLink size={14} />
                    </a>
                  </span>
                </article>
              </div>
              <div className="onboardingDestinations">
                <button className="primaryDestination" type="button" onClick={() => onFinish("context")}>
                  <HardDrive size={20} /><span><b>Open Context</b><small>Continue to the empty or newly built Context Library.</small></span><ArrowRight size={17} />
                </button>
                <button type="button" onClick={() => onFinish("settings")}>
                  <KeyRound size={20} /><span><b>Connect an AI provider</b><small>Save a BYOK connection and start pending analysis automatically.</small></span><ArrowRight size={17} />
                </button>
                <button type="button" onClick={() => onFinish("import")}>
                  <FolderOpen size={20} /><span><b>Import history later</b><small>The existing ZIP, JSON, and local-path import screen remains available.</small></span><ArrowRight size={17} />
                </button>
              </div>
            </div>
          )}

          {step < 4 && (
            <footer className="onboardingActions">
              <button
                className="textButton"
                type="button"
                onClick={step === 0 ? () => setStep(4) : () => setStep((value) => Math.max(0, value - 1))}
              >
                {step === 0 ? "Start without import" : <><ArrowLeft size={15} /> Back</>}
              </button>
              <button
                className="primaryButton"
                type="button"
                onClick={() => setStep((value) => Math.min(4, value + 1))}
                disabled={busy || step === 3}
              >
                {step === 0 ? "See recommended backfill" : step === 1 ? "View export steps" : step === 2 ? "I have the export file" : "Choose a file above"} <ArrowRight size={15} />
              </button>
            </footer>
          )}
        </div>
      </section>
    </div>
  );
}

function ExportGuide({ steps, note, href }: { steps: string[]; note: string; href: string }) {
  return (
    <div className="exportGuide">
      <ol>{steps.map((step) => <li key={step}>{step}</li>)}</ol>
      <p>{note}</p>
      <a href={href} target="_blank" rel="noreferrer">Open official instructions <ExternalLink size={14} /></a>
    </div>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function deletionNotice(result: DeletionResult) {
  return `Deleted ${result.conversations.toLocaleString()} conversations, ${result.messages.toLocaleString()} messages, ${result.embeddings.toLocaleString()} embeddings, and ${result.reports.toLocaleString()} related reports.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) throw new Error(data?.detail || `Request failed (${response.status}).`);
  return data as T;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}
