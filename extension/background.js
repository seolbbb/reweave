const NATIVE_HOST = "com.reweave.bridge";
const PROTOCOL_VERSION = 1;
const MAX_CAPTURE_REQUEST_BYTES = 32 * 1024 * 1024;
const PROVIDERS = [
  {
    id: "chatgpt",
    adapter: "chatgpt-adapter.js",
    matches(url) {
      return (
        ["chatgpt.com", "chat.openai.com"].includes(url.hostname.toLowerCase()) &&
        url.pathname.split("/").filter(Boolean).includes("c")
      );
    },
  },
  {
    id: "claude",
    adapter: "claude-adapter.js",
    matches(url) {
      const parts = url.pathname.split("/").filter(Boolean);
      return (
        url.hostname.toLowerCase() === "claude.ai" &&
        parts.length === 2 &&
        parts[0] === "chat" &&
        /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(parts[1])
      );
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

function providerForUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") {
      return null;
    }
    return PROVIDERS.find((provider) => provider.matches(url)) || null;
  } catch {
    return null;
  }
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

function saveConversation(sendResponse) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs?.[0];
    const provider = providerForUrl(tab?.url);
    if (chrome.runtime.lastError || !tab?.id || !provider) {
      sendResponse(captureResponse("error", "unsupported_page"));
      return;
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id },
        files: [provider.adapter],
      },
      (results) => {
        if (chrome.runtime.lastError) {
          sendResponse(captureResponse("error", "page_access_failed", { provider: provider.id }));
          return;
        }

        const extraction = results?.[0]?.result;
        if (!extraction || typeof extraction !== "object" || typeof extraction.ok !== "boolean") {
          sendResponse(
            captureResponse("incompatible", "malformed_adapter_response", {
              provider: provider.id,
            }),
          );
          return;
        }
        if (!extraction.ok) {
          sendResponse(
            captureResponse("error", extraction.reason || "changed_dom", {
              provider: provider.id,
            }),
          );
          return;
        }
        if (extraction.capture?.provider !== provider.id) {
          sendResponse(
            captureResponse("incompatible", "malformed_adapter_response", {
              provider: provider.id,
            }),
          );
          return;
        }

        const nativeRequest = {
          type: "capture_conversation",
          protocol_version: PROTOCOL_VERSION,
          capture: extraction.capture,
        };
        const payloadBytes = new TextEncoder().encode(JSON.stringify(nativeRequest)).byteLength;
        if (payloadBytes > MAX_CAPTURE_REQUEST_BYTES) {
          sendResponse(
            captureResponse("error", "capture_too_large", { provider: provider.id }),
          );
          return;
        }

        chrome.runtime.sendNativeMessage(NATIVE_HOST, nativeRequest, (response) => {
          if (chrome.runtime.lastError) {
            sendResponse(
              captureResponse("unavailable", "native_host_unavailable", {
                provider: provider.id,
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
                provider: provider.id,
              }),
            );
            return;
          }
          sendResponse({ ...response, provider: provider.id });
        });
      },
    );
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "reweave:check-availability") {
    checkAvailability(sendResponse);
    return true;
  }
  if (message?.type === "reweave:save-conversation") {
    saveConversation(sendResponse);
    return true;
  }
  return false;
});
