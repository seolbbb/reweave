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
import { Workspace } from "./Workspace";

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

  it("starts in the dedicated search workspace with shared primary navigation", () => {
    const html = renderToStaticMarkup(createElement(Workspace));

    expect(html).toContain("Search your archive");
    expect(html).toContain("Sources for insight");
    expect(html).toContain("Reports");
    expect(html).toContain("Import");
    expect(html).toContain("Settings");
    expect(html).not.toContain("Report outline");
  });
});
