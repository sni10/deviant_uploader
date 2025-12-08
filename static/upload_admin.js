(() => {
  let deviations = [];
  let presets = [];
  let galleries = [];
  let selectedPresetId = null;

  function showLoading(text = "Processing...") {
    document.getElementById("loadingText").textContent = text;
    document.getElementById("loading").classList.add("active");
    document.getElementById("overlay").classList.add("active");
  }

  function hideLoading() {
    document.getElementById("loading").classList.remove("active");
    document.getElementById("overlay").classList.remove("active");
  }

  function setStatus(message, type = "info") {
    const statusEl = document.getElementById("statusMessage");
    if (!statusEl) return;
    statusEl.textContent = message;
    const color =
      type === "error" ? "#dc3545" : type === "success" ? "#198754" : "#6c757d";
    statusEl.style.color = color;
  }

  function toggleMatureOptions() {
    const isMature = document.getElementById("isMature").checked;
    document.getElementById("matureOptions").style.display = isMature ? "block" : "none";
  }

  async function loadGalleries() {
    try {
      const response = await fetch("/api/admin/galleries");
      const data = await response.json();

      if (data.success) {
        galleries = data.galleries;
        const select = document.getElementById("gallerySelect");
        select.innerHTML = '<option value="">-- No Gallery --</option>';

        galleries.forEach((gallery) => {
          const option = document.createElement("option");
          option.value = gallery.folderid;
          option.textContent = gallery.name + (gallery.size ? ` (${gallery.size})` : "");
          select.appendChild(option);
        });
      }
    } catch (error) {
      console.error("Failed to load galleries:", error);
    }
  }

  async function loadPresets() {
    try {
      const response = await fetch("/api/admin/presets");
      const data = await response.json();

      if (data.success) {
        presets = data.presets;
        const select = document.getElementById("presetSelect");
        select.innerHTML = '<option value="">-- New Preset --</option>';

        presets.forEach((preset) => {
          const option = document.createElement("option");
          option.value = preset.id;
          option.textContent = preset.name + (preset.is_default ? " (Default)" : "");
          select.appendChild(option);
        });

        const defaultPreset = presets.find((p) => p.is_default);
        if (defaultPreset) {
          select.value = defaultPreset.id;
          onPresetChange();
        }
      }
    } catch (error) {
      console.error("Failed to load presets:", error);
      setStatus("Failed to load presets", "error");
    }
  }

  function onPresetChange() {
    const select = document.getElementById("presetSelect");
    selectedPresetId = select.value ? parseInt(select.value, 10) : null;

    if (selectedPresetId) {
      const preset = presets.find((p) => p.id === selectedPresetId);
      if (preset) {
        loadPresetToForm(preset);
      }
    } else {
      clearForm();
    }
    updateButtonStates();
  }

  function loadPresetToForm(preset) {
    document.getElementById("presetName").value = preset.name || "";
    document.getElementById("baseTitle").value = preset.base_title || "";
    document.getElementById("titleIncrement").value =
      preset.last_used_increment || preset.title_increment_start || 1;
    document.getElementById("gallerySelect").value = preset.gallery_folderid || "";
    document.getElementById("tags").value = Array.isArray(preset.tags)
      ? preset.tags.join(", ")
      : preset.tags || "";
    document.getElementById("artistComments").value = preset.artist_comments || "";
    document.getElementById("displayResolution").value = preset.display_resolution || 0;
    document.getElementById("isAiGenerated").checked = preset.is_ai_generated !== false;
    document.getElementById("feature").checked = preset.feature !== false;
    document.getElementById("allowComments").checked = preset.allow_comments !== false;
    document.getElementById("allowFreeDownload").checked = preset.allow_free_download || false;
    document.getElementById("isMature").checked = preset.is_mature || false;

    if (preset.is_mature) {
      document.getElementById("matureLevel").value = preset.mature_level || "";
      const classifications = preset.mature_classification || [];
      document.getElementById("matureNudity").checked = classifications.includes("nudity");
      document.getElementById("matureSexual").checked = classifications.includes("sexual");
      document.getElementById("matureGore").checked = classifications.includes("gore");
      document.getElementById("matureLanguage").checked = classifications.includes("language");
      document.getElementById("matureIdeology").checked = classifications.includes("ideology");
    }

    toggleMatureOptions();
  }

  function clearForm() {
    document.getElementById("presetName").value = "";
    document.getElementById("baseTitle").value = "";
    document.getElementById("titleIncrement").value = 1;
    document.getElementById("gallerySelect").value = "";
    document.getElementById("tags").value = "";
    document.getElementById("artistComments").value = "";
    document.getElementById("displayResolution").value = 0;
    document.getElementById("isAiGenerated").checked = true;
    document.getElementById("feature").checked = true;
    document.getElementById("allowComments").checked = true;
    document.getElementById("allowFreeDownload").checked = false;
    document.getElementById("isMature").checked = false;
    document.getElementById("matureLevel").value = "";
    document.getElementById("matureNudity").checked = false;
    document.getElementById("matureSexual").checked = false;
    document.getElementById("matureGore").checked = false;
    document.getElementById("matureLanguage").checked = false;
    document.getElementById("matureIdeology").checked = false;
    toggleMatureOptions();
  }

  function getFormData() {
    const tags = document
      .getElementById("tags")
      .value.split(",")
      .map((t) => t.trim())
      .filter((t) => t.length > 0);

    const matureClassification = [];
    if (document.getElementById("matureNudity").checked) matureClassification.push("nudity");
    if (document.getElementById("matureSexual").checked) matureClassification.push("sexual");
    if (document.getElementById("matureGore").checked) matureClassification.push("gore");
    if (document.getElementById("matureLanguage").checked) matureClassification.push("language");
    if (document.getElementById("matureIdeology").checked) matureClassification.push("ideology");

    return {
      name: document.getElementById("presetName").value,
      base_title: document.getElementById("baseTitle").value,
      title_increment_start: parseInt(document.getElementById("titleIncrement").value, 10) || 1,
      gallery_folderid: document.getElementById("gallerySelect").value || null,
      tags,
      artist_comments: document.getElementById("artistComments").value || null,
      display_resolution: parseInt(document.getElementById("displayResolution").value, 10) || 0,
      is_ai_generated: document.getElementById("isAiGenerated").checked,
      feature: document.getElementById("feature").checked,
      allow_comments: document.getElementById("allowComments").checked,
      allow_free_download: document.getElementById("allowFreeDownload").checked,
      is_mature: document.getElementById("isMature").checked,
      mature_level: document.getElementById("matureLevel").value || null,
      mature_classification: matureClassification,
    };
  }

  async function savePreset() {
    const formData = getFormData();

    if (!formData.name || !formData.base_title) {
      setStatus("Preset Name and Base Title are required", "error");
      return;
    }

    showLoading("Saving preset...");

    try {
      const response = await fetch("/api/admin/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (data.success) {
        setStatus("Preset saved successfully", "success");
        await loadPresets();
        document.getElementById("presetSelect").value = data.preset_id;
        selectedPresetId = data.preset_id;
        updateButtonStates();
      } else {
        setStatus("Save failed: " + data.error, "error");
      }
    } catch (error) {
      console.error("Save failed:", error);
      setStatus("Save failed: " + error.message, "error");
    } finally {
      hideLoading();
    }
  }

  async function loadDrafts() {
    try {
      const response = await fetch("/api/admin/drafts");
      const data = await response.json();

      if (data.success) {
        deviations = data.deviations;
        renderTable();
        setStatus(`Loaded ${deviations.length} deviations`);
      }
    } catch (error) {
      console.error("Failed to load drafts:", error);
      setStatus("Failed to load drafts", "error");
    }
  }

  async function scanFiles() {
    showLoading("Scanning upload folder...");

    try {
      const response = await fetch("/api/admin/scan", { method: "POST" });
      const data = await response.json();

      if (data.success) {
        deviations = data.drafts;
        renderTable();
        setStatus(`Scanned: ${data.count} files`, "success");
      } else {
        setStatus("Scan failed: " + data.error, "error");
      }
    } catch (error) {
      console.error("Scan failed:", error);
      setStatus("Scan failed: " + error.message, "error");
    } finally {
      hideLoading();
    }
  }

  function statusBadge(status) {
    const normalized = (status || "").toLowerCase();
    const cls =
      normalized === "stashing"
        ? "status-stashing"
        : normalized === "stashed"
        ? "status-stashed"
        : normalized === "publishing"
        ? "status-publishing"
        : normalized === "published"
        ? "status-published"
        : normalized === "failed"
        ? "status-failed"
        : "status-draft";
    return `<span class="badge status-badge ${cls}">${status || "draft"}</span>`;
  }

  function renderTable() {
    const tbody = document.getElementById("tableBody");

    if (!deviations.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" class="text-center text-muted py-4">
            <div class="fw-semibold mb-1">No files found</div>
            <div class="small">Upload images to the upload folder and click "Scan Files"</div>
          </td>
        </tr>
      `;
      updateButtonStates();
      return;
    }

    tbody.innerHTML = deviations
      .map(
        (dev) => `
          <tr>
            <td><input type="checkbox" class="form-check-input deviation-checkbox" data-id="${dev.id}" onchange="updateButtonStates()"></td>
            <td>
              <img src="/api/admin/thumbnail/${dev.id}" alt="${dev.filename}" class="thumbnail"
                   onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2264%22 height=%2264%22%3E%3Crect fill=%22%23e9ecef%22 width=%2264%22 height=%2264%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 text-anchor=%22middle%22 dy=%22.3em%22 fill=%22%23999%22 font-size=%228%22%3ENo Image%3C/text%3E%3C/svg%3E'">
            </td>
            <td class="text-nowrap">${dev.filename}</td>
            <td>${dev.title || "-"}</td>
            <td>${statusBadge(dev.status)}</td>
            <td>
              <button class="btn btn-outline-danger btn-sm" onclick="deleteSingle(${dev.id})">Delete</button>
            </td>
          </tr>
        `
      )
      .join("");

    updateButtonStates();
  }

  function toggleSelectAll() {
    const selectAll = document.getElementById("selectAll");
    document.querySelectorAll(".deviation-checkbox").forEach((cb) => {
      cb.checked = selectAll.checked;
    });
    updateButtonStates();
  }

  function updateButtonStates() {
    const selected = getSelectedIds();
    const hasSelection = selected.length > 0;
    const hasPresetConfig =
      document.getElementById("presetName").value && document.getElementById("baseTitle").value;

    document.getElementById("uploadBtn").disabled = !hasSelection || !hasPresetConfig;
    document.getElementById("deleteBtn").disabled = !hasSelection;
  }

  function getSelectedIds() {
    return Array.from(document.querySelectorAll(".deviation-checkbox:checked")).map((cb) =>
      parseInt(cb.dataset.id, 10)
    );
  }

  async function uploadSelected() {
    const selectedIds = getSelectedIds();
    if (!selectedIds.length) return;

    const formData = getFormData();
    if (!formData.name || !formData.base_title) {
      setStatus("Please fill in Preset Name and Base Title", "error");
      return;
    }

    showLoading(`Uploading ${selectedIds.length} files to DeviantArt...`);

    try {
      const presetResponse = await fetch("/api/admin/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
      const presetData = await presetResponse.json();

      if (!presetData.success) {
        setStatus("Failed to save preset: " + presetData.error, "error");
        hideLoading();
        return;
      }

      const presetId = presetData.preset_id;

      const response = await fetch("/api/admin/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          preset_id: presetId,
          deviation_ids: selectedIds,
        }),
      });

      const data = await response.json();

      if (data.success) {
        const results = data.results || {};
        const successCount = results.success ? results.success.length : 0;
        const failedCount = results.failed ? results.failed.length : 0;

        await loadDrafts();
        await loadPresets();

        if (failedCount === 0) {
          setStatus(`Successfully uploaded ${successCount} files!`, "success");
        } else {
          setStatus(`Uploaded ${successCount}, failed ${failedCount}`, failedCount > 0 ? "error" : "success");
        }
      } else {
        setStatus("Upload failed: " + data.error, "error");
      }
    } catch (error) {
      console.error("Upload failed:", error);
      setStatus("Upload failed: " + error.message, "error");
    } finally {
      hideLoading();
    }
  }

  async function deleteSelected() {
    const selectedIds = getSelectedIds();
    if (!selectedIds.length) return;

    if (!confirm(`Delete ${selectedIds.length} selected files and their database records?`)) return;

    showLoading(`Deleting ${selectedIds.length} files...`);

    try {
      const response = await fetch("/api/admin/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deviation_ids: selectedIds }),
      });

      const data = await response.json();

      if (data.success) {
        await loadDrafts();
        setStatus(`Deleted ${data.count} files`, "success");
      } else {
        setStatus("Delete failed: " + data.error, "error");
      }
    } catch (error) {
      console.error("Delete failed:", error);
      setStatus("Delete failed: " + error.message, "error");
    } finally {
      hideLoading();
    }
  }

  async function deleteSingle(id) {
    if (!confirm("Delete this file and its database record?")) return;

    showLoading("Deleting...");

    try {
      const response = await fetch("/api/admin/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deviation_ids: [id] }),
      });

      const data = await response.json();

      if (data.success) {
        await loadDrafts();
        setStatus("File deleted", "success");
      } else {
        setStatus("Delete failed: " + data.error, "error");
      }
    } catch (error) {
      console.error("Delete failed:", error);
      setStatus("Delete failed: " + error.message, "error");
    } finally {
      hideLoading();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    loadGalleries();
    loadPresets();
    loadDrafts();
  });

  // Expose for inline handlers
  window.onPresetChange = onPresetChange;
  window.toggleMatureOptions = toggleMatureOptions;
  window.savePreset = savePreset;
  window.scanFiles = scanFiles;
  window.uploadSelected = uploadSelected;
  window.deleteSelected = deleteSelected;
  window.deleteSingle = deleteSingle;
  window.toggleSelectAll = toggleSelectAll;
  window.updateButtonStates = updateButtonStates;
})();
