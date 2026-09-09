import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  chooseAvailableModel,
  isModelUnavailable,
  modelErrorStatus,
  safeFilename,
  selectConversation,
  type SearchResult,
  toggleSelectedConversation
} from "./main";
import {
  compactMarkdownSource,
  extractMarkdownHeadings,
  linkifyCitationReferences,
  MarkdownContent,
  parseCitationHref,
  safeMarkdownUrl
} from "./MarkdownContent";
import { HighlightedText, extractHighlightTerms } from "./textHighlight";
import { OnboardingWizard } from "./ArchiveManagement";
import { MemoryAuditView } from "./MemoryAudit";
import { isAuditItemReviewed, manualClaimsFromText } from "./memoryAuditHelpers";
import {
  ONBOARDING_STORAGE_KEY,
  rememberOnboardingComplete,
  shouldOpenOnboarding,
  Workspace
} from "./Workspace";
import {
  buildContextScopeGroups,
  contextBriefEntries,
  contextHomeItems,
  ContextItemDetail,
  ContextWorkspace,
  evidenceOpenTarget,
  type ContextEvidence,
  type ContextItem
} from "./ContextWorkspace";

const result: SearchResult = {
  id: "conversation-1",
  source: "chatgpt",
  title: "Photosynthesis",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: null,
  raw_message_count: 2,
  match_count: 1,
  excerpts: []
};

const secondResult: SearchResult = {
  ...result,
  id: "conversation-2",
  title: "Mitochondria"
};

