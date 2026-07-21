import fs from "node:fs";
import vm from "node:vm";
import { parseHTML } from "linkedom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const reminderSource = fs.readFileSync(
  new URL("../../extension/reminder.js", import.meta.url),
  "utf8",
);
const backgroundSource = fs.readFileSync(
  new URL("../../extension/background.js", import.meta.url),
  "utf8",
);

const identities = {
  chatgpt: {
    externalId: "conversation-42",
    url: "https://chatgpt.com/c/conversation-42",
  },
  claude: {
    externalId: "12345678-1234-4234-8234-123456789abc",
    url: "https://claude.ai/chat/12345678-1234-4234-8234-123456789abc",
  },
};

function messagesForCount(assistantCount) {
  return Array.from({ length: assistantCount * 2 }, (_, index) => ({
    external_id: `message-${index}`,
    role: index % 2 === 0 ? "user" : "assistant",
    content: `content-${index}`,
    timestamp: null,
  }));
}

function reminderHarness(provider) {
  const identity = identities[provider];
  const { document, window } = parseHTML("<!doctype html><html><body><main></main></body></html>");
  const location = new URL(identity.url);
  const sent = [];
  let runtimeListener;
  let assistantCount = 1;
  let snapshotOverride = null;
  let captureCalls = 0;
  let nativeResponse = {
    type: "capture_result",
    status: "saved",
    reason: "stored",
    protocol_version: 1,
  };
  const adapter = {
    provider,
    snapshot() {
      return (
        snapshotOverride || {
          ok: true,
          provider,
          external_id: identity.externalId,
          message_count: assistantCount * 2,
          assistant_count: assistantCount,
        }
      );
    },
    capture() {
      captureCalls += 1;
      return {
        ok: true,
        capture: {
          provider,
          external_id: identity.externalId,
          title: "Reminder test",
          created_at: null,
          updated_at: null,
          messages: messagesForCount(assistantCount),
        },
      };
    },
  };
  const chrome = {
    runtime: {
      lastError: undefined,
      onMessage: {
        addListener(listener) {
          runtimeListener = listener;
        },
      },
      sendMessage(message, callback) {
        sent.push(message);
        callback(
          message.type === "reweave:save-reminder-capture" ? nativeResponse : { ok: true },
        );
      },
    },
  };
  const context = {
    __reweaveProviderAdapter: adapter,
    addEventListener: window.addEventListener.bind(window),
    chrome,
    clearInterval,
    clearTimeout,
    document,
    location,
    MutationObserver: window.MutationObserver,
    setInterval,
    setTimeout,
    URL,
  };
  vm.runInNewContext(reminderSource, context);
  return {
    context,
    controller: context.__reweaveReminderController,
    document,
    identity,
    location,
    runtimeListener,
    sent,
    setAssistantCount(value) {
      assistantCount = value;
    },
    setNativeResponse(value) {
      nativeResponse = value;
    },
    setSnapshot(value) {
      snapshotOverride = value;
    },
    get captureCalls() {
      return captureCalls;
    },
  };
}

