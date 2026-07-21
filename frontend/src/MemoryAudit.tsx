import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronRight,
  Download,
  FileSearch,
  Loader2,
  Plus,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X
} from "lucide-react";
import {
  isAuditItemReviewed,
  manualClaimsFromText,
  type DraftAuditClaim
} from "./memoryAuditHelpers";

export type AuditLLMSettings = {
  profile_id: string;
  model: string;
  max_context_chars: number;
  temperature: number;
};

type StatementKind = "direct_statement" | "model_inference" | "unclear" | "";
type EvidenceVerdict =
  | "supported"
  | "contradicted"
  | "mixed"
  | "not_found"
  | "unclear"
  | "";
type Severity = "low" | "medium" | "high" | "unclear" | "";
type EvidenceRelationship = "supports" | "contradicts" | "context";

type AuditEvidence = {
  id: string;
  conversation_id: string;
  message_id: string;
  message_index: number;
  relationship: EvidenceRelationship;
  available: boolean;
  source?: string;
  title: string;
  role?: string;
  timestamp?: string | null;
  excerpt: string;
};

type AuditCandidate = {
  conversation_id: string;
  message_id: string;
  message_index: number;
  source: string;
  title: string;
  role: string;
  timestamp: string | null;
  excerpt: string;
  match_kind: string;
};

type AuditSuggestion = {
  statement_kind: Exclude<StatementKind, "">;
  evidence_verdict: Exclude<EvidenceVerdict, "">;
  issue_tags: string[];
  severity: Exclude<Severity, "">;
  rationale: string;
};

type AuditItem = {
  id: string;
  session_id: string;
  claim_text: string;
  llm_statement_kind: StatementKind;
  llm_evidence_verdict: EvidenceVerdict;
  llm_issue_tags: string[];
  llm_severity: Severity;
  llm_rationale: string;
  search_queries: string[];
  user_statement_kind: StatementKind;
  user_evidence_verdict: EvidenceVerdict;
  user_issue_tags: string[];
  user_severity: Severity;
  redacted_example: string;
  notes: string;
  evidence: AuditEvidence[];
  created_at: string;
  updated_at: string;
};

type AuditSession = {
  id: string;
  assistant_source: "chatgpt" | "claude";
  status: "draft" | "completed";
  provenance_understood: boolean | null;
  first_discrepancy_at: string | null;
  started_at: string;
  completed_at: string | null;
  updated_at: string;
  item_count: number;
  reviewed_count: number;
  discrepancy_count: number;
  items: AuditItem[];
};

type AuditSessionSummary = Omit<AuditSession, "items" | "provenance_understood" | "first_discrepancy_at">;

type EvidenceSuggestionResponse = {
  mode_used: string;
  candidates: AuditCandidate[];
  suggestion: AuditSuggestion | null;
  suggestion_error: string | null;
};

const issueTags = [
  "stale",
  "wrong",
  "conflicting",
  "unsupported",
  "sensitive",
  "overshared"
] as const;

