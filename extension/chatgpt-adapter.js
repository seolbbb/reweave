(() => {
  const supportedHosts = new Set(["chatgpt.com", "chat.openai.com"]);
  const supportedRoles = new Set(["user", "assistant", "system", "tool"]);
  const reweaveBlockPattern = /<reweave_context>[\s\S]*?<\/reweave_context>/gi;
  const maxDraftChars = 20_000;
  const maxComposerChars = 28_000;

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

  function composerElement() {
    const selectors = [
      "#prompt-textarea",
      '[data-testid="composer-input"]',
      'textarea[data-id="root"]',
      'form textarea',
      'form [contenteditable="true"]',
    ];
    const matches = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
    const usable = [...new Set(matches)].filter(
      (node) =>
        !node.hasAttribute("hidden") &&
        node.getAttribute("aria-hidden") !== "true" &&
        node.getAttribute("aria-disabled") !== "true" &&
        !node.disabled,
    );
    return usable.length === 1 ? usable[0] : null;
  }

  function composerText(node) {
    const raw = typeof node.value === "string"
      ? node.value
      : typeof node.innerText === "string"
        ? node.innerText
        : node.textContent;
    return (raw || "").replace(/\r\n?/g, "\n").replace(/\u00a0/g, " ");
  }

  function draftWithoutContext(value) {
    return value
      .replace(reweaveBlockPattern, " ")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }

  function collectContextRequest() {
    const captureResult = captureConversation();
    if (!captureResult.ok) {
      return captureResult;
    }
    const messages = captureResult.capture.messages.map(({ role, content }) => ({ role, content }));
    if (
      messages.length > 500 ||
      messages.some(
        (message, index) =>
          !["user", "assistant"].includes(message.role) ||
          message.role !== (index % 2 === 0 ? "user" : "assistant"),
      ) ||
      messages.at(-1)?.role !== "assistant"
    ) {
      return failure("incomplete_conversation");
    }

    const composer = composerElement();
    if (!composer) {
      return failure("changed_dom");
    }
    const expectedDraft = composerText(composer);
    const draft = draftWithoutContext(expectedDraft);
    if (!draft) {
      return failure("empty_draft");
    }
    if (draft.length > maxDraftChars || expectedDraft.length > maxComposerChars) {
      return failure("draft_too_large");
    }
    return {
      ok: true,
      adapter_version: 1,
      provider: "chatgpt",
      external_id: captureResult.capture.external_id,
      messages,
      draft,
      expected_draft: expectedDraft,
      assistant_count: messages.filter((message) => message.role === "assistant").length,
    };
  }

  function setComposerText(node, value) {
    if (typeof node.value === "string") {
      const prototype = Object.getPrototypeOf(node);
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (setter) {
        setter.call(node, value);
      } else {
        node.value = value;
      }
    } else {
      node.textContent = value;
    }
    const InputEventConstructor = globalThis.InputEvent || globalThis.Event;
    node.dispatchEvent(
      new InputEventConstructor("input", {
        bubbles: true,
        composed: true,
        inputType: "insertText",
        data: value,
      }),
    );
  }

  function insertContext(insertionText, expectedDraft, expectedExternalId) {
    if (
      typeof insertionText !== "string" ||
      !/^<reweave_context>[\s\S]*<\/reweave_context>$/.test(insertionText) ||
      insertionText.length > 20_000 ||
      typeof expectedDraft !== "string" ||
      conversationIdFromLocation() !== expectedExternalId
    ) {
      return failure("invalid_context");
    }
    const composer = composerElement();
    if (!composer) {
      return failure("changed_dom");
    }
    if (composerText(composer) !== expectedDraft) {
      return failure("draft_changed");
    }
    const draft = draftWithoutContext(expectedDraft);
    if (!draft) {
      return failure("empty_draft");
    }
    const nextValue = `${insertionText}\n\n${draft}`;
    if (nextValue.length > maxComposerChars) {
      return failure("draft_too_large");
    }
    setComposerText(composer, nextValue);
    const insertedValue = typeof composer.value === "string" ? composer.value : composer.textContent;
    return insertedValue === nextValue
      ? { ok: true, context_chars: insertionText.length }
      : failure("insertion_failed");
  }

  globalThis.__reweaveProviderAdapter = Object.freeze({
    provider: "chatgpt",
    capture: captureConversation,
    collectContextRequest,
    insertContext,
    snapshot: reminderSnapshot,
  });

  return captureConversation();
})();
