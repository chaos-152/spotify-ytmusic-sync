const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

async function refreshStatus() {
  const status = await api("/api/status");

  const ytStatus = $("ytmusic-status");
  const ytBtn = $("ytmusic-connect-btn");
  const errBox = $("ytmusic-error");

  if (status.ytmusic_connected) {
    ytStatus.textContent = "Connected";
    ytStatus.className = "status connected";
    ytBtn.classList.add("hidden");
    $("ytmusic-device-box").classList.add("hidden");
    if (errBox) errBox.classList.add("hidden");
  } else if (!status.ytmusic_configured) {
    ytStatus.textContent = "Not configured (missing credentials in .env)";
    ytStatus.className = "status";
  } else {
    ytStatus.textContent = "Ready to connect";
    ytStatus.className = "status";
  }

  loadLinks();
  return status;
}


async function loadLinks() {
  const container = $("links-list");
  const links = await api("/api/links");
  container.innerHTML = "";
  if (links.length === 0) {
    container.textContent = "No playlists imported yet — use the form above.";
    return;
  }
  for (const link of links) {
    const row = document.createElement("div");
    row.className = "link-item";
    row.style.flexDirection = "column";
    row.style.alignItems = "stretch";
    row.style.gap = "0.6rem";

    const ytLinkBtn = link.ytmusic_playlist_id
      ? `<a href="https://music.youtube.com/playlist?list=${encodeURIComponent(link.ytmusic_playlist_id)}" target="_blank" rel="noopener" class="btn small secondary" style="text-decoration:none;">Open in YT Music ↗</a>`
      : "";

    row.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div class="pl-name">${escapeHtml(link.source_name)}</div>
          <div class="pl-meta">${link.track_count} tracks in CSV</div>
          <div class="run-status" id="run-status-${link.id}">—</div>
        </div>
        <div>
          ${ytLinkBtn}
        </div>
      </div>

      <div id="progress-wrap-${link.id}" class="progress-wrap hidden">
        <div class="progress-bar-container">
          <div id="progress-bar-${link.id}" class="progress-bar"></div>
        </div>
        <div id="progress-status-${link.id}" class="progress-status">
          <span>Starting sync…</span>
          <span>0%</span>
        </div>
      </div>

      <div class="btn-row">
        <button class="btn small" id="sync-btn-${link.id}">Sync now</button>
        <button class="btn small outline" id="preview-btn-${link.id}">Pre-Sync Preview</button>
        <button class="btn small outline" id="tracks-btn-${link.id}">View Tracks</button>
        <button class="btn small outline hidden" id="inspect-btn-${link.id}">Inspect Last Run</button>
      </div>
    `;

    row.querySelector(`#sync-btn-${link.id}`).addEventListener("click", () => triggerSync(link.id));
    row.querySelector(`#preview-btn-${link.id}`).addEventListener("click", () => openPreSyncPreview(link));
    row.querySelector(`#tracks-btn-${link.id}`).addEventListener("click", () => openTrackPreview(link));

    container.appendChild(row);
    refreshRunStatus(link.id);
  }
}

async function triggerSync(linkId) {
  const syncBtn = $(`sync-btn-${linkId}`);
  if (syncBtn) {
    syncBtn.disabled = true;
    syncBtn.textContent = "Starting…";
  }
  await api(`/api/links/${linkId}/sync`, { method: "POST" });
  pollRunStatus(linkId);
}

