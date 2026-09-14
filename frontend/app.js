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

  const setupBtn = $("setup-guide-btn");

  if (status.ytmusic_connected) {
    ytStatus.textContent = "Connected";
    ytStatus.className = "status connected";
    ytBtn.classList.add("hidden");
    if (setupBtn) setupBtn.classList.add("hidden");
    $("ytmusic-device-box").classList.add("hidden");
    if (errBox) errBox.classList.add("hidden");
  } else if (!status.ytmusic_configured) {
    ytStatus.textContent = "Not configured (missing credentials)";
    ytStatus.className = "status";
    ytBtn.classList.add("hidden");
    if (setupBtn) setupBtn.classList.remove("hidden");
  } else {
    ytStatus.textContent = "Ready to connect";
    ytStatus.className = "status";
    ytBtn.classList.remove("hidden");
    if (setupBtn) setupBtn.classList.add("hidden");
  }

  loadLinks();
  return status;
}

function openSetupModal() {
  const content = `
    <div style="font-size:0.86rem; line-height: 1.55; color: #ddd;">
      <p style="margin-top:0;">To sync playlists with YouTube Music at zero cost, this tool uses Google's official OAuth 2.0 Device Authorization flow.</p>
      
      <div style="background:#161616; border:1px solid #333; border-radius:8px; padding:0.9rem 1.1rem; margin:1rem 0;">
        <div style="font-weight:700; color:#fff; margin-bottom:0.5rem;">Google Cloud Console (Free 2-minute Setup):</div>
        <ol style="margin:0; padding-left:1.2rem; color:#bbb;">
          <li style="margin-bottom:0.35rem;">Open <a href="https://console.cloud.google.com/" target="_blank" rel="noopener" style="color:#1ed760; text-decoration:underline; font-weight:600;">Google Cloud Console ↗</a> and create a project.</li>
          <li style="margin-bottom:0.35rem;">Under <strong>APIs & Services &rarr; Library</strong>, search for and enable <strong>YouTube Data API v3</strong>.</li>
          <li style="margin-bottom:0.35rem;">Under <strong>OAuth consent screen</strong>, select <strong>External</strong>, and add your Google email under <strong>Test users</strong>.</li>
          <li style="margin-bottom:0.35rem;">Under <strong>Credentials &rarr; Create Credentials &rarr; OAuth client ID</strong>, choose Application type: <strong>TVs and Limited Input devices</strong>.</li>
        </ol>
      </div>

      <form id="setup-credentials-form" onsubmit="submitCredentials(event)">
        <div style="margin-bottom:0.8rem;">
          <label style="display:block; margin-bottom:0.3rem; font-weight:600; color:#fff;">Google Client ID:</label>
          <input type="text" id="setup-client-id" placeholder="e.g. 123456789-xyz.apps.googleusercontent.com" required style="width:100%; box-sizing:border-box; background:#222; border:1px solid #444; border-radius:6px; color:#fff; padding:0.6rem 0.8rem;">
        </div>

        <div style="margin-bottom:1rem;">
          <label style="display:block; margin-bottom:0.3rem; font-weight:600; color:#fff;">Google Client Secret:</label>
          <input type="password" id="setup-client-secret" placeholder="e.g. GOCSPX-..." required style="width:100%; box-sizing:border-box; background:#222; border:1px solid #444; border-radius:6px; color:#fff; padding:0.6rem 0.8rem;">
        </div>

        <p id="setup-feedback" class="import-status muted" style="margin-bottom:1rem;"></p>

        <div style="display:flex; justify-content:flex-end; gap:0.6rem;">
          <button type="button" class="btn secondary small" onclick="closeModal()">Cancel</button>
          <button type="submit" id="save-credentials-btn" class="btn small">Save & Configure</button>
        </div>
      </form>
    </div>
  `;

  openModal("Google Cloud Credentials Setup", "Configure your OAuth Client ID and Secret directly", content);
}
window.openSetupModal = openSetupModal;

