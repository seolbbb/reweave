const NATIVE_HOST = "com.reweave.bridge";
const PROTOCOL_VERSION = 1;
const MAX_CAPTURE_REQUEST_BYTES = 32 * 1024 * 1024;
const MAX_CONTEXT_REQUEST_BYTES = 512 * 1024;
const CONTEXT_BUDGET_CHARS = 6_000;
const DEFAULT_ACTION_TITLE = "Reweave";
const REMINDER_ACTION_TITLE = "Unsaved conversation — Save to Reweave";
const PROVIDERS = [
  {
    id: "chatgpt",
    adapter: "chatgpt-adapter.js",
    externalId(url) {
      if (!["chatgpt.com", "chat.openai.com"].includes(url.hostname.toLowerCase())) {
        return null;
      }
      const parts = url.pathname.split("/").filter(Boolean);
      const markerIndex = parts.indexOf("c");
      const value = markerIndex >= 0 ? parts[markerIndex + 1] : null;
      return value && value.length <= 200 && /^[A-Za-z0-9_-]+$/.test(value) ? value : null;
    },
  },
  {
    id: "claude",
    adapter: "claude-adapter.js",
    externalId(url) {
      const parts = url.pathname.split("/").filter(Boolean);
      const value = parts.length === 2 && parts[0] === "chat" ? parts[1] : null;
      return url.hostname.toLowerCase() === "claude.ai" &&
        value &&
        /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
        ? value
        : null;
    },
  },
];

function statusResponse(status, reason) {
  return {
    type: "status",
    status,
    reason,
    protocol_version: PROTOCOL_VERSION,
  };
}

function captureResponse(status, reason, extra = {}) {
  return {
    type: "capture_result",
    status,
    reason,
    protocol_version: PROTOCOL_VERSION,
    ...extra,
  };
}

function contextResponse(status, reason, extra = {}) {
  return {
    type: "context_result",
    status,
    reason,
    protocol_version: PROTOCOL_VERSION,
    ...extra,
  };
}

function contextForUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") {
      return null;
    }
    for (const provider of PROVIDERS) {
      const externalId = provider.externalId(url);
      if (externalId) {
        return { provider, externalId };
      }
    }
    return null;
  } catch {
    return null;
  }
}

function clearTabReminder(tabId) {
  if (!Number.isInteger(tabId)) {
    return;
  }
  chrome.action.setBadgeText({ tabId, text: "" }, () => void chrome.runtime.lastError);
  chrome.action.setTitle(
    { tabId, title: DEFAULT_ACTION_TITLE },
    () => void chrome.runtime.lastError,
  );
}

function setTabReminder(tabId) {
  chrome.action.setBadgeBackgroundColor(
    { tabId, color: "#ea580c" },
    () => void chrome.runtime.lastError,
  );
  chrome.action.setBadgeText({ tabId, text: "SAVE" }, () => void chrome.runtime.lastError);
  chrome.action.setTitle(
    { tabId, title: REMINDER_ACTION_TITLE },
    () => void chrome.runtime.lastError,
  );
}

function checkAvailability(sendResponse) {
  chrome.runtime.sendNativeMessage(
    NATIVE_HOST,
    { type: "ping", protocol_version: PROTOCOL_VERSION },
    (response) => {
      const browserError = chrome.runtime.lastError;
      if (browserError) {
        sendResponse(statusResponse("unavailable", "native_host_unavailable"));
        return;
      }

      if (
        response?.type !== "status" ||
        response?.protocol_version !== PROTOCOL_VERSION ||
        !["ready", "unavailable", "incompatible", "error"].includes(response.status)
      ) {
        sendResponse(statusResponse("incompatible", "malformed_response"));
        return;
      }
      sendResponse(response);
    },
  );
}

function captureMatchesContext(capture, context) {
  return Boolean(
    capture &&
      typeof capture === "object" &&
      capture.provider === context.provider.id &&
      capture.external_id === context.externalId &&
      Array.isArray(capture.messages),
  );
}