async function refreshRunStatus(linkId) {
  const runs = await api(`/api/links/${linkId}/runs`);
  const statusEl = $(`run-status-${linkId}`);
  const progressWrap = $(`progress-wrap-${linkId}`);
  const progressBar = $(`progress-bar-${linkId}`);
  const progressStatus = $(`progress-status-${linkId}`);
  const syncBtn = $(`sync-btn-${linkId}`);
  const inspectBtn = $(`inspect-btn-${linkId}`);

  if (!statusEl) return;
  if (runs.length === 0) {
    statusEl.textContent = "Never synced";
    if (progressWrap) progressWrap.classList.add("hidden");
    if (inspectBtn) inspectBtn.classList.add("hidden");
    if (syncBtn) { syncBtn.disabled = false; syncBtn.textContent = "Sync now"; }
    return;
  }

  const latest = runs[0];
  statusEl.className = `run-status ${latest.status}`;

  if (latest.status === "running") {
    if (syncBtn) { syncBtn.disabled = true; syncBtn.textContent = "Syncing…"; }
    if (progressWrap) progressWrap.classList.remove("hidden");
    const total = latest.total || 1;
    const current = latest.current || 0;
    const pct = Math.min(100, Math.round((current / total) * 100));
    if (progressBar) progressBar.style.width = `${pct}%`;
    if (progressStatus) {
      progressStatus.innerHTML = `
        <span>${escapeHtml(latest.message || `Processing track ${current}/${total}…`)}</span>
        <span>${pct}%</span>
      `;
    }
    statusEl.textContent = `Syncing… (${current}/${total})`;
    if (inspectBtn) inspectBtn.classList.add("hidden");
  } else {
    if (progressWrap) progressWrap.classList.add("hidden");
    if (syncBtn) { syncBtn.disabled = false; syncBtn.textContent = "Sync again"; }

    if (latest.status === "done") {
      statusEl.textContent = `Last sync: ${latest.added} added, ${latest.skipped} skipped`;
    } else {
      statusEl.textContent = "Last sync failed — check backend logs";
    }

    if (inspectBtn) {
      inspectBtn.classList.remove("hidden");
      inspectBtn.onclick = () => openRunInspection(latest);
    }
  }
}

function pollRunStatus(linkId) {
  const interval = setInterval(async () => {
    const runs = await api(`/api/links/${linkId}/runs`);
    if (runs.length && runs[0].status !== "running") {
      clearInterval(interval);
      loadLinks(); // Refresh link list in case playlist ID was updated
    } else {
      refreshRunStatus(linkId);
    }
  }, 1500);
}

// ---- Modal Management ----

function openModal(title, subtitle, contentHtml, tabs = [], footerHtml = "") {
  $("modal-title").textContent = title;
  $("modal-subtitle").textContent = subtitle;
  $("modal-content").innerHTML = contentHtml;

  const tabsContainer = $("modal-tabs");
  if (tabs.length > 0) {
    tabsContainer.classList.remove("hidden");
    tabsContainer.innerHTML = "";
    tabs.forEach((tab, i) => {
      const btn = document.createElement("button");
      btn.className = `tab-btn ${i === 0 ? "active" : ""}`;
      btn.textContent = tab.label;
      btn.onclick = () => {
        tabsContainer.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        tab.onClick();
      };
      tabsContainer.appendChild(btn);
    });
  } else {
    tabsContainer.classList.add("hidden");
  }

  const footer = $("modal-footer");
  if (footerHtml) {
    footer.innerHTML = footerHtml;
    footer.classList.remove("hidden");
  } else {
    footer.classList.add("hidden");
  }

  $("modal-backdrop").classList.remove("hidden");
}

function closeModal() {
  const backdrop = $("modal-backdrop");
  if (backdrop) backdrop.classList.add("hidden");
  const content = $("modal-content");
  if (content) content.innerHTML = "";
  const tabs = $("modal-tabs");
  if (tabs) {
    tabs.innerHTML = "";
    tabs.classList.add("hidden");
  }
  const footer = $("modal-footer");
  if (footer) {
    footer.innerHTML = "";
    footer.classList.add("hidden");
  }
}
window.closeModal = closeModal;

const modalCloseBtn = $("modal-close-btn");
if (modalCloseBtn) {
  modalCloseBtn.addEventListener("click", (e) => {
    e.preventDefault();
    closeModal();
  });
}

