import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, expect, it, vi } from "vitest";
import { ContextSearch, SourceContextLinks } from "./ContextSearch";

let root: Root | undefined;
afterEach(async () => { if (root) await act(async () => root?.unmount()); root = undefined; vi.unstubAllGlobals(); });

function surface() {
  const parsed = parseHTML("<html><body><main></main></body></html>");
  vi.stubGlobal("document", parsed.document);
  vi.stubGlobal("window", parsed.window);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  root = createRoot(parsed.document.querySelector("main") as unknown as HTMLElement);
  return parsed.document;
}
function searchFetch(handler: (...args: unknown[]) => unknown) {
  return vi.fn((...args: unknown[]) => String(args[0]).includes("/spaces")
    ? Promise.resolve({ok: true, json: async () => ({results: []})}) : handler(...args));
}
function response(summary: string, id = "item-one") {
  return {ok: true, json: async () => ({hits: [{item_id: id, summary, item_type: "value", epistemic_kind: "inferred", confidence: 0.6, sensitivity: "sensitive", reasons: ["Exact identifier"]}], diagnostics: {semantic_available: false, fallback_used: true, strategy: "global_keyword"}})};
}

it("keeps uncertain sensitive local results inspectable without granting external use", async () => {
  const document = surface(); const open = vi.fn();
  vi.stubGlobal("fetch", searchFetch(vi.fn().mockResolvedValue(response("A local inferred value"))));
  await act(async () => root?.render(<ContextSearch query="value" onOpenItem={open}/>));
  expect(document.body.textContent).toContain("Sensitive: kept local");
  expect(document.body.textContent).toContain("inferred");
  expect(document.body.textContent).toContain("60% confidence");
  await act(async () => (document.querySelector(".contextSearchItem") as unknown as HTMLElement).click());
  expect(open).toHaveBeenCalledWith("item-one");
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(document.body.textContent).not.toContain("Insert");
});

it("ignores a previous query response after a newer query has completed", async () => {
  const document = surface(); let resolveOld!: (value: ReturnType<typeof response>) => void;
  vi.stubGlobal("fetch", searchFetch(vi.fn().mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; })).mockResolvedValueOnce(response("Current result", "new"))));
  await act(async () => root?.render(<ContextSearch query="old" onOpenItem={vi.fn()}/>));
  await act(async () => root?.render(<ContextSearch query="new" onOpenItem={vi.fn()}/>));
  await act(async () => resolveOld(response("Obsolete result", "old")));
  expect(document.body.textContent).toContain("Current result");
  expect(document.body.textContent).not.toContain("Obsolete result");
});

it("opens source-derived context without losing the original source on errors", async () => {
  const document = surface(); const open = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: true, json: async () => ({results: [{id: "derived", canonical_text: "Source-backed decision", epistemic_kind: "observed"}]})}));
  await act(async () => root?.render(<SourceContextLinks conversationId="source" onOpenItem={open}/>));
  await act(async () => (document.querySelector("button") as unknown as HTMLElement).click());
  expect(open).toHaveBeenCalledWith("derived");
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok: false}));
  await act(async () => root?.render(<SourceContextLinks conversationId="unavailable" onOpenItem={open}/>));
  expect(document.body.textContent).toContain("The source remains available below");
});
