import React from "react";
import { createRoot } from "react-dom/client";
import { Workspace } from "./Workspace";
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

export type LLMProfile = {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  default_model: string;
  custom_models: string[];
  keys: Array<{
    id: string;
    label: string;
    enabled: boolean;
    priority: number;
    has_secret: boolean;
  }>;
  connected: boolean;
  masked_key: string;
};

type ModelLoadStatus =
  | "idle"
  | "loading"
  | "success"
  | "empty"
  | "invalid-key"
  | "permission"
  | "rate-limit"
  | "network"
  | "error";

const customModelValue = "__custom__";

if (typeof document !== "undefined") {
  const rootElement = document.getElementById("root");
  if (rootElement) {
    createRoot(rootElement).render(
      <React.StrictMode>
        <Workspace />
      </React.StrictMode>
    );
  }
}

export function safeFilename(value: string) {
  const filename = value.trim().replace(/[<>:"/\\|?*\u0000-\u001f]+/g, "-");
  return filename || "reweave-insight";
}

export function isModelUnavailable(
  model: string,
  status: ModelLoadStatus,
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

export function modelErrorStatus(status: number): ModelLoadStatus {
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
