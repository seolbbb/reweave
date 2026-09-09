const title = document.querySelector("#title");
const detail = document.querySelector("#detail");
const retry = document.querySelector("#retry");
const save = document.querySelector("#save");
const useContext = document.querySelector("#use");
const destinationPanel = document.querySelector("#destination-panel");
const destinationChoice = document.querySelector("#destination-choice");
const scopeChoices = document.querySelector("#scope-choices");
const rememberDestination = document.querySelector("#remember-destination");
const sensitivePanel = document.querySelector("#sensitive-panel");
const sensitiveItems = document.querySelector("#sensitive-items");
const confirmSensitive = document.querySelector("#confirm-sensitive");
const reviewSensitive = document.querySelector("#review-sensitive");
const changeDestination = document.querySelector("#change-destination");
let currentIdentity = null;
let destinationRevision = 0;
let previewToken = null;

function appendText(parent, tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  parent.appendChild(element);
  return element;
}

function renderDestination(response) {
  document.body.dataset.status = "ready";
  title.textContent = "Choose this conversation's destination";
  detail.textContent = "Your draft is unchanged. The saved choice applies only to this conversation.";
  destinationPanel.hidden = false;
  sensitivePanel.hidden = true;
  useContext.hidden = true;
  reviewSensitive.hidden = true;
  destinationRevision = response.destination_revision;
  destinationChoice.value = response.destination === "unknown" ? "" : response.destination;
  document.querySelector("#destination-hint").textContent = response.suggested_destination
    ? `Local context suggests ${response.suggested_destination}. Confirm the actual destination yourself.`
    : "The page address does not establish who can see this conversation.";
  scopeChoices.replaceChildren();
  appendText(scopeChoices, "legend", "Allowed spaces");
  for (const space of response.spaces || []) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = space.space_id;
    checkbox.dataset.scopeType = space.scope_type;
    checkbox.checked = (response.allowed_space_ids || []).includes(space.space_id);
    label.appendChild(checkbox);
    appendText(label, "span", `${space.name} (${space.scope_type})${space.suggested ? " · suggested" : ""}`);
    scopeChoices.appendChild(label);
  }
  filterDestinationScopes();
}

function filterDestinationScopes() {
  const types = {
    private: ["core_self", "personal", "work", "project", "topic", "destination"],
    work: ["core_self", "work", "project", "topic", "destination"],
    client: ["core_self", "project", "topic", "destination"],
    shared: ["core_self", "project", "topic", "destination"],
  }[destinationChoice.value] || [];
  for (const input of scopeChoices.querySelectorAll("input")) {
    input.disabled = !types.includes(input.dataset.scopeType);
    if (input.disabled) input.checked = false;
  }
  const selected = scopeChoices.querySelectorAll("input:checked").length;
  rememberDestination.disabled = !destinationChoice.value || (destinationChoice.value !== "private" && selected === 0);
}

function renderSensitive(response) {
  title.textContent = "Select sensitive items to use once";
  detail.textContent = "Nothing from this preview has been inserted. Review the claims and their evidence.";
  document.body.dataset.status = "ready";
  destinationPanel.hidden = true;
  sensitivePanel.hidden = false;
  previewToken = response.preview_token;
  sensitiveItems.replaceChildren();
  document.querySelector("#sensitive-hint").textContent = `Destination: ${response.destination}. Inferences remain uncertain even when you approve their use.`;
  for (const item of response.items || []) {
    const article = document.createElement("article");
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = item.item_id;
    input.dataset.version = String(item.version);
    label.appendChild(input);
    appendText(label, "span", `${item.epistemic_kind} · confidence ${Math.round(item.confidence * 100)}% · version ${item.version}`);
    article.appendChild(label);
    appendText(article, "p", item.text);
    if (item.inference_rationale) appendText(article, "p", `Rationale: ${item.inference_rationale}`, "detail");
    for (const source of item.sources || []) {
      appendText(article, "p", `${source.provider} · ${source.title} · message ${source.message_index + 1}${source.source_changed ? " · source changed" : ""}${source.source_available === false ? " · preserved source snapshot" : ""}`, "privacy-note");
      appendText(article, "blockquote", source.excerpt || "No evidence excerpt available.");
    }
    sensitiveItems.appendChild(article);
  }
  if (!response.items?.length) appendText(sensitiveItems, "p", "No relevant sensitive items are available within the approved scopes and preview size limit.");
  confirmSensitive.disabled = true;
}

const stateCopy = {
  ready: {
    title: "Use or save this conversation",
    detail: "Add relevant local context to your draft, or save the complete conversation.",
    use: true,
    save: true,
    retry: false,
  },
  unavailable: {
    title: "Open Reweave to continue",
    detail: "Start the desktop app, then retry the connection.",
    use: false,
    save: false,
    retry: true,
  },
  incompatible: {
    title: "Update Reweave",
    detail: "The app and extension use different bridge versions. Update both, then retry.",
    use: false,
    save: false,
    retry: true,
  },
};

