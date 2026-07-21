import fs from "node:fs";
import vm from "node:vm";
import { parseHTML } from "linkedom";
import { describe, expect, it } from "vitest";

const adapterSource = fs.readFileSync(
  new URL("../../extension/claude-adapter.js", import.meta.url),
  "utf8",
);
const backgroundSource = fs.readFileSync(
  new URL("../../extension/background.js", import.meta.url),
  "utf8",
);
const popupSource = fs.readFileSync(
  new URL("../../extension/popup.js", import.meta.url),
  "utf8",
);
const popupHtml = fs.readFileSync(
  new URL("../../extension/popup.html", import.meta.url),
  "utf8",
);
const claudeUrl = "https://claude.ai/chat/12345678-1234-4234-8234-123456789abc";

function fixture(name) {
  return fs.readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), "utf8");
}

function runAdapter(html, url = claudeUrl) {
  const { document } = parseHTML(html);
  return vm.runInNewContext(adapterSource, {
    document,
    location: new URL(url),
    Set,
  });
}

function loadBackground({ extraction, tabUrl = claudeUrl } = {}) {
  let listener;
  const calls = {
    nativeMessages: [],
    tabQueries: 0,
    injections: [],
    tabMessages: [],
    badges: [],
    titles: [],
  };
  const chrome = {
    runtime: {
      lastError: undefined,
      onMessage: {
        addListener(registered) {
          listener = registered;
        },
      },
      onStartup: { addListener() {} },
      sendNativeMessage(_host, message, callback) {
        calls.nativeMessages.push(message);
        if (message.type === "ping") {
          callback({ type: "status", status: "ready", reason: "connected", protocol_version: 1 });
          return;
        }
        callback({
          type: "capture_result",
          status: "saved",
          reason: "stored",
          protocol_version: 1,
          outcome: "created",
          message_count: 4,
        });
      },
    },
    tabs: {
      onUpdated: { addListener() {} },
      query(_query, callback) {
        calls.tabQueries += 1;
        callback([{ id: 23, url: tabUrl }]);
      },
      sendMessage(tabId, message, callback) {
        calls.tabMessages.push({ tabId, message });
        callback({ ok: true });
      },
    },
    scripting: {
      executeScript(options, callback) {
        calls.injections.push(options);
        callback([
          {
            frameId: 0,
            result: options.files[0] === "reminder.js" ? { ok: true } : extraction,
          },
        ]);
      },
    },
    action: {
      setBadgeBackgroundColor(_options, callback) {
        callback?.();
      },
      setBadgeText(options, callback) {
        calls.badges.push(options);
        callback?.();
      },
      setTitle(options, callback) {
        calls.titles.push(options);
        callback?.();
      },
    },
  };
  vm.runInNewContext(backgroundSource, { chrome, URL, TextEncoder });
  return { listener, calls };
}

function sendRuntimeMessage(listener, message) {
  return new Promise((resolve) => {
    expect(listener(message, {}, resolve)).toBe(true);
  });
}

function renderPopupSaveResult(saveResponse) {
  const { document, window } = parseHTML(popupHtml);
  const chrome = {
    runtime: {
      lastError: undefined,
      sendMessage(message, callback) {
        if (message.type === "reweave:check-availability") {
          callback({ status: "ready" });
          return;
        }
        callback(saveResponse);
      },
    },
  };
  vm.runInNewContext(popupSource, { chrome, document });
  document.querySelector("#save").dispatchEvent(new window.Event("click"));
  return {
    title: document.querySelector("#title").textContent,
    detail: document.querySelector("#detail").textContent,
    status: document.body.dataset.status,
  };
}

