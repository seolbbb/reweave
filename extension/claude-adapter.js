(() => {
  const conversationIdPattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
  const userSelectors = [
    '[data-testid="user-message"]',
    ".font-user-message",
    '[data-testid*="human-message"]',
  ];
  const assistantSelectors = [
    ".font-claude-response",
    ".font-claude-response-body",
    '[data-testid="chat-message-text"]',
    '[data-testid*="assistant-message"]',
  ];

  function failure(reason) {
    return { ok: false, reason };
  }

  function conversationIdFromLocation() {
    if (location.protocol !== "https:" || location.hostname.toLowerCase() !== "claude.ai") {
      return null;
    }
    const parts = location.pathname.split("/").filter(Boolean);
    if (parts.length !== 2 || parts[0] !== "chat" || !conversationIdPattern.test(parts[1])) {
      return null;
    }
    return parts[1];
  }

  function isLoggedOut() {
    return Boolean(
      document.querySelector(
        '[data-testid="login-button"], [data-testid*="login"], a[href*="/login"], a[href*="/signup"]',
      ),
    );
  }

  function isWithinComposer(node) {
    return Boolean(
      node.closest(
        'form, footer, textarea, [contenteditable="true"], [data-testid*="composer"], [data-testid*="input"]',
      ),
    );
  }

  function normalizedText(node) {
    const clone = node.cloneNode(true);
    clone
      .querySelectorAll(
        [
          "button",
          "svg",
          "script",
          "style",
          "noscript",
          "textarea",
          '[contenteditable="true"]',
          '[role="toolbar"]',
          '[aria-hidden="true"]',
          ".sr-only",
          '[class*="sr-only"]',
          '[data-testid*="copy"]',
          '[data-testid*="feedback"]',
          '[data-testid*="retry"]',
        ].join(","),
      )
      .forEach((element) => element.remove());
    const visibleText = typeof clone.innerText === "string" ? clone.innerText : clone.textContent;
    return (visibleText || "")
      .replace(/\r\n?/g, "\n")
      .replace(/\u00a0/g, " ")
      .replace(/[ \t]+\n/g, "\n")
      .trim();
  }

  function preferredMessageSelector(selectors) {
    for (const selector of selectors) {
      const matches = Array.from(document.querySelectorAll(selector)).filter(
        (node) => !isWithinComposer(node) && normalizedText(node),
      );
      const deepest = matches.filter(
        (node) => !matches.some((other) => other !== node && node.contains(other)),
      );
      if (deepest.length) {
        return selector;
      }
    }
    return null;
  }

  function preferredStructuralSelector(selectors) {
    for (const selector of selectors) {
      const matches = Array.from(document.querySelectorAll(selector)).filter(
        (node) => !isWithinComposer(node),
      );
      const deepest = matches.filter(
        (node) => !matches.some((other) => other !== node && node.contains(other)),
      );
      if (deepest.length) {
        return selector;
      }
    }
    return null;
  }

  function pageHasIncompleteHistory() {
    return Boolean(
      document.querySelector(
        [
          '[data-testid*="load-more"]',
          '[data-testid*="show-more"]',
          '[data-testid*="older-message"]',
          '[data-testid*="earlier-message"]',
        ].join(","),
      ),
    );
  }

  function pageIsStreaming() {
    return Boolean(
      document.querySelector(
        [
          '[data-testid*="stop-response"]',
          '[data-testid*="stop-button"]',
          'button[aria-label*="Stop response"]',
          'button[aria-label*="Stop generating"]',
        ].join(","),
      ),
    );
  }

  function awareTimestamp(value) {
    if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value.trim())) {
      return null;
    }
    return Number.isNaN(Date.parse(value)) ? null : value.trim();
  }

  function timestampForMessage(node) {
    const container = node.closest("[data-message-timestamp]");
    const direct = node.getAttribute("data-message-timestamp");
    const inherited = container?.getAttribute("data-message-timestamp");
    const timed = node.closest("[data-message-id]")?.querySelector("time[datetime]")?.getAttribute("datetime");
    return awareTimestamp(direct) || awareTimestamp(inherited) || awareTimestamp(timed);
  }

  function externalMessageId(node, conversationId, index) {
    const container = node.closest("[data-message-id], [data-uuid]");
    const providerId =
      node.getAttribute("data-message-id") ||
      node.getAttribute("data-uuid") ||
      container?.getAttribute("data-message-id") ||
      container?.getAttribute("data-uuid");
    if (providerId && providerId.trim().length <= 512) {
      return providerId.trim();
    }
    return `${conversationId}:turn:${index}`;
  }

  function reminderSnapshot() {
    const conversationId = conversationIdFromLocation();
    if (!conversationId) {
      return failure(isLoggedOut() ? "logged_out" : "unsupported_page");
    }
    if (pageHasIncompleteHistory()) {
      return failure("incomplete_conversation");
    }

    const userSelector = preferredStructuralSelector(userSelectors);
    const assistantSelector = preferredStructuralSelector(assistantSelectors);
    if (!userSelector && !assistantSelector) {
      return failure(isLoggedOut() ? "logged_out" : "changed_dom");
    }

    const combinedSelector = [userSelector, assistantSelector].filter(Boolean).join(",");
    const turns = Array.from(document.querySelectorAll(combinedSelector))
      .filter((node) => !isWithinComposer(node))
      .map((node) => ({
        role: userSelector && node.matches(userSelector) ? "user" : "assistant",
      }));
    const userCount = turns.filter((turn) => turn.role === "user").length;
    const assistantCount = turns.length - userCount;

    if (
      turns[0]?.role !== "user" ||
      assistantCount > userCount ||
      userCount - assistantCount > 1 ||
      turns.some((turn, index) => turn.role !== (index % 2 === 0 ? "user" : "assistant"))
    ) {
      return failure("incomplete_conversation");
    }
    if (pageIsStreaming()) {
      return {
        ok: false,
        reason: "streaming",
        provider: "claude",
        external_id: conversationId,
      };
    }

    return {
      ok: true,
      provider: "claude",
      external_id: conversationId,
      message_count: turns.length,
      assistant_count: assistantCount,
    };
  }

  function conversationTitle() {
    const rawTitle = document.title
      .replace(/\s*[|–—-]\s*Claude\s*$/i, "")
      .replace(/^Claude\s*[|–—-]\s*/i, "")
      .trim();
    return rawTitle && !/^Claude$/i.test(rawTitle) ? rawTitle : "Untitled Claude conversation";
  }

  function captureConversation() {
    const snapshot = reminderSnapshot();
    if (!snapshot.ok) {
      return failure(snapshot.reason);
    }

    const userSelector = preferredMessageSelector(userSelectors);
    const assistantSelector = preferredMessageSelector(assistantSelectors);
    if (!userSelector && !assistantSelector) {
      return failure(isLoggedOut() ? "logged_out" : "changed_dom");
    }

    const combinedSelector = [userSelector, assistantSelector].filter(Boolean).join(",");
    const turns = Array.from(document.querySelectorAll(combinedSelector))
      .filter((node) => !isWithinComposer(node) && normalizedText(node))
      .map((node) => ({
        role: userSelector && node.matches(userSelector) ? "user" : "assistant",
        node,
      }));

    const messages = turns.map(({ role, node }, index) => ({
      external_id: externalMessageId(node, snapshot.external_id, index),
      role,
      content: normalizedText(node),
      timestamp: timestampForMessage(node),
    }));
    if (
      messages.length !== snapshot.message_count ||
      messages[0]?.role !== "user" ||
      messages.filter((message) => message.role === "assistant").length !==
        snapshot.assistant_count ||
      messages.some(
        (message, index) => message.role !== (index % 2 === 0 ? "user" : "assistant"),
      )
    ) {
      return failure("incomplete_conversation");
    }
    if (messages.some((message) => !message.content)) {
      return failure("invalid_conversation");
    }
    if (new Set(messages.map((message) => message.external_id)).size !== messages.length) {
      return failure("invalid_conversation");
    }

    const timestamps = messages.map((message) => message.timestamp).filter(Boolean);
    return {
      ok: true,
      adapter_version: 1,
      capture: {
        provider: "claude",
        external_id: snapshot.external_id,
        title: conversationTitle(),
        created_at: timestamps[0] || null,
        updated_at: timestamps[timestamps.length - 1] || null,
        messages,
      },
    };
  }

  globalThis.__reweaveProviderAdapter = Object.freeze({
    provider: "claude",
    capture: captureConversation,
    snapshot: reminderSnapshot,
  });

  return captureConversation();
})();
