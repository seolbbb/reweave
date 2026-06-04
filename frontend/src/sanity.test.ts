import { describe, expect, it } from "vitest";
import {
  chooseAvailableModel,
  isModelUnavailable,
  modelErrorStatus,
  selectConversation,
  type SearchResult,
  toggleSelectedConversation
} from "./main";

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
});
