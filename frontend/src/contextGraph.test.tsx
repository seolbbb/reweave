import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { DOMParser, parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ContextGraph,
  GraphSharing,
  graphSharePayload,
  inspectShareSvg,
  layoutContextGraph,
  rawSpaceId,
  shareSvgToPng,
  type ContextGraphData,
} from "./ContextGraph";
import { ContextWorkspace, type ContextItem } from "./ContextWorkspace";

const graph: ContextGraphData = {
  nodes: [
    {
      id: "space:project-a",
      kind: "space",
      label: "Private product name",
      scope_type: "project",
    },
    {
      id: "item-a",
      kind: "item",
      label: "A private decision with source evidence",
      item_type: "decision",
      epistemic_kind: "observed",
      sensitivity: "normal",
    },
    {
      id: "item-b",
      kind: "item",
      label: "An inferred lesson",
      item_type: "lesson",
      epistemic_kind: "inferred",
      sensitivity: "normal",
    },
    {
      id: "secret",
      kind: "item",
      label: "Sensitive detail",
      sensitivity: "sensitive",
    },
  ],
  edges: [
    { source: "item-a", target: "space:project-a", relationship: "belongs_to" },
    { source: "item-b", target: "space:project-a", relationship: "belongs_to" },
    { source: "item-a", target: "item-b", relationship: "supports" },
    { source: "secret", target: "space:project-a", relationship: "belongs_to" },
  ],
  total_items: 230,
  shown_items: 3,
  truncated: true,
  spaces: [
    { id: "project-a", name: "Private product name", scope_type: "project" },
    { id: "work-a", name: "Work", scope_type: "work" },
    {
      id: "personal-a",
      name: "Personal private space",
      scope_type: "personal",
    },
    { id: "core-a", name: "Core Self private space", scope_type: "core_self" },
  ],
};
const svg =
  '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="700"><text x="20" y="40">Project 1</text><text x="20" y="80">Decision 1</text></svg>';
const preview = {
  preview_token: "one-use-synthetic",
  svg,
  node_count: 3,
  edge_count: 2,
  excluded_count: 1,
  warnings: [],
  expires_in_seconds: 600,
};
const surfaces: Array<{ root: Root; restore: () => void }> = [];