export function MemoryAuditView({
  modelReady,
  llmSettings,
  onOpenEvidence,
  onOpenSettings
}: {
  modelReady: boolean;
  llmSettings: AuditLLMSettings | null;
  onOpenEvidence: (conversationId: string, messageIndex: number) => void;
  onOpenSettings: () => void;
}) {
  const [sessions, setSessions] = useState<AuditSessionSummary[]>([]);
  const [session, setSession] = useState<AuditSession | null>(null);
  const [starting, setStarting] = useState(true);
  const [assistantSource, setAssistantSource] = useState<"chatgpt" | "claude">("chatgpt");
  const [rawText, setRawText] = useState("");
  const [busy, setBusy] = useState(false);
  const [savingItemId, setSavingItemId] = useState("");
  const [status, setStatus] = useState("Start with the memory summary shown by ChatGPT.");
  const [allSources, setAllSources] = useState(false);
  const [provenanceUnderstood, setProvenanceUnderstood] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<string, EvidenceSuggestionResponse>>({});

  useEffect(() => {
    void loadSessions();
  }, []);

  const allReviewed = useMemo(
    () => Boolean(session?.items.length) && session!.items.every(isAuditItemReviewed),
    [session]
  );

  async function loadSessions(preferredId?: string) {
    try {
      const data = await auditApi<{ results: AuditSessionSummary[] }>("/api/memory-audits");
      setSessions(data.results);
      const targetId = preferredId ?? data.results[0]?.id;
      if (targetId) await openSession(targetId);
    } catch (error) {
      setStatus(auditMessage(error, "Could not load memory-audit sessions."));
    } finally {
      setStarting(false);
    }
  }

  async function openSession(id: string) {
    setBusy(true);
    try {
      const next = await auditApi<AuditSession>(`/api/memory-audits/${id}`);
      setSession(next);
      setAssistantSource(next.assistant_source);
      setProvenanceUnderstood(Boolean(next.provenance_understood));
      setSuggestions({});
      setStatus(
        next.status === "completed"
          ? "This pilot is complete. You can still review its local findings."
          : "Review every item. AI suggestions never become findings until you save them."
      );
    } catch (error) {
      setStatus(auditMessage(error, "Could not open this audit session."));
    } finally {
      setBusy(false);
    }
  }

  function startNewSession() {
    setSession(null);
    setAssistantSource("chatgpt");
    setRawText("");
    setSuggestions({});
    setProvenanceUnderstood(false);
    setStatus("Paste the memory summary shown by ChatGPT. The raw paste is not stored.");
  }

  async function createAudit(items: DraftAuditClaim[]) {
    if (!items.length) {
      setStatus("Add at least one memory item before starting the audit.");
      return;
    }
    const created = await auditApi<AuditSession>("/api/memory-audits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assistant_source: assistantSource, items })
    });
    setSession(created);
    setRawText("");
    setStatus(`Audit started with ${created.item_count} memory items.`);
    await loadSessions(created.id);
  }

  async function startAssistedAudit() {
    if (!rawText.trim()) {
      setStatus("Paste a memory summary before starting the audit.");
      return;
    }
    if (!modelReady || !llmSettings) {
      setStatus("Connect an AI provider in Settings, or use one item per line without AI.");
      return;
    }
    setBusy(true);
    setStatus("Separating the pasted summary into reviewable memory items...");
    try {
      const extracted = await auditApi<{ items: DraftAuditClaim[] }>("/api/memory-audits/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          assistant_source: assistantSource,
          raw_text: rawText,
          settings: llmSettings
        })
      });
      await createAudit(extracted.items);
    } catch (error) {
      setStatus(
        `${auditMessage(error, "AI extraction failed.")} Your paste is still here; use one item per line to continue manually.`
      );
    } finally {
      setBusy(false);
    }
  }

  async function startManualAudit() {
    const items = manualClaimsFromText(rawText);
    if (!items.length) {
      setStatus("Enter at least one memory item. Put each item on its own line.");
      return;
    }
    setBusy(true);
    try {
      await createAudit(items);
    } catch (error) {
      setStatus(auditMessage(error, "Could not create the manual audit."));
    } finally {
      setBusy(false);
    }
  }

  function updateLocalItem(itemId: string, changes: Partial<AuditItem>) {
    setSession((current) =>
      current
        ? {
            ...current,
            items: current.items.map((item) =>
              item.id === itemId ? { ...item, ...changes } : item
            )
          }
        : current
    );
  }

  async function saveItem(item: AuditItem) {
    if (!session || !isAuditItemReviewed(item)) {
      setStatus("Choose a statement type, evidence verdict, and severity before saving.");
      return;
    }
    setSavingItemId(item.id);
    try {
      const updated = await saveAuditItem(session.id, item);
      setSession(updated);
      setStatus("Human review saved. AI suggestions remain separate.");
      await refreshSessionList();
    } catch (error) {
      setStatus(auditMessage(error, "Could not save this memory review."));
    } finally {
      setSavingItemId("");
    }
  }

  async function refreshSessionList() {
    const data = await auditApi<{ results: AuditSessionSummary[] }>("/api/memory-audits");
    setSessions(data.results);
  }

  async function findEvidence(item: AuditItem) {
    if (!session) return;
    setSavingItemId(item.id);
    setStatus("Searching the local archive for possible evidence...");
    try {
      const result = await auditApi<EvidenceSuggestionResponse>(
        `/api/memory-audits/${session.id}/items/${item.id}/evidence-suggestions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            all_sources: allSources,
            settings: modelReady && llmSettings ? llmSettings : null
          })
        }
      );
      setSuggestions((current) => ({ ...current, [item.id]: result }));
      setStatus(
        result.suggestion_error
          ? `Local evidence is ready. AI review was unavailable: ${result.suggestion_error}`
          : `Found ${result.candidates.length} local evidence candidates using ${result.mode_used} search.`
      );
    } catch (error) {
      setStatus(auditMessage(error, "Could not search for evidence."));
    } finally {
      setSavingItemId("");
    }
  }

  function useSuggestion(item: AuditItem, suggestion: AuditSuggestion) {
    updateLocalItem(item.id, {
      user_statement_kind: suggestion.statement_kind,
      user_evidence_verdict: suggestion.evidence_verdict,
      user_issue_tags: [...suggestion.issue_tags],
      user_severity: suggestion.severity
    });
    setStatus("Suggestion copied as an unsaved draft. Review it before saving.");
  }

  function toggleIssueTag(item: AuditItem, tag: string) {
    const tags = item.user_issue_tags.includes(tag)
      ? item.user_issue_tags.filter((itemTag) => itemTag !== tag)
      : [...item.user_issue_tags, tag];
    updateLocalItem(item.id, { user_issue_tags: tags });
  }

  function attachCandidate(
    item: AuditItem,
    candidate: AuditCandidate,
    relationship: EvidenceRelationship
  ) {
    const existing = item.evidence.find((evidence) => evidence.message_id === candidate.message_id);
    const evidence: AuditEvidence = {
      id: existing?.id ?? `draft-${candidate.message_id}`,
      conversation_id: candidate.conversation_id,
      message_id: candidate.message_id,
      message_index: candidate.message_index,
      relationship,
      available: true,
      source: candidate.source,
      title: candidate.title,
      role: candidate.role,
      timestamp: candidate.timestamp,
      excerpt: candidate.excerpt
    };
    updateLocalItem(item.id, {
      evidence: [
        ...item.evidence.filter((itemEvidence) => itemEvidence.message_id !== candidate.message_id),
        evidence
      ]
    });
  }

  function removeEvidence(item: AuditItem, messageId: string) {
    updateLocalItem(item.id, {
      evidence: item.evidence.filter((evidence) => evidence.message_id !== messageId)
    });
  }

  async function completePilot() {
    if (!session || !allReviewed || !provenanceUnderstood) return;
    setBusy(true);
    setStatus("Saving final human decisions and completing the pilot...");
    try {
      for (const item of session.items) {
        await saveAuditItem(session.id, item);
      }
      const completed = await auditApi<AuditSession>(`/api/memory-audits/${session.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "completed", provenance_understood: true })
      });
      setSession(completed);
      setStatus("Pilot complete. Export only the redacted research summary.");
      await refreshSessionList();
    } catch (error) {
      setStatus(auditMessage(error, "Could not complete the pilot."));
    } finally {
      setBusy(false);
    }
  }

  async function deleteSession() {
    if (!session || !window.confirm("Delete this local memory-audit session permanently?")) return;
    setBusy(true);
    try {
      await auditApi(`/api/memory-audits/${session.id}`, { method: "DELETE" });
      setSession(null);
      setSuggestions({});
      setStatus("The local audit session was deleted.");
      await loadSessions();
    } catch (error) {
      setStatus(auditMessage(error, "Could not delete this audit session."));
    } finally {
      setBusy(false);
    }
  }

  async function downloadExport(format: "json" | "csv") {
    if (!session) return;
    try {
      const response = await fetch(`/api/memory-audits/${session.id}/export?format=${format}`);
      if (!response.ok) throw new Error("Could not export the redacted pilot summary.");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `memory-audit-${session.id.slice(0, 8)}.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
      setStatus(`Redacted ${format.toUpperCase()} exported without memory or evidence text.`);
    } catch (error) {
      setStatus(auditMessage(error, "Could not export this audit."));
    }
  }

  return (
    <section className="auditScreen">
      <aside className="auditSessionRail">
        <header>
          <div>
            <span className="sectionLabel">Phase 0 validation</span>
            <h2>Memory audits</h2>
          </div>
          <button className="iconButton" type="button" onClick={startNewSession} aria-label="New audit">
            <Plus size={18} />
          </button>
        </header>
        <button className="primaryButton auditNewButton" type="button" onClick={startNewSession}>
          <Plus size={16} /> New pilot
        </button>
        <div className="auditSessionList">
          {starting && <div className="auditRailEmpty"><Loader2 className="spin" size={18} /> Loading audits</div>}
          {!starting && !sessions.length && (
            <div className="auditRailEmpty"><ShieldCheck size={21} /><p>No audit sessions yet.</p></div>
          )}
          {sessions.map((summary) => (
            <button
              className={session?.id === summary.id ? "auditSessionItem active" : "auditSessionItem"}
              type="button"
              onClick={() => void openSession(summary.id)}
              key={summary.id}
            >
              <span><strong>{sourceLabel(summary.assistant_source)} pilot</strong><small>{formatAuditDate(summary.started_at)}</small></span>
              <span className={summary.status === "completed" ? "auditStatus complete" : "auditStatus"}>
                {summary.status === "completed" ? "Complete" : `${summary.reviewed_count}/${summary.item_count}`}
              </span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
        <div className="auditGateNote">
          <strong>P0 remains in progress</strong>
          <p>This pilot does not pass the 8-10 participant and 50-case gate.</p>
        </div>
      </aside>

      <div className="auditWorkspace">
        {!session ? (
          <AuditStart
            assistantSource={assistantSource}
            setAssistantSource={setAssistantSource}
            rawText={rawText}
            setRawText={setRawText}
            busy={busy}
            modelReady={modelReady}
            onAssistedStart={startAssistedAudit}
            onManualStart={startManualAudit}
            onOpenSettings={onOpenSettings}
            status={status}
          />
        ) : (
          <>
            <header className="auditHeader">
              <div>
                <span className="sectionLabel">{sourceLabel(session.assistant_source)} memory audit</span>
                <h1>{session.status === "completed" ? "Pilot review" : "Verify every memory against evidence"}</h1>
                <p>AI can suggest. Only your saved decisions count as findings.</p>
              </div>
              <div className="auditHeaderActions">
                <button className="secondaryButton" type="button" onClick={() => void downloadExport("json")}>
                  <Download size={16} /> JSON
                </button>
                <button className="secondaryButton" type="button" onClick={() => void downloadExport("csv")}>
                  <Download size={16} /> CSV
                </button>
                <button className="dangerButton" type="button" onClick={() => void deleteSession()} disabled={busy}>
                  <Trash2 size={16} /> Delete
                </button>
              </div>
            </header>
            <div className="auditProgressBar" aria-label={`${session.reviewed_count} of ${session.item_count} reviewed`}>
              <span style={{ width: `${Math.round((session.reviewed_count / Math.max(session.item_count, 1)) * 100)}%` }} />
            </div>
            <AuditStatus status={status} session />
            <div className="auditToolbar">
              <span><strong>{session.reviewed_count}/{session.item_count}</strong> saved reviews</span>
              <span><strong>{session.discrepancy_count}</strong> flagged items</span>
              <label className="auditSourceToggle">
                <input type="checkbox" checked={allSources} onChange={(event) => setAllSources(event.target.checked)} />
                Search all assistant sources
              </label>
            </div>
            <div className="auditItemList">
              {session.items.map((item, index) => (
                <AuditItemCard
                  item={item}
                  index={index}
                  suggestionResult={suggestions[item.id]}
                  busy={savingItemId === item.id}
                  onChange={(changes) => updateLocalItem(item.id, changes)}
                  onToggleTag={(tag) => toggleIssueTag(item, tag)}
                  onFindEvidence={() => void findEvidence(item)}
                  onUseSuggestion={(suggestion) => useSuggestion(item, suggestion)}
                  onAttach={(candidate, relationship) => attachCandidate(item, candidate, relationship)}
                  onRemoveEvidence={(messageId) => removeEvidence(item, messageId)}
                  onOpenEvidence={onOpenEvidence}
                  onSave={() => void saveItem(item)}
                  key={item.id}
                />
              ))}
              <section className="auditCompletionCard">
                <div>
                  <span className="sectionLabel">Comprehension check</span>
                  <h2>Can you explain what the assistant remembers and why?</h2>
                  <p>Complete the pilot only after every item has a human decision and evidence has been reviewed.</p>
                </div>
                <label className="auditConfirmation">
                  <input
                    type="checkbox"
                    checked={provenanceUnderstood}
                    onChange={(event) => setProvenanceUnderstood(event.target.checked)}
                  />
                  I can explain each memory and the evidence behind it.
                </label>
                <button
                  className="primaryButton"
                  type="button"
                  onClick={() => void completePilot()}
                  disabled={!allReviewed || !provenanceUnderstood || busy}
                >
                  {busy ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
                  Complete pilot
                </button>
              </section>
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function AuditStart({
  assistantSource,
  setAssistantSource,
  rawText,
  setRawText,
  busy,
  modelReady,
  onAssistedStart,
  onManualStart,
  onOpenSettings,
  status
}: {
  assistantSource: "chatgpt" | "claude";
  setAssistantSource: (source: "chatgpt" | "claude") => void;
  rawText: string;
  setRawText: (value: string) => void;
  busy: boolean;
  modelReady: boolean;
  onAssistedStart: () => void;
  onManualStart: () => void;
  onOpenSettings: () => void;
  status: string;
}) {
  return (
    <div className="auditStart">
      <header className="pageHeader">
        <span className="sectionLabel">One-person pilot</span>
        <h1>Audit what an AI remembers about you</h1>
        <p>Paste a provider memory summary, verify every item against your local conversations, and keep only human-confirmed research findings.</p>
      </header>
      <AuditStatus status={status} />
      <section className="auditStartCard">
        <div className="auditStep"><span>1</span><div><strong>Choose the source</strong><p>The first live pilot uses ChatGPT. Claude remains available for a later session.</p></div></div>
        <label>
          Assistant source
          <select value={assistantSource} onChange={(event) => setAssistantSource(event.target.value as "chatgpt" | "claude")}>
            <option value="chatgpt">ChatGPT</option>
            <option value="claude">Claude</option>
          </select>
        </label>
        <div className="auditStep"><span>2</span><div><strong>Paste the memory summary</strong><p>The raw paste is sent only to your configured model for item extraction and is never stored by Reweave.</p></div></div>
        <label>
          Memory summary
          <textarea
            value={rawText}
            onChange={(event) => setRawText(event.target.value)}
            placeholder="Paste the memory summary here. For manual mode, put one memory item on each line."
            rows={12}
          />
        </label>
        <div className="auditPrivacyNotice">
          <ShieldCheck size={20} />
          <div><strong>Archive stays local</strong><p>AI assistance receives the pasted summary first. Later review sends only one claim and up to five evidence excerpts capped at 6,000 characters.</p></div>
        </div>
        {!modelReady && (
          <div className="auditProviderNotice">
            <AlertCircle size={18} />
            <span>AI assistance is not connected. Continue manually or <button type="button" onClick={onOpenSettings}>open Settings</button>.</span>
          </div>
        )}
        <div className="auditStartActions">
          <button className="primaryButton" type="button" onClick={onAssistedStart} disabled={busy || !modelReady}>
            {busy ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}
            Extract with AI
          </button>
          <button className="secondaryButton" type="button" onClick={onManualStart} disabled={busy}>
            <Plus size={16} /> Use one item per line
          </button>
        </div>
      </section>
    </div>
  );
}

function AuditStatus({ status, session = false }: { status: string; session?: boolean }) {
  const error = status.includes("failed") || status.includes("Could not");
  return (
    <div className={`${error ? "auditToast error" : "auditToast"}${session ? " session" : ""}`} role="status">
      {error ? <AlertCircle size={15} /> : <ShieldCheck size={15} />}
      {status}
    </div>
  );
}

function AuditItemCard({
  item,
  index,
  suggestionResult,
  busy,
  onChange,
  onToggleTag,
  onFindEvidence,
  onUseSuggestion,
  onAttach,
  onRemoveEvidence,
  onOpenEvidence,
  onSave
}: {
  item: AuditItem;
  index: number;
  suggestionResult?: EvidenceSuggestionResponse;
  busy: boolean;
  onChange: (changes: Partial<AuditItem>) => void;
  onToggleTag: (tag: string) => void;
  onFindEvidence: () => void;
  onUseSuggestion: (suggestion: AuditSuggestion) => void;
  onAttach: (candidate: AuditCandidate, relationship: EvidenceRelationship) => void;
  onRemoveEvidence: (messageId: string) => void;
  onOpenEvidence: (conversationId: string, messageIndex: number) => void;
  onSave: () => void;
}) {
  const suggestion = suggestionResult?.suggestion;
  return (
    <article className={isAuditItemReviewed(item) ? "auditItemCard reviewed" : "auditItemCard"}>
      <header className="auditItemHeader">
        <div><span className="auditItemNumber">Memory {index + 1}</span><h2>{item.claim_text}</h2></div>
        {isAuditItemReviewed(item) && <span className="auditSavedBadge"><Check size={13} /> Reviewed</span>}
      </header>
      {(item.llm_statement_kind || item.llm_rationale) && (
        <div className="auditInitialSuggestion">
          <Sparkles size={15} />
          <span><strong>Extraction suggestion</strong>{formatChoice(item.llm_statement_kind)}{item.llm_rationale ? ` - ${item.llm_rationale}` : ""}</span>
        </div>
      )}
      <div className="auditDecisionGrid">
        <label>Statement type<select value={item.user_statement_kind} onChange={(event) => onChange({ user_statement_kind: event.target.value as StatementKind })}><option value="">Choose...</option><option value="direct_statement">Direct statement</option><option value="model_inference">Model inference</option><option value="unclear">Unclear</option></select></label>
        <label>Evidence verdict<select value={item.user_evidence_verdict} onChange={(event) => onChange({ user_evidence_verdict: event.target.value as EvidenceVerdict })}><option value="">Choose...</option><option value="supported">Supported</option><option value="contradicted">Contradicted</option><option value="mixed">Mixed</option><option value="not_found">Not found</option><option value="unclear">Unclear</option></select></label>
        <label>Severity<select value={item.user_severity} onChange={(event) => onChange({ user_severity: event.target.value as Severity })}><option value="">Choose...</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="unclear">Unclear</option></select></label>
      </div>
      <fieldset className="auditIssueTags">
        <legend>Issue tags <span>Leave empty when no problem is present.</span></legend>
        <div>{issueTags.map((tag) => <button className={item.user_issue_tags.includes(tag) ? "active" : ""} type="button" onClick={() => onToggleTag(tag)} key={tag}>{item.user_issue_tags.includes(tag) && <Check size={12} />}{tag}</button>)}</div>
      </fieldset>
      <div className="auditEvidenceSection">
        <div className="auditEvidenceHeading"><div><FileSearch size={17} /><span><strong>Evidence review</strong><small>{item.evidence.length} attached source{item.evidence.length === 1 ? "" : "s"}</small></span></div><button className="secondaryButton" type="button" onClick={onFindEvidence} disabled={busy}>{busy ? <Loader2 className="spin" size={15} /> : <Search size={15} />} Find evidence</button></div>
        {item.evidence.length > 0 && <div className="auditAttachedEvidence">{item.evidence.map((evidence) => <div className={evidence.available ? "auditEvidenceRow" : "auditEvidenceRow unavailable"} key={evidence.message_id}><button className="auditEvidenceOpen" type="button" onClick={() => evidence.available && onOpenEvidence(evidence.conversation_id, evidence.message_index)} disabled={!evidence.available}><span className={`auditRelation ${evidence.relationship}`}>{evidence.relationship}</span><span><strong>{evidence.title}</strong><small>{evidence.available ? `Message #${evidence.message_index}` : "The archived source was deleted or is unavailable."}</small></span></button><button className="iconButton" type="button" onClick={() => onRemoveEvidence(evidence.message_id)} aria-label="Remove evidence"><X size={15} /></button></div>)}</div>}
        {suggestionResult && (
          <div className="auditSuggestionPanel">
            {suggestion ? <div className="auditSuggestionSummary"><Sparkles size={16} /><div><strong>AI suggestion - not a finding</strong><p>{formatChoice(suggestion.statement_kind)} / {formatChoice(suggestion.evidence_verdict)} / {formatChoice(suggestion.severity)}{suggestion.issue_tags.length ? ` / ${suggestion.issue_tags.join(", ")}` : ""}</p><small>{suggestion.rationale}</small></div><button className="secondaryButton" type="button" onClick={() => onUseSuggestion(suggestion)}>Use as draft</button></div> : suggestionResult.suggestion_error && <div className="auditSuggestionError"><AlertCircle size={15} /> {suggestionResult.suggestion_error}</div>}
            <div className="auditCandidateList">{suggestionResult.candidates.length ? suggestionResult.candidates.map((candidate) => <div className="auditCandidate" key={candidate.message_id}><button type="button" onClick={() => onOpenEvidence(candidate.conversation_id, candidate.message_index)}><span><strong>{candidate.title}</strong><small>{candidate.source} / message #{candidate.message_index} / {candidate.match_kind}</small></span><ChevronRight size={15} /></button><p>{candidate.excerpt}</p><div><button type="button" onClick={() => onAttach(candidate, "supports")}>Supports</button><button type="button" onClick={() => onAttach(candidate, "contradicts")}>Contradicts</button><button type="button" onClick={() => onAttach(candidate, "context")}>Context</button></div></div>) : <div className="auditNoCandidates">No matching evidence was found. A missing result is not proof that the memory is wrong.</div>}</div>
          </div>
        )}
      </div>
      <div className="auditNotesGrid">
        <label>Redacted research example<textarea value={item.redacted_example} onChange={(event) => onChange({ redacted_example: event.target.value })} placeholder="Describe the pattern without personal details. This field is included in exports." rows={3} /></label>
        <label>Private reviewer notes<textarea value={item.notes} onChange={(event) => onChange({ notes: event.target.value })} placeholder="Local only. Never included in redacted exports." rows={3} /></label>
      </div>
      <footer className="auditItemFooter"><span>{isAuditItemReviewed(item) ? "Ready to save as a human decision." : "Complete the three decision fields to save."}</span><button className="primaryButton" type="button" onClick={onSave} disabled={!isAuditItemReviewed(item) || busy}>{busy ? <Loader2 className="spin" size={15} /> : <Save size={15} />} Save human review</button></footer>
    </article>
  );
}

async function saveAuditItem(sessionId: string, item: AuditItem) {
  return auditApi<AuditSession>(`/api/memory-audits/${sessionId}/items/${item.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      statement_kind: item.user_statement_kind,
      evidence_verdict: item.user_evidence_verdict,
      issue_tags: item.user_issue_tags,
      severity: item.user_severity,
      redacted_example: item.redacted_example,
      notes: item.notes,
      evidence: item.evidence.map((evidence) => ({
        conversation_id: evidence.conversation_id,
        message_id: evidence.message_id,
        message_index: evidence.message_index,
        relationship: evidence.relationship
      }))
    })
  });
}

async function auditApi<T = unknown>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : data;
    throw new Error(typeof detail === "string" ? detail : "Request failed.");
  }
  return data as T;
}

function auditMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function sourceLabel(source: string) {
  return source === "chatgpt" ? "ChatGPT" : "Claude";
}

function formatChoice(value: string) {
  return value ? value.replaceAll("_", " ") : "unclear";
}

function formatAuditDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}
