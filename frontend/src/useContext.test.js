import fs from "node:fs";
import vm from "node:vm";
import { parseHTML } from "linkedom";
import { describe, expect, it } from "vitest";

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
const contextBlock = [
  "<reweave_context>",
  "[Reweave:project-high] Preserve project provenance.",
  "</reweave_context>",
].join("\n");

const providers = [
  {
    id: "chatgpt",
    file: "chatgpt-adapter.js",
    fixture: "chatgpt_current_conversation.html",
    url: "https://chatgpt.com/c/conversation-42",
    externalId: "conversation-42",
    draft: "Draft a source-grounded release note.",
    addComposer(html, draft) {
      return html.replace(
        "</body>",
        `<footer><div id="prompt-textarea" contenteditable="true">${draft}</div></footer></body>`,
      );
    },
    composer: "#prompt-textarea",
  },
  {
    id: "claude",
    file: "claude-adapter.js",
    fixture: "claude_current_conversation.html",
    url: "https://claude.ai/chat/12345678-1234-4234-8234-123456789abc",
    externalId: "12345678-1234-4234-8234-123456789abc",
    draft: "Unsent draft must not be captured.",
    addComposer(html, draft) {
      return html.replace("Unsent draft must not be captured.", draft);
    },
    composer: '[data-testid="composer-input"]',
  },
];

function fixture(name) {
  return fs.readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), "utf8");
}

function loadAdapter(provider, draft = provider.draft, html = fixture(provider.fixture)) {
  const parsed = parseHTML(provider.addComposer(html, draft));
  const context = {
    document: parsed.document,
    location: new URL(provider.url),
    Set,
    Event: parsed.window.Event,
    InputEvent: parsed.window.InputEvent || parsed.window.Event,
  };
  vm.runInNewContext(
    fs.readFileSync(new URL(`../../extension/${provider.file}`, import.meta.url), "utf8"),
    context,
  );
  return {
    document: parsed.document,
    window: parsed.window,
    adapter: context.__reweaveProviderAdapter,
  };
}

describe.each(providers)("$id explicit Use adapter", (provider) => {
  it("collects the complete chat and non-empty draft only on explicit Use", () => {
    const { adapter } = loadAdapter(provider);

    const result = adapter.collectContextRequest();

    expect(result).toMatchObject({
      ok: true,
      provider: provider.id,
      external_id: provider.externalId,
      draft: provider.draft,
      expected_draft: provider.draft,
    });
    expect(result.messages).toHaveLength(provider.id === "chatgpt" ? 2 : 4);
    expect(result.messages.every((message, index) => message.role === (index % 2 ? "assistant" : "user"))).toBe(true);
  });

  it("inserts one identifiable block, preserves the draft, and replaces only on request", () => {
    const { adapter, document } = loadAdapter(provider);
    const first = adapter.collectContextRequest();

    expect(
      adapter.insertContext(contextBlock, first.expected_draft, provider.externalId),
    ).toEqual({ ok: true, context_chars: contextBlock.length });
    const composer = document.querySelector(provider.composer);
    expect(composer.textContent).toBe(`${contextBlock}\n\n${provider.draft}`);

    const refreshedRequest = adapter.collectContextRequest();
    const refreshedBlock = contextBlock.replace("project-high", "project-refreshed");
    expect(refreshedRequest.draft).toBe(provider.draft);
    expect(
      adapter.insertContext(
        refreshedBlock,
        refreshedRequest.expected_draft,
        provider.externalId,
      ).ok,
    ).toBe(true);
    expect(composer.textContent).toBe(`${refreshedBlock}\n\n${provider.draft}`);
    expect(composer.textContent.match(/<reweave_context>/g)).toHaveLength(1);
  });

  it("fails closed for empty, oversized, changed, and streaming drafts", () => {
    expect(loadAdapter(provider, "   ").adapter.collectContextRequest().reason).toBe("empty_draft");
    expect(loadAdapter(provider, "x".repeat(20_001)).adapter.collectContextRequest().reason).toBe(
      "draft_too_large",
    );

    const loaded = loadAdapter(provider);
    const request = loaded.adapter.collectContextRequest();
    loaded.document.querySelector(provider.composer).textContent = "The user kept typing.";
    expect(
      loaded.adapter.insertContext(contextBlock, request.expected_draft, provider.externalId).reason,
    ).toBe("draft_changed");

    const streamingHtml = fixture(provider.fixture).replace(
      "<main>",
      '<main><button data-testid="stop-response">Stop</button>',
    );
    expect(loadAdapter(provider, provider.draft, streamingHtml).adapter.collectContextRequest().reason).toBe(
      "streaming",
    );
  });
});