async function render(content: ReactNode) {
  const parsed = parseHTML("<html><body><div id='root'></div></body></html>");
  const replacements = {
    document: parsed.document,
    window: parsed.window,
    HTMLElement: parsed.window.HTMLElement,
    Event: parsed.window.Event,
    DOMParser,
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
  return { document: parsed.document as unknown as Document, root };
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function button(document: Document, text: string) {
  const result = Array.from(document.querySelectorAll("button")).find((entry) =>
    entry.textContent?.includes(text),
  );
  if (!result) throw new Error(`Missing button: ${text}`);
  return result;
}
async function click(document: Document, text: string) {
  await act(async () => button(document, text).click());
}
async function check(document: Document, name: string, checked = true) {
  const label = Array.from(
    document.querySelectorAll(".graphShareScopes label"),
  ).find((entry) => entry.textContent?.includes(name));
  const input = label?.querySelector("input");
  if (!input) throw new Error(`Missing scope: ${name}`);
  await act(async () => {
    input.checked = checked;
    input.click();
  });
}
function objectUrls() {
  let counter = 0;
  const create = vi
    .spyOn(URL, "createObjectURL")
    .mockImplementation(() => `blob:graph-${++counter}`);
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  return { create, revoke };
}
async function prepare(document: Document) {
  await click(document, "Share a redacted graph");
  await check(document, "Private product name");
  await click(document, "Preview redacted graph");
}
async function imageLoaded(document: Document) {
  const image = document.querySelector(".graphSharePreview img");
  expect(image).not.toBeNull();
  await act(async () => image?.dispatchEvent(new Event("load")));
}
afterEach(async () => {
  for (const surface of surfaces.splice(0).reverse()) {
    await act(async () => surface.root.unmount());
    surface.restore();
  }
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("recorded Context Graph", () => {
  it("lays out actual nodes deterministically and retains raw item ids", () => {
    const forward = layoutContextGraph(graph.nodes, graph.edges);
    expect(
      layoutContextGraph(
        [...graph.nodes].reverse(),
        [...graph.edges].reverse(),
      ),
    ).toEqual(forward);
    expect(forward.nodes.map((node) => node.id).sort()).toEqual(
      graph.nodes.map((node) => node.id).sort(),
    );
    expect(rawSpaceId("space:project-a")).toBe("project-a");
    expect(rawSpaceId("item-a")).toBe("item-a");
  });
  it("navigates from the accessible list to sources and filters by a raw space id", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(json(graph)));
    vi.stubGlobal("fetch", fetchMock);
    const onOpenItem = vi.fn().mockResolvedValue(true);
    const { document } = await render(<ContextGraph onOpenItem={onOpenItem} />);
    expect(document.body.textContent).toContain("Showing 3 of 230");
    expect(document.querySelectorAll(".graphNode[tabindex='0']")).toHaveLength(
      graph.nodes.length,
    );
    await click(document, "A private decision with source evidence");
    expect(document.querySelector(".graphSelection")?.textContent).toContain(
      "Supports",
    );
    await click(document, "Read context & sources");
    expect(onOpenItem).toHaveBeenCalledWith("item-a");
    await click(document, "Private product name");
    expect(fetchMock.mock.calls.at(-1)?.[0]).toContain("space_id=project-a");
  });
  it("opens a search result through the existing Context Item detail", async () => {
    const item: ContextItem = {
      id: "outside-page",
      canonical_text: "Selected global search result",
      item_type: "decision",
      epistemic_kind: "observed",
      confidence: 1,
      sensitivity: "normal",
      status: "active",
      current_version: 1,
      created_at: "2026-09-10",
      updated_at: "2026-09-10",
      last_confirmed_at: null,
      stale_at: null,
      scopes: [],
      evidence: [],
      versions: [],
      links: [],
    };
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(
          json(
            url.includes("/items/outside-page")
              ? item
              : url === "/api/context/items?limit=100&offset=0"
                ? {
                    results: [
                      {
                        ...item,
                        id: "first-page",
                        canonical_text: "Already loaded context",
                      },
                    ],
                    has_more: true,
                  }
                : { results: [], has_more: false },
          ),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const onViewChange = vi.fn();
    const { document } = await render(
      <ContextWorkspace
        openItemId="outside-page"
        onViewChange={onViewChange}
        onOpenLibrary={() => {}}
        onOpenEvidence={async () => false}
      />,
    );
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === "/api/context/items/outside-page",
      ),
    ).toBe(true);
    expect(onViewChange).toHaveBeenCalledWith("explorer");
    expect(document.body.textContent).toContain(
      "Selected global search result",
    );
    expect(
      button(document, "List & sources").getAttribute("aria-pressed"),
    ).toBe("true");
    await click(document, "Load more context");
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === "/api/context/items?limit=100&offset=1",
      ),
    ).toBe(true);
  });
});

