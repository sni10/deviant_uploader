(() => {
  let statsData = [];
  let sortConfig = { column: "views", direction: "desc" };
  let optionsCache = { users: [], galleries: [] };

  function setStatus(message, type = "info") {
    const el = document.getElementById("status");
    if (!el) return;
    const cls =
      type === "error" ? "danger" : type === "success" ? "success" : "secondary";
    el.className = `alert alert-${cls} py-2 mb-3`;
    el.textContent = message;
  }

  async function updateUserHeader(username) {
    const headerEl = document.getElementById("user-header");
    if (!headerEl) return;

    if (!username) {
      headerEl.textContent = "";
      return;
    }

    try {
      const resp = await fetch(
        `/api/user_stats/latest?username=${encodeURIComponent(username)}`
      );
      const json = await resp.json();
      if (!json.success || !json.data) {
        headerEl.textContent = "";
        return;
      }

      const data = json.data;
      const watchers = data.watchers ?? 0;
      const watchersDiff = data.watchers_diff ?? 0;
      const profileUrl = data.profile_url || `https://www.deviantart.com/${username}`;

      let diffHtml = "";
      if (watchersDiff > 0) {
        diffHtml = ` <span class="positive">(+${watchersDiff})</span>`;
      } else if (watchersDiff < 0) {
        diffHtml = ` <span class="negative">(${watchersDiff})</span>`;
      }

      headerEl.innerHTML = `&mdash; <a href="${profileUrl}" target="_blank" rel="noopener">watchers: ${watchers}</a>${diffHtml}`;
    } catch (e) {
      console.error("Failed to load user header stats", e);
    }
  }

  async function loadStats() {
    setStatus("Loading stats...");
    try {
      const resp = await fetch("/api/stats");
      const json = await resp.json();
      if (!json.success) throw new Error(json.error || "Unknown error");
      statsData = json.data || [];
      applySort();
      renderTable();
      setStatus(`Loaded ${statsData.length} deviations`, "success");
    } catch (e) {
      setStatus("Error: " + e.message, "error");
    }
  }

  async function syncStats() {
    const username = document.getElementById("user-select").value;
    const galleries = optionsCache.galleries || [];

    if (galleries.length === 0) {
      setStatus("No galleries available to sync", "error");
      return;
    }

    setStatus(`Syncing ${galleries.length} galleries...`);

    let syncedCount = 0;
    let errorCount = 0;
    let lastUserStats = null;

    try {
      for (let i = 0; i < galleries.length; i++) {
        const gallery = galleries[i];
        const folderid = gallery.folderid;

        setStatus(`Syncing gallery ${i + 1}/${galleries.length}: ${gallery.name}...`);

        try {
          const resp = await fetch("/api/stats/sync", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              folderid,
              username: username || undefined,
            }),
          });
          const json = await resp.json();

          if (!json.success) {
            throw new Error(json.error || "Unknown error");
          }

          syncedCount++;

          // Update user stats from last successful sync
          if (json.data.user_stats) {
            lastUserStats = json.data.user_stats;
          }

        } catch (e) {
          console.error(`Failed to sync gallery ${gallery.name}:`, e);
          errorCount++;
        }

        // Wait 3 seconds before next gallery (except for last one)
        if (i < galleries.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 3000));
        }
      }

      // Update user header with last stats
      if (lastUserStats && lastUserStats.username) {
        const headerEl = document.getElementById("user-header");
        const watchers = lastUserStats.watchers ?? 0;
        const watchersDiff = lastUserStats.watchers_diff ?? 0;
        const profileUrl =
          lastUserStats.profile_url || `https://www.deviantart.com/${lastUserStats.username}`;

        let diffHtml = "";
        if (watchersDiff > 0) {
          diffHtml = ` <span class="positive">(+${watchersDiff})</span>`;
        } else if (watchersDiff < 0) {
          diffHtml = ` <span class="negative">(${watchersDiff})</span>`;
        }

        headerEl.innerHTML = `&mdash; <a href="${profileUrl}" target="_blank" rel="noopener">watchers: ${watchers}</a>${diffHtml}`;
      }

      const statusMsg = errorCount > 0
        ? `Synced ${syncedCount}/${galleries.length} galleries (${errorCount} failed)`
        : `Successfully synced all ${syncedCount} galleries`;
      setStatus(statusMsg, errorCount > 0 ? "error" : "success");

      await loadStats();
    } catch (e) {
      setStatus("Error: " + e.message, "error");
    }
  }

  async function loadOptions() {
    setStatus("Loading options...");
    try {
      const resp = await fetch("/api/options");
      const json = await resp.json();
      if (!json.success) throw new Error(json.error || "Unable to load options");

      optionsCache = json.data || { users: [], galleries: [] };
      populateSelect("user-select", optionsCache.users, (u) => ({
        value: u.username,
        label: `${u.username}`,
      }));

      setStatus("Options loaded", "success");
    } catch (e) {
      setStatus("Error loading options: " + e.message, "error");
    }
  }

  function populateSelect(id, items, mapFn) {
    const select = document.getElementById(id);
    select.innerHTML = "";
    if (!items || items.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No data";
      select.appendChild(opt);
      return;
    }
    for (const item of items) {
      const mapped = mapFn(item);
      const opt = document.createElement("option");
      opt.value = mapped.value;
      opt.textContent = mapped.label;
      select.appendChild(opt);
    }

    if (id === "user-select") {
      select.onchange = () => updateUserHeader(select.value);
      if (select.value) {
        updateUserHeader(select.value);
      }
    }
  }

  function formatDiff(value) {
    if (value > 0) return `<span class="positive">+${value}</span>`;
    if (value < 0) return `<span class="negative">${value}</span>`;
    return "0";
  }

  function getSortClass(column) {
    if (sortConfig.column !== column) return "sortable";
    return sortConfig.direction === "asc" ? "sort-asc" : "sort-desc";
  }

  function sortBy(column) {
    if (sortConfig.column === column) {
      sortConfig.direction = sortConfig.direction === "asc" ? "desc" : "asc";
    } else {
      sortConfig.column = column;
      sortConfig.direction = "desc";
    }
    applySort();
    renderTable();
  }

  function combinedSort() {
    sortConfig = { column: "combined", direction: "desc" };
    applySort();
    renderTable();
  }

  function formatDate(dateStr) {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) {
      return dateStr;
    }
    return date.toLocaleString();
  }

  function applySort() {
    const { column, direction } = sortConfig;
    statsData.sort((a, b) => {
      let valA;
      let valB;

      if (column === "combined") {
        valA = (a.views || 0) + (a.favourites || 0) * 10;
        valB = (b.views || 0) + (b.favourites || 0) * 10;
      } else if (column === "creation_time") {
        const dA = a.creation_time ? new Date(a.creation_time).getTime() : 0;
        const dB = b.creation_time ? new Date(b.creation_time).getTime() : 0;
        valA = Number.isNaN(dA) ? 0 : dA;
        valB = Number.isNaN(dB) ? 0 : dB;
      } else {
        valA = a[column] || 0;
        valB = b[column] || 0;
      }

      return direction === "asc" ? valA - valB : valB - valA;
    });
  }

  function renderTable() {
    const rows = statsData
      .map((row) => {
        const url = row.url || null;
        const thumb = row.thumb_url
          ? `<img class="thumb" src="${row.thumb_url}" alt="thumb">`
          : "-";
        const thumbCell = url
          ? `<a href="${url}" target="_blank" rel="noopener">${thumb}</a>`
          : thumb;
        const titleCell = url
          ? `<a href="${url}" target="_blank" rel="noopener">${row.title || "Untitled"}</a>`
          : row.title || "Untitled";
        const publishedAt = row.creation_time ? formatDate(row.creation_time) : "-";

        return `
          <tr>
            <td>${thumbCell}</td>
            <td>${titleCell}</td>
            <td>${row.is_mature ? '<span class="badge bg-warning text-dark">Mature</span>' : ""}</td>
            <td>${row.views ?? 0}</td>
            <td>${formatDiff(row.views_diff ?? 0)}</td>
            <td>${row.favourites ?? 0}</td>
            <td>${formatDiff(row.favourites_diff ?? 0)}</td>
            <td>${row.comments ?? 0}</td>
            <td>${formatDiff(row.comments_diff ?? 0)}</td>
            <td>${(row.views || 0) + (row.favourites || 0) * 10}</td>
            <td>${publishedAt}</td>
          </tr>
        `;
      })
      .join("");

    const table = `
      <table class="table table-hover table-sm align-middle table-sortable">
        <thead class="table-light">
          <tr>
            <th>Thumb</th>
            <th>Title</th>
            <th class="${getSortClass("is_mature")}" onclick="sortBy('is_mature')">Mature</th>
            <th class="${getSortClass("views")}" onclick="sortBy('views')">Views</th>
            <th class="${getSortClass("views_diff")}" onclick="sortBy('views_diff')">&#916;</th>
            <th class="${getSortClass("favourites")}" onclick="sortBy('favourites')">Favs</th>
            <th class="${getSortClass("favourites_diff")}" onclick="sortBy('favourites_diff')">&#916;</th>
            <th class="${getSortClass("comments")}" onclick="sortBy('comments')">Comments</th>
            <th class="${getSortClass("comments_diff")}" onclick="sortBy('comments_diff')">&#916;</th>
            <th class="${getSortClass("combined")}" onclick="combinedSort()">Score</th>
            <th class="${getSortClass("creation_time")}" onclick="sortBy('creation_time')">Published</th>
          </tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="11" class="text-center text-muted py-4">No data</td></tr>'}</tbody>
      </table>`;

    const tableContainer = document.getElementById("stats-table");
    if (tableContainer) {
      tableContainer.innerHTML = table;
    }
  }

  document.addEventListener("DOMContentLoaded", async () => {
    await loadOptions();
    await loadStats();
  });

  // Expose for inline handlers
  window.syncStats = syncStats;
  window.loadStats = loadStats;
  window.combinedSort = combinedSort;
  window.sortBy = sortBy;
})();
