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
  linkifyCitationReferences,
  MarkdownContent,
  parseCitationHref,
  safeMarkdownUrl
} from "./MarkdownContent";

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

  it("creates a safe Markdown download filename", () => {
    expect(safeFilename('Insights: AI / "careers"')).toBe("Insights- AI - -careers-");
  });

});