function startReminder(harness, assistantCount = 1) {
  return harness.controller.start({
    type: "reweave:start-reminder",
    provider: harness.context.__reweaveProviderAdapter.provider,
    external_id: harness.identity.externalId,
    assistant_count: assistantCount,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe.each(["chatgpt", "claude"])("%s page-lifetime reminder", (provider) => {
  it("waits for 30 seconds of inactivity, keeps a badge after auto-hide, and re-arms after dismissal", () => {
    const harness = reminderHarness(provider);
    const activeBefore = harness.document.activeElement;

    expect(startReminder(harness)).toEqual({ ok: true });
    expect(harness.document.activeElement).toBe(activeBefore);
    harness.setAssistantCount(2);
    harness.controller.scheduleEvaluation();
    vi.advanceTimersByTime(29_999);
    expect(harness.controller.getState().pending).toBe(false);
    vi.advanceTimersByTime(1);

    expect(harness.controller.getState()).toMatchObject({
      active: true,
      pending: true,
      prompt_visible: true,
    });
    expect(harness.sent.at(-1)).toMatchObject({
      type: "reweave:reminder-pending",
      provider,
      external_id: harness.identity.externalId,
      assistant_count: 2,
    });

    const shadow = harness.document.querySelector("[data-reweave-reminder-host]").shadowRoot;
    expect(shadow.querySelector(".card").getAttribute("role")).toBe("region");
    expect(shadow.querySelector('[role="status"]').getAttribute("aria-live")).toBe("polite");
    expect(shadow.querySelector("style").textContent).toContain("min-height: 44px");
    expect(shadow.querySelector("style").textContent).toContain("prefers-color-scheme: dark");
    expect(shadow.querySelector("style").textContent).toContain("prefers-reduced-motion: reduce");

    vi.advanceTimersByTime(8_000);
    expect(harness.controller.getState()).toMatchObject({
      pending: true,
      prompt_visible: false,
    });
    expect(harness.controller.dismissNow()).toEqual({ ok: true, assistant_count: 2 });
    expect(harness.controller.evaluateNow()).toMatchObject({ pending: false, assistant_count: 2 });

    harness.setAssistantCount(3);
    expect(harness.controller.evaluateNow()).toMatchObject({ pending: true, assistant_count: 3 });
  });

  it("waits through streaming but stops and clears state on DOM or identity uncertainty", () => {
    const harness = reminderHarness(provider);
    expect(startReminder(harness)).toEqual({ ok: true });
    harness.setSnapshot({
      ok: false,
      reason: "streaming",
      provider,
      external_id: harness.identity.externalId,
    });

    expect(harness.controller.evaluateNow()).toEqual({
      active: true,
      pending: false,
      reason: "streaming",
    });
    harness.setSnapshot({ ok: false, reason: "changed_dom" });
    expect(harness.controller.evaluateNow()).toEqual({
      active: false,
      reason: "changed_dom",
    });
    expect(harness.controller.getState().active).toBe(false);
    expect(harness.document.querySelector("[data-reweave-reminder-host]")).toBeNull();
    expect(harness.sent.at(-1)).toMatchObject({ type: "reweave:reminder-clear", provider });
  });

  it("stops after a same-origin conversation URL change even without a DOM mutation", () => {
    const harness = reminderHarness(provider);
    expect(startReminder(harness)).toEqual({ ok: true });
    harness.location.href =
      provider === "chatgpt"
        ? "https://chatgpt.com/c/conversation-99"
        : "https://claude.ai/chat/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

    vi.advanceTimersByTime(999);
    expect(harness.controller.getState().active).toBe(true);
    vi.advanceTimersByTime(1);
    expect(harness.controller.getState().active).toBe(false);
    expect(harness.sent.at(-1)).toMatchObject({ type: "reweave:reminder-clear", provider });
  });

  it("re-Saves explicitly and keeps the reminder retryable when the app is unavailable", () => {
    const harness = reminderHarness(provider);
    expect(startReminder(harness)).toEqual({ ok: true });
    harness.setAssistantCount(2);
    harness.controller.evaluateNow();

    expect(harness.controller.saveNow()).toEqual({ ok: true });
    expect(harness.captureCalls).toBe(1);
    expect(harness.sent.find((message) => message.type === "reweave:save-reminder-capture")).toMatchObject({
      provider,
      capture: { provider, external_id: harness.identity.externalId },
    });
    expect(harness.controller.getState()).toMatchObject({
      assistant_baseline: 2,
      pending: false,
      prompt_visible: false,
    });

    harness.setAssistantCount(3);
    harness.controller.evaluateNow();
    harness.setNativeResponse({
      type: "capture_result",
      status: "unavailable",
      reason: "native_host_unavailable",
      protocol_version: 1,
    });
    expect(harness.controller.saveNow()).toEqual({ ok: true });
    expect(harness.controller.getState()).toMatchObject({
      pending: true,
      prompt_visible: true,
      prompt_detail: "Open Reweave, then try Save again.",
    });
  });
});

describe("reminder background boundary", () => {
  function loadBackground() {
    let listener;
    let startupListener;
    let tabUpdatedListener;
    const calls = { badges: [], colors: [], native: [], queries: 0, titles: [] };
    const chrome = {
      action: {
        setBadgeBackgroundColor(options, callback) {
          calls.colors.push(options);
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
      runtime: {
        lastError: undefined,
        onMessage: { addListener(value) { listener = value; } },
        onStartup: { addListener(value) { startupListener = value; } },
        sendNativeMessage(_host, message, callback) {
          calls.native.push(message);
          callback({
            type: "capture_result",
            status: "saved",
            reason: "stored",
            protocol_version: 1,
          });
        },
      },
      scripting: { executeScript() { throw new Error("unexpected injection"); } },
      tabs: {
        onUpdated: { addListener(value) { tabUpdatedListener = value; } },
        query(_query, callback) {
          calls.queries += 1;
          callback([{ id: 4 }, { id: 9 }]);
        },
      },
    };
    vm.runInNewContext(backgroundSource, { chrome, TextEncoder, URL });
    return { calls, listener, startupListener, tabUpdatedListener };
  }

  function send(listener, message, sender) {
    let response;
    const asyncResult = listener(message, sender, (value) => {
      response = value;
    });
    return { asyncResult, response };
  }

  it("validates the top-frame sender, saves without reinjection, and clears badges on navigation/startup", () => {
    const background = loadBackground();
    const sender = {
      frameId: 0,
      url: identities.chatgpt.url,
      tab: { id: 4, url: identities.chatgpt.url },
    };

    expect(
      send(
        background.listener,
        {
          type: "reweave:reminder-pending",
          provider: "chatgpt",
          external_id: identities.chatgpt.externalId,
          assistant_count: 2,
        },
        sender,
      ),
    ).toEqual({ asyncResult: false, response: { ok: true } });
    expect(background.calls.badges.at(-1)).toEqual({ tabId: 4, text: "SAVE" });

    const invalid = send(
      background.listener,
      {
        type: "reweave:reminder-pending",
        provider: "claude",
        external_id: identities.chatgpt.externalId,
        assistant_count: 2,
      },
      sender,
    );
    expect(invalid.response).toEqual({ ok: false, reason: "invalid_sender" });

    const capture = {
      provider: "chatgpt",
      external_id: identities.chatgpt.externalId,
      title: "Reminder test",
      created_at: null,
      updated_at: null,
      messages: messagesForCount(2),
    };
    const saved = send(
      background.listener,
      { type: "reweave:save-reminder-capture", provider: "chatgpt", capture },
      sender,
    );
    expect(saved.asyncResult).toBe(true);
    expect(saved.response).toMatchObject({ status: "saved", provider: "chatgpt" });
    expect(background.calls.native).toHaveLength(1);
    expect(background.calls.queries).toBe(0);

    background.tabUpdatedListener(4, { status: "loading" });
    background.startupListener();
    expect(background.calls.queries).toBe(1);
    expect(background.calls.badges).toContainEqual({ tabId: 4, text: "" });
    expect(background.calls.badges).toContainEqual({ tabId: 9, text: "" });
  });
});
