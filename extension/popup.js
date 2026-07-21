const title = document.querySelector("#title");
const detail = document.querySelector("#detail");
const retry = document.querySelector("#retry");

const stateCopy = {
  ready: {
    title: "Reweave is ready",
    detail: "The local app is available. Save and Use actions will be added next.",
    retry: false,
  },
  unavailable: {
    title: "Open Reweave to continue",
    detail: "Start the desktop app, then retry the connection.",
    retry: true,
  },
  incompatible: {
    title: "Update Reweave",
    detail: "The app and extension use different bridge versions. Update both, then retry.",
    retry: true,
  },
};

function renderStatus(status) {
  const safeStatus = stateCopy[status] ? status : "unavailable";
  const copy = stateCopy[safeStatus];
  document.body.dataset.status = safeStatus;
  title.textContent = copy.title;
  detail.textContent = copy.detail;
  retry.hidden = !copy.retry;
}

function checkAvailability() {
  document.body.removeAttribute("data-status");
  title.textContent = "Checking Reweave…";
  detail.textContent = "Confirming that the local app is available.";
  retry.hidden = true;

  chrome.runtime.sendMessage({ type: "reweave:check-availability" }, (response) => {
    if (chrome.runtime.lastError || !response) {
      renderStatus("unavailable");
      return;
    }
    renderStatus(response.status);
  });
}

retry.addEventListener("click", checkAvailability);
checkAvailability();
