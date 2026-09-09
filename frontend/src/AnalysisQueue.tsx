import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock3, Loader2, Pause, Play, RefreshCw } from "lucide-react";
import "./analysisQueue.css";

type Policy = {
  enabled: boolean;
  daily_attempt_limit: number;
  daily_token_limit: number;
  analysis_mode: string;
  personal_instructions: string;
};
type PolicyState = {
  policy: Policy;
  provider_connected: boolean;
  model: string | null;
  usage: {
    reserved_attempts: number;
    reserved_tokens: number;
    remaining_attempts: number;
    remaining_tokens: number;
    explanation: string;
  };
};
export type AnalysisJob = {
  id: string;
  source_record_id: string;
  source_title: string;
  status: string;
  last_error_code: string | null;
  last_error_summary: string | null;
  next_retry_at: string | null;
  attempt_count: number;
  estimated_input_tokens?: number | null;
  coverage?: {
    total_segments: number; completed_segments: number;
    covered_characters: number; total_characters: number; complete: boolean;
  } | null;
};

export function analysisJobLabel(job: AnalysisJob, connected: boolean, enabled: boolean) {
  if (job.status === "complete") return "Ready to read";
  if (job.status === "running") return "Analyzing";
  if (job.status === "superseded") return "Replaced by a newer save";
  if (job.status === "failed") return "Needs a retry";
  if (job.last_error_code === "analysis_limit") return "Waiting for allowance";
  if (job.last_error_code === "analysis_partial") return "Progress saved · more analysis queued";
  if (!enabled) return "Analysis paused";
  if (!connected) return "Saved · waiting for an AI connection";
  return "Saved · queued";
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "Could not update analysis.");
  }
  return response.json() as Promise<T>;
}

export function notifyContextChanged() {
  window.dispatchEvent(new Event("reweave:context-changed"));
}

export async function queueConversation(conversationId: string) {
  await request("/api/context/analysis/queue", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_ids: [conversationId], reanalyze: true })
  });
  notifyContextChanged();
}