function contextExtractionMatches(extraction, context) {
  if (
    !extraction ||
    typeof extraction !== "object" ||
    extraction.ok !== true ||
    extraction.provider !== context.provider.id ||
    extraction.external_id !== context.externalId ||
    typeof extraction.draft !== "string" ||
    !extraction.draft.trim() ||
    extraction.draft.length > 20_000 ||
    typeof extraction.expected_draft !== "string" ||
    extraction.expected_draft.length > 28_000 ||
    !Array.isArray(extraction.messages) ||
    extraction.messages.length > 500 ||
    !Number.isInteger(extraction.assistant_count) ||
    extraction.assistant_count < 1
  ) {
    return false;
  }
  let totalChars = 0;
  for (const [index, message] of extraction.messages.entries()) {
    if (
      !message ||
      typeof message !== "object" ||
      message.role !== (index % 2 === 0 ? "user" : "assistant") ||
      typeof message.content !== "string" ||
      !message.content.trim() ||
      message.content.length > 50_000
    ) {
      return false;
    }
    totalChars += message.content.length;
  }
  return (
    extraction.messages.at(-1)?.role === "assistant" &&
    totalChars <= 200_000 &&
    extraction.assistant_count ===
      extraction.messages.filter((message) => message.role === "assistant").length
  );
}

function collectContextRequestFromPage() {
  const adapter = globalThis.__reweaveProviderAdapter;
  return typeof adapter?.collectContextRequest === "function"
    ? adapter.collectContextRequest()
    : { ok: false, reason: "changed_dom" };
}

function insertContextIntoPage(insertionText, expectedDraft, expectedExternalId) {
  const adapter = globalThis.__reweaveProviderAdapter;
  return typeof adapter?.insertContext === "function"
    ? adapter.insertContext(insertionText, expectedDraft, expectedExternalId)
    : { ok: false, reason: "changed_dom" };
}

function forwardCapture(context, capture, sendResponse, onSaved = () => {}) {
  const nativeRequest = {
    type: "capture_conversation",
    protocol_version: PROTOCOL_VERSION,
    capture,
  };
  const payloadBytes = new TextEncoder().encode(JSON.stringify(nativeRequest)).byteLength;
  if (payloadBytes > MAX_CAPTURE_REQUEST_BYTES) {
    sendResponse(captureResponse("error", "capture_too_large", { provider: context.provider.id }));
    return;
  }

  chrome.runtime.sendNativeMessage(NATIVE_HOST, nativeRequest, (response) => {
    if (chrome.runtime.lastError) {
      sendResponse(
        captureResponse("unavailable", "native_host_unavailable", {
          provider: context.provider.id,
        }),
      );
      return;
    }
    if (
      response?.type !== "capture_result" ||
      response?.protocol_version !== PROTOCOL_VERSION ||
      !["saved", "error", "unavailable", "incompatible"].includes(response.status)
    ) {
      sendResponse(
        captureResponse("incompatible", "malformed_response", {
          provider: context.provider.id,
        }),
      );
      return;
    }
    if (response.status === "saved") {
      onSaved();
    }
    sendResponse({ ...response, provider: context.provider.id });
  });
}

function installReminder(tabId, context, capture, done) {
  clearTabReminder(tabId);
  chrome.scripting.executeScript(
    {
      target: { tabId },
      files: ["reminder.js"],
    },
    () => {
      if (chrome.runtime.lastError) {
        clearTabReminder(tabId);
        done(false);
        return;
      }
      const assistantCount = capture.messages.filter(
        (message) => message?.role === "assistant",
      ).length;
      chrome.tabs.sendMessage(
        tabId,
        {
          type: "reweave:start-reminder",
          provider: context.provider.id,
          external_id: context.externalId,
          assistant_count: assistantCount,
        },
        (response) => {
          const failed = Boolean(chrome.runtime.lastError) || response?.ok !== true;
          if (failed) {
            clearTabReminder(tabId);
          }
          done(!failed);
        },
      );
    },
  );
}

