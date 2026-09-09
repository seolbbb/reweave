import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { parseHTML } from "linkedom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  BackupManager,
  backupFileProblem,
  MAX_BACKUP_FILE_BYTES,
  validBackupPassword,
  type BackupPreview,
} from "./BackupManager";

const password = "synthetic-backup-password";
const preview: BackupPreview = {
  conversations: 4,
  messages: 12,
  briefs: 3,
  context_items: 8,
  versions: 10,
  links: 2,
  profiles: 1,
  created_at: "2026-09-10T00:00:00Z",
  database_bytes: 8192,
  requires_reconnect: true,
  notice: "Provider secrets excluded.",
};
const surfaces: Array<{ root: Root; restore: () => void }> = [];

async function render(onRestored = vi.fn()) {
  const parsed = parseHTML("<html><body><div id='root'></div></body></html>");
  parsed.window.requestAnimationFrame = (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  };
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
    root.render(<BackupManager onRestored={onRestored} />);
  });
  return { document: parsed.document as unknown as Document, onRestored };
}

function field(document: Document, title: string) {
  const label = Array.from(document.querySelectorAll("label")).find((entry) =>
    entry.textContent?.trim().startsWith(title),
  );
  const input = label?.querySelector("input");
  if (!input) throw new Error(`Missing input: ${title}`);
  return input;
}
async function type(document: Document, title: string, value: string) {
  const input = field(document, title);
  await act(async () => {
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function button(document: Document, title: string) {
  const result = Array.from(document.querySelectorAll("button")).find((entry) =>
    entry.textContent?.includes(title),
  );
  if (!result) throw new Error(`Missing button: ${title}`);
  return result;
}
async function click(document: Document, title: string) {
  await act(async () => {
    const target = button(document, title);
    target.click();
    if (target.type === "submit" && !target.disabled)
      target
        .closest("form")
        ?.dispatchEvent(
          new Event("submit", { bubbles: true, cancelable: true }),
        );
  });
}
async function chooseFile(
  document: Document,
  file = new File(["synthetic encrypted fixture"], "test-library.reweave"),
) {
  const input = field(document, "Choose .reweave backup");
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  await act(async () =>
    input.dispatchEvent(new Event("change", { bubbles: true })),
  );
}
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
afterEach(async () => {
  for (const surface of surfaces.splice(0).reverse()) {
    await act(async () => surface.root.unmount());
    surface.restore();
  }
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("encrypted backup and restore", () => {
  it("checks the password and file limits before sending anything", async () => {
    expect(validBackupPassword("too-short")).toBe(false);
    expect(validBackupPassword("😀".repeat(6))).toBe(false);
    expect(validBackupPassword(password)).toBe(true);
    expect(
      backupFileProblem({
        name: "archive.reweave",
        size: MAX_BACKUP_FILE_BYTES + 1,
      }),
    ).toContain("2 GiB");
    expect(backupFileProblem({ name: "archive.zip", size: 128 })).toContain(
      ".reweave",
    );
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render();
    await type(document, "Backup password", "short");
    await type(document, "Repeat backup password", "short");
    expect(button(document, "Download encrypted backup").disabled).toBe(true);
    await chooseFile(document);
    await type(document, "Restore password", "short");
    expect(button(document, "Preview backup").disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("requires a preview and exact typed confirmation, then clears secrets after restoring", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("/preview")
        ? json({ preview })
        : json({
            preview,
            requires_reconnect: true,
            notice: "Restored",
            recovery_pending: false,
          }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { document, onRestored } = await render();
    await chooseFile(document);
    await type(document, "Restore password", password);
    expect(document.querySelector(".backupPreview")).toBeNull();
    await click(document, "Preview backup");
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/archive/encrypted-restore/preview",
    );
    expect(document.body.textContent).toContain("Review this backup");
    expect(button(document, "Replace library with this backup").disabled).toBe(
      true,
    );
    await type(document, "Type RESTORE", "restore");
    expect(button(document, "Replace library with this backup").disabled).toBe(
      true,
    );
    await type(document, "Type RESTORE", "RESTORE");
    await click(document, "Replace library with this backup");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, request] = fetchMock.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/archive/encrypted-restore");
    expect(url).not.toContain(password);
    expect((request.body as FormData).get("password")).toBe(password);
    expect((request.body as FormData).get("confirmation")).toBe("RESTORE");
    expect(field(document, "Restore password").value).toBe("");
    expect(document.querySelector(".backupPreview")).toBeNull();
    expect(onRestored).toHaveBeenCalledOnce();
    expect(document.body.textContent).toContain(
      "Reconnect provider credentials",
    );
  });

  it("invalidates a preview when the password changes and cancels without restoring", async () => {
    const fetchMock = vi.fn(async () => json({ preview }));
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render();
    await chooseFile(document);
    await type(document, "Restore password", password);
    await click(document, "Preview backup");
    expect(document.querySelector(".backupPreview")).not.toBeNull();
    await type(document, "Restore password", `${password}-changed`);
    expect(document.querySelector(".backupPreview")).toBeNull();
    await click(document, "Cancel restore");
    expect(field(document, "Restore password").value).toBe("");
    expect(document.querySelector(".backupSelectedFile")).toBeNull();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("keeps a busy restore's input and preview for an explicit retry", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("/preview")
        ? json({ preview })
        : json({ detail: "Busy" }, 409),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { document, onRestored } = await render();
    await chooseFile(document);
    await type(document, "Restore password", password);
    await click(document, "Preview backup");
    await type(document, "Type RESTORE", "RESTORE");
    await click(document, "Replace library with this backup");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "Your input is kept",
    );
    expect(field(document, "Restore password").value).toBe(password);
    expect(field(document, "Type RESTORE").value).toBe("RESTORE");
    expect(button(document, "Try restore again").disabled).toBe(false);
    expect(onRestored).not.toHaveBeenCalled();
  });

  it("downloads an authenticated encrypted blob and revokes its URL without storing its password", async () => {
    const create = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:test-backup");
    const revoke = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => undefined);
    const fetchMock = vi.fn(
      async () =>
        new Response(
          new Blob(["encrypted fixture"], { type: "application/octet-stream" }),
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { document } = await render();
    await type(document, "Backup password", password);
    await type(document, "Repeat backup password", password);
    await click(document, "Download encrypted backup");
    const [url, request] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/archive/encrypted-backup");
    expect(request.credentials).toBe("same-origin");
    expect(JSON.parse(String(request.body))).toEqual({ password });
    expect(create).toHaveBeenCalledOnce();
    expect(revoke).toHaveBeenCalledWith("blob:test-backup");
    expect(field(document, "Backup password").value).toBe("");
    expect(field(document, "Repeat backup password").value).toBe("");
    expect(document.querySelector('a[href="blob:test-backup"]')).toBeNull();
  });

  it("shows the committed restore and restart requirement without refreshing a recovery-locked app", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/preview")
          ? json({ preview })
          : json({
              preview,
              requires_reconnect: true,
              notice: "Restart required",
              recovery_pending: true,
            }),
      ),
    );
    const { document, onRestored } = await render();
    const refresh = vi.fn();
    const restart = vi.fn();
    window.addEventListener("reweave:context-changed", refresh);
    window.addEventListener("reweave:restart-required", restart);
    await chooseFile(document);
    await type(document, "Restore password", password);
    await click(document, "Preview backup");
    await type(document, "Type RESTORE", "RESTORE");
    await click(document, "Replace library with this backup");
    expect(document.body.textContent).toContain(
      "Your backup was restored. Restart Reweave",
    );
    expect(document.querySelector('[role="alert"]')).toBeNull();
    expect(field(document, "Restore password").value).toBe("");
    expect(onRestored).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    expect(restart).toHaveBeenCalledOnce();
  });
});