export function AnalysisQueue({ onOpenSource, onOpenSettings }: {
  onOpenSource: (id: string) => void;
  onOpenSettings?: () => void;
}) {
  const [state, setState] = useState<PolicyState | null>(null);
  const [jobs, setJobs] = useState<AnalysisJob[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState("");
  const [limit, setLimit] = useState(20);
  const [draft, setDraft] = useState<Policy | null>(null);
  const [prompt, setPrompt] = useState<{version: string; system_prompt: string} | null>(null);
  const [restartRequired, setRestartRequired] = useState(false);
  const restartRef = useRef(false);
  const signature = useRef("");

  useEffect(() => {
    let disposed = false;
    let loading = false;
    const controller = new AbortController();
    const load = async () => {
      if (loading || restartRef.current) return;
      loading = true;
      try {
        const [policy, queue] = await Promise.all([
          request<PolicyState>("/api/context/analysis/policy", { signal: controller.signal }),
          request<{ results: AnalysisJob[] }>(
            `/api/context/analysis/queue?limit=${limit}${filter ? `&status=${filter}` : ""}`,
            { signal: controller.signal }
          )
        ]);
        if (disposed) return;
        setState(policy);
        setJobs(queue.results);
        setError("");
        const next = queue.results.map((job) => `${job.id}:${job.status}`).join("|");
        if (signature.current && signature.current !== next) notifyContextChanged();
        signature.current = next;
      } catch (cause) {
        if (!disposed && !restartRef.current) setError(cause instanceof Error ? cause.message : "Analysis is unavailable.");
      } finally { loading = false; }
    };
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    const refresh = () => void load();
    const requireRestart = () => {
      restartRef.current = true;
      setRestartRequired(true);
      controller.abort();
      window.clearInterval(timer);
    };
    window.addEventListener("reweave:context-changed", refresh);
    window.addEventListener("reweave:restart-required", requireRestart);
    return () => {
      disposed = true;
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("reweave:context-changed", refresh);
      window.removeEventListener("reweave:restart-required", requireRestart);
    };
  }, [revision, filter, limit]);

  async function savePolicy(policy: Policy) {
    setBusy(true); setError("");
    try {
      const result = await request<PolicyState>("/api/context/analysis/policy", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policy)
      });
      setState(result); setDraft(null); setPrompt(null); setRevision((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save analysis settings.");
    } finally { setBusy(false); }
  }

  async function retry(job: AnalysisJob) {
    setBusy(true); setError("");
    try {
      await request(`/api/context/analysis/queue/${encodeURIComponent(job.id)}/retry`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}"
      });
      setRevision((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not retry this conversation.");
    } finally { setBusy(false); }
  }

  if (restartRequired) return <section className="analysisPanel" aria-label="Analysis activity">
    <h2>Library restored</h2><p role="status">Restart Reweave to finish recovery before continuing analysis.</p>
  </section>;

  return <section className="analysisPanel" aria-label="Analysis activity">
    <div className="analysisPanelHeading">
      <div><span className="sectionLabel">Quiet background work</span><h2>From sources to context</h2></div>
      {state && <button className="secondaryButton" type="button" disabled={busy}
        onClick={() => void savePolicy({ ...state.policy, enabled: !state.policy.enabled })}>
        {state.policy.enabled ? <Pause size={16} /> : <Play size={16} />}
        {state.policy.enabled ? "Pause analysis" : "Resume analysis"}
      </button>}
    </div>
    {error && <p className="analysisError" role="alert">{error}
      <button type="button" className="secondaryButton" onClick={() => setRevision((n) => n + 1)}>
        <RefreshCw size={16} /> Refresh
      </button>
    </p>}
    {!state && !error && <p role="status">Loading analysis activity…</p>}
    {state && <>
      <p className="analysisSummary">
        {!state.provider_connected ? "Your conversations stay saved and searchable. Connect your AI provider to analyze them."
          : !state.policy.enabled ? "Analysis is paused. Sources and queued work remain on this device."
            : state.usage.remaining_attempts === 0 || state.usage.remaining_tokens === 0
              ? "Today's analysis allowance is used. Pending sources remain safely queued."
              : `Newly saved conversations are analyzed with ${state.model || "your saved model"} after 30 quiet seconds or when three sources are queued.`}
      </p>
      {!state.provider_connected && onOpenSettings && <button className="secondaryButton" type="button"
        onClick={onOpenSettings}>Connect an AI provider</button>}
      <details className="analysisSettings" onToggle={(event) => {
        if (event.currentTarget.open && !draft) setDraft(state.policy);
      }}>
        <summary>Analysis settings · {state.usage.remaining_attempts} of {state.policy.daily_attempt_limit} daily provider attempts available</summary>
        <p>{state.usage.explanation}</p>
        <p>Long conversations are analyzed in complete, resumable parts. A source may also use one bounded call to verify relationships with existing Context. All calls share this allowance.</p>
        <p>{state.usage.reserved_tokens.toLocaleString()} of {state.policy.daily_token_limit.toLocaleString()} token allowance reserved. Provider prices vary; this is not a spending guarantee.</p>
        <form onSubmit={(event) => { event.preventDefault(); if (draft) void savePolicy(draft); }}>
          <div className="analysisSettingsFields">
            <label>Daily provider attempts<input type="number" min={1} max={1000} required
              value={draft?.daily_attempt_limit ?? state.policy.daily_attempt_limit}
              onChange={(event) => setDraft({ ...(draft || state.policy), daily_attempt_limit: Number(event.target.value) })} /></label>
            <label>Daily token allowance<input type="number" min={1000} max={10000000} required
              value={draft?.daily_token_limit ?? state.policy.daily_token_limit}
              onChange={(event) => setDraft({ ...(draft || state.policy), daily_token_limit: Number(event.target.value) })} /></label>
            <label>Analysis emphasis<select value={draft?.analysis_mode ?? state.policy.analysis_mode}
              onChange={(event) => setDraft({ ...(draft || state.policy), analysis_mode: event.target.value })}>
              <option value="auto">Auto</option><option value="project">Project</option>
              <option value="learning">Learning</option><option value="research_writing">Research / Writing</option>
              <option value="context_handoff">Context Handoff</option>
            </select></label>
          </div>
          <label>Additional analysis instructions<textarea rows={3} maxLength={4000}
            value={draft?.personal_instructions ?? state.policy.personal_instructions}
            onChange={(event) => setDraft({ ...(draft || state.policy), personal_instructions: event.target.value })} /></label>
          <p>Applies to future analysis. Evidence, scope, and privacy rules always take priority.</p>
          <button className="primaryButton" type="submit" disabled={busy}>Save analysis settings</button>
        </form>
      </details>
      <details className="analysisSettings" onToggle={(event) => {
        if (event.currentTarget.open && !prompt) {
          void request<{version: string; system_prompt: string}>("/api/context/analysis/prompt")
            .then(setPrompt).catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load the active prompt."));
        }
      }}>
        <summary>View the active analysis instructions</summary>
        <p>These saved instructions apply to future analysis. Your original conversation is supplied separately as untrusted evidence.</p>
        {prompt ? <><p>Prompt version: {prompt.version}</p><pre style={{whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 360, overflow: "auto"}}>{prompt.system_prompt}</pre></> : <p>Loading saved instructions…</p>}
      </details>
      <details className="analysisRecent" open={jobs.some((job) => job.status === "failed")}>
        <summary>Recent analysis {jobs.length > 0 ? `(${jobs.length}${jobs.length === limit ? "+" : ""})` : ""}</summary>
        <label className="analysisStatusFilter">Status<select value={filter} onChange={(event) => {
          setFilter(event.target.value); setLimit(20);
        }}><option value="">All</option><option value="pending">Queued</option><option value="running">Analyzing</option>
          <option value="failed">Needs a retry</option><option value="complete">Ready to read</option></select></label>
        {jobs.length === 0 && <p>{filter ? "No analysis matches this status." : "Import an export or explicitly Save a conversation with the extension to begin."}</p>}
        <ul className="analysisJobs">{jobs.map((job) => <li key={job.id}>
          {job.status === "running" ? <Loader2 size={18} className="spin" /> : job.status === "complete"
            ? <CheckCircle2 size={18} /> : <Clock3 size={18} />}
          <div><button className="analysisSourceLink" type="button" onClick={() => onOpenSource(job.source_record_id)}>{job.source_title}</button>
            <p>{analysisJobLabel(job, state.provider_connected, state.policy.enabled)}</p>
            {job.coverage && <p>{job.coverage.completed_segments} of {job.coverage.total_segments} source parts saved · {job.coverage.total_characters ? Math.floor(100 * job.coverage.covered_characters / job.coverage.total_characters) : 100}% read{!job.coverage.complete && " · incomplete"}</p>}
            {job.estimated_input_tokens != null && <small>Estimated input envelope: {job.estimated_input_tokens.toLocaleString()} tokens, including synthesis and relationship allowances. Actual reservations also include maximum output and possible key attempts.</small>}
            {job.last_error_summary && <p>{job.last_error_summary}</p>}
            {job.next_retry_at && <small>Next automatic attempt: {new Date(job.next_retry_at).toLocaleString()}</small>}
          </div>
          {["failed", "pending"].includes(job.status) && state.provider_connected && state.policy.enabled &&
            <button type="button" className="secondaryButton" disabled={busy} onClick={() => void retry(job)}>
              <RefreshCw size={15} /> {job.status === "failed" ? "Retry" : "Analyze now"}
            </button>}
        </li>)}</ul>
        {jobs.length === limit && limit < 1000 && <button className="secondaryButton" type="button"
          onClick={() => setLimit((value) => Math.min(1000, value + 50))}>Show more activity</button>}
      </details>
    </>}
  </section>;
}
