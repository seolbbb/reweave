const title = document.querySelector("#title");
const detail = document.querySelector("#detail");
const retry = document.querySelector("#retry");
const save = document.querySelector("#save");

const stateCopy = {
  ready: {
    title: "Save this ChatGPT conversation",
    detail: "Reweave is ready. Save the complete conversation to your local library.",
    save: true,
    retry: false,
  },
  unavailable: {
    title: "Open Reweave to continue",
    detail: "Start the desktop app, then retry the connection.",
    save: false,
    retry: true,
  },
  incompatible: {
    title: "Update Reweave",
    detail: "The app and extension use different bridge versions. Update both, then retry.",
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
  save.hidden = !copy.save;
  save.disabled = false;
  save.textContent = "Save current conversation";
  retry.hidden = !copy.retry;
}

function renderSaveResult(response) {
  retry.hidden = true;
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

  const errorCopy = {
    unsupported_page: ["Open a ChatGPT conversation", "Save works on an open ChatGPT conversation page."],
    logged_out: ["Sign in to ChatGPT", "Sign in, open a conversation, then try Save again."],
    changed_dom: ["ChatGPT page changed", "Reload the conversation and try again."],
    page_access_failed: ["Could not read this page", "Keep the ChatGPT tab active and try Save again."],
    malformed_adapter_response: ["Update the extension", "The ChatGPT adapter is incompatible with this extension."],
    incomplete_conversation: ["Load the whole conversation", "Scroll to the beginning, let it finish loading, then save again."],
    invalid_conversation: ["Could not validate this conversation", "Reload the ChatGPT conversation and try again."],
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

function checkAvailability() {
  document.body.removeAttribute("data-status");
  title.textContent = "Checking Reweave…";
  detail.textContent = "Confirming that the local app is available.";
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
  detail.textContent = "Reading the active ChatGPT conversation and storing it locally.";
  save.disabled = true;
  save.textContent = "Saving…";
  retry.hidden = true;

  chrome.runtime.sendMessage({ type: "reweave:save-chatgpt" }, (response) => {
    if (chrome.runtime.lastError || !response) {
      renderSaveResult({ status: "unavailable", reason: "native_host_unavailable" });
      return;
    }
    renderSaveResult(response);
  });
}

retry.addEventListener("click", checkAvailability);
save.addEventListener("click", saveConversation);
checkAvailability();
