(() => {
  let statusInterval = null;
  let workerRunning = false;

  function setStatus(message, type = "info") {
    const el = document.getElementById("status");
    if (!el) return;
    const cls =
      type === "error" ? "danger" : type === "success" ? "success" : "secondary";
    el.className = `alert alert-${cls} py-2 mb-3`;
    el.textContent = message;
  }

  function addLog(message) {
    const logEl = document.getElementById("log");
    if (!logEl) return;
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.textContent = `[${timestamp}] ${message}`;
    logEl.appendChild(entry);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function updateStats(data) {
    document.getElementById("stat-pending").textContent = data.queue_stats.pending || 0;
    document.getElementById("stat-faved").textContent = data.queue_stats.faved || 0;
    document.getElementById("stat-failed").textContent = data.queue_stats.failed || 0;
    document.getElementById("stat-processed").textContent = data.processed || 0;

    // Update worker status badge
    const statusBadge = document.getElementById("worker-status");
    if (data.running) {
      statusBadge.textContent = "Running";
      statusBadge.className = "badge bg-success";
    } else {
      statusBadge.textContent = "Stopped";
      statusBadge.className = "badge bg-secondary";
    }

    // Update buttons
    document.getElementById("btn-start").disabled = data.running;
    document.getElementById("btn-stop").disabled = !data.running;

    workerRunning = data.running;
  }

  async function fetchStatus() {
    try {
      const resp = await fetch("/api/mass-fave/status");
      const json = await resp.json();
      if (json.success) {
        updateStats(json.data);
      }
    } catch (e) {
      console.error("Failed to fetch status:", e);
    }
  }

  async function collectFeed() {
    const pages = parseInt(document.getElementById("pages-input").value, 10);

    if (pages < 1 || pages > 20) {
      setStatus("Pages must be between 1 and 20", "error");
      return;
    }

    setStatus(`Collecting ${pages} pages from feed...`);
    addLog(`Starting collection: ${pages} pages`);

    try {
      const resp = await fetch("/api/mass-fave/collect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pages }),
      });
      const json = await resp.json();

      if (!json.success) {
        throw new Error(json.error || "Unknown error");
      }

      const result = json.data;
      const msg = `Collected ${result.deviations_added} deviations from ${result.pages} pages (offset: ${result.offset})`;
      setStatus(msg, "success");
      addLog(msg);
      await fetchStatus();
    } catch (e) {
      const msg = "Collection failed: " + e.message;
      setStatus(msg, "error");
      addLog(msg);
    }
  }

  async function startWorker() {
    setStatus("Starting worker...");
    addLog("Starting worker");

    try {
      const resp = await fetch("/api/mass-fave/worker/start", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) {
        throw new Error(json.message || "Unknown error");
      }

      setStatus("Worker started", "success");
      addLog("Worker started successfully");
      await fetchStatus();

      // Start polling
      if (!statusInterval) {
        statusInterval = setInterval(fetchStatus, 2000);
      }
    } catch (e) {
      const msg = "Failed to start worker: " + e.message;
      setStatus(msg, "error");
      addLog(msg);
    }
  }

  async function stopWorker() {
    setStatus("Stopping worker...");
    addLog("Stopping worker");

    try {
      const resp = await fetch("/api/mass-fave/worker/stop", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) {
        throw new Error(json.message || "Unknown error");
      }

      setStatus("Worker stopped", "success");
      addLog("Worker stopped successfully");
      await fetchStatus();

      // Stop polling if worker stopped
      if (statusInterval && !workerRunning) {
        clearInterval(statusInterval);
        statusInterval = null;
      }
    } catch (e) {
      const msg = "Failed to stop worker: " + e.message;
      setStatus(msg, "error");
      addLog(msg);
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    await fetchStatus();
    addLog("Page loaded");

    // Start polling if worker is running
    const initialStatus = await fetch("/api/mass-fave/status").then((r) => r.json());
    if (initialStatus.success && initialStatus.data.running) {
      statusInterval = setInterval(fetchStatus, 2000);
    }
  });

  // Expose for inline handlers
  window.collectFeed = collectFeed;
  window.startWorker = startWorker;
  window.stopWorker = stopWorker;
})();
