import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OnboardingWizard } from "./ArchiveManagement";

type TestSurface = {
  document: Document;
  root: Root;
  restore: () => void;
};

const activeSurfaces: TestSurface[] = [];

async function renderOnboarding(onFinish = vi.fn()) {
  const parsed = parseHTML("<html><body><div id='root'></div></body></html>");
  const replacements = {
    document: parsed.document,
    window: parsed.window,
    HTMLElement: parsed.window.HTMLElement,
    Event: parsed.window.Event,
    IS_REACT_ACT_ENVIRONMENT: true
  };
  const previous = new Map(
    Object.keys(replacements).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)])
  );
  for (const [key, value] of Object.entries(replacements)) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  }

  const rootNode = parsed.document.getElementById("root");
  if (!rootNode) throw new Error("Missing onboarding test root.");
  const root = createRoot(rootNode as unknown as HTMLElement);

  await act(async () => {
    root.render(
      <OnboardingWizard
        open
        busy={false}
        onImport={async () => null}
        onFinish={onFinish}
      />
    );
  });

  const surface: TestSurface = {
    document: parsed.document as unknown as Document,
    root,
    restore: () => {
      for (const [key, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete (globalThis as Record<string, unknown>)[key];
      }
    }
  };
  activeSurfaces.push(surface);
  return { ...surface, onFinish };
}

function findButton(document: Document, label: string) {
  const button = Array.from(document.querySelectorAll("button"))
    .find((candidate) => candidate.textContent?.includes(label));
  if (!button) throw new Error(`Could not find button containing: ${label}`);
  return button as HTMLButtonElement;
}

async function click(button: HTMLButtonElement) {
  await act(async () => {
    button.click();
  });
}

afterEach(async () => {
  while (activeSurfaces.length) {
    const surface = activeSurfaces.pop();
    if (!surface) continue;
    await act(async () => surface.root.unmount());
    surface.restore();
  }
});

describe("first-run onboarding", () => {
  it("recommends export backfill while allowing a direct no-import path", async () => {
    const { document, onFinish } = await renderOnboarding();

    expect(document.body.textContent).toContain("A historical export builds useful context faster");
    await click(findButton(document, "Start without import"));

    expect(document.body.textContent).toContain("no export or API key required");
    expect(document.body.textContent).toContain("starts queued Context analysis automatically");
    expect(document.body.textContent).toContain("current Chrome or Edge extension");
    expect(document.body.textContent).toContain("does not install it automatically");

    await click(findButton(document, "Open Context"));
    expect(onFinish).toHaveBeenCalledWith("context");
  });

  it("keeps optional export guidance and the existing Import and Settings destinations", async () => {
    const { document, onFinish } = await renderOnboarding();

    await click(findButton(document, "See recommended backfill"));
    expect(document.body.textContent).toContain("Recommended: import an export");
    expect(document.body.textContent).toContain("Start with new conversations");

    await click(findButton(document, "View export steps"));
    expect(document.body.textContent).toContain("Export from your AI service");
    await click(findButton(document, "I have the export file"));
    expect(document.body.textContent).toContain("Choose ZIP or JSON files");
    await click(findButton(document, "Back"));
    await click(findButton(document, "Continue without waiting"));

    await click(findButton(document, "Connect an AI provider"));
    expect(onFinish).toHaveBeenCalledWith("settings");

    onFinish.mockClear();
    await click(findButton(document, "Import history later"));
    expect(onFinish).toHaveBeenCalledWith("import");
  });
});
