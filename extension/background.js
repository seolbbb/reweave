const NATIVE_HOST = "com.reweave.bridge";
const PROTOCOL_VERSION = 1;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "reweave:check-availability") {
    return false;
  }

  chrome.runtime.sendNativeMessage(
    NATIVE_HOST,
    { type: "ping", protocol_version: PROTOCOL_VERSION },
    (response) => {
      const browserError = chrome.runtime.lastError;
      if (browserError) {
        sendResponse({
          type: "status",
          status: "unavailable",
          reason: "native_host_unavailable",
          protocol_version: PROTOCOL_VERSION,
        });
        return;
      }

      if (
        response?.type !== "status" ||
        response?.protocol_version !== PROTOCOL_VERSION ||
        !["ready", "unavailable", "incompatible", "error"].includes(response.status)
      ) {
        sendResponse({
          type: "status",
          status: "incompatible",
          reason: "malformed_response",
          protocol_version: PROTOCOL_VERSION,
        });
        return;
      }
      sendResponse(response);
    },
  );
  return true;
});
