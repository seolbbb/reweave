import fs from "node:fs";
import vm from "node:vm";
import { parseHTML } from "linkedom";
import { describe, expect, it } from "vitest";

const adapterSource = fs.readFileSync(
  new URL("../../extension/chatgpt-adapter.js", import.meta.url),
  "utf8",
);
const backgroundSource = fs.readFileSync(
  new URL("../../extension/background.js", import.meta.url),
  "utf8",
);

function fixture(name) {
  return fs.readFileSync(new URL(`../../tests/fixtures/${name}`, import.meta.url), "utf8");
}

function runAdapter(html, url = "https://chatgpt.com/c/conversation-42") {
  const { document } = parseHTML(html);
  return vm.runInNewContext(adapterSource, {
    document,
    location: new URL(url),
    Set,
  });
}

function loadBackground({ extraction, encoder = TextEncoder } = {}) {
  let listener;
  const calls = {
    nativeMessages: [],
    tabQueries: 0,
    injections: [],
  };
  const chrome = {
    runtime: {
      lastError: undefined,
      onMessage: {
        addListener(registered) {
          listener = registered;
        },
      },
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
          message_count: 2,
        });
      },
    },
    tabs: {
      query(_query, callback) {
        calls.tabQueries += 1;
        callback([{ id: 17, url: "https://chatgpt.com/c/conversation-42" }]);
      },
    },
    scripting: {
      executeScript(options, callback) {
        calls.injections.push(options);
        callback([{ frameId: 0, result: extraction }]);
      },
    },
  };
  vm.runInNewContext(backgroundSource, { chrome, URL, TextEncoder: encoder });
  return { listener, calls };
}

function sendRuntimeMessage(listener, message) {
  return new Promise((resolve) => {
    expect(listener(message, {}, resolve)).toBe(true);
  });
}

describe("ChatGPT explicit Save adapter", () => {
  it("normalizes a complete ordered fixture without provider toolbar text", () => {
    const result = runAdapter(fixture("chatgpt_current_conversation.html"));

    expect(result.ok).toBe(true);
    expect(result.capture).toEqual({
      provider: "chatgpt",
      external_id: "conversation-42",
      title: "Reweave delivery plan",
      created_at: "2026-07-21T09:00:00Z",
      updated_at: "2026-07-21T09:00:30+00:00",
      messages: [
        {
          external_id: "message-user-1",
          role: "user",
          content: "Keep this exact question.\nSecond line.",
          timestamp: "2026-07-21T09:00:00Z",
        },
        {
          external_id: "message-assistant-1",
          role: "assistant",
          content: "This answer stays ordered.\nNo toolbar text is captured.",
          timestamp: "2026-07-21T09:00:30+00:00",
        },
      ],
    });
  });

  it("fails closed for logged-out, changed-DOM, and unsupported pages", () => {
    expect(runAdapter(fixture("chatgpt_logged_out.html")).reason).toBe("logged_out");
    expect(runAdapter(fixture("chatgpt_changed_dom.html")).reason).toBe("changed_dom");
    expect(
      runAdapter(fixture("chatgpt_current_conversation.html"), "https://example.com/c/42").reason,
    ).toBe("unsupported_page");
    expect(
      runAdapter(fixture("chatgpt_current_conversation.html"), "http://chatgpt.com/c/42").reason,
    ).toBe("unsupported_page");
  });

  it("rejects missing leading or middle turns instead of saving a partial conversation", () => {
    const current = fixture("chatgpt_current_conversation.html");
    const missingBeginning = current
      .replace("conversation-turn-0", "conversation-turn-12")
      .replace("conversation-turn-1", "conversation-turn-13");
    const missingMiddle = current.replace("conversation-turn-1", "conversation-turn-2");

    expect(runAdapter(missingBeginning).reason).toBe("incomplete_conversation");
    expect(runAdapter(missingMiddle).reason).toBe("incomplete_conversation");
  });

  it("does not inspect a tab during availability checks and injects only after Save", async () => {
    const extraction = runAdapter(fixture("chatgpt_current_conversation.html"));
    const { listener, calls } = loadBackground({ extraction });

    expect(calls.tabQueries).toBe(0);
    expect(calls.injections).toHaveLength(0);

    const availability = await sendRuntimeMessage(listener, {
      type: "reweave:check-availability",
    });
    expect(availability.status).toBe("ready");
    expect(calls.tabQueries).toBe(0);
    expect(calls.injections).toHaveLength(0);

    const saved = await sendRuntimeMessage(listener, { type: "reweave:save-conversation" });
    expect(saved.outcome).toBe("created");
    expect(saved.provider).toBe("chatgpt");
    expect(calls.tabQueries).toBe(1);
    expect(calls.injections).toEqual([
      { target: { tabId: 17 }, files: ["chatgpt-adapter.js"] },
    ]);
    expect(calls.nativeMessages.at(-1)).toEqual({
      type: "capture_conversation",
      protocol_version: 1,
      capture: extraction.capture,
    });
  });

  it("reports an oversized capture before starting the native host", async () => {
    class OversizedEncoder {
      encode() {
        return { byteLength: 32 * 1024 * 1024 + 1 };
      }
    }
    const extraction = runAdapter(fixture("chatgpt_current_conversation.html"));
    const { listener, calls } = loadBackground({ extraction, encoder: OversizedEncoder });

    const result = await sendRuntimeMessage(listener, { type: "reweave:save-conversation" });

    expect(result).toMatchObject({ status: "error", reason: "capture_too_large" });
    expect(calls.nativeMessages).toHaveLength(0);
  });
});
