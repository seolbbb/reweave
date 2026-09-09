import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContextReview, type ReviewRow } from "./ContextReview";

const row: ReviewRow = {
  item: { id: "private-item", canonical_text: "A private inferred preference.", item_type: "preference", epistemic_kind: "inferred",
    confidence: 0.4, sensitivity: "sensitive", status: "active", current_version: 1, created_at: "2026-09-09T00:00:00Z",
    updated_at: "2026-09-09T00:00:00Z", last_confirmed_at: null, stale_at: null, scopes: [], evidence: [], versions: [], links: [] },
  reasons: [{ code: "sensitive_inference", label: "Sensitive inference", detail: "Check the source before relying on this inference." }],
  related_items: [], effective_confidence: 0.4, review_key: "a".repeat(64), state: "open", history: [],
};
const results = (rows: ReviewRow[] = [row]) => ({ results: rows, total: rows.length, open_count: rows.length, reason_counts: {} });
function response(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } }); }
const surfaces: Array<{ root: Root; restore: () => void }> = [];
async function render(content: ReactNode) {
  const parsed = parseHTML("<html><body><div id='root'></div></body></html>");
  const replacements = { document: parsed.document, window: parsed.window, HTMLElement: parsed.window.HTMLElement,
    Event: parsed.window.Event, IS_REACT_ACT_ENVIRONMENT: true };
  const previous = new Map(Object.keys(replacements).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(replacements)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const root = createRoot(parsed.document.getElementById("root") as unknown as HTMLElement);
  surfaces.push({ root, restore: () => { for (const [key, descriptor] of previous) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete (globalThis as Record<string, unknown>)[key];
  } } });
  await act(async () => root.render(content));
  return parsed.document as unknown as Document;
}
function button(document: Document, text: string) {
  const found = [...document.querySelectorAll("button")].find(node => node.textContent === text);
  if (!found) throw new Error(`Missing button: ${text}`);
  return found;
}
async function click(document: Document, text: string) { await act(async () => button(document, text).click()); }
afterEach(async () => { for (const surface of surfaces.splice(0).reverse()) { await act(async () => surface.root.unmount()); surface.restore(); } vi.unstubAllGlobals(); });

describe("Exception Review", () => {
  it("shows a calm empty state and keeps deletion separately gated", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(results([]))));
    const document = await render(<ContextReview onOpenItem={() => {}} />);
    expect(document.body.textContent).toContain("No exceptions need your attention");
    expect(button(document, "Delete Library").disabled).toBe(true);
    expect(document.querySelector(".contextReviewDanger")?.hasAttribute("open")).toBe(false);
    expect(document.body.textContent).toContain("Raw source conversations, provider credentials");
  });

  it("opens correction and dismisses exactly the viewed version without permission fields", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(results())).mockResolvedValueOnce(response(row)).mockResolvedValueOnce(response(results([])));
    vi.stubGlobal("fetch", fetchMock);
    const open = vi.fn();
    const document = await render(<ContextReview onOpenItem={open} />);
    expect(document.body.textContent).toContain(row.reasons[0].detail);
    await click(document, "Read evidence or correct");
    expect(open).toHaveBeenCalledWith(row.item.id);
    await click(document, "Hide this version");
    const [path, options] = fetchMock.mock.calls[1];
    expect(path).toBe(`/api/context/review/items/${row.item.id}/dismiss`);
    expect(JSON.parse(options.body)).toEqual({ expected_version: 1, review_key: row.review_key });
    expect(document.body.textContent).toContain("Its data and permissions are unchanged");
  });

  it("shows stale conflicts without losing the current evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(results())).mockResolvedValueOnce(response({ detail: "This item changed. Refresh Review." }, 409)));
    const document = await render(<ContextReview onOpenItem={() => {}} />);
    await click(document, "Confirm accuracy");
    expect(document.querySelector('[role="alert"]')?.textContent).toContain("This item changed");
    expect(document.body.textContent).toContain(row.item.canonical_text);
    expect(button(document, "Confirm accuracy").disabled).toBe(false);
  });

  it("resolves a linked pair only after an explicit version-bound choice", async () => {
    const related = { id: "other", version: 3, canonical_text: "A different decision.", relationship: "contradicts" };
    const fetchMock = vi.fn().mockResolvedValueOnce(response(results([{ ...row, related_items: [related] }]))).mockResolvedValueOnce(response(row)).mockResolvedValueOnce(response(results([])));
    vi.stubGlobal("fetch", fetchMock);
    const document = await render(<ContextReview onOpenItem={() => {}} />);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await click(document, "Keep both as valid");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({ expected_version: 1, related_item_id: "other", related_version: 3, resolution: "keep_both" });
    expect(document.body.textContent).toContain("Both items and their versions are preserved");
  });

  it("requires the exact delete phrase and reports committed restart without retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response(results())).mockResolvedValueOnce(response({ deleted: { items: 1, briefs: 2 }, restart_required: true, notice: "Restart Reweave before continuing." }));
    vi.stubGlobal("fetch", fetchMock);
    const deleted = vi.fn();
    const document = await render(<ContextReview onOpenItem={() => {}} onLibraryDeleted={deleted} />);
    const input = document.querySelector("#delete-derived-library") as HTMLInputElement;
    await act(async () => { input.value = "delete library"; input.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(button(document, "Delete Library").disabled).toBe(true);
    await act(async () => { input.value = "DELETE LIBRARY"; input.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(button(document, "Delete Library").disabled).toBe(false);
    await click(document, "Delete Library");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ confirmation: "DELETE LIBRARY" });
    expect(document.body.textContent).toContain("1 items and 2 briefs deleted");
    expect(document.body.textContent).toContain("Restart Reweave before continuing");
    expect(button(document, "Delete Library").disabled).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(deleted).not.toHaveBeenCalled();
  });
});
