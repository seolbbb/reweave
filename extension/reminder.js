(() => {
  const existing = globalThis.__reweaveReminderController;
  if (existing) {
    return { ok: true, reused: true };
  }

  const REMINDER_IDLE_MS = 30_000;
  const PROMPT_VISIBLE_MS = 8_000;
  const IDENTITY_CHECK_MS = 1_000;
  const state = {
    active: false,
    provider: null,
    externalId: null,
    assistantBaseline: 0,
    pending: false,
    saving: false,
  };
  let observer = null;
  let idleTimer = null;
  let hideTimer = null;
  let identityTimer = null;
  let host = null;
  let card = null;
  let detail = null;
  let saveButton = null;
  let dismissButton = null;

  function sendExtensionMessage(message, callback = () => {}) {
    try {
      chrome.runtime.sendMessage(message, (response) => {
        const failed = Boolean(chrome.runtime.lastError);
        callback(failed ? null : response);
      });
    } catch {
      callback(null);
    }
  }

  function providerAdapter() {
    const adapter = globalThis.__reweaveProviderAdapter;
    return adapter && typeof adapter.capture === "function" && typeof adapter.snapshot === "function"
      ? adapter
      : null;
  }

  function currentExternalId(provider) {
    try {
      const url = new URL(location.href);
      if (url.protocol !== "https:") {
        return null;
      }
      const parts = url.pathname.split("/").filter(Boolean);
      if (provider === "chatgpt") {
        if (!["chatgpt.com", "chat.openai.com"].includes(url.hostname.toLowerCase())) {
          return null;
        }
        const markerIndex = parts.indexOf("c");
        const value = markerIndex >= 0 ? parts[markerIndex + 1] : null;
        return value && value.length <= 200 && /^[A-Za-z0-9_-]+$/.test(value) ? value : null;
      }
      if (provider === "claude") {
        const value = parts.length === 2 && parts[0] === "chat" ? parts[1] : null;
        return url.hostname.toLowerCase() === "claude.ai" &&
          value &&
          /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value)
          ? value
          : null;
      }
      return null;
    } catch {
      return null;
    }
  }

  function identityIsCurrent() {
    return Boolean(
      state.active &&
        state.externalId &&
        currentExternalId(state.provider) === state.externalId,
    );
  }

  function clearTimer(name) {
    if (name === "idle" && idleTimer !== null) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    if (name === "hide" && hideTimer !== null) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (name === "identity" && identityTimer !== null) {
      clearInterval(identityTimer);
      identityTimer = null;
    }
  }

  function clearBadge() {
    if (!state.provider) {
      return;
    }
    sendExtensionMessage({
      type: "reweave:reminder-clear",
      provider: state.provider,
    });
  }

  function setPromptVisible(visible) {
    if (!card) {
      return;
    }
    card.hidden = !visible;
  }

  function ensurePrompt() {
    if (host?.isConnected) {
      return;
    }

    host = document.createElement("div");
    host.setAttribute("data-reweave-reminder-host", "true");
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        :host {
          color-scheme: light dark;
          position: fixed;
          right: 20px;
          bottom: 20px;
          z-index: 2147483000;
          width: min(360px, calc(100vw - 32px));
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
            "Segoe UI", sans-serif;
          font-size: 16px;
          line-height: 1.5;
          pointer-events: none;
        }
        * { box-sizing: border-box; }
        [hidden] { display: none !important; }
        .card {
          display: grid;
          gap: 14px;
          padding: 16px;
          color: #0f172a;
          background: #ffffff;
          border: 1px solid #cbd5e1;
          border-radius: 12px;
          box-shadow: 0 12px 32px rgb(15 23 42 / 0.18);
          pointer-events: auto;
          animation: reweave-enter 180ms ease-out;
        }
        .heading { display: flex; align-items: flex-start; gap: 10px; }
        .mark {
          flex: 0 0 auto;
          width: 24px;
          height: 24px;
          margin-top: 2px;
          border: 6px solid #2563eb;
          border-radius: 50%;
          box-shadow: inset 0 0 0 2px #ffffff;
        }
        .eyebrow {
          margin: 0 0 2px;
          color: #475569;
          font-size: 12px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        .title { margin: 0; font-size: 17px; font-weight: 700; line-height: 1.3; }
        .detail { margin: 4px 0 0; color: #475569; font-size: 14px; }
        .actions { display: grid; grid-template-columns: 1fr auto; gap: 8px; }
        button {
          min-height: 44px;
          padding: 10px 14px;
          border: 0;
          border-radius: 10px;
          color: #ffffff;
          background: #2563eb;
          font: inherit;
          font-weight: 700;
          cursor: pointer;
          touch-action: manipulation;
          transition: background-color 180ms ease-out, opacity 180ms ease-out;
        }
        button:hover { background: #1d4ed8; }
        button:focus-visible { outline: 3px solid #ea580c; outline-offset: 2px; }
        button:disabled { cursor: wait; opacity: 0.62; }
        button.secondary {
          color: #0f172a;
          background: #f1f5f9;
          box-shadow: inset 0 0 0 1px #cbd5e1;
        }
        button.secondary:hover { background: #e2e8f0; }
        @keyframes reweave-enter {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @media (max-width: 420px) {
          :host { right: 16px; bottom: 16px; }
          .actions { grid-template-columns: 1fr; }
        }
        @media (prefers-color-scheme: dark) {
          .card { color: #f8fafc; background: #1e293b; border-color: #475569; }
          .mark { border-color: #60a5fa; box-shadow: inset 0 0 0 2px #1e293b; }
          .eyebrow, .detail { color: #cbd5e1; }
          button { color: #0f172a; background: #60a5fa; }
          button:hover { background: #93c5fd; }
          button:focus-visible { outline-color: #fb923c; }
          button.secondary { color: #f8fafc; background: #334155; box-shadow: inset 0 0 0 1px #475569; }
          button.secondary:hover { background: #475569; }
        }
        @media (prefers-reduced-motion: reduce) {
          .card { animation: none; }
          button { transition: none; }
        }
      </style>
      <section class="card" role="region" aria-labelledby="reweave-reminder-title" hidden>
        <div class="heading">
          <span class="mark" aria-hidden="true"></span>
          <div>
            <p class="eyebrow">Reweave</p>
            <p class="title" id="reweave-reminder-title">Save your latest conversation?</p>
            <p class="detail" role="status" aria-live="polite">A new response is ready to save.</p>
          </div>
        </div>
        <div class="actions">
          <button type="button" data-action="save">Save to Reweave</button>
          <button type="button" class="secondary" data-action="dismiss">Not now</button>
        </div>
      </section>
    `;
    card = shadow.querySelector(".card");
    detail = shadow.querySelector(".detail");
    saveButton = shadow.querySelector('[data-action="save"]');
    dismissButton = shadow.querySelector('[data-action="dismiss"]');
    saveButton.addEventListener("click", (event) => {
      if (event.isTrusted) {
        saveNow();
      }
    });
    dismissButton.addEventListener("click", (event) => {
      if (event.isTrusted) {
        dismissNow();
      }
    });
    shadow.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && event.isTrusted) {
        dismissNow();
      }
    });
    document.documentElement.append(host);
  }

  function stop() {
    clearTimer("idle");
    clearTimer("hide");
    clearTimer("identity");
    observer?.disconnect();
    observer = null;
    clearBadge();
    host?.remove();
    host = null;
    card = null;
    detail = null;
    saveButton = null;
    dismissButton = null;
    state.active = false;
    state.pending = false;
    state.saving = false;
  }

  function showReminder(snapshot) {
    if (state.pending || !state.active) {
      return;
    }
    state.pending = true;
    ensurePrompt();
    detail.textContent = "A new response is ready to save.";
    saveButton.textContent = "Save to Reweave";
    saveButton.disabled = false;
    dismissButton.disabled = false;
    setPromptVisible(true);
    sendExtensionMessage({
      type: "reweave:reminder-pending",
      provider: state.provider,
      external_id: state.externalId,
      assistant_count: snapshot.assistant_count,
    });
    clearTimer("hide");
    hideTimer = setTimeout(() => {
      hideTimer = null;
      setPromptVisible(false);
    }, PROMPT_VISIBLE_MS);
  }

  function evaluateNow() {
    if (!state.active) {
      return { active: false };
    }
    if (!identityIsCurrent()) {
      stop();
      return { active: false, reason: "navigation" };
    }

    const adapter = providerAdapter();
    const snapshot = adapter?.snapshot();
    if (!snapshot?.ok) {
      if (
        snapshot?.reason === "streaming" &&
        snapshot.provider === state.provider &&
        snapshot.external_id === state.externalId
      ) {
        return { active: true, pending: state.pending, reason: "streaming" };
      }
      stop();
      return { active: false, reason: snapshot?.reason || "changed_dom" };
    }
    if (
      snapshot.provider !== state.provider ||
      snapshot.external_id !== state.externalId ||
      snapshot.assistant_count < state.assistantBaseline
    ) {
      stop();
      return { active: false, reason: "identity_changed" };
    }
    if (snapshot.assistant_count > state.assistantBaseline) {
      showReminder(snapshot);
    }
    return {
      active: true,
      pending: state.pending,
      assistant_count: snapshot.assistant_count,
    };
  }

  function scheduleEvaluation() {
    if (!state.active) {
      return;
    }
    if (!identityIsCurrent()) {
      stop();
      return;
    }
    clearTimer("idle");
    idleTimer = setTimeout(() => {
      idleTimer = null;
      evaluateNow();
    }, REMINDER_IDLE_MS);
  }

  function mutationTouchesConversation(records) {
    const selector = [
      '[data-testid^="conversation-turn-"]',
      '[data-testid="user-message"]',
      '[data-testid*="human-message"]',
      '[data-testid="chat-message-text"]',
      '[data-testid*="assistant-message"]',
      ".font-user-message",
      ".font-claude-response",
      ".font-claude-response-body",
    ].join(",");
    const touches = (node) => {
      const element = node?.nodeType === 1 ? node : node?.parentElement;
      return Boolean(
        element &&
          (element.matches?.(selector) ||
            element.closest?.(selector) ||
            element.querySelector?.(selector)),
      );
    };
    return records.some(
      (record) =>
        touches(record.target) ||
        Array.from(record.addedNodes || []).some(touches) ||
        Array.from(record.removedNodes || []).some(touches),
    );
  }

  function handleMutations(records) {
    if (!identityIsCurrent()) {
      stop();
      return;
    }
    if (mutationTouchesConversation(records)) {
      scheduleEvaluation();
    }
  }

  function dismissNow() {
    if (!state.active) {
      return { ok: false, reason: "inactive" };
    }
    const snapshot = providerAdapter()?.snapshot();
    if (!snapshot?.ok || snapshot.external_id !== state.externalId) {
      stop();
      return { ok: false, reason: snapshot?.reason || "changed_dom" };
    }
    state.assistantBaseline = snapshot.assistant_count;
    state.pending = false;
    clearTimer("hide");
    setPromptVisible(false);
    clearBadge();
    return { ok: true, assistant_count: state.assistantBaseline };
  }

  function saveNow() {
    if (!state.active || state.saving) {
      return { ok: false, reason: state.saving ? "saving" : "inactive" };
    }
    const adapter = providerAdapter();
    const extraction = adapter?.capture();
    if (
      !extraction?.ok ||
      extraction.capture?.provider !== state.provider ||
      extraction.capture?.external_id !== state.externalId
    ) {
      if (extraction?.reason === "streaming") {
        ensurePrompt();
        detail.textContent = "Wait for the response to finish, then save again.";
        setPromptVisible(true);
        return { ok: false, reason: "streaming" };
      }
      stop();
      return { ok: false, reason: extraction?.reason || "changed_dom" };
    }

    state.saving = true;
    ensurePrompt();
    clearTimer("hide");
    setPromptVisible(true);
    detail.textContent = "Saving the complete conversation locally…";
    saveButton.textContent = "Saving…";
    saveButton.disabled = true;
    dismissButton.disabled = true;
    sendExtensionMessage(
      {
        type: "reweave:save-reminder-capture",
        provider: state.provider,
        capture: extraction.capture,
      },
      (response) => {
        state.saving = false;
        if (response?.status === "saved") {
          state.assistantBaseline = extraction.capture.messages.filter(
            (message) => message.role === "assistant",
          ).length;
          state.pending = false;
          clearBadge();
          setPromptVisible(false);
          return;
        }
        detail.textContent =
          response?.reason === "app_not_running" ||
          response?.reason === "native_host_unavailable" ||
          response?.status === "unavailable"
            ? "Open Reweave, then try Save again."
            : "Could not save. No archive changes were made.";
        saveButton.textContent = "Try Save again";
        saveButton.disabled = false;
        dismissButton.disabled = false;
        setPromptVisible(true);
      },
    );
    return { ok: true };
  }

  function start(message) {
    const adapter = providerAdapter();
    if (
      !adapter ||
      !["chatgpt", "claude"].includes(message.provider) ||
      adapter.provider !== message.provider ||
      typeof message.external_id !== "string" ||
      !Number.isInteger(message.assistant_count) ||
      message.assistant_count < 0
    ) {
      stop();
      return { ok: false, reason: "invalid_baseline" };
    }

    state.active = true;
    state.provider = message.provider;
    state.externalId = message.external_id;
    state.assistantBaseline = message.assistant_count;
    state.pending = false;
    state.saving = false;
    if (!identityIsCurrent()) {
      stop();
      return { ok: false, reason: "identity_changed" };
    }

    const snapshot = adapter.snapshot();
    const validSnapshot =
      (snapshot?.ok || snapshot?.reason === "streaming") &&
      snapshot.provider === state.provider &&
      snapshot.external_id === state.externalId;
    if (!validSnapshot) {
      stop();
      return { ok: false, reason: snapshot?.reason || "changed_dom" };
    }

    ensurePrompt();
    setPromptVisible(false);
    clearTimer("idle");
    clearTimer("hide");
    observer?.disconnect();
    observer = new MutationObserver(handleMutations);
    observer.observe(document.documentElement, {
      attributes: true,
      characterData: true,
      childList: true,
      subtree: true,
    });
    clearTimer("identity");
    identityTimer = setInterval(() => {
      if (!identityIsCurrent()) {
        stop();
      }
    }, IDENTITY_CHECK_MS);
    clearBadge();
    if (snapshot.ok && snapshot.assistant_count > state.assistantBaseline) {
      scheduleEvaluation();
    }
    return { ok: true };
  }

  const controller = Object.freeze({
    dismissNow,
    evaluateNow,
    getState() {
      return {
        active: state.active,
        provider: state.provider,
        external_id: state.externalId,
        assistant_baseline: state.assistantBaseline,
        pending: state.pending,
        saving: state.saving,
        prompt_visible: Boolean(card && !card.hidden),
        prompt_detail: detail?.textContent || null,
      };
    },
    saveNow,
    scheduleEvaluation,
    start,
    stop,
  });
  globalThis.__reweaveReminderController = controller;
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "reweave:start-reminder") {
      return false;
    }
    sendResponse(controller.start(message));
    return false;
  });
  addEventListener("pagehide", () => controller.stop(), { once: true });

  return { ok: true, reused: false };
})();