describe("redacted graph sharing", () => {
  it("requires a displayed preview and never fills public labels from private text", async () => {
    const urls = objectUrls();
    const fetchMock = vi.fn().mockResolvedValue(json(preview));
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render(<GraphSharing graph={graph} />);
    await click(document, "Share a redacted graph");
    expect(
      document.querySelector(".graphShareScopes")?.textContent,
    ).not.toContain("Personal private space");
    expect(
      document.querySelector(".graphShareScopes")?.textContent,
    ).not.toContain("Core Self private space");
    expect(button(document, "Preview redacted graph").disabled).toBe(true);
    expect(document.body.textContent).not.toContain(
      "Export this preview as PNG",
    );
    await check(document, "Private product name");
    const inputs = Array.from(
      document.querySelectorAll<HTMLInputElement>(".publicLabelEditor input"),
    );
    expect(inputs).toHaveLength(3);
    expect(inputs.every((input) => input.value === "")).toBe(true);
    await click(document, "Preview redacted graph");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const request = fetchMock.mock.calls[0][1];
    expect(JSON.parse(request.body)).toEqual({
      space_ids: ["project-a"],
      labels: {},
    });
    expect(request.credentials).toBe("same-origin");
    expect(button(document, "Export this preview as PNG").disabled).toBe(true);
    expect(urls.create).toHaveBeenCalledWith(expect.any(Blob));
    await imageLoaded(document);
    expect(button(document, "Export this preview as PNG").disabled).toBe(false);
  });
  it("invalidates and revokes the preview when a written label changes", async () => {
    const urls = objectUrls();
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(json(preview)));
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render(<GraphSharing graph={graph} />);
    await prepare(document);
    const input = document.querySelector<HTMLInputElement>(
      'input[aria-label="Public label for A private decision with source evidence"]',
    )!;
    await act(async () => {
      input.value = "Publicly written decision";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(document.querySelector(".graphSharePreview")).toBeNull();
    expect(urls.revoke).toHaveBeenCalledWith("blob:graph-1");
    await click(document, "Preview redacted graph");
    expect(JSON.parse(fetchMock.mock.calls.at(-1)?.[1].body)).toEqual({
      space_ids: ["project-a"],
      labels: { "item-a": "Publicly written decision" },
    });
  });
  it("cancels without exporting, clears labels, and returns focus", async () => {
    const urls = objectUrls();
    const fetchMock = vi.fn().mockResolvedValue(json(preview));
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render(<GraphSharing graph={graph} />);
    await prepare(document);
    const focus = vi.spyOn(button(document, "Share a redacted graph"), "focus");
    await click(document, "Cancel sharing");
    expect(document.querySelector(".graphSharePreview")).toBeNull();
    expect(document.querySelector(".publicLabelEditor")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(urls.revoke).toHaveBeenCalledWith("blob:graph-1");
    expect(focus).toHaveBeenCalled();
  });
  it("invalidates the approved image after changing selected spaces", async () => {
    const urls = objectUrls();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(preview)));
    const { document } = await render(<GraphSharing graph={graph} />);
    await prepare(document);
    await check(document, "Work");
    expect(document.querySelector(".graphSharePreview")).toBeNull();
    expect(urls.revoke).toHaveBeenCalledWith("blob:graph-1");
    expect(document.body.textContent).toContain(
      "combines several selected spaces",
    );
  });
  it("rejects an expired export token and requires a new preview with focus restored", async () => {
    objectUrls();
    const fetchMock = vi
      .fn()
      .mockImplementation((url: string) =>
        Promise.resolve(
          url.endsWith("/export")
            ? json({ detail: "Preview expired" }, 409)
            : json(preview),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render(<GraphSharing graph={graph} />);
    await prepare(document);
    await imageLoaded(document);
    const focus = vi.spyOn(button(document, "Preview redacted graph"), "focus");
    await click(document, "Export this preview as PNG");
    expect(JSON.parse(fetchMock.mock.calls.at(-1)?.[1].body)).toEqual({
      preview_token: preview.preview_token,
      confirmation: "EXPORT",
    });
    expect(document.querySelector(".graphSharePreview")).toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "Prepare a new preview",
    );
    expect(focus).toHaveBeenCalled();
  });
  it("does not rasterize an SVG that differs from the approved preview", async () => {
    objectUrls();
    const image = vi.fn();
    vi.stubGlobal("Image", image);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((url: string) =>
          Promise.resolve(
            url.endsWith("/export")
              ? new Response(svg.replace("Decision 1", "Changed"))
              : json(preview),
          ),
        ),
    );
    const { document } = await render(<GraphSharing graph={graph} />);
    await prepare(document);
    await imageLoaded(document);
    await click(document, "Export this preview as PNG");
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "did not match",
    );
    expect(image).not.toHaveBeenCalled();
  });
  it("renders the same SVG at its natural dimensions and releases its temporary URL", async () => {
    const urls = objectUrls();
    const { document } = await render(<div />);
    const png = new Blob(["png fixture"], { type: "image/png" });
    const drawImage = vi.fn();
    const canvas = {
      width: 0,
      height: 0,
      getContext: () => ({ drawImage }),
      toBlob: (callback: BlobCallback) => callback(png),
    };
    const createElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation(((tag: string) =>
      tag === "canvas"
        ? canvas
        : createElement(tag)) as typeof document.createElement);
    class FakeImage {
      onload: (() => void) | null = null;
      set src(_value: string) {
        this.onload?.();
      }
    }
    vi.stubGlobal("Image", FakeImage);
    expect(
      await shareSvgToPng(svg.replace('height="700"', 'height="1500"')),
    ).toBe(png);
    expect(canvas.width).toBe(1000);
    expect(canvas.height).toBe(1500);
    expect(drawImage).toHaveBeenCalledWith(
      expect.any(FakeImage),
      0,
      0,
      1000,
      1500,
    );
    expect(urls.revoke).toHaveBeenCalledWith("blob:graph-1");
  });
  it("rejects external resources in SVGs before display or canvas use", async () => {
    await render(<div />);
    expect(inspectShareSvg(svg)).toEqual({ width: 1000, height: 700 });
    expect(() =>
      inspectShareSvg(
        svg.replace(
          "</svg>",
          '<image href="https://example.com/private"/></svg>',
        ),
      ),
    ).toThrow("external");
    expect(() =>
      inspectShareSvg(svg.replace("</svg>", "<script>alert(1)</script></svg>")),
    ).toThrow("external");
    expect(
      graphSharePayload(["project-a", "project-a"], {
        "item-a": "  Public  ",
        "item-b": "",
      }),
    ).toEqual({ space_ids: ["project-a"], labels: { "item-a": "Public" } });
  });
});
