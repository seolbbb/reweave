import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ContextManagement,
  correctionDraft,
  correctionPatch,
} from "./ContextManagement";
import { ContextItemDetail, type ContextItem } from "./ContextWorkspace";

const item: ContextItem = {
  id: "context-one",
  canonical_text: "Keep the current decision.",
  item_type: "decision",
  epistemic_kind: "observed",
  confidence: 0.9,
  sensitivity: "normal",
  status: "active",
  current_version: 2,
  created_at: "2026-09-09T12:00:00Z",
  updated_at: "2026-09-09T12:00:00Z",
  last_confirmed_at: null,
  stale_at: null,
  scopes: [
    {
      scope_type: "work",
      scope_key: "",
      confidence: 0.9,
      created_at: "2026-09-09T12:00:00Z",
    },
  ],
  evidence: [],
  links: [],
  authority: "user",
  inference_rationale: "",
  versions: [
    {
      version: 1,
      canonical_text: "Earlier wording.",
      change_reason: "Initial extraction",
      created_at: "2026-09-08T12:00:00Z",
      item_type: "decision",
      epistemic_kind: "inferred",
      status: "active",
      sensitivity: "normal",
      scopes: [
        {
          scope_type: "project",
          scope_key: "Earlier project",
          confidence: 0.8,
        },
      ],
      evidence_ids: ["evidence-one"],
    },
    {
      version: 2,
      canonical_text: "Keep the current decision.",
      change_reason: "User clarification",
      created_at: "2026-09-09T12:00:00Z",
      scopes: [{ scope_type: "work", scope_key: "", confidence: 0.9 }],
    },
  ],
};

const surfaces: Array<{ root: Root; restore: () => void }> = [];
async function render(content: ReactNode) {
  const parsed = parseHTML("<html><body><div id='root'></div></body></html>");
  const replacements = {
    document: parsed.document,
    window: parsed.window,
    HTMLElement: parsed.window.HTMLElement,
    Event: parsed.window.Event,
    IS_REACT_ACT_ENVIRONMENT: true,
  };
  const previous = new Map(
    Object.keys(replacements).map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ]),
  );
  for (const [key, value] of Object.entries(replacements))
    Object.defineProperty(globalThis, key, {
      configurable: true,
      writable: true,
      value,
    });
  const root = createRoot(
    parsed.document.getElementById("root") as unknown as HTMLElement,
  );
  surfaces.push({
    root,
    restore: () => {
      for (const [key, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete (globalThis as Record<string, unknown>)[key];
      }
    },
  });
  await act(async () => {
    root.render(content);
  });
  return parsed.document as unknown as Document;
}
async function click(document: Document, text: string) {
  const button = Array.from(document.querySelectorAll("button")).find((entry) =>
    entry.textContent?.includes(text),
  );
  if (!button) throw new Error(`Missing button: ${text}`);
  await act(async () => button.click());
}
afterEach(async () => {
  for (const surface of surfaces.splice(0).reverse()) {
    await act(async () => surface.root.unmount());
    surface.restore();
  }
  vi.unstubAllGlobals();
});
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Context correction and history", () => {
  it("sends only edited fields with optimistic concurrency and leaves original evidence untouched", () => {
    const draft = correctionDraft(item);
    draft.canonical_text = "The corrected decision.";
    draft.change_reason = "  Clarify the intent  ";
    const patch = correctionPatch(item, draft, 5);
    expect(patch).toEqual({
      expected_version: 5,
      change_reason: "Clarify the intent",
      canonical_text: "The corrected decision.",
    });
    expect(patch).not.toHaveProperty("evidence");
    expect(patch).not.toHaveProperty("scopes");
    expect(patch).not.toHaveProperty("authority");
  });

  it("preserves explicit scope confidence and records inference rationale without inventing Core Self", () => {
    const draft = correctionDraft(item);
    draft.epistemic_kind = "inferred";
    draft.inference_rationale =
      "The quoted preference appears in two decisions.";
    draft.scopes.push({
      scope_type: "project",
      scope_key: "Writing",
      confidence: 0.85,
    });
    draft.change_reason = "Clarify where this applies";
    const patch = correctionPatch(item, draft, 2);
    expect(patch).toMatchObject({
      epistemic_kind: "inferred",
      inference_rationale: draft.inference_rationale,
      scopes: [
        { scope_type: "work", scope_key: "", confidence: 0.9 },
        { scope_type: "project", scope_key: "Writing", confidence: 0.85 },
      ],
    });
    expect(draft.scopes.some((scope) => scope.scope_type === "core_self")).toBe(
      false,
    );
  });

  it("shows recorded version text and spaces, restoring only after explicit confirmation", async () => {
    const updated = {
      ...item,
      current_version: 3,
      canonical_text: "Earlier wording.",
    };
    const fetchMock = vi.fn(async () => response(updated));
    vi.stubGlobal("fetch", fetchMock);
    const onUpdated = vi.fn();
    const document = await render(
      <ContextManagement item={item} onUpdated={onUpdated} />,
    );
    expect(document.body.textContent).toContain("Earlier wording.");
    expect(document.body.textContent).toContain("Earlier project");
    await click(document, "Restore version 1");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain(
      "Existing history stays available",
    );
    await click(document, "Confirm restore");
    expect(fetchMock).toHaveBeenCalledOnce();
    const [, request] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(JSON.parse(String(request.body))).toEqual({
      version: 1,
      expected_version: 2,
    });
    expect(onUpdated).toHaveBeenCalledWith(updated);
  });

  it("does not retry a conflicting restore and requires refreshing the saved item", async () => {
    const fetchMock = vi.fn(async () =>
      response({ detail: "Newer version exists" }, 409),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onUpdated = vi.fn();
    const document = await render(
      <ContextManagement item={item} onUpdated={onUpdated} />,
    );
    await click(document, "Restore version 1");
    await click(document, "Confirm restore");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onUpdated).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "This item changed before the restore",
    );
    expect(document.body.textContent).toContain("Refresh saved item");
  });

  it("marks a changed source without replacing its preserved evidence or inference with current source text", async () => {
    const inferred: ContextItem = {
      ...item,
      epistemic_kind: "inferred",
      inference_rationale:
        "The original decision suggests a preference for small steps.",
      evidence: [
        {
          id: "evidence-one",
          source_conversation_id: "source-one",
          source_message_id: "message-one",
          source_record_id: "source-one",
          source_external_id: null,
          source_message_record_id: "message-one",
          source_provider: "claude",
          source_title: "Original source",
          source_message_index: 2,
          source_role: "user",
          source_timestamp: null,
          excerpt: "Retained original quotation.",
          relationship: "supports",
          source_available: true,
          source_changed: true,
          created_at: item.created_at,
        },
      ],
    };
    const document = await render(
      <ContextItemDetail
        item={inferred}
        onOpenEvidence={vi.fn(async () => true)}
      />,
    );
    expect(
      document.querySelector(".sourceChangedNotice")?.textContent,
    ).toContain("Source changed since analysis");
    expect(document.querySelector("blockquote")?.textContent).toBe(
      "Retained original quotation.",
    );
    expect(
      document.querySelector(".inferenceRationale")?.textContent,
    ).toContain(inferred.inference_rationale);
    expect(document.body.textContent).toContain("Open source message #2");
  });
});