function forwardContextAssembly(context, extraction, sendResponse, onReady) {
  const contextRequest = {
    provider: context.provider.id,
    external_id: context.externalId,
    messages: extraction.messages,
    draft: extraction.draft,
    destination: "private",
    allowed_scopes: [],
    max_context_chars: CONTEXT_BUDGET_CHARS,
  };
  const nativeRequest = {
    type: "assemble_context",
    protocol_version: PROTOCOL_VERSION,
    context_request: contextRequest,
  };
  const payloadBytes = new TextEncoder().encode(JSON.stringify(nativeRequest)).byteLength;
  if (payloadBytes > MAX_CONTEXT_REQUEST_BYTES) {
    sendResponse(
      contextResponse("error", "context_request_too_large", {
        provider: context.provider.id,
      }),
    );
    return;
  }

  chrome.runtime.sendNativeMessage(NATIVE_HOST, nativeRequest, (response) => {
    if (chrome.runtime.lastError) {
      sendResponse(
        contextResponse("unavailable", "native_host_unavailable", {
          provider: context.provider.id,
        }),
      );
      return;
    }
    const validReady =
      response?.status === "ready" &&
      typeof response.insertion_text === "string" &&
      /^<reweave_context>[\s\S]*<\/reweave_context>$/.test(response.insertion_text) &&
      response.insertion_text.length <= 20_000 &&
      Number.isInteger(response.item_count) &&
      response.item_count > 0 &&
      response.context_chars === response.insertion_text.length;
    if (
      response?.type !== "context_result" ||
      response?.protocol_version !== PROTOCOL_VERSION ||
      !["ready", "error", "unavailable", "incompatible"].includes(response.status) ||
      (response.status === "ready" && !validReady)
    ) {
      sendResponse(
        contextResponse("incompatible", "malformed_response", {
          provider: context.provider.id,
        }),
      );
      return;
    }
    if (response.status !== "ready") {
      sendResponse({ ...response, provider: context.provider.id });
      return;
    }
    onReady(response);
  });
}

function useReweave(sendResponse) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs?.[0];
    const context = contextForUrl(tab?.url);
    if (chrome.runtime.lastError || !Number.isInteger(tab?.id) || !context) {
      sendResponse(contextResponse("error", "unsupported_page"));
      return;
    }

    chrome.scripting.executeScript(
      { target: { tabId: tab.id }, files: [context.provider.adapter] },
      () => {
        if (chrome.runtime.lastError) {
          sendResponse(
            contextResponse("error", "page_access_failed", { provider: context.provider.id }),
          );
          return;
        }
        chrome.scripting.executeScript(
          { target: { tabId: tab.id }, func: collectContextRequestFromPage },
          (results) => {
            if (chrome.runtime.lastError) {
              sendResponse(
                contextResponse("error", "page_access_failed", { provider: context.provider.id }),
              );
              return;
            }
            const extraction = results?.[0]?.result;
            if (!extraction || typeof extraction !== "object" || typeof extraction.ok !== "boolean") {
              sendResponse(
                contextResponse("incompatible", "malformed_adapter_response", {
                  provider: context.provider.id,
                }),
              );
              return;
            }
            if (!extraction.ok) {
              sendResponse(
                contextResponse("error", extraction.reason || "changed_dom", {
                  provider: context.provider.id,
                }),
              );
              return;
            }
            if (!contextExtractionMatches(extraction, context)) {
              sendResponse(
                contextResponse("incompatible", "malformed_adapter_response", {
                  provider: context.provider.id,
                }),
              );
              return;
            }

            forwardContextAssembly(context, extraction, sendResponse, (nativeResponse) => {
              chrome.scripting.executeScript(
                {
                  target: { tabId: tab.id },
                  func: insertContextIntoPage,
                  args: [
                    nativeResponse.insertion_text,
                    extraction.expected_draft,
                    context.externalId,
                  ],
                },
                (insertResults) => {
                  if (chrome.runtime.lastError) {
                    sendResponse(
                      contextResponse("error", "page_access_failed", {
                        provider: context.provider.id,
                      }),
                    );
                    return;
                  }
                  const insertion = insertResults?.[0]?.result;
                  if (!insertion?.ok) {
                    sendResponse(
                      contextResponse("error", insertion?.reason || "insertion_failed", {
                        provider: context.provider.id,
                      }),
                    );
                    return;
                  }
                  installReminder(
                    tab.id,
                    context,
                    { messages: extraction.messages },
                    () =>
                      sendResponse(
                        contextResponse("inserted", "context_inserted", {
                          provider: context.provider.id,
                          item_count: nativeResponse.item_count,
                          context_chars: nativeResponse.context_chars,
                        }),
                      ),
                  );
                },
              );
            });
          },
        );
      },
    );
  });
}