function renderStatus(status) {
  const safeStatus = stateCopy[status] ? status : "unavailable";
  const copy = stateCopy[safeStatus];
  document.body.dataset.status = safeStatus;
  title.textContent = copy.title;
  detail.textContent = copy.detail;
  useContext.hidden = !copy.use;
  useContext.disabled = false;
  useContext.textContent = "Use Reweave context";
  save.hidden = !copy.save;
  save.disabled = false;
  save.textContent = "Save current conversation";
  retry.hidden = !copy.retry;
}

function renderSaveResult(response) {
  retry.hidden = true;
  useContext.hidden = false;
  save.hidden = false;
  save.disabled = false;
  save.textContent = "Save again";

  if (response?.status === "saved") {
    const outcomeCopy = {
      created: ["Saved to Reweave", "The complete conversation is now in your local library."],
      updated: ["Updated in Reweave", "New or changed messages were saved to your local library."],
      unchanged: ["Already up to date", "Reweave already has this exact conversation."],
    };
    const copy = outcomeCopy[response.outcome] || outcomeCopy.updated;
    document.body.dataset.status = "saved";
    title.textContent = copy[0];
    detail.textContent = response.message_count
      ? `${copy[1]} ${response.message_count} messages checked.`
      : copy[1];
    return;
  }

  const providerName = response?.provider === "claude" ? "Claude" : "ChatGPT";
  const errorCopy = {
    unsupported_page: [
      "Open a supported conversation",
      "Save works on an open ChatGPT or Claude conversation page.",
    ],
    logged_out: [
      `Sign in to ${providerName}`,
      `Sign in to ${providerName}, open a conversation, then try Save again.`,
    ],
    changed_dom: [`${providerName} page changed`, "Reload the conversation and try again."],
    page_access_failed: [
      "Could not read this page",
      `Keep the ${providerName} tab active and try Save again.`,
    ],
    malformed_adapter_response: [
      "Update the extension",
      `The ${providerName} adapter is incompatible with this extension.`,
    ],
    incomplete_conversation: ["Load the whole conversation", "Scroll to the beginning, let it finish loading, then save again."],
    invalid_conversation: ["Could not validate this conversation", `Reload the ${providerName} conversation and try again.`],
    capture_too_large: ["Conversation is too large", "This conversation exceeds the safe local transfer limit."],
    invalid_capture: ["Could not validate this conversation", "No archive changes were made. Reload and try again."],
    app_not_running: ["Open Reweave to continue", "Start the desktop app, then save again."],
    connection_failed: ["Reconnect to Reweave", "Keep the desktop app open, then save again."],
    native_host_unavailable: ["Reconnect to Reweave", "Start Reweave and confirm the extension is installed correctly."],
    protocol_mismatch: ["Update Reweave", "Update the app and extension, then try again."],
    malformed_response: ["Update Reweave", "The app returned an incompatible response."],
  };
  const copy = errorCopy[response?.reason] || ["Could not save", "No archive changes were made. Try again."];
  document.body.dataset.status = response?.status === "incompatible" ? "incompatible" : "error";
  title.textContent = copy[0];
  detail.textContent = copy[1];
}

function renderContextResult(response) {
  retry.hidden = true;
  useContext.hidden = false;
  useContext.disabled = false;
  useContext.textContent = "Refresh Reweave context";
  save.hidden = false;
  save.disabled = false;
  rememberDestination.disabled = false;
  if (response?.provider && response?.external_id) {
    currentIdentity = { provider: response.provider, external_id: response.external_id };
  }
  changeDestination.hidden = !currentIdentity;
  reviewSensitive.hidden = !response?.sensitive_available;
  if (response?.status === "destination_confirmation_required") {
    renderDestination(response);
    return;
  }
  if (response?.status === "sensitive_preview") {
    renderSensitive(response);
    return;
  }
  destinationPanel.hidden = true;
  sensitivePanel.hidden = true;
  if (response?.status === "destination_saved") {
    document.body.dataset.status = "ready";
    title.textContent = "Destination remembered";
    detail.textContent = `Saved as ${response.destination} for this conversation. Choose Use to add context.`;
    useContext.textContent = "Use with saved destination";
    return;
  }
  const reasons = document.querySelector("#use-reasons");
  reasons.replaceChildren();
  for (const item of response?.used || []) appendText(reasons, "li", `${item.item_id}: ${(item.reasons || []).join("; ")}`);
  for (const reason of response?.excluded_reasons || []) appendText(reasons, "li", reason);
  document.querySelector("#use-explanation").hidden = !reasons.children.length;

  if (response?.status === "inserted") {
    document.body.dataset.status = "saved";
    title.textContent = "Context added to your draft";
    detail.textContent = response.item_count === 1
      ? "One relevant Context Item was added. Review the draft before sending."
      : `${response.item_count} relevant Context Items were added. Review the draft before sending.`;
    return;
  }

  const providerName = response?.provider === "claude" ? "Claude" : "ChatGPT";
  const errorCopy = {
    unsupported_page: [
      "Open a supported conversation",
      "Use works on a signed-in ChatGPT or Claude conversation page with a confirmed destination.",
    ],
    logged_out: [`Sign in to ${providerName}`, `Sign in to ${providerName}, then try Use again.`],
    changed_dom: [`${providerName} page changed`, "Reload the conversation and try again."],
    streaming: ["Wait for the response", "Let the current response finish, then try Use again."],
    incomplete_conversation: [
      "Load the whole conversation",
      "Load the complete conversation and wait for the latest response, then try again.",
    ],
    empty_draft: ["Write a request first", "Add a non-empty draft, then choose Use Reweave context."],
    draft_too_large: ["Draft is too large", "Shorten the draft or existing Context block, then try again."],
    draft_changed: ["Draft changed safely", "Reweave did not overwrite your edits. Choose Use again."],
    conversation_changed: ["The active conversation changed", "Choose Use again to review the destination for the current conversation."],
    destination_changed: ["Destination choices changed", "Choose Change destination to review the latest allowed spaces."],
    confirmation_expired: ["Preview needs to be refreshed", "Your draft is unchanged. Review sensitive context again before approving it."],
    context_unavailable: ["No relevant Context found", "Your draft is unchanged. Try a more specific request."],
    context_request_too_large: ["Conversation is too large", "This chat exceeds the safe local transfer limit."],
    invalid_context: ["Could not assemble Context", "Your draft is unchanged. Reload and try again."],
    insertion_failed: ["Could not update the draft", "Your draft is unchanged. Reload and try again."],
    app_not_running: ["Open Reweave to continue", "Start the desktop app, then try Use again."],
    connection_failed: ["Reconnect to Reweave", "Keep the desktop app open, then try Use again."],
    native_host_unavailable: ["Reconnect to Reweave", "Start Reweave and confirm the extension is installed correctly."],
    protocol_mismatch: ["Update Reweave", "Update the app and extension, then try again."],
    malformed_response: ["Update Reweave", "The app returned an incompatible response."],
  };
  const copy = errorCopy[response?.reason] || [
    "Could not add Context",
    "Your draft is unchanged. Try again.",
  ];
  document.body.dataset.status = response?.status === "incompatible" ? "incompatible" : "error";
  title.textContent = copy[0];
  detail.textContent = copy[1];
}