function loadBackground({ insertion = { ok: true }, nativeStatus = "ready", nativeReplies = [], url = "https://chatgpt.com/c/conversation-42" } = {}) {
  let listener;
  const extraction = {
    ok: true,
    provider: "chatgpt",
    external_id: "conversation-42",
    messages: [
      { role: "user", content: "Continue Reweave." },
      { role: "assistant", content: "Source provenance matters." },
    ],
    draft: "Draft a source-grounded release note.",
    expected_draft: "Draft a source-grounded release note.",
    assistant_count: 1,
  };
  const calls = { tabQueries: 0, injections: [], nativeMessages: [], tabMessages: [] };
  const chrome = {
    runtime: {
      id: "synthetic-extension",
      getURL: (path) => `chrome-extension://synthetic-extension/${path}`,
      lastError: undefined,
      onMessage: { addListener(callback) { listener = callback; } },
      onStartup: { addListener() {} },
      sendNativeMessage(_host, message, callback) {
        calls.nativeMessages.push(message);
        if (message.type === "ping") {
          callback({ type: "status", status: "ready", reason: "connected", protocol_version: 1 });
          return;
        }
        if (nativeReplies.length) {
          callback({ type: "context_result", protocol_version: 1, ...nativeReplies.shift() });
          return;
        }
        if (nativeStatus !== "ready") {
          callback({
            type: "context_result",
            status: "error",
            reason: nativeStatus,
            protocol_version: 1,
          });
          return;
        }
        callback({
          type: "context_result",
          status: "ready",
          reason: "context_ready",
          protocol_version: 1,
          insertion_text: contextBlock,
          item_count: 1,
          context_chars: contextBlock.length,
        });
      },
    },
    tabs: {
      onUpdated: { addListener() {} },
      query(_query, callback) {
        calls.tabQueries += 1;
        callback([{ id: 17, url }]);
      },
      sendMessage(tabId, message, callback) {
        calls.tabMessages.push({ tabId, message });
        callback({ ok: true });
      },
    },
    scripting: {
      executeScript(options, callback) {
        calls.injections.push(options);
        if (options.files?.[0] === "reminder.js") {
          callback([{ frameId: 0, result: { ok: true } }]);
          return;
        }
        if (options.files) {
          callback([{ frameId: 0, result: { ok: true } }]);
          return;
        }
        callback([{ frameId: 0, result: options.args ? insertion : extraction }]);
      },
    },
    action: {
      setBadgeBackgroundColor(_options, callback) { callback?.(); },
      setBadgeText(_options, callback) { callback?.(); },
      setTitle(_options, callback) { callback?.(); },
    },
  };
  vm.runInNewContext(backgroundSource, { chrome, URL, TextEncoder });
  return { listener, calls };
}

function sendMessage(listener, message) {
  return new Promise((resolve) => {
    expect(listener(message, { id: "synthetic-extension", url: "chrome-extension://synthetic-extension/popup.html" }, resolve)).toBe(true);
  });
}