async function submitCredentials(e) {
  e.preventDefault();
  const clientId = $("setup-client-id").value.trim();
  const clientSecret = $("setup-client-secret").value.trim();
  const feedback = $("setup-feedback");
  const saveBtn = $("save-credentials-btn");

  if (!clientId || !clientSecret) {
    feedback.textContent = "Please provide both Client ID and Client Secret.";
    feedback.className = "import-status error";
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";
  feedback.textContent = "Saving credentials and initializing environment…";
  feedback.className = "import-status muted";

  try {
    await api("/api/setup/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    });

    feedback.textContent = "✅ Credentials saved successfully! Refreshing…";
    feedback.className = "import-status success";

    setTimeout(() => {
      closeModal();
      refreshStatus();
    }, 1200);
  } catch (err) {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save & Configure";
    feedback.textContent = `Failed to save: ${err.message}`;
    feedback.className = "import-status error";
  }
}
window.submitCredentials = submitCredentials;


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

// ---- Track Preview with Duplicate Detection (Feature 1) ----

async function openTrackPreview(link) {
  openModal(
    `Tracks in "${link.source_name}"`,
    `Loading parsed CSV tracks…`,
    `<p class="muted">Loading tracks from local database…</p>`
  );

  try {
    const tracks = await api(`/api/links/${link.id}/tracks`);
    const dupCount = tracks.filter((t) => t.is_duplicate).length;
    const uniqueCount = tracks.length - dupCount;

    let noticeHtml = "";
    if (dupCount > 0) {
      noticeHtml = `
        <div style="background: rgba(255, 170, 0, 0.08); border: 1px solid rgba(255, 170, 0, 0.28); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.82rem; color: #ffbb33; line-height: 1.45;">
          ⚠️ <strong>Duplicate Detection:</strong> Found <strong>${dupCount} repeated track${dupCount > 1 ? "s" : ""}</strong> in this playlist CSV. They are flagged below and will be automatically skipped during sync to prevent cluttering YouTube Music.
        </div>
      `;
    }

    const renderTrackTable = (filter) => {
      let filtered = tracks;
      if (filter === "unique") filtered = tracks.filter((t) => !t.is_duplicate);
      if (filter === "duplicates") filtered = tracks.filter((t) => t.is_duplicate);

      if (filtered.length === 0) {
        return `${noticeHtml}<p class="muted" style="padding: 1.5rem 0; text-align:center;">No tracks under the "${filter}" filter.</p>`;
      }

      let html = noticeHtml + `
        <table class="telemetry-table">
          <thead>
            <tr>
              <th style="width: 40px;">#</th>
              <th>Title</th>
              <th>Artist</th>
              <th>Album</th>
              <th style="width: 130px;">Status</th>
              <th style="width: 70px; text-align: right;">Length</th>
            </tr>
          </thead>
          <tbody>
      `;

      filtered.forEach((t, idx) => {
        const durSec = t.duration_ms ? Math.round(t.duration_ms / 1000) : null;
        const durStr = durSec ? `${Math.floor(durSec / 60)}:${String(durSec % 60).padStart(2, "0")}` : "—";
        const badge = t.is_duplicate
          ? `<span class="badge neutral" title="First appeared at track #${t.first_seen_index}">Duplicate (matches #${t.first_seen_index})</span>`
          : `<span class="badge success">Unique</span>`;

        html += `
          <tr>
            <td style="color:#888;">${idx + 1}</td>
            <td style="font-weight:600; color:#fff;">${escapeHtml(t.title)}</td>
            <td style="color:#ccc;">${escapeHtml(t.artist)}</td>
            <td style="color:#888;">${escapeHtml(t.album || "—")}</td>
            <td>${badge}</td>
            <td style="text-align:right; font-family:monospace; color:#888;">${durStr}</td>
          </tr>
        `;
      });

      html += `</tbody></table>`;
      return html;
    };

    const subtitle = `${tracks.length} tracks &bull; ${uniqueCount} unique &bull; ${dupCount} duplicate${dupCount === 1 ? "" : "s"}`;
    const tabs = [
      { label: `All (${tracks.length})`, onClick: () => { $("modal-content").innerHTML = renderTrackTable("all"); } },
      { label: `Unique (${uniqueCount})`, onClick: () => { $("modal-content").innerHTML = renderTrackTable("unique"); } },
      { label: `Duplicates (${dupCount})`, onClick: () => { $("modal-content").innerHTML = renderTrackTable("duplicates"); } },
    ];

    openModal(`Tracks in "${link.source_name}"`, subtitle, renderTrackTable("all"), tabs);
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
    const items = preview.details || [];
    const dupCount = items.filter((d) => d.category === "duplicate").length;
    const gapCount = items.filter((d) => d.category === "threshold_miss" || d.category === "no_results" || d.category === "error").length;
    const toAddCount = items.filter((d) => d.status === "matched").length;

    let noticeHtml = "";
    if (dupCount > 0) {
      noticeHtml = `
        <div style="background: rgba(255, 170, 0, 0.08); border: 1px solid rgba(255, 170, 0, 0.28); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.82rem; color: #ffbb33; line-height: 1.45;">
          ℹ️ <strong>Duplicate Detection:</strong> Detected <strong>${dupCount} duplicate track${dupCount > 1 ? "s" : ""}</strong> (already present in your YouTube Music playlist or repeated in this batch). They will be skipped automatically during sync.
        </div>
      `;
    }

    const subtitle = `Total: ${preview.total} &bull; To Add: ${toAddCount} &bull; Duplicates: ${dupCount} &bull; Catalog Gaps: ${gapCount}`;

    const renderPreviewTable = (filter) => {
      let filtered = items;
      if (filter === "matched") filtered = items.filter((d) => d.status === "matched");
      if (filter === "duplicates") filtered = items.filter((d) => d.category === "duplicate");
      if (filter === "gaps") filtered = items.filter((d) => d.category === "threshold_miss" || d.category === "no_results" || d.category === "error");

      if (filtered.length === 0) {
        return `${noticeHtml}<p class="muted" style="padding: 1.5rem 0; text-align:center;">No tracks under the "${filter}" filter.</p>`;
      }

      let html = noticeHtml + `
        <table class="telemetry-table">
          <thead>
            <tr>
              <th>Target Track</th>
              <th>Proposed YouTube Candidate</th>
              <th style="width: 100px;">Outcome</th>
              <th style="width: 140px;">Score / Reason</th>
            </tr>
          </thead>
          <tbody>
      `;

      filtered.forEach((item) => {
        let badge = "";
        if (item.status === "matched") {
          badge = `<span class="badge success">Will Add</span>`;
        } else if (item.category === "duplicate") {
          badge = `<span class="badge neutral">Duplicate</span>`;
        } else if (item.category === "threshold_miss" || item.category === "no_results") {
          badge = `<span class="badge warning">Catalog Gap</span>`;
        } else {
          badge = `<span class="badge danger">Error</span>`;
        }

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
      { label: `To Add (${toAddCount})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("matched"); } },
      { label: `Duplicates (${dupCount})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("duplicates"); } },
      { label: `Catalog Gaps (${gapCount})`, onClick: () => { $("modal-content").innerHTML = renderPreviewTable("gaps"); } },
    ];

    const footerHtml = `
      <button class="btn secondary small" onclick="closeModal()">Cancel</button>
      <button class="btn small" id="approve-sync-btn" ${toAddCount === 0 ? "disabled" : ""}>
        ${toAddCount > 0 ? `Approve & Add ${toAddCount} Tracks` : "All Tracks Up to Date"}
      </button>
    `;

    openModal(`Pre-Sync Match Preview: "${link.source_name}"`, subtitle, renderPreviewTable("all"), tabs, footerHtml);

    const approveBtn = $("approve-sync-btn");
    if (approveBtn && toAddCount > 0) {
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