const modalBackdrop = $("modal-backdrop");
if (modalBackdrop) {
  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) closeModal();
  });
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeModal();
});

// ---- Track Preview (Feature 1) ----

async function openTrackPreview(link) {
  openModal(
    `Tracks in "${link.source_name}"`,
    `Loading parsed CSV tracks…`,
    `<p class="muted">Loading tracks from local database…</p>`
  );

  try {
    const tracks = await api(`/api/links/${link.id}/tracks`);
    const subtitle = `${tracks.length} tracks parsed from CSV`;

    let tableHtml = `
      <table class="telemetry-table">
        <thead>
          <tr>
            <th style="width: 40px;">#</th>
            <th>Title</th>
            <th>Artist</th>
            <th>Album</th>
            <th style="width: 70px; text-align: right;">Length</th>
          </tr>
        </thead>
        <tbody>
    `;

    tracks.forEach((t, idx) => {
      const durSec = t.duration_ms ? Math.round(t.duration_ms / 1000) : null;
      const durStr = durSec ? `${Math.floor(durSec / 60)}:${String(durSec % 60).padStart(2, "0")}` : "—";
      tableHtml += `
        <tr>
          <td style="color:#888;">${idx + 1}</td>
          <td style="font-weight:600; color:#fff;">${escapeHtml(t.title)}</td>
          <td style="color:#ccc;">${escapeHtml(t.artist)}</td>
          <td style="color:#888;">${escapeHtml(t.album || "—")}</td>
          <td style="text-align:right; font-family:monospace; color:#888;">${durStr}</td>
        </tr>
      `;
    });

    tableHtml += `</tbody></table>`;
    openModal(`Tracks in "${link.source_name}"`, subtitle, tableHtml);
  } catch (err) {
    openModal(
      `Tracks in "${link.source_name}"`,
      "Error loading tracks",
      `<p style="color:#ff6b6b;">Failed to load tracks: ${escapeHtml(err.message)}</p>`
    );
  }
}

// ---- Run Telemetry & Missing Tracks Inspection (Feature 2) ----

