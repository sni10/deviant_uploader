(() => {
  let statusInterval = null;
  let workerRunning = false;
  let currentEditingMessageId = null;
  let messageModal = null;

  let savedWatchers = [];

  function setStatus(message, type = "info") {
    const el = document.getElementById("status");
    if (!el) return;
    const cls =
      type === "error" ? "danger" : type === "success" ? "success" : "secondary";
    el.className = `alert alert-${cls} py-2 mb-3`;
    el.textContent = message;
  }

  function updateStats(data) {
    document.getElementById("stat-queue").textContent = data.queue_remaining || 0;
    document.getElementById("stat-sent").textContent = data.send_stats?.sent || 0;
    document.getElementById("stat-failed").textContent = data.send_stats?.failed || 0;
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
      const resp = await fetch("/api/profile-messages/worker/status");
      const json = await resp.json();
      if (json.success) {
        updateStats(json.data);
        // Update watchers list if worker is running
        if (json.data.running) {
          await loadWatchersList();
        }
      }
    } catch (e) {
      console.error("Failed to fetch status:", e);
    }
  }

  async function loadMessages() {
    try {
      const resp = await fetch("/api/profile-messages");
      const json = await resp.json();

      if (!json.success) {
        throw new Error(json.error || "Failed to load messages");
      }

      const messages = json.data || [];
      const container = document.getElementById("messages-list");
      const select = document.getElementById("message-select");

      if (messages.length === 0) {
        container.innerHTML = '<p class="text-muted">No message templates created yet.</p>';
        select.innerHTML = '<option value="">Select message template</option>';
        return;
      }

      // Render messages list
      container.innerHTML = messages
        .map(
          (m) => `
        <div class="card mb-2">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start">
              <div class="flex-grow-1">
                <h6 class="mb-1">
                  ${escapeHtml(m.title)}
                  ${m.is_active ? '<span class="badge bg-success ms-2">Active</span>' : '<span class="badge bg-secondary ms-2">Inactive</span>'}
                </h6>
                <p class="mb-1 text-muted small">${escapeHtml(m.body)}</p>
              </div>
              <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="editMessage(${m.message_id})">Edit</button>
                <button class="btn btn-outline-danger" onclick="deleteMessage(${m.message_id})">Delete</button>
              </div>
            </div>
          </div>
        </div>
      `
        )
        .join("");

      // Update select dropdown
      select.innerHTML =
        '<option value="">Select message template</option>' +
        messages
          .filter((m) => m.is_active)
          .map((m) => `<option value="${m.message_id}">${escapeHtml(m.title)}</option>`)
          .join("");
    } catch (e) {
      setStatus("Failed to load messages: " + e.message, "error");
    }
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  window.showCreateMessageModal = function () {
    currentEditingMessageId = null;
    document.getElementById("messageModalTitle").textContent = "Create Message Template";
    document.getElementById("message-title").value = "";
    document.getElementById("message-body").value = "";
    document.getElementById("message-active").checked = true;
    messageModal.show();
  };

  window.editMessage = async function (messageId) {
    try {
      const resp = await fetch("/api/profile-messages");
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const message = json.data.find((m) => m.message_id === messageId);
      if (!message) throw new Error("Message not found");

      currentEditingMessageId = messageId;
      document.getElementById("messageModalTitle").textContent = "Edit Message Template";
      document.getElementById("message-title").value = message.title;
      document.getElementById("message-body").value = message.body;
      document.getElementById("message-active").checked = message.is_active;
      messageModal.show();
    } catch (e) {
      setStatus("Failed to load message: " + e.message, "error");
    }
  };

  window.saveMessage = async function () {
    const title = document.getElementById("message-title").value.trim();
    const body = document.getElementById("message-body").value.trim();
    const is_active = document.getElementById("message-active").checked;

    if (!title || !body) {
      setStatus("Title and body are required", "error");
      return;
    }

    try {
      let resp;
      if (currentEditingMessageId) {
        // Update existing
        resp = await fetch(`/api/profile-messages/${currentEditingMessageId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, body, is_active }),
        });
      } else {
        // Create new
        resp = await fetch("/api/profile-messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, body }),
        });
      }

      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(
        currentEditingMessageId ? "Message updated successfully" : "Message created successfully",
        "success"
      );
      messageModal.hide();
      await loadMessages();
    } catch (e) {
      setStatus("Failed to save message: " + e.message, "error");
    }
  };

  window.deleteMessage = async function (messageId) {
    if (!confirm("Are you sure you want to delete this message template?")) return;

    try {
      const resp = await fetch(`/api/profile-messages/${messageId}`, {
        method: "DELETE",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      setStatus("Message deleted successfully", "success");
      await loadMessages();
    } catch (e) {
      setStatus("Failed to delete message: " + e.message, "error");
    }
  };

  function formatFetchedAt(value) {
    if (!value) return "-";
    const dt = new Date(value);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleString();
    }

    const normalized = typeof value === "string" ? value.replace(" ", "T") : value;
    const dt2 = new Date(normalized);
    if (!Number.isNaN(dt2.getTime())) {
      return dt2.toLocaleString();
    }

    return String(value);
  }

  function renderSavedWatchersTable() {
    const tbody = document.getElementById("saved-watchers-table-body");
    if (!tbody) return;

    if (!savedWatchers || savedWatchers.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted">No saved watchers</td></tr>';
      return;
    }

    tbody.innerHTML = savedWatchers
      .map(
        (w, index) => `
      <tr>
        <td class="text-muted">${index + 1}</td>
        <td>
          <input type="checkbox" class="form-check-input"
            ${w.selected ? "checked" : ""}
            onchange="toggleSavedWatcherByIndex(${index}, this.checked)">
        </td>
        <td>${escapeHtml(w.username)}</td>
        <td>${escapeHtml(w.userid)}</td>
        <td>${formatFetchedAt(w.fetched_at)}</td>
      </tr>
    `
      )
      .join("");
  }

  window.loadSavedWatchers = async function () {
    try {
      const resp = await fetch("/api/profile-messages/watchers/saved?limit=500");
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const watchers = json.data || [];

      const prevSelected = new Set(
        (savedWatchers || []).filter((w) => w.selected).map((w) => w.username)
      );

      savedWatchers = watchers.map((w) => ({
        ...w,
        selected: prevSelected.has(w.username),
      }));

      renderSavedWatchersTable();
    } catch (e) {
      console.error("Failed to load saved watchers:", e);
    }
  };

  window.toggleSavedWatcherByIndex = function (index, selected) {
    const w = savedWatchers?.[index];
    if (!w) return;
    w.selected = !!selected;
  };

  window.selectAllSavedWatchers = function () {
    savedWatchers = (savedWatchers || []).map((w) => ({ ...w, selected: true }));
    renderSavedWatchersTable();
  };

  window.deselectAllSavedWatchers = function () {
    savedWatchers = (savedWatchers || []).map((w) => ({ ...w, selected: false }));
    renderSavedWatchersTable();
  };

  window.addSelectedSavedToQueue = async function () {
    const selected = (savedWatchers || [])
      .filter((w) => w.selected)
      .map((w) => ({ username: w.username, userid: w.userid }));

    if (selected.length === 0) {
      setStatus("No saved watchers selected", "error");
      return;
    }

    try {
      const resp = await fetch(
        "/api/profile-messages/watchers/add-selected-to-queue",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ watchers: selected }),
        }
      );
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const msg = `Added ${json.added_count} watchers to queue (${json.skipped_count} skipped, ${json.invalid_count} invalid)`;
      setStatus(msg, "success");
      await loadWatchersList();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to add selected to queue: " + e.message, "error");
    }
  };

  window.saveWatcherToDb = async function (username, userid) {
    try {
      const resp = await fetch("/api/profile-messages/watchers/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, userid }),
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus(json.message, "success");
      await loadSavedWatchers();
    } catch (e) {
      setStatus("Failed to save watcher: " + e.message, "error");
    }
  };

  window.saveSelectedToDb = async function () {
    try {
      const resp = await fetch("/api/profile-messages/watchers/save-selected", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const msg = `Saved ${json.saved_count} selected watchers to database (${json.skipped_count} not selected, ${json.failed_count} failed)`;
      setStatus(msg, "success");
      await loadSavedWatchers();
    } catch (e) {
      setStatus("Failed to save watchers: " + e.message, "error");
    }
  };

  window.removeSelectedFromQueue = async function () {
    if (!confirm("Remove selected watchers from queue?")) return;

    try {
      const resp = await fetch("/api/profile-messages/queue/remove-selected", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus(
        `Removed ${json.removed_count} watchers from queue (${json.remaining_count} remaining)`,
        "success",
      );
      await loadWatchersList();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to remove selected: " + e.message, "error");
    }
  };

  async function loadWatchersList() {
    try {
      const resp = await fetch("/api/profile-messages/queue/list");
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const watchers = json.data || [];
      const tbody = document.getElementById("watchers-table-body");

      if (watchers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No watchers in queue</td></tr>';
        return;
      }

      tbody.innerHTML = watchers
        .map(
          (w, index) => `
        <tr>
          <td class="text-muted">${index + 1}</td>
          <td>
            <input type="checkbox" class="form-check-input"
              ${w.selected ? "checked" : ""}
              onchange="toggleWatcher('${escapeHtml(w.username)}', this.checked)">
          </td>
          <td>${escapeHtml(w.username)}</td>
          <td>${escapeHtml(w.userid)}</td>
        </tr>
      `
        )
        .join("");
    } catch (e) {
      console.error("Failed to load watchers list:", e);
    }
  }

  window.toggleWatcher = async function (username, selected) {
    try {
      const resp = await fetch("/api/profile-messages/queue/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, selected }),
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      await fetchStatus();
    } catch (e) {
      setStatus("Failed to toggle selection: " + e.message, "error");
      await loadWatchersList(); // Reload to restore state
    }
  };

  window.selectAllWatchers = async function () {
    try {
      const resp = await fetch("/api/profile-messages/queue/select-all", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      setStatus(`Selected ${json.selected_count} watchers`, "success");
      await loadWatchersList();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to select all: " + e.message, "error");
    }
  };

  window.deselectAllWatchers = async function () {
    try {
      const resp = await fetch("/api/profile-messages/queue/deselect-all", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      setStatus(`Deselected ${json.deselected_count} watchers`, "success");
      await loadWatchersList();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to deselect all: " + e.message, "error");
    }
  };

  window.fetchWatchers = async function () {
    const username = document.getElementById("username-input").value.trim();
    const maxWatchers = parseInt(document.getElementById("max-watchers-input").value, 10);

    if (!username) {
      setStatus("Username is required", "error");
      return;
    }

    if (maxWatchers < 1 || maxWatchers > 500) {
      setStatus("Max watchers must be between 1 and 500", "error");
      return;
    }

    setStatus(`Fetching watchers for ${username}...`);

    try {
      const resp = await fetch("/api/profile-messages/fetch-watchers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, max_watchers: maxWatchers }),
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const result = json.data;
      const msg = `Fetched ${result.watchers_count} watchers${result.has_more ? " (more available)" : ""}`;
      setStatus(msg, "success");
      await fetchStatus();
      await loadWatchersList(); // Load the list after fetching
    } catch (e) {
      setStatus("Failed to fetch watchers: " + e.message, "error");
    }
  };

  window.clearQueue = async function () {
    if (!confirm("Clear watchers queue?")) return;

    try {
      const resp = await fetch("/api/profile-messages/queue/clear", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      setStatus(`Cleared ${json.cleared_count} watchers from queue`, "success");
      await fetchStatus();
      await loadWatchersList();
    } catch (e) {
      setStatus("Failed to clear queue: " + e.message, "error");
    }
  };

  window.startWorker = async function () {
    const messageId = document.getElementById("message-select").value;

    if (!messageId) {
      setStatus("Please select a message template", "error");
      return;
    }

    setStatus("Starting broadcast worker...");

    try {
      const resp = await fetch("/api/profile-messages/worker/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message_id: parseInt(messageId, 10) }),
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus("Broadcast worker started", "success");
      await fetchStatus();

      // Start polling
      if (!statusInterval) {
        statusInterval = setInterval(fetchStatus, 2000);
      }
    } catch (e) {
      setStatus("Failed to start worker: " + e.message, "error");
    }
  };

  window.stopWorker = async function () {
    setStatus("Stopping broadcast worker...");

    try {
      const resp = await fetch("/api/profile-messages/worker/stop", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus("Broadcast worker stopped", "success");
      await fetchStatus();

      // Stop polling if worker stopped
      if (statusInterval && !workerRunning) {
        clearInterval(statusInterval);
        statusInterval = null;
      }
    } catch (e) {
      setStatus("Failed to stop worker: " + e.message, "error");
    }
  };

  window.loadLogs = async function () {
    try {
      const resp = await fetch("/api/profile-messages/logs?limit=50");
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      const logs = json.data || [];
      const tbody = document.getElementById("logs-table-body");

      if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No logs yet</td></tr>';
        return;
      }

      tbody.innerHTML = logs
        .map(
          (log) => `
        <tr>
          <td>${new Date(log.sent_at).toLocaleString()}</td>
          <td><a href="${log.profile_url}" target="_blank">${escapeHtml(log.recipient_username)}</a></td>
          <td>
            ${log.status === "sent" ? '<span class="badge bg-success">Sent</span>' : '<span class="badge bg-danger">Failed</span>'}
          </td>
          <td>${log.commentid ? escapeHtml(log.commentid) : "-"}</td>
          <td>${log.error_message ? escapeHtml(log.error_message.substring(0, 50)) : "-"}</td>
          <td>
            ${log.profile_url ? `<a href="${log.profile_url}" target="_blank" class="btn btn-sm btn-outline-primary">Profile</a>` : "-"}
          </td>
        </tr>
      `
        )
        .join("");
    } catch (e) {
      setStatus("Failed to load logs: " + e.message, "error");
    }
  };

  document.addEventListener("DOMContentLoaded", async () => {
    // Initialize Bootstrap modal
    messageModal = new bootstrap.Modal(document.getElementById("messageModal"));

    await loadMessages();
    await fetchStatus();
    await loadSavedWatchers(); // Load saved watchers from DB
    await loadWatchersList(); // Load current queue
    await loadLogs();

    // Start polling if worker is running
    const initialStatus = await fetch("/api/profile-messages/worker/status").then((r) => r.json());
    if (initialStatus.success && initialStatus.data.running) {
      statusInterval = setInterval(fetchStatus, 2000);
    }
  });
})();