function saveConversation(sendResponse) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs?.[0];
    const context = contextForUrl(tab?.url);
    if (chrome.runtime.lastError || !Number.isInteger(tab?.id) || !context) {
      sendResponse(captureResponse("error", "unsupported_page"));
      return;
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id },
        files: [context.provider.adapter],
      },
      (results) => {
        if (chrome.runtime.lastError) {
          sendResponse(
            captureResponse("error", "page_access_failed", { provider: context.provider.id }),
          );
          return;
        }

        const extraction = results?.[0]?.result;
        if (!extraction || typeof extraction !== "object" || typeof extraction.ok !== "boolean") {
          sendResponse(
            captureResponse("incompatible", "malformed_adapter_response", {
              provider: context.provider.id,
            }),
          );
          return;
        }
        if (!extraction.ok) {
          sendResponse(
            captureResponse("error", extraction.reason || "changed_dom", {
              provider: context.provider.id,
            }),
          );
          return;
        }
        if (!captureMatchesContext(extraction.capture, context)) {
          sendResponse(
            captureResponse("incompatible", "malformed_adapter_response", {
              provider: context.provider.id,
            }),
          );
          return;
        }

        forwardCapture(context, extraction.capture, (response) => {
          if (response.status !== "saved") {
            sendResponse(response);
            return;
          }
          installReminder(tab.id, context, extraction.capture, () => sendResponse(response));
        });
      },
    );
  });
}

function senderContext(sender) {
  if (!Number.isInteger(sender?.tab?.id) || (sender.frameId ?? 0) !== 0) {
    return null;
  }
  const context = contextForUrl(sender.url || sender.tab.url);
  return context ? { ...context, tabId: sender.tab.id } : null;
}

function handleReminderPending(message, sender, sendResponse) {
  const context = senderContext(sender);
  const valid = Boolean(
    context &&
      message.provider === context.provider.id &&
      message.external_id === context.externalId &&
      Number.isInteger(message.assistant_count) &&
      message.assistant_count > 0,
  );
  if (!valid) {
    sendResponse({ ok: false, reason: "invalid_sender" });
    return;
  }
  setTabReminder(context.tabId);
  sendResponse({ ok: true });
}

function handleReminderClear(message, sender, sendResponse) {
  const context = senderContext(sender);
  if (!context || message.provider !== context.provider.id) {
    sendResponse({ ok: false, reason: "invalid_sender" });
    return;
  }
  clearTabReminder(context.tabId);
  sendResponse({ ok: true });
}

function saveReminderCapture(message, sender, sendResponse) {
  const context = senderContext(sender);
  if (
    !context ||
    message.provider !== context.provider.id ||
    !captureMatchesContext(message.capture, context)
  ) {
    sendResponse(captureResponse("error", "invalid_sender"));
    return;
  }
  forwardCapture(context, message.capture, sendResponse, () => clearTabReminder(context.tabId));
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "reweave:check-availability") {
    checkAvailability(sendResponse);
    return true;
  }
  if (message?.type === "reweave:save-conversation") {
    saveConversation(sendResponse);
    return true;
  }
  if (message?.type === "reweave:use-context") {
    useReweave(sendResponse);
    return true;
  }
  if (message?.type === "reweave:reminder-pending") {
    handleReminderPending(message, sender, sendResponse);
    return false;
  }
  if (message?.type === "reweave:reminder-clear") {
    handleReminderClear(message, sender, sendResponse);
    return false;
  }
  if (message?.type === "reweave:save-reminder-capture") {
    saveReminderCapture(message, sender, sendResponse);
    return true;
  }
  return false;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    clearTabReminder(tabId);
  }
});

chrome.runtime.onStartup.addListener(() => {
  chrome.tabs.query({}, (tabs) => {
    if (chrome.runtime.lastError) {
      return;
    }
    for (const tab of tabs || []) {
      clearTabReminder(tab.id);
    }
  });
});