function openRunInspection(run) {
  let details = [];
  const isLegacy = !run.details;

  if (run.details) {
    details = typeof run.details === "string" ? JSON.parse(run.details) : run.details;
  } else if (run.errors) {
    // Fallback for legacy runs without detailed telemetry
    const errs = typeof run.errors === "string" ? JSON.parse(run.errors) : run.errors;
    details = errs.map((e) => ({
      title: e.track || "Track",
      artist: "",
      status: "skipped",
      category: "threshold_miss",
      reason: e.reason || "Skipped",
    }));
  }

  let noticeHtml = "";
  if (isLegacy) {
    const unloggedDups = Math.max(0, run.skipped - details.length);
    noticeHtml = `
      <div style="background: rgba(255, 170, 0, 0.08); border: 1px solid rgba(255, 170, 0, 0.28); border-radius: 8px; padding: 0.85rem 1rem; margin-bottom: 1.2rem; font-size: 0.82rem; color: #ffbb33; line-height: 1.45;">
        <strong>ℹ️ Legacy Run Note:</strong> This sync (Run #${run.id}) was completed before full per-track telemetry was enabled.
        Of the ${run.skipped} skipped songs:
        <ul style="margin: 0.4rem 0 0.4rem 1.2rem; padding: 0;">
          <li><strong>${details.length} tracks</strong> were catalog gaps that did not meet confidence criteria (listed below).</li>
          ${unloggedDups > 0 ? `<li><strong>${unloggedDups} tracks</strong> were duplicates already present in your YouTube Music playlist from an earlier sync run.</li>` : ""}
        </ul>
        <em>Running a new sync or Pre-Sync Preview now captures complete audit records for all tracks!</em>
      </div>
    `;
  }

  const renderTable = (filter) => {
    let filtered = details;
    if (filter === "added") filtered = details.filter((d) => d.status === "added" || d.status === "matched");
    if (filter === "skipped") filtered = details.filter((d) => d.status === "skipped" || d.status === "error");

    if (filtered.length === 0) {
      return `${noticeHtml}<p class="muted" style="padding: 1.5rem 0; text-align:center;">No items found under the "${filter}" filter.</p>`;
    }

    let html = noticeHtml + `
      <table class="telemetry-table">
        <thead>
          <tr>
            <th>Source Track</th>
            <th>Matched YouTube Title & Channel</th>
            <th style="width: 100px;">Status</th>
            <th>Details / Reason</th>
          </tr>
        </thead>
        <tbody>
    `;

    filtered.forEach((item) => {
      let badge = "";
      if (item.status === "added" || item.status === "matched") {
        badge = `<span class="badge success">Added</span>`;
      } else if (item.category === "duplicate") {
        badge = `<span class="badge neutral">Duplicate</span>`;
      } else if (item.category === "threshold_miss" || item.category === "no_results") {
        badge = `<span class="badge warning">Catalog Gap</span>`;
      } else {
        badge = `<span class="badge danger">Error</span>`;
      }

      const matchDesc = item.matched_title
        ? `<strong>${escapeHtml(item.matched_title)}</strong>${item.matched_artist ? ` <span style="color:#888;">[${escapeHtml(item.matched_artist)}]</span>` : ""}`
        : `<span style="color:#666;">—</span>`;

      const reasonDesc = item.reason
        ? `<span style="color:#aaa;">${escapeHtml(item.reason)}</span>`
        : (item.score !== undefined ? `<span style="color:#888; font-family:monospace;">Score: ${item.score}</span>` : `<span style="color:#666;">Match confirmed</span>`);

      html += `
        <tr>
          <td>
            <div style="font-weight:600; color:#fff;">${escapeHtml(item.title)}</div>
            <div style="color:#888; font-size:0.75rem;">${escapeHtml(item.artist)}</div>
          </td>
          <td>${matchDesc}</td>
          <td>${badge}</td>
          <td style="font-size:0.78rem;">${reasonDesc}</td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    return html;
  };

  const addedCount = run.added;
  const skippedCount = run.skipped;
  const subtitle = `Run #${run.id} &bull; ${addedCount} added, ${skippedCount} skipped (Finished: ${new Date(run.finished_at * 1000).toLocaleTimeString()})`;

  const addedFiltered = details.filter((d) => d.status === "added" || d.status === "matched").length;
  const skippedFiltered = details.filter((d) => d.status === "skipped" || d.status === "error").length;

  const tabs = isLegacy
    ? [
        { label: `Catalog Gaps (${details.length})`, onClick: () => { $("modal-content").innerHTML = renderTable("all"); } },
      ]
    : [
        { label: `All (${details.length})`, onClick: () => { $("modal-content").innerHTML = renderTable("all"); } },
        { label: `Added (${addedFiltered})`, onClick: () => { $("modal-content").innerHTML = renderTable("added"); } },
        { label: `Skipped (${skippedFiltered})`, onClick: () => { $("modal-content").innerHTML = renderTable("skipped"); } },
      ];

  openModal(`Sync Run Telemetry`, subtitle, renderTable("all"), tabs);
}

// ---- Pre-Sync Match Preview & Approval (Feature 4) ----

async function openPreSyncPreview(link) {
  openModal(
    `Pre-Sync Match Preview: "${link.source_name}"`,
    "Searching YouTube Music candidates and evaluating confidence gates (0 Data API quota used)…",
    `<div style="text-align:center; padding: 2rem 0;">
       <p style="font-weight:600;">Evaluating matches against YouTube Music…</p>
       <p class="muted" style="font-size:0.8rem; margin-top:0.4rem;">Testing core title similarity, canonical artists, and version tags without mutating any playlists.</p>
     </div>`
  );

  try {
    const preview = await api(`/api/links/${link.id}/preview`, { method: "POST" });
    const subtitle = `Total: ${preview.total} &bull; Matched: ${preview.matched_count} &bull; Skipped/Gaps: ${preview.skipped_count}`;

    const renderPreviewTable = (filter) => {
      let items = preview.details || [];
      if (filter === "matched") items = items.filter((d) => d.status === "matched");
      if (filter === "skipped") items = items.filter((d) => d.status === "skipped" || d.status === "error");

      let html = `
        <table class="telemetry-table">
          <thead>
            <tr>
              <th>Target Track</th>
              <th>Proposed YouTube Candidate</th>
              <th style="width: 90px;">Outcome</th>
              <th style="width: 130px;">Score / Reason</th>
            </tr>
          </thead>
          <tbody>
      `;

      items.forEach((item) => {
        const badge = item.status === "matched"
          ? `<span class="badge success">Match</span>`
          : `<span class="badge warning">Skip</span>`;

        const cand = item.matched_title
          ? `<strong>${escapeHtml(item.matched_title)}</strong>${item.matched_artist ? ` <span style="color:#888;">[${escapeHtml(item.matched_artist)}]</span>` : ""}`
          : `<span style="color:#666;">No valid candidate</span>`;

        const scoreInfo = item.status === "matched"
          ? `<span style="font-family:monospace; color:#1ed760; font-weight:600;">Score: ${item.score}</span>`
          : `<span style="color:#aaa; font-size:0.75rem;">${escapeHtml(item.reason || "Below threshold")}</span>`;

        html += `
          <tr>
            <td>
              <div style="font-weight:600; color:#fff;">${escapeHtml(item.title)}</div>
              <div style="color:#888; font-size:0.75rem;">${escapeHtml(item.artist)}</div>
            </td>
            <td>${cand}</td>
            <td>${badge}</td>
            <td>${scoreInfo}</td>
          </tr>
        `;
      });

      html += `</tbody></table>`;
      return html;
    };

    const tabs = [
      { label: `All (${preview.total})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("all"); } },
      { label: `Matches (${preview.matched_count})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("matched"); } },
      { label: `Skipped (${preview.skipped_count})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("skipped"); } },
    ];

    const footerHtml = `
      <button class="btn secondary small" onclick="closeModal()">Cancel</button>
      <button class="btn small" id="approve-sync-btn">Approve & Start Sync</button>
    `;

    openModal(`Pre-Sync Match Preview: "${link.source_name}"`, subtitle, renderPreviewTable("all"), tabs, footerHtml);

    const approveBtn = $("approve-sync-btn");
    if (approveBtn) {
      approveBtn.onclick = () => {
        closeModal();
        triggerSync(link.id);
      };
    }
  } catch (err) {
    openModal(
      `Pre-Sync Match Preview: "${link.source_name}"`,
      "Preview error",
      `<p style="color:#ff6b6b;">Failed to generate preview: ${escapeHtml(err.message)}</p>`
    );
  }
}

// ---- CSV import with drag-and-drop & auto-name ----

const dropzone = $("dropzone");
const fileInput = $("playlist-csv");
const playlistNameInput = $("playlist-name");

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function derivePlaylistName(filename) {
  return filename
    .replace(/\.[^/.]+$/, "")
    .replace(/[_\-]+/g, " ")
    .replace(/\s*\(\d+\)$/, "")
    .trim();
}

function updateSelectedFile(file) {
  if (!file) {
    $("dropzone-content").classList.remove("hidden");
    $("file-info").classList.add("hidden");
    return;
  }
  $("dropzone-content").classList.add("hidden");
  $("file-info").classList.remove("hidden");
  $("file-name").textContent = file.name;
  $("file-size").textContent = `(${formatBytes(file.size)})`;

  if (!playlistNameInput.value.trim() || playlistNameInput.dataset.autofilled === "true") {
    playlistNameInput.value = derivePlaylistName(file.name);
    playlistNameInput.dataset.autofilled = "true";
  }
}

["dragenter", "dragover"].forEach((name) => {
  dropzone.addEventListener(name, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((name) => {
  dropzone.addEventListener(name, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

fileInput.addEventListener("change", (e) => {
  if (e.target.files && e.target.files[0]) {
    updateSelectedFile(e.target.files[0]);
  } else {
    updateSelectedFile(null);
  }
});

$("remove-file-btn").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  fileInput.value = "";
  updateSelectedFile(null);
  if (playlistNameInput.dataset.autofilled === "true") {
    playlistNameInput.value = "";
    delete playlistNameInput.dataset.autofilled;
  }
});

playlistNameInput.addEventListener("input", () => {
  delete playlistNameInput.dataset.autofilled;
});

$("import-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = playlistNameInput.value.trim();
  const statusEl = $("import-status");
  const submitBtn = $("import-submit-btn");

  if (!fileInput.files.length) {
    statusEl.className = "import-status error";
    statusEl.textContent = "Please choose or drop a CSV file.";
    return;
  }

  const formData = new FormData();
  formData.append("name", name);
  formData.append("file", fileInput.files[0]);

  statusEl.className = "import-status muted";
  statusEl.textContent = "Importing…";
  submitBtn.disabled = true;
  submitBtn.textContent = "Importing…";

  try {
    const result = await api("/api/import-csv", { method: "POST", body: formData });
    statusEl.className = "import-status success";
    statusEl.textContent = `Imported "${result.source_name}" — ${result.track_count} tracks.`;
    $("import-form").reset();
    updateSelectedFile(null);
    delete playlistNameInput.dataset.autofilled;
    loadLinks();
  } catch (err) {
    statusEl.className = "import-status error";
    statusEl.textContent = `Import failed: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Import";
  }
});


// ---- YT Music device-code connect flow ----

$("copy-code-btn").addEventListener("click", () => {
  const code = $("ytmusic-user-code").textContent;
  if (code) {
    navigator.clipboard.writeText(code).then(() => {
      $("copy-code-btn").textContent = "✅ Copied!";
      setTimeout(() => { $("copy-code-btn").textContent = "📋 Copy"; }, 2000);
    });
  }
});

$("ytmusic-connect-btn").addEventListener("click", async () => {
  const btn = $("ytmusic-connect-btn");
  const errBox = $("ytmusic-error");
  if (errBox) errBox.classList.add("hidden");

  btn.disabled = true;
  btn.textContent = "Starting…";

  try {
    const device = await api("/api/ytmusic/start-auth", { method: "POST" });

    const box = $("ytmusic-device-box");
    box.classList.remove("hidden");
    $("ytmusic-verify-url").href = device.verification_url;
    $("ytmusic-verify-url").textContent = device.verification_url;
    $("ytmusic-user-code").textContent = device.user_code;
    btn.textContent = "Waiting for approval…";

    const pollStatus = $("ytmusic-poll-status");
    let attempts = 0;

    const poll = setInterval(async () => {
      attempts++;
      try {
        await api("/api/ytmusic/complete-auth", { method: "POST" });
        clearInterval(poll);
        pollStatus.textContent = "✅ Connected! Refreshing…";
        pollStatus.style.color = "#1DB954";
        refreshStatus();
      } catch (e) {
        // 428 = not approved yet, keep polling
        if (pollStatus) {
          pollStatus.textContent = `Waiting for you to enter the code on Google… (attempt ${attempts})`;
        }
      }
    }, (device.interval || 5) * 1000);
  } catch (err) {
    btn.disabled = false;
    btn.textContent = "Connect YT Music";
    if (errBox) {
      errBox.textContent = `Connection failed: ${err.message}`;
      errBox.classList.remove("hidden");
    }
  }
});

refreshStatus();