function checkAvailability() {
  document.body.removeAttribute("data-status");
  title.textContent = "Checking Reweave…";
  detail.textContent = "Confirming that the local app is available.";
  useContext.hidden = true;
  save.hidden = true;
  retry.hidden = true;

  chrome.runtime.sendMessage({ type: "reweave:check-availability" }, (response) => {
    if (chrome.runtime.lastError || !response) {
      renderStatus("unavailable");
      return;
    }
    renderStatus(response.status);
  });
}

function saveConversation() {
  document.body.dataset.status = "saving";
  title.textContent = "Saving conversation…";
  detail.textContent = "Reading the active supported conversation and storing it locally.";
  save.disabled = true;
  save.textContent = "Saving…";
  useContext.hidden = true;
  retry.hidden = true;

  chrome.runtime.sendMessage({ type: "reweave:save-conversation" }, (response) => {
    if (chrome.runtime.lastError || !response) {
      renderSaveResult({ status: "unavailable", reason: "native_host_unavailable" });
      return;
    }
    renderSaveResult(response);
  });
}

function useReweave(options = {}) {
  document.body.dataset.status = "saving";
  title.textContent = "Adding Reweave context…";
  detail.textContent = "Reading the active conversation and draft after your explicit request.";
  useContext.disabled = true;
  useContext.textContent = "Adding Context…";
  save.hidden = true;
  retry.hidden = true;
  rememberDestination.disabled = true;
  confirmSensitive.disabled = true;

  chrome.runtime.sendMessage({ type: "reweave:use-context", options }, (response) => {
    if (chrome.runtime.lastError || !response) {
      renderContextResult({ status: "unavailable", reason: "native_host_unavailable" });
      return;
    }
    renderContextResult(response);
  });
}

retry.addEventListener("click", checkAvailability);
save.addEventListener("click", saveConversation);
useContext.addEventListener("click", () => useReweave());
destinationChoice.addEventListener("change", filterDestinationScopes);
scopeChoices.addEventListener("change", filterDestinationScopes);
rememberDestination.addEventListener("click", () => useReweave({
  action: "save_destination", expected_identity: currentIdentity,
  destination: destinationChoice.value, expected_revision: destinationRevision,
  allowed_space_ids: Array.from(scopeChoices.querySelectorAll("input:checked")).map(input => input.value),
}));
changeDestination.addEventListener("click", () => useReweave({ action: "destination_settings" }));
reviewSensitive.addEventListener("click", () => useReweave({ action: "preview_sensitive", expected_identity: currentIdentity }));
sensitiveItems.addEventListener("change", () => {
  confirmSensitive.disabled = sensitiveItems.querySelectorAll("input:checked").length === 0;
});
confirmSensitive.addEventListener("click", () => useReweave({
  action: "confirm_sensitive", expected_identity: currentIdentity, preview_token: previewToken,
  selected_items: Array.from(sensitiveItems.querySelectorAll("input:checked")).map(input => ({
    item_id: input.value, version: Number(input.dataset.version),
  })),
}));
checkAvailability();