describe("frontend state helpers", () => {
  it("keeps selected conversations from multiple searches without duplicates", () => {
    const selectedFromFirstSearch = selectConversation({}, result);
    const selectedFromSecondSearch = selectConversation(selectedFromFirstSearch, secondResult);
    const selectedAgain = selectConversation(selectedFromSecondSearch, result);

    expect(Object.values(selectedAgain)).toEqual([result, secondResult]);
    expect(toggleSelectedConversation(selectedAgain, result)).toEqual({
      [secondResult.id]: secondResult
    });
  });

  it("marks a selected model unavailable only after a successful provider refresh", () => {
    expect(isModelUnavailable("old-model", "success", ["current-model"])).toBe(true);
    expect(isModelUnavailable("current-model", "success", ["current-model"])).toBe(false);
    expect(isModelUnavailable("old-model", "error", [])).toBe(false);
  });

  it("preserves the current model and otherwise chooses a sensible provider model", () => {
    const models = ["gpt-audio-preview", "gpt-current-mini", "gpt-premium"];

    expect(chooseAvailableModel("gpt-premium", "", models, "openai")).toBe("gpt-premium");
    expect(chooseAvailableModel("", "gpt-premium", models, "openai")).toBe("gpt-premium");
    expect(chooseAvailableModel("", "removed-model", models, "openai")).toBe("gpt-current-mini");
  });

  it("maps provider failures to useful connection states", () => {
    expect(modelErrorStatus(401)).toBe("invalid-key");
    expect(modelErrorStatus(403)).toBe("permission");
    expect(modelErrorStatus(429)).toBe("rate-limit");
    expect(modelErrorStatus(502)).toBe("network");
  });

  it("blocks dangerous Markdown links while preserving safe links", () => {
    expect(safeMarkdownUrl("javascript:alert(1)")).toBe("");
    expect(safeMarkdownUrl("data:text/html,bad")).toBe("");
    expect(safeMarkdownUrl("//example.com/unsafe-relative")).toBe("");
    expect(safeMarkdownUrl("https://example.com")).toBe("https://example.com");
    expect(safeMarkdownUrl("#source:conversation-1:3")).toBe("#source:conversation-1:3");
  });

  it("sanitizes rendered Markdown HTML and dangerous links", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        markdown: '[safe](https://example.com)\n\n<script>alert("bad")</script>\n\n[bad](javascript:alert(1))'
      })
    );

    expect(html).not.toContain("<script");
    expect(html).not.toContain("javascript:");
    expect(html).toContain('href="https://example.com"');
  });

  it("turns source references into citation links", () => {
    const linked = linkifyCitationReferences("Claim [conversation-1#m3].");

    expect(linked).toContain("(#source:conversation-1:3)");
    expect(parseCitationHref("#source:conversation-1:3")).toEqual({
      conversationId: "conversation-1",
      messageIndex: 3
    });
  });

  it("removes orphan Markdown markers from compact excerpts", () => {
    expect(compactMarkdownSource("partial **bold marker --- ### heading...")).toBe(
      "partial bold marker · heading..."
    );
    expect(compactMarkdownSource("complete **bold** marker")).toBe("complete **bold** marker");
    expect(compactMarkdownSource("matched **[AI]** term")).toBe("matched **\\[AI\\]** term");
  });

  it("strips leading Markdown headings from compact excerpts", () => {
    expect(compactMarkdownSource("## Computational Imaging\n\nBody text")).toBe(
      "Computational Imaging\n\nBody text"
    );
    expect(compactMarkdownSource("질문\n\n### 알고리즘")).toBe("질문\n알고리즘");
  });

  it("does not render compact excerpts with report heading elements", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        markdown: "## Computational Imaging\n\nMatched algorithm text.",
        compact: true
      })
    );

    expect(html).toContain("compactMarkdown");
    expect(html).not.toContain("<h2");
    expect(html).toContain("Computational Imaging");
  });

  it("renders conversation Markdown safely with the conversation style path", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        markdown: '# Computational Imaging\n\n<script>alert("bad")</script>\n\n[bad](javascript:alert(1))',
        variant: "conversation"
      })
    );

    expect(html).toContain("conversationMarkdown");
    expect(html).toContain("<h1>Computational Imaging</h1>");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain('id="computational-imaging"');
  });

  it("highlights English and Korean search terms without injecting HTML", () => {
    const html = renderToStaticMarkup(
      createElement(HighlightedText, {
        text: 'AI 한국 <script>alert("bad")</script>',
        terms: extractHighlightTerms("한국 ai")
      })
    );

    expect(html).toContain('<mark class="queryHighlight">AI</mark>');
    expect(html).toContain('<mark class="queryHighlight">한국</mark>');
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("highlights compact Markdown excerpt text safely", () => {
    const html = renderToStaticMarkup(
      createElement(MarkdownContent, {
        markdown: 'Matched **AI** and 한국 terms.\n\n<script>alert("bad")</script>',
        compact: true,
        highlightTerms: extractHighlightTerms("한국 ai")
      })
    );

    expect(html).toContain('<mark class="queryHighlight">AI</mark>');
    expect(html).toContain('<mark class="queryHighlight">한국</mark>');
    expect(html).not.toContain("<script>");
  });

  it("extracts report outline items with stable matching heading ids", () => {
    expect(
      extractMarkdownHeadings("# Overview\n\n## 핵심 개념\n\n## Overview\n\n#### Hidden detail")
    ).toEqual([
      { id: "overview", level: 1, text: "Overview" },
      { id: "핵심-개념", level: 2, text: "핵심 개념" },
      { id: "overview-2", level: 2, text: "Overview" }
    ]);
  });

  it("creates a safe Markdown download filename", () => {
    expect(safeFilename('Insights: AI / "careers"')).toBe("Insights- AI - -careers-");
  });

  it("creates manual audit claims without storing the original pasted block", () => {
    expect(manualClaimsFromText("- First memory\n2. Second memory\n\n* Third memory")).toEqual([
      { claim_text: "First memory", search_queries: ["First memory"] },
      { claim_text: "Second memory", search_queries: ["Second memory"] },
      { claim_text: "Third memory", search_queries: ["Third memory"] }
    ]);
    expect(
      isAuditItemReviewed({
        user_statement_kind: "direct_statement",
        user_evidence_verdict: "supported",
        user_severity: "low"
      })
    ).toBe(true);
  });

  it("renders the local-first memory audit start flow", () => {
    const html = renderToStaticMarkup(
      createElement(MemoryAuditView, {
        modelReady: false,
        llmSettings: null,
        onOpenEvidence: () => undefined,
        onOpenSettings: () => undefined
      })
    );

    expect(html).toContain("Audit what an AI remembers about you");
    expect(html).toContain("is never stored by Reweave");
    expect(html).toContain("Use one item per line");
  });

  it("starts in Context Home with shared primary navigation", () => {
    const html = renderToStaticMarkup(createElement(Workspace));

    expect(html).toContain("Context Home");
    expect(html).toContain("Gathering your Context Library");
    expect(html).toContain("Context");
    expect(html).toContain("Library");
    expect(html).toContain("Explore");
    expect(html).toContain("Sources");
    expect(html).toContain('role="search"');
    expect(html).not.toContain(">Audit<");
    expect(html).not.toContain(">Reports<");
    expect(html).not.toContain("Ask archive");
    expect(html).toContain("Import");
    expect(html).toContain("Settings");
    expect(html).not.toContain("Report outline");
  });

  it("renders the selected destination without duplicate tab navigation", () => {
    const html = renderToStaticMarkup(
      createElement(ContextWorkspace, {
        onOpenLibrary: () => undefined,
        onOpenEvidence: async () => true
      })
    );

    expect(html).not.toContain('role="tablist"');
    expect(html).toContain("Context Home");
    expect(html).toContain("Refresh Context Library");
    expect(html).toContain("Loading source-grounded briefs and items from this device");
  });

  it("keeps one linked Context Item discoverable in each of its scopes", () => {
    const item: ContextItem = {
      id: "context-1",
      canonical_text: "Use relationship labels for links.",
      item_type: "decision",
      epistemic_kind: "observed",
      confidence: 0.94,
      sensitivity: "normal",
      status: "active",
      current_version: 1,
      created_at: "2026-07-21T00:00:00Z",
      updated_at: "2026-07-21T00:00:00Z",
      last_confirmed_at: null,
      stale_at: null,
      scopes: [
        { scope_type: "work", scope_key: "", confidence: 0.94, created_at: "2026-07-21T00:00:00Z" },
        { scope_type: "project", scope_key: "Reweave", confidence: 0.94, created_at: "2026-07-21T00:00:00Z" }
      ],
      evidence: [],
      versions: [],
      links: []
    };
    const groups = buildContextScopeGroups([item]);

    expect(groups.find((group) => group.key === "work")?.items).toEqual([item]);
    expect(groups.find((group) => group.key === "project:Reweave")?.items).toEqual([item]);
    expect(contextHomeItems([item], ["decision"])).toEqual([item]);
    expect(groups.find((group) => group.key === "core_self")?.items).toEqual([]);
  });

  it("keeps Brief-only decisions visible when extraction creates no Context Items", () => {
    const entries = contextBriefEntries([
      {
        id: "brief-1",
        source_conversation_id: "conversation-1",
        source_record_id: "conversation-1",
        source_provider: "chatgpt",
        source_title: "Reweave planning",
        source_created_at: "2026-07-21T00:00:00Z",
        main_subject: "Context navigation",
        user_goal: "Plan the first Context view.",
        important_outcomes: [],
        decisions: ["Use one linked model for Home and Explorer."],
        lessons: [],
        unresolved_questions: [],
        actions: [],
        analysis_mode: "project",
        analysis_status: "complete",
        created_at: "2026-07-21T00:00:00Z",
        updated_at: "2026-07-21T00:00:00Z",
        context_item_ids: [],
        item_count: 0
      }
    ], "decisions");

    expect(entries).toEqual([{
      id: "brief-1:decisions:0",
      text: "Use one linked model for Home and Explorer.",
      sourceTitle: "Reweave planning"
    }]);
  });

  it("opens live Context evidence while keeping removed-source snapshots readable", () => {
    const availableEvidence: ContextEvidence = {
      id: "evidence-live",
      source_conversation_id: "conversation-1",
      source_message_id: "message-3",
      source_record_id: "conversation-1",
      source_external_id: "external-1",
      source_message_record_id: "message-3",
      source_provider: "chatgpt",
      source_title: "Reweave planning",
      source_message_index: 3,
      source_role: "user",
      source_timestamp: null,
      excerpt: "Use one linked model for every Context view.",
      relationship: "supports",
      source_available: true,
      created_at: "2026-07-21T00:00:00Z"
    };
    const retainedEvidence: ContextEvidence = {
      ...availableEvidence,
      id: "evidence-retained",
      source_conversation_id: null,
      source_message_id: null,
      source_available: false,
      excerpt: "Keep a compact explanation after the source is removed."
    };

    expect(evidenceOpenTarget(availableEvidence)).toEqual({
      conversationId: "conversation-1",
      messageIndex: 3
    });
    expect(evidenceOpenTarget(retainedEvidence)).toBeNull();

    const html = renderToStaticMarkup(
      createElement(ContextItemDetail, {
        item: {
          id: "context-evidence",
          canonical_text: "Context stays linked to inspectable evidence.",
          item_type: "insight",
          epistemic_kind: "observed",
          confidence: 0.96,
          sensitivity: "normal",
          status: "active",
          current_version: 1,
          created_at: "2026-07-21T00:00:00Z",
          updated_at: "2026-07-21T00:00:00Z",
          last_confirmed_at: null,
          stale_at: null,
          scopes: [],
          evidence: [availableEvidence, retainedEvidence],
          versions: [],
          links: []
        },
        onOpenEvidence: async () => true
      })
    );

    expect(html).toContain("Open source message #3");
    expect(html).toContain("Original conversation unavailable");
    expect(html).toContain("Compact evidence is retained on this device");
    expect(html).toContain('aria-label="Open source message 3 in Reweave planning"');
  });

  it("renders a first-run wizard with optional backfill and explicit capture guidance", () => {
    const html = renderToStaticMarkup(
      createElement(OnboardingWizard, {
        open: true,
        busy: false,
        onImport: async () => null,
        onFinish: () => undefined
      })
    );

    expect(html).toContain("Start a Context Library on your terms");
    expect(html).toContain("Local by default");
    expect(html).toContain("Optional history");
    expect(html).toContain("without an API key");
    expect(html).toContain("Start without import");
  });

  it("keeps first-run completion durable without reopening for existing users", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      }
    };

    expect(shouldOpenOnboarding(0, storage)).toBe(true);
    expect(shouldOpenOnboarding(null, storage)).toBe(false);
    expect(shouldOpenOnboarding(4, storage)).toBe(false);

    rememberOnboardingComplete(storage);

    expect(values.get(ONBOARDING_STORAGE_KEY)).toBe("true");
    expect(shouldOpenOnboarding(0, storage)).toBe(false);
  });
});
