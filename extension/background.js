const NATIVE_HOST = "com.reweave.bridge";
const PROTOCOL_VERSION = 1;
const MAX_CAPTURE_REQUEST_BYTES = 32 * 1024 * 1024;

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

function isSupportedChatGptUrl(value) {
  try {
    const url = new URL(value);
    return (
      url.protocol === "https:" &&
      ["chatgpt.com", "chat.openai.com"].includes(url.hostname.toLowerCase()) &&
      url.pathname.split("/").filter(Boolean).includes("c")
    );
  } catch {
    return false;
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

function saveChatGptConversation(sendResponse) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs?.[0];
    if (chrome.runtime.lastError || !tab?.id || !isSupportedChatGptUrl(tab.url)) {
      sendResponse(captureResponse("error", "unsupported_page"));
      return;
    }

    chrome.scripting.executeScript(
      {
        target: { tabId: tab.id },
        files: ["chatgpt-adapter.js"],
      },
      (results) => {
        if (chrome.runtime.lastError) {
          sendResponse(captureResponse("error", "page_access_failed"));
          return;
        }

        const extraction = results?.[0]?.result;
        if (!extraction || typeof extraction !== "object" || typeof extraction.ok !== "boolean") {
          sendResponse(captureResponse("incompatible", "malformed_adapter_response"));
          return;
        }
        if (!extraction.ok) {
          sendResponse(captureResponse("error", extraction.reason || "changed_dom"));
          return;
        }

        const nativeRequest = {
          type: "capture_conversation",
          protocol_version: PROTOCOL_VERSION,
          capture: extraction.capture,
        };
        const payloadBytes = new TextEncoder().encode(JSON.stringify(nativeRequest)).byteLength;
        if (payloadBytes > MAX_CAPTURE_REQUEST_BYTES) {
          sendResponse(captureResponse("error", "capture_too_large"));
          return;
        }

        chrome.runtime.sendNativeMessage(NATIVE_HOST, nativeRequest, (response) => {
          if (chrome.runtime.lastError) {
            sendResponse(captureResponse("unavailable", "native_host_unavailable"));
            return;
          }
          if (
            response?.type !== "capture_result" ||
            response?.protocol_version !== PROTOCOL_VERSION ||
            !["saved", "error", "unavailable", "incompatible"].includes(response.status)
          ) {
            sendResponse(captureResponse("incompatible", "malformed_response"));
            return;
          }
          sendResponse(response);
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
  if (message?.type === "reweave:save-chatgpt") {
    saveChatGptConversation(sendResponse);
    return true;
  }
  return false;
});
