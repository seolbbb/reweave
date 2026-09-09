import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ContextHome,
  ContextWorkspace,
  type ContextBrief,
  type ContextItem,
} from "./ContextWorkspace";
import { ChatUseGuide } from "./ChatUseGuide";

const brief: ContextBrief = {
  id: "brief-one",
  source_conversation_id: "source-one",
  source_record_id: "source-one",
  source_provider: "claude",
  source_title: "Connected notes",
  source_created_at: "2026-09-09T12:00:00Z",
  main_subject: "Keep decisions connected",
  user_goal: "Return to an earlier choice without repeating the explanation.",
  important_outcomes: [],
  decisions: ["Link notes before introducing folders."],
  lessons: [],
  unresolved_questions: ["Which details belong across projects?"],
  actions: ["Try the structure with one project."],
  analysis_mode: "project",
  analysis_status: "complete",
  created_at: "2026-09-09T12:00:00Z",
  updated_at: "2026-09-09T12:00:00Z",
  context_item_ids: [],
  item_count: 0,
};

const item: ContextItem = {
  id: "item-one",
  canonical_text: "Keep relationships explicit.",
  item_type: "lesson",
  epistemic_kind: "inferred",
  confidence: 0.8,
  sensitivity: "normal",
  status: "active",
  current_version: 1,
  created_at: brief.created_at,
  updated_at: brief.updated_at,
  last_confirmed_at: null,
  stale_at: null,
  scopes: [
    {
      scope_type: "project",
      scope_key: "Notes",
      confidence: 0.9,
      created_at: brief.created_at,
    },
  ],
  evidence: [],
  versions: [],
  links: [],
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

async function click(document: Document, label: string) {
  const button = Array.from(document.querySelectorAll("button")).find((entry) =>
    entry.textContent?.includes(label),
  );
  if (!button) throw new Error(`Missing button: ${label}`);
  await act(async () => {
    button.click();
  });
}

afterEach(async () => {
  for (const surface of surfaces.splice(0).reverse()) {
    await act(async () => surface.root.unmount());
    surface.restore();
  }
  vi.unstubAllGlobals();
});

describe("Reading Room source and navigation behavior", () => {
  it("keeps a zero-item Brief readable and opens the saved source explicitly", async () => {
    const onOpenEvidence = vi.fn(async () => true);
    const document = await render(
      <ContextHome
        briefs={[brief]}
        brief={brief}
        items={[]}
        groups={[]}
        onSelectBrief={vi.fn()}
        onOpenExplorer={vi.fn()}
        onOpenEvidence={onOpenEvidence}
      />,
    );

    expect(document.body.textContent).toContain(
      "Link notes before introducing folders.",
    );
    expect(document.body.textContent).toContain(
      "useful Brief without separate Context Items",
    );
    expect(document.body.textContent).toContain(
      "Which details belong across projects?",
    );
    expect(document.querySelector(".briefSupportingDetails")).toBeNull();
    expect(onOpenEvidence).not.toHaveBeenCalled();
    await click(document, "View source");
    expect(onOpenEvidence).toHaveBeenCalledWith("source-one", 0);
  });

  it("retains a Brief when its original source is removed without offering a broken source action", async () => {
    const retained = { ...brief, source_conversation_id: null };
    const onOpenEvidence = vi.fn(async () => false);
    const document = await render(
      <ContextHome
        briefs={[retained]}
        brief={retained}
        items={[]}
        groups={[]}
        onSelectBrief={vi.fn()}
        onOpenExplorer={vi.fn()}
        onOpenEvidence={onOpenEvidence}
      />,
    );

    expect(document.body.textContent).toContain(
      "Original source removed · Brief retained",
    );
    expect(document.body.textContent).toContain(
      "Link notes before introducing folders.",
    );
    expect(
      document.querySelector('[aria-label="View source Connected notes"]'),
    ).toBeNull();
    expect(onOpenEvidence).not.toHaveBeenCalled();
  });

  it("labels an inferred item near its text and preserves the read-source route", async () => {
    const onOpenExplorer = vi.fn();
    const document = await render(
      <ContextHome
        briefs={[brief]}
        brief={{
          ...brief,
          context_item_ids: [item.id],
          item_count: 1,
          lessons: ["Preserve the longer explanation in this Brief."],
        }}
        items={[item]}
        groups={[]}
        onSelectBrief={vi.fn()}
        onOpenExplorer={onOpenExplorer}
        onOpenEvidence={vi.fn(async () => true)}
      />,
    );

    const itemNode = Array.from(
      document.querySelectorAll(".contextReadingItem"),
    ).find((node) => node.textContent?.includes(item.canonical_text));
    expect(itemNode?.textContent).toContain("Inferred");
    const supporting = document.querySelector(".briefSupportingDetails");
    expect(supporting?.hasAttribute("open")).toBe(false);
    expect(supporting?.textContent).toContain(
      "Preserve the longer explanation in this Brief.",
    );
    await click(document, "Read context & sources");
    expect(onOpenExplorer).toHaveBeenCalledWith(item);
  });

  it("keeps a useful error at the source action when its original conversation cannot open", async () => {
    const document = await render(
      <ContextHome
        briefs={[brief]}
        brief={brief}
        items={[]}
        groups={[]}
        onSelectBrief={vi.fn()}
        onOpenExplorer={vi.fn()}
        onOpenEvidence={vi.fn(async () => false)}
      />,
    );
    await click(document, "View source");
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "This saved Brief is still available",
    );
  });

  it("loads subsequent pages and refreshes after analysis without losing the selected view", async () => {
    const second = {
      ...item,
      id: "item-two",
      canonical_text: "A second retained lesson.",
    };
    const fetchMock = vi.fn(async (input: string) => {
      const url = new URL(input, "http://localhost");
      if (url.pathname.endsWith("/briefs"))
        return new Response(
          JSON.stringify({ results: [brief], has_more: false }),
          { headers: { "Content-Type": "application/json" } },
        );
      const offset = Number(url.searchParams.get("offset"));
      return new Response(
        JSON.stringify({
          results: offset ? [second] : [item],
          has_more: !offset,
        }),
        { headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const document = await render(
      <ContextWorkspace
        view="explorer"
        onOpenLibrary={vi.fn()}
        onOpenEvidence={vi.fn(async () => true)}
      />,
    );
    expect(document.body.textContent).toContain("Keep relationships explicit.");
    await click(document, "Load more context");
    expect(
      fetchMock.mock.calls.some(([url]) =>
        url.includes("items?limit=100&offset=1"),
      ),
    ).toBe(true);
    expect(document.body.textContent).toContain("A second retained lesson.");
    expect(document.body.textContent).not.toContain("Load more context");
    const priorCalls = fetchMock.mock.calls.length;
    await act(async () => {
      window.dispatchEvent(new Event("reweave:context-changed"));
    });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(priorCalls);
    expect(document.body.textContent).toContain("Explore your context");
  });

  it("explains extension Use without reading a page, copying text, or submitting a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onOpenSettings = vi.fn();
    const document = await render(
      <ChatUseGuide onOpenSettings={onOpenSettings} />,
    );
    expect(document.body.textContent).toContain("existing draft");
    expect(document.body.textContent).toContain("send the message yourself");
    expect(document.body.textContent).toContain(
      "Save and Use are separate, explicit actions",
    );
    await click(document, "Extension setup & connection");
    expect(onOpenSettings).toHaveBeenCalledOnce();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not let an older background refresh overwrite newer corrected context", async () => {
    let itemRequests = 0;
    let releaseOld: (() => void) | undefined;
    const json = (data: unknown) =>
      new Response(JSON.stringify(data), {
        headers: { "Content-Type": "application/json" },
      });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string) => {
        if (input.includes("/briefs?"))
          return json({ results: [brief], has_more: false });
        itemRequests += 1;
        if (itemRequests === 2)
          return new Promise<Response>((resolve) => {
            releaseOld = () =>
              resolve(
                json({
                  results: [
                    { ...item, canonical_text: "Outdated background result." },
                  ],
                  has_more: false,
                }),
              );
          });
        return json({
          results: [
            {
              ...item,
              canonical_text:
                itemRequests > 2
                  ? "The newest correction is preserved."
                  : item.canonical_text,
            },
          ],
          has_more: false,
        });
      }),
    );
    const document = await render(
      <ContextWorkspace
        view="explorer"
        onOpenLibrary={vi.fn()}
        onOpenEvidence={vi.fn(async () => true)}
      />,
    );
    await act(async () => {
      window.dispatchEvent(new Event("reweave:context-changed"));
    });
    await act(async () => {
      window.dispatchEvent(new Event("reweave:context-changed"));
    });
    expect(document.body.textContent).toContain(
      "The newest correction is preserved.",
    );
    await act(async () => {
      releaseOld?.();
    });
    expect(document.body.textContent).toContain(
      "The newest correction is preserved.",
    );
    expect(document.body.textContent).not.toContain(
      "Outdated background result.",
    );
  });
});
