(() => {
  const supportedHosts = new Set(["chatgpt.com", "chat.openai.com"]);
  const supportedRoles = new Set(["user", "assistant", "system", "tool"]);

  function failure(reason) {
    return { ok: false, reason };
  }

  function conversationIdFromLocation() {
    if (location.protocol !== "https:" || !supportedHosts.has(location.hostname.toLowerCase())) {
      return null;
    }
    const parts = location.pathname.split("/").filter(Boolean);
    const markerIndex = parts.indexOf("c");
    if (markerIndex < 0 || !parts[markerIndex + 1]) {
      return null;
    }
    const conversationId = parts[markerIndex + 1];
    if (conversationId.length > 200 || !/^[A-Za-z0-9_-]+$/.test(conversationId)) {
      return null;
    }
    return conversationId;
  }

  function isLoggedOut() {
    return Boolean(
      document.querySelector(
        '[data-testid="login-button"], a[href*="/auth/login"], button[data-testid*="login"]',
      ),
    );
  }

  function pageIsStreaming() {
    return Boolean(
      document.querySelector(
        [
          '[data-testid*="stop-button"]',
          '[data-testid*="stop-response"]',
          'button[aria-label*="Stop generating"]',
          'button[aria-label*="Stop response"]',
        ].join(","),
      ),
    );
  }

  function turnNodes() {
    const articleTurns = Array.from(
      document.querySelectorAll('article[data-testid^="conversation-turn-"]'),
    );
    const candidates = articleTurns.length
      ? articleTurns
      : Array.from(document.querySelectorAll('[data-testid^="conversation-turn-"]'));
    const candidateSet = new Set(candidates);
    return candidates.filter((node) => {
      let parent = node.parentElement;
      while (parent) {
        if (candidateSet.has(parent)) {
          return false;
        }
        parent = parent.parentElement;
      }
      return true;
    });
  }

  function completeTurnSequence(turns) {
    const positions = turns.map((turn) => {
      const testId = turn.getAttribute("data-testid") || "";
      const match = testId.match(/^conversation-turn-(\d+)$/);
      return match ? Number(match[1]) : null;
    });
    if (positions.some((position) => position === null)) {
      return "changed_dom";
    }
    if (positions[0] > 1) {
      return "incomplete_conversation";
    }
    return positions.every(
      (position, index) => index === 0 || position === positions[index - 1] + 1,
    )
      ? null
      : "incomplete_conversation";
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
          "[hidden]",
          '[aria-hidden="true"]',
          '[data-testid*="copy"]',
          '[data-testid*="feedback"]',
          '[data-testid*="regenerate"]',
          '[data-testid*="voice"]',
        ].join(","),
      )
      .forEach((element) => element.remove());
    const visibleText = typeof clone.innerText === "string" ? clone.innerText : clone.textContent;
    return (visibleText || "").replace(/\r\n?/g, "\n").replace(/\u00a0/g, " ").trim();
  }

  function contentForTurn(turn, roleRoot, role) {
    const preferredSelectors = [
      "[data-message-content]",
      ...(role === "assistant" ? [".markdown"] : [".whitespace-pre-wrap"]),
    ];
    for (const selector of preferredSelectors) {
      const candidates = Array.from(roleRoot.querySelectorAll(selector)).filter(
        (node, index, all) => !all.some((other, otherIndex) => otherIndex !== index && other.contains(node)),
      );
      if (candidates.length) {
        const content = candidates.map(normalizedText).filter(Boolean).join("\n\n");
        if (content) {
          return content;
        }
      }
    }
    return normalizedText(roleRoot || turn);
  }

  function awareTimestamp(value) {
    if (typeof value !== "string" || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value.trim())) {
      return null;
    }
    return Number.isNaN(Date.parse(value)) ? null : value.trim();
  }

  function timestampForTurn(turn) {
    const direct = turn.getAttribute("data-message-timestamp");
    const timed = turn.querySelector("time[datetime]")?.getAttribute("datetime");
    return awareTimestamp(direct) || awareTimestamp(timed);
  }

  function roleForTurn(turn) {
    const roleNode = turn.matches("[data-message-author-role]")
      ? turn
      : turn.querySelector("[data-message-author-role]");
    const role = roleNode?.getAttribute("data-message-author-role") || turn.getAttribute("data-turn");
    return supportedRoles.has(role) ? { role, roleNode: roleNode || turn } : null;
  }

  function externalMessageId(turn, conversationId, index) {
    const providerId =
      turn.getAttribute("data-message-id") ||
      turn.querySelector("[data-message-id]")?.getAttribute("data-message-id");
    if (providerId && providerId.trim().length <= 512) {
      return providerId.trim();
    }
    const testId = turn.getAttribute("data-testid") || "";
    const position = testId.match(/^conversation-turn-(\d+)$/)?.[1] || String(index);
    return `${conversationId}:turn:${position}`;
  }

  function reminderSnapshot() {
    const conversationId = conversationIdFromLocation();
    if (!conversationId) {
      return failure(isLoggedOut() ? "logged_out" : "unsupported_page");
    }

    const turns = turnNodes();
    if (!turns.length) {
      return failure(isLoggedOut() ? "logged_out" : "changed_dom");
    }
    const sequenceError = completeTurnSequence(turns);
    if (sequenceError) {
      return failure(sequenceError);
    }

    const roles = [];
    for (const turn of turns) {
      const roleResult = roleForTurn(turn);
      if (!roleResult) {
        return failure("changed_dom");
      }
      roles.push(roleResult.role);
    }
    if (roles[0] !== "user") {
      return failure("incomplete_conversation");
    }
    if (pageIsStreaming()) {
      return {
        ok: false,
        reason: "streaming",
        provider: "chatgpt",
        external_id: conversationId,
      };
    }

    return {
      ok: true,
      provider: "chatgpt",
      external_id: conversationId,
      message_count: turns.length,
      assistant_count: roles.filter((role) => role === "assistant").length,
    };
  }

  function conversationTitle() {
    const rawTitle = document.title
      .replace(/\s*[|–—-]\s*ChatGPT\s*$/i, "")
      .replace(/^ChatGPT\s*[|–—-]\s*/i, "")
      .trim();
    return rawTitle || "Untitled ChatGPT conversation";
  }

  function captureConversation() {
    const snapshot = reminderSnapshot();
    if (!snapshot.ok) {
      return failure(snapshot.reason);
    }

    const turns = turnNodes();
    const messages = [];
    for (const [index, turn] of turns.entries()) {
      const roleResult = roleForTurn(turn);
      if (!roleResult) {
        return failure("changed_dom");
      }
      const content = contentForTurn(turn, roleResult.roleNode, roleResult.role);
      if (!content) {
        return failure("invalid_conversation");
      }
      messages.push({
        external_id: externalMessageId(turn, snapshot.external_id, index),
        role: roleResult.role,
        content,
        timestamp: timestampForTurn(turn),
      });
    }

    if (new Set(messages.map((message) => message.external_id)).size !== messages.length) {
      return failure("invalid_conversation");
    }

    const timestamps = messages.map((message) => message.timestamp).filter(Boolean);
    return {
      ok: true,
      adapter_version: 1,
      capture: {
        provider: "chatgpt",
        external_id: snapshot.external_id,
        title: conversationTitle(),
        created_at: timestamps[0] || null,
        updated_at: timestamps[timestamps.length - 1] || null,
        messages,
      },
    };
  }

  globalThis.__reweaveProviderAdapter = Object.freeze({
    provider: "chatgpt",
    capture: captureConversation,
    snapshot: reminderSnapshot,
  });

  return captureConversation();
})();
