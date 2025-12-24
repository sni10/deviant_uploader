(() => {
  let statusInterval = null;
  let workerRunning = false;
  let currentEditingTemplateId = null;
  let templateModal = null;
  let templatesCache = [];
  let queueItems = [];

  function setStatus(message, type = "info") {
    const el = document.getElementById("status");
    if (!el) return;
    const cls =
      type === "error" ? "danger" : type === "success" ? "success" : "secondary";
    el.className = `alert alert-${cls} py-2 mb-3`;
    el.textContent = message;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }

  function formatDate(value) {
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

  function updateStats(data) {
    document.getElementById("stat-pending").textContent = data.queue_stats?.pending || 0;
    document.getElementById("stat-commented").textContent = data.queue_stats?.commented || 0;
    document.getElementById("stat-failed").textContent = data.queue_stats?.failed || 0;
    document.getElementById("stat-processed").textContent = data.processed || 0;

    const statusBadge = document.getElementById("worker-status");
    if (data.running) {
      statusBadge.textContent = "Running";
      statusBadge.className = "badge bg-success";
    } else {
      statusBadge.textContent = "Stopped";
      statusBadge.className = "badge bg-secondary";
    }

    document.getElementById("btn-start").disabled = data.running;
    document.getElementById("btn-stop").disabled = !data.running;
    workerRunning = data.running;
  }

  async function fetchStatus() {
    try {
      const resp = await fetch("/api/deviation-comments/worker/status");
      const json = await resp.json();
      if (json.success) {
        updateStats(json.data);
        if (json.data.running) {
          await loadQueue();
        }

        if (statusInterval && !json.data.running) {
          clearInterval(statusInterval);
          statusInterval = null;
        }
      }
    } catch (e) {
      console.error("Failed to fetch status:", e);
    }
  }

  function renderTemplatesList() {
    const container = document.getElementById("templates-list");
    if (!container) return;

    if (!templatesCache || templatesCache.length === 0) {
      container.innerHTML = '<p class="text-muted">No templates created yet.</p>';
      return;
    }

    container.innerHTML = templatesCache
      .map(
        (t) => `
        <div class="card mb-2">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start">
              <div class="flex-grow-1">
                <h6 class="mb-1">
                  ${escapeHtml(t.title)}
                  ${
                    t.is_active
                      ? '<span class="badge bg-success ms-2">Active</span>'
                      : '<span class="badge bg-secondary ms-2">Inactive</span>'
                  }
                </h6>
                <p class="mb-1 text-muted small">${escapeHtml(t.body)}</p>
              </div>
              <div class="btn-group btn-group-sm">
                <button class="btn btn-outline-primary" onclick="editTemplate(${t.message_id})">Edit</button>
                <button class="btn btn-outline-danger" onclick="deleteTemplate(${t.message_id})">Delete</button>
              </div>
            </div>
          </div>
        </div>
      `
      )
      .join("");
  }

  function renderTemplateSelect() {
    const select = document.getElementById("template-select");
    if (!select) return;
    const currentValue = select.value || "";

    const options = ['<option value="">Random Active Template</option>'];
    for (const t of templatesCache) {
      const label = t.is_active ? t.title : `${t.title} (inactive)`;
      options.push(
        `<option value="${t.message_id}">${escapeHtml(label)}</option>`
      );
    }

    select.innerHTML = options.join("");
    select.value = currentValue;
  }

  async function loadTemplates() {
    try {
      const resp = await fetch("/api/deviation-comments/messages");
      const json = await resp.json();

      if (!json.success) throw new Error(json.error);

      templatesCache = json.data || [];
      renderTemplatesList();
      renderTemplateSelect();
    } catch (e) {
      setStatus("Failed to load templates: " + e.message, "error");
    }
  }

  window.showCreateTemplateModal = function () {
    currentEditingTemplateId = null;
    document.getElementById("templateModalTitle").textContent = "Create Template";
    document.getElementById("template-title").value = "";
    document.getElementById("template-body").value = "";
    document.getElementById("template-active").checked = true;
    templateModal.show();
  };

  window.editTemplate = function (messageId) {
    const template = templatesCache.find((t) => t.message_id === messageId);
    if (!template) {
      setStatus("Template not found", "error");
      return;
    }

    currentEditingTemplateId = messageId;
    document.getElementById("templateModalTitle").textContent = "Edit Template";
    document.getElementById("template-title").value = template.title;
    document.getElementById("template-body").value = template.body;
    document.getElementById("template-active").checked = template.is_active;
    templateModal.show();
  };

  window.saveTemplate = async function () {
    const title = document.getElementById("template-title").value.trim();
    const body = document.getElementById("template-body").value.trim();
    const is_active = document.getElementById("template-active").checked;

    if (!title || !body) {
      setStatus("Title and body are required", "error");
      return;
    }

    try {
      let resp;
      if (currentEditingTemplateId) {
        resp = await fetch(`/api/deviation-comments/messages/${currentEditingTemplateId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, body, is_active }),
        });
      } else {
        resp = await fetch("/api/deviation-comments/messages", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, body }),
        });
      }

      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(
        currentEditingTemplateId ? "Template updated successfully" : "Template created successfully",
        "success"
      );
      templateModal.hide();
      await loadTemplates();
    } catch (e) {
      setStatus("Failed to save template: " + e.message, "error");
    }
  };

  window.deleteTemplate = async function (messageId) {
    if (!confirm("Delete this template?")) return;

    try {
      const resp = await fetch(`/api/deviation-comments/messages/${messageId}`, {
        method: "DELETE",
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus("Template deleted successfully", "success");
      await loadTemplates();
    } catch (e) {
      setStatus("Failed to delete template: " + e.message, "error");
    }
  };

  window.collectWatchFeed = async function () {
    const pages = parseInt(document.getElementById("pages-input").value, 10);
    if (pages < 1) {
      setStatus("Pages must be at least 1", "error");
      return;
    }

    setStatus("Collecting watch feed...");
    try {
      const resp = await fetch("/api/deviation-comments/collect/watch-feed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pages }),
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(
        `Collected ${json.data.deviations_added} deviations from watch feed`,
        "success"
      );
      await fetchStatus();
      await loadQueue();
    } catch (e) {
      setStatus("Failed to collect watch feed: " + e.message, "error");
    }
  };

  window.collectGlobalFeed = async function () {
    const pages = parseInt(document.getElementById("pages-input").value, 10);
    if (pages < 1) {
      setStatus("Pages must be at least 1", "error");
      return;
    }

    setStatus("Collecting global feed...");
    try {
      const resp = await fetch("/api/deviation-comments/collect/global-feed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pages }),
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(
        `Collected ${json.data.deviations_added} deviations from global feed`,
        "success"
      );
      await fetchStatus();
      await loadQueue();
    } catch (e) {
      setStatus("Failed to collect global feed: " + e.message, "error");
    }
  };

  function renderQueue() {
    const tbody = document.getElementById("queue-table-body");
    if (!tbody) return;

    if (!queueItems || queueItems.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No pending items</td></tr>';
      return;
    }

    tbody.innerHTML = queueItems
      .map(
        (item, index) => `
        <tr>
          <td class="text-muted">${index + 1}</td>
          <td>
            <input type="checkbox" class="form-check-input"
              ${item.selected ? "checked" : ""}
              onchange="toggleQueueSelection(${index}, this.checked)">
          </td>
          <td>
            ${
              item.deviation_url
                ? `<a href="${escapeHtml(item.deviation_url)}" target="_blank">${escapeHtml(item.deviationid)}</a>`
                : `${escapeHtml(item.deviationid)}`
            }
            ${item.title ? `<div class="text-muted small">${escapeHtml(item.title)}</div>` : ""}
          </td>
          <td>${item.author_username ? escapeHtml(item.author_username) : "-"}</td>
          <td>${escapeHtml(item.source || "-")}</td>
          <td>
            ${item.status === "pending" ? '<span class="badge bg-secondary">Pending</span>' : escapeHtml(item.status)}
          </td>
          <td>${item.attempts ?? 0}</td>
          <td>${item.last_error ? escapeHtml(item.last_error).slice(0, 60) : "-"}</td>
        </tr>
      `
      )
      .join("");
  }

  window.toggleQueueSelection = function (index, selected) {
    const item = queueItems?.[index];
    if (!item) return;
    item.selected = !!selected;
  };

  window.loadQueue = async function () {
    try {
      const resp = await fetch("/api/deviation-comments/queue?status=pending&limit=200");
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      const prevSelected = new Set(
        (queueItems || []).filter((item) => item.selected).map((item) => item.deviationid)
      );

      queueItems = (json.data || []).map((item) => ({
        ...item,
        selected: prevSelected.has(item.deviationid),
      }));

      renderQueue();
    } catch (e) {
      console.error("Failed to load queue:", e);
    }
  };

  window.removeSelectedFromQueue = async function () {
    const selectedIds = (queueItems || [])
      .filter((item) => item.selected)
      .map((item) => item.deviationid);

    if (selectedIds.length === 0) {
      setStatus("No queue items selected", "error");
      return;
    }

    if (!confirm("Remove selected queue entries?")) return;

    try {
      const resp = await fetch("/api/deviation-comments/queue/remove-selected", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deviationids: selectedIds }),
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(`Removed ${json.removed_count} queue entries`, "success");
      await loadQueue();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to remove selected: " + e.message, "error");
    }
  };

  window.clearPendingQueue = async function () {
    if (!confirm("Clear pending queue?")) return;

    try {
      const resp = await fetch("/api/deviation-comments/queue/clear", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "pending" }),
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(`Cleared ${json.cleared_count} pending entries`, "success");
      await loadQueue();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to clear queue: " + e.message, "error");
    }
  };

  window.resetFailedQueue = async function () {
    if (!confirm("Reset failed entries to pending?")) return;

    try {
      const resp = await fetch("/api/deviation-comments/queue/reset-failed", {
        method: "POST",
      });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      setStatus(`Reset ${json.reset_count} failed entries`, "success");
      await loadQueue();
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to reset failed entries: " + e.message, "error");
    }
  };

  window.startWorker = async function () {
    const templateId = document.getElementById("template-select").value || null;
    setStatus("Starting comment worker...");

    try {
      const resp = await fetch("/api/deviation-comments/worker/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template_id: templateId }),
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus("Comment worker started", "success");
      await fetchStatus();

      if (!statusInterval) {
        statusInterval = setInterval(fetchStatus, 2000);
      }
    } catch (e) {
      setStatus("Failed to start worker: " + e.message, "error");
    }
  };

  window.stopWorker = async function () {
    setStatus("Stopping comment worker...");

    try {
      const resp = await fetch("/api/deviation-comments/worker/stop", {
        method: "POST",
      });
      const json = await resp.json();

      if (!json.success) throw new Error(json.message || json.error);

      setStatus("Comment worker stopped", "success");
      
      // Clear interval immediately when stop is requested
      if (statusInterval) {
        clearInterval(statusInterval);
        statusInterval = null;
      }
      
      // Update status after clearing interval
      await fetchStatus();
    } catch (e) {
      setStatus("Failed to stop worker: " + e.message, "error");
    }
  };

  window.loadLogs = async function () {
    try {
      const resp = await fetch("/api/deviation-comments/logs?limit=50");
      const json = await resp.json();
      if (!json.success) throw new Error(json.error);

      const logs = json.data || [];
      const tbody = document.getElementById("logs-table-body");

      if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No logs yet</td></tr>';
        return;
      }

      tbody.innerHTML = logs
        .map(
          (log) => `
        <tr>
          <td>${formatDate(log.sent_at)}</td>
          <td>
            ${
              log.deviation_url
                ? `<a href="${escapeHtml(log.deviation_url)}" target="_blank">${escapeHtml(log.deviationid)}</a>`
                : escapeHtml(log.deviationid)
            }
          </td>
          <td>
            ${
              log.status === "sent"
                ? '<span class="badge bg-success">Sent</span>'
                : log.status === "deleted"
                ? '<span class="badge bg-secondary">Deleted</span>'
                : '<span class="badge bg-danger">Failed</span>'
            }
          </td>
          <td>${log.commentid ? escapeHtml(log.commentid) : "-"}</td>
          <td>${log.error_message ? escapeHtml(log.error_message).slice(0, 80) : "-"}</td>
        </tr>
      `
        )
        .join("");
    } catch (e) {
      setStatus("Failed to load logs: " + e.message, "error");
    }
  };

  document.addEventListener("DOMContentLoaded", async () => {
    templateModal = new bootstrap.Modal(document.getElementById("templateModal"));

    await loadTemplates();
    await fetchStatus();
    await loadQueue();
    await loadLogs();

    const initialStatus = await fetch("/api/deviation-comments/worker/status").then((r) => r.json());
    if (initialStatus.success && initialStatus.data.running) {
      statusInterval = setInterval(fetchStatus, 2000);
    }
  });
})();