describe("explicit Use background and popup", () => {
  it("does not inspect the provider page before Use or infer private rights from its address", async () => {
    const { listener, calls } = loadBackground();

    expect(calls.tabQueries).toBe(0);
    await sendMessage(listener, { type: "reweave:check-availability" });
    expect(calls.tabQueries).toBe(0);
    expect(calls.injections).toHaveLength(0);

    const result = await sendMessage(listener, { type: "reweave:use-context" });

    expect(result).toMatchObject({ status: "inserted", item_count: 1, provider: "chatgpt" });
    expect(calls.tabQueries).toBe(1);
    expect(calls.nativeMessages.at(-1)).toMatchObject({
      type: "assemble_context",
      protocol_version: 1,
      context_request: {
        action: "use",
        draft: "Draft a source-grounded release note.",
      },
    });
    expect(calls.nativeMessages.at(-1).context_request.destination).toBeUndefined();
    expect(calls.nativeMessages.at(-1).context_request.allowed_scopes).toBeUndefined();
    expect(calls.injections.map((entry) => entry.files?.[0] || entry.func.name)).toEqual([
      "chatgpt-adapter.js",
      "collectContextRequestFromPage",
      "insertContextIntoPage",
      "reminder.js",
    ]);
    expect(calls.tabMessages.at(-1).message).toMatchObject({
      type: "reweave:start-reminder",
      provider: "chatgpt",
      assistant_count: 1,
    });
  });

  it("leaves the draft unchanged and skips reminders after an insertion race", async () => {
    const { listener, calls } = loadBackground({ insertion: { ok: false, reason: "draft_changed" } });

    const result = await sendMessage(listener, { type: "reweave:use-context" });

    expect(result).toMatchObject({ status: "error", reason: "draft_changed" });
    expect(calls.tabMessages).toHaveLength(0);
  });

  it("renders an explicit Use action and actionable result states", () => {
    const { document, window } = parseHTML(popupHtml);
    const chrome = {
      runtime: {
        lastError: undefined,
        sendMessage(message, callback) {
          callback(
            message.type === "reweave:check-availability"
              ? { status: "ready" }
              : { status: "inserted", item_count: 1, provider: "chatgpt" },
          );
        },
      },
    };
    vm.runInNewContext(popupSource, { chrome, document });

    const useButton = document.querySelector("#use");
    expect(useButton.hidden).toBe(false);
    useButton.dispatchEvent(new window.Event("click"));
    expect(document.querySelector("#title").textContent).toBe("Context added to your draft");
    expect(useButton.textContent).toBe("Refresh Reweave context");
  });
});