describe("Claude explicit Save adapter", () => {
  it("normalizes a complete ordered fixture without toolbar or screen-reader text", () => {
    const result = runAdapter(fixture("claude_current_conversation.html"));

    expect(result.ok).toBe(true);
    expect(result.capture).toEqual({
      provider: "claude",
      external_id: "12345678-1234-4234-8234-123456789abc",
      title: "Reweave delivery plan",
      created_at: "2026-07-21T10:00:00Z",
      updated_at: "2026-07-21T10:02:00Z",
      messages: [
        {
          external_id: "claude-user-1",
          role: "user",
          content: "Keep this Claude question.\nSecond line.",
          timestamp: "2026-07-21T10:00:00Z",
        },
        {
          external_id: "claude-assistant-1",
          role: "assistant",
          content: "This Claude answer stays ordered.\nNo response toolbar is captured.",
          timestamp: "2026-07-21T10:00:30+00:00",
        },
        {
          external_id: "claude-user-2",
          role: "user",
          content: "Keep the follow-up too.",
          timestamp: null,
        },
        {
          external_id: "claude-assistant-2",
          role: "assistant",
          content: "The follow-up remains in the same conversation.",
          timestamp: "2026-07-21T10:02:00Z",
        },
      ],
    });
  });

  it("fails closed for logged-out, changed-DOM, and unsupported pages", () => {
    expect(runAdapter(fixture("claude_logged_out.html")).reason).toBe("logged_out");
    expect(runAdapter(fixture("claude_changed_dom.html")).reason).toBe("changed_dom");
    expect(runAdapter(fixture("claude_current_conversation.html"), "https://example.com/chat/123").reason).toBe(
      "unsupported_page",
    );
    expect(runAdapter(fixture("claude_current_conversation.html"), "http://claude.ai/chat/123").reason).toBe(
      "unsupported_page",
    );
  });

  it("counts complete turns for reminders without cloning or reading message content", () => {
    const { document } = parseHTML(fixture("claude_current_conversation.html"));
    const context = { document, location: new URL(claudeUrl), Set };
    vm.runInNewContext(adapterSource, context);
    for (const turn of document.querySelectorAll(
      '[data-testid="user-message"], .font-claude-response, .font-claude-response-body',
    )) {
      turn.cloneNode = () => {
        throw new Error("content was read");
      };
    }

    expect(context.__reweaveProviderAdapter.snapshot()).toEqual({
      ok: true,
      provider: "claude",
      external_id: "12345678-1234-4234-8234-123456789abc",
      message_count: 4,
      assistant_count: 2,
    });
  });

  it("rejects missing turns, earlier-message controls, and streaming responses", () => {
    const current = fixture("claude_current_conversation.html");
    const missingBeginning = current.replace(
      /<section data-message-id="claude-user-1"[\s\S]*?<\/section>/,
      "",
    );
    const missingMiddle = current.replace(
      /<section data-message-id="claude-assistant-1"[\s\S]*?<\/section>/,
      "",
    );
    const earlierMessages = current.replace("<main>", '<main><button data-testid="load-more-messages">Earlier</button>');
    const streaming = current.replace("<main>", '<main><button data-testid="stop-response">Stop</button>');

    expect(runAdapter(missingBeginning).reason).toBe("incomplete_conversation");
    expect(runAdapter(missingMiddle).reason).toBe("incomplete_conversation");
    expect(runAdapter(earlierMessages).reason).toBe("incomplete_conversation");
    expect(runAdapter(streaming).reason).toBe("streaming");
  });

  it("injects the Claude adapter only after the generic Save action", async () => {
    const extraction = runAdapter(fixture("claude_current_conversation.html"));
    const { listener, calls } = loadBackground({ extraction });

    const availability = await sendRuntimeMessage(listener, {
      type: "reweave:check-availability",
    });
    expect(availability.status).toBe("ready");
    expect(calls.tabQueries).toBe(0);
    expect(calls.injections).toHaveLength(0);

    const saved = await sendRuntimeMessage(listener, { type: "reweave:save-conversation" });
    expect(saved).toMatchObject({ status: "saved", outcome: "created", provider: "claude" });
    expect(calls.tabQueries).toBe(1);
    expect(calls.injections).toEqual([
      { target: { tabId: 23 }, files: ["claude-adapter.js"] },
      { target: { tabId: 23 }, files: ["reminder.js"] },
    ]);
    expect(calls.tabMessages).toEqual([
      {
        tabId: 23,
        message: {
          type: "reweave:start-reminder",
          provider: "claude",
          external_id: "12345678-1234-4234-8234-123456789abc",
          assistant_count: 2,
        },
      },
    ]);
    expect(calls.nativeMessages.at(-1)).toEqual({
      type: "capture_conversation",
      protocol_version: 1,
      capture: extraction.capture,
    });
  });

  it("rejects an adapter payload that does not match the active provider", async () => {
    const extraction = runAdapter(fixture("claude_current_conversation.html"));
    extraction.capture.provider = "chatgpt";
    const { listener, calls } = loadBackground({ extraction });

    const result = await sendRuntimeMessage(listener, { type: "reweave:save-conversation" });

    expect(result).toMatchObject({
      status: "incompatible",
      reason: "malformed_adapter_response",
      provider: "claude",
    });
    expect(calls.nativeMessages).toHaveLength(0);
  });

  it("renders provider-specific Claude failure guidance in the shared popup", () => {
    const rendered = renderPopupSaveResult({
      type: "capture_result",
      status: "error",
      reason: "changed_dom",
      provider: "claude",
      protocol_version: 1,
    });

    expect(rendered).toEqual({
      title: "Claude page changed",
      detail: "Reload the conversation and try again.",
      status: "error",
    });
  });
});