describe("destination and sensitive trust in the extension", () => {
  it("returns destination review without inserting or installing a reminder", async () => {
    const { listener, calls } = loadBackground({ nativeReplies: [{
      status: "destination_confirmation_required", destination_revision: 0, spaces: [],
    }] });
    const result = await sendMessage(listener, { type: "reweave:use-context" });
    expect(result.status).toBe("destination_confirmation_required");
    expect(result.external_id).toBe("conversation-42");
    expect(calls.injections.map(x => x.func?.name)).not.toContain("insertContextIntoPage");
    expect(calls.tabMessages).toEqual([]);
  });

  it("requires an explicit retry after remembering a destination", async () => {
    const { listener, calls } = loadBackground({ nativeReplies: [{ status: "destination_saved", destination: "private", destination_revision: 1 }] });
    const result = await sendMessage(listener, { type: "reweave:use-context", options: {
      action: "save_destination", destination: "private", allowed_space_ids: [], expected_revision: 0,
      expected_identity: { provider: "chatgpt", external_id: "conversation-42" },
    } });
    expect(result.status).toBe("destination_saved");
    expect(calls.nativeMessages).toHaveLength(1);
    expect(calls.injections.some(x => x.func?.name === "insertContextIntoPage")).toBe(false);
  });

  it("rejects page and content-script approval messages before reading any page", () => {
    const { listener, calls } = loadBackground();
    let result;
    expect(listener({ type: "reweave:use-context", options: { action: "save_destination", destination: "private" } }, {
      id: "synthetic-extension", url: "https://chatgpt.com/c/conversation-42", tab: { id: 17 },
    }, value => { result = value; })).toBe(false);
    expect(result.reason).toBe("invalid_sender");
    expect(calls.tabQueries).toBe(0);
    expect(calls.nativeMessages).toEqual([]);
  });

  it("does not apply an earlier conversation's choices to the new active tab", async () => {
    const { listener, calls } = loadBackground();
    const result = await sendMessage(listener, { type: "reweave:use-context", options: {
      action: "save_destination", expected_identity: { provider: "claude", external_id: "different" },
    } });
    expect(result.reason).toBe("conversation_changed");
    expect(calls.injections).toEqual([]);
  });

  it("consumes sensitive confirmation only for the same explicit action and preserves draft checks", async () => {
    const { listener, calls } = loadBackground({ nativeReplies: [{ status: "sensitive_confirmed", confirmation_token: "one-use-token" }], insertion: { ok: false, reason: "draft_changed" } });
    const result = await sendMessage(listener, { type: "reweave:use-context", options: {
      action: "confirm_sensitive", preview_token: "preview", selected_items: [{ item_id: "project-high", version: 1 }],
    } });
    expect(calls.nativeMessages).toHaveLength(2);
    expect(calls.nativeMessages[1].context_request.confirmation_token).toBe("one-use-token");
    expect(calls.nativeMessages[1].context_request.draft).toBe(calls.nativeMessages[0].context_request.draft);
    expect(result.reason).toBe("draft_changed");
    expect(calls.tabMessages).toEqual([]);
  });

  it("checks the provider again before insertion after a cross-provider navigation", async () => {
    const { listener, calls } = loadBackground();
    await sendMessage(listener, { type: "reweave:use-context" });
    const insertion = calls.injections.find(x => x.func?.name === "insertContextIntoPage");
    let inserted = false;
    const result = vm.runInNewContext(`(${insertion.func.toString()})(...args)`, {
      args: insertion.args,
      __reweaveProviderAdapter: { provider: "claude", insertContext() { inserted = true; return { ok: true }; } },
    });
    expect(result.reason).toBe("conversation_changed");
    expect(inserted).toBe(false);
  });

  it("shows local preview text safely and never selects sensitive items automatically", () => {
    const { document, window } = parseHTML(popupHtml);
    const messages = [];
    const chrome = { runtime: { sendMessage(message, callback) {
      messages.push(message);
      if (message.type === "reweave:check-availability") return callback({ status: "ready" });
      callback({ status: "sensitive_preview", provider: "chatgpt", external_id: "conversation-42", destination: "private", preview_token: "preview", items: [{
        item_id: "sensitive", version: 2, text: "<script>bad()</script> Sensitive claim.", epistemic_kind: "inferred", confidence: 0.6,
        sources: [{ provider: "test", title: "Synthetic evidence", message_index: 0, excerpt: "Evidence text." }],
      }] });
    } } };
    vm.runInNewContext(popupSource, { chrome, document });
    document.querySelector("#use").dispatchEvent(new window.Event("click"));
    expect(document.querySelector("#sensitive-panel").hidden).toBe(false);
    expect(document.querySelector("#sensitive-items script")).toBeNull();
    expect(document.querySelector("#sensitive-items").textContent).toContain("<script>bad()</script>");
    expect(document.querySelector("#confirm-sensitive").disabled).toBe(true);
    expect(messages).toHaveLength(2);
  });

  it("requires a destination choice and does not Use automatically after saving", () => {
    const { document, window } = parseHTML(popupHtml);
    const messages = [];
    const chrome = { runtime: { sendMessage(message, callback) {
      messages.push(message);
      if (message.type === "reweave:check-availability") return callback({ status: "ready" });
      if (message.options?.action === "save_destination") return callback({ status: "destination_saved", provider: "chatgpt", external_id: "conversation-42", destination: "private", destination_revision: 1 });
      callback({ status: "destination_confirmation_required", provider: "chatgpt", external_id: "conversation-42", destination: "unknown", destination_revision: 0, spaces: [] });
    } } };
    vm.runInNewContext(popupSource, { chrome, document });
    document.querySelector("#use").dispatchEvent(new window.Event("click"));
    expect(document.querySelector("#destination-panel").hidden).toBe(false);
    expect(document.querySelector("#remember-destination").disabled).toBe(true);
    const choice = document.querySelector("#destination-choice");
    choice.querySelector('[value="private"]').selected = true;
    choice.dispatchEvent(new window.Event("change"));
    document.querySelector("#remember-destination").dispatchEvent(new window.Event("click"));
    expect(messages.at(-1).options.action).toBe("save_destination");
    expect(messages).toHaveLength(3);
    expect(document.querySelector("#use").textContent).toBe("Use with saved destination");
  });
});
