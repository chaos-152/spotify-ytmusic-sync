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

// ---- Directional Tab Navigation ----
function switchTab(tabName) {
  const ytTabBtn = $("tab-btn-move-to-yt");
  const spTabBtn = $("tab-btn-move-to-sp");
  const ytView = $("view-move-to-yt");
  const spView = $("view-move-to-sp");

  if (!ytTabBtn || !spTabBtn || !ytView || !spView) return;

  if (tabName === "move-to-spotify") {
    ytTabBtn.classList.remove("active");
    spTabBtn.classList.add("active");
    ytView.classList.add("hidden");
    spView.classList.remove("hidden");
    history.replaceState(null, "", "?tab=move-to-spotify");
  } else {
    spTabBtn.classList.remove("active");
    ytTabBtn.classList.add("active");
    spView.classList.add("hidden");
    ytView.classList.remove("hidden");
    history.replaceState(null, "", "?tab=move-to-yt");
  }
}
window.switchTab = switchTab;

if ($("tab-btn-move-to-yt")) {
  $("tab-btn-move-to-yt").addEventListener("click", () => switchTab("move-to-yt"));
}
if ($("tab-btn-move-to-sp")) {
  $("tab-btn-move-to-sp").addEventListener("click", () => switchTab("move-to-spotify"));
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

  const spStatus = $("spotify-status");
  if (spStatus) {
    if (status.spotify_configured) {
      spStatus.textContent = "Configured (Catalog Search Active)";
      spStatus.className = "status connected";
    } else {
      spStatus.textContent = "Not configured (Client ID/Secret missing)";
      spStatus.className = "status";
    }
  }

  const spUserStatus = $("spotify-user-status");
  const spLoginBtn = $("spotify-login-btn");
  const spLogoutBtn = $("spotify-logout-btn");
  if (spUserStatus) {
    if (status.spotify_user_connected) {
      spUserStatus.textContent = `Connected as ${status.spotify_user_name || "Spotify User"}`;
      spUserStatus.className = "status connected";
      if (spLoginBtn) spLoginBtn.classList.add("hidden");
      if (spLogoutBtn) spLogoutBtn.classList.remove("hidden");
    } else {
      spUserStatus.textContent = "Not connected";
      spUserStatus.className = "status";
      if (spLoginBtn) spLoginBtn.classList.remove("hidden");
      if (spLogoutBtn) spLogoutBtn.classList.add("hidden");
    }
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

        <div style="margin-top:0.75rem; padding:0.6rem 0.8rem; background:#221b10; border:1px solid #734f18; border-radius:6px; font-size:0.8rem; color:#f0c674;">
          <strong>💡 Good to know for BYOK personal projects:</strong>
          <ul style="margin:0.3rem 0 0 0; padding-left:1.1rem; line-height:1.45;">
            <li><strong>"Google hasn't verified this app" warning:</strong> When you enter the code at <code>google.com/device</code>, Google will display an "unverified app" screen. Click <strong>Advanced &rarr; Go to (unsafe)</strong> to proceed — this is normal and expected for private personal developer projects.</li>
            <li><strong>7-Day Token Lifespan:</strong> Google expires Testing-mode OAuth refresh tokens after <strong>7 days</strong>. If you return after a week and sync fails, simply click <em>Connect YT Music</em> to refresh your session in 5 seconds.</li>
          </ul>
        </div>
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
 
function openSpotifySetupModal() {
  const content = `
    <div style="font-size:0.86rem; line-height: 1.55; color: #ddd;">
      <p style="margin-top:0;">To resolve YouTube tracks to exact Spotify URIs (<code>spotify:track:XXXX</code>), our Inverted Preprocessor queries the Spotify catalog using official Client Credentials.</p>
      
      <div style="background:#161616; border:1px solid #333; border-radius:8px; padding:0.9rem 1.1rem; margin:1rem 0;">
        <div style="font-weight:700; color:#fff; margin-bottom:0.5rem;">Spotify Developer Dashboard Setup:</div>
        <ol style="margin:0; padding-left:1.2rem; color:#bbb;">
          <li style="margin-bottom:0.35rem;">Log into <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noopener" style="color:#1ed760; text-decoration:underline; font-weight:600;">Spotify Developer Dashboard ↗</a>.</li>
          <li style="margin-bottom:0.35rem;">Click <strong>Create App</strong>. Enter any app name (e.g. <em>Playlist Sync</em>) and description.</li>
          <li style="margin-bottom:0.35rem;">Select <strong>Web API</strong> as the API you plan to use.</li>
          <li style="margin-bottom:0.35rem;">Under <strong>Redirect URIs</strong>, add: <code style="color:#1ed760; background:#222; padding:2px 5px; border-radius:4px;">http://127.0.0.1:8000/api/spotify/callback</code><br><span style="font-size:0.78rem; color:#aaa;">(⚠️ Spotify requires the numeric IP literal <code>127.0.0.1</code> — <code>localhost</code> is rejected by Spotify).</span></li>
          <li style="margin-bottom:0.35rem;">Go to <strong>Settings</strong> and copy your <strong>Client ID</strong> and <strong>Client Secret</strong>.</li>
        </ol>
        <div style="margin-top:0.6rem; font-size:0.78rem; color:#ffbb33; line-height:1.4;">
          ⚠️ <strong>2026 Developer Requirement:</strong> Spotify requires an active Spotify Premium subscription to register an app on the developer dashboard.
        </div>
      </div>

      <form id="setup-spotify-form" onsubmit="submitSpotifyCredentials(event)">
        <div style="margin-bottom:0.8rem;">
          <label style="display:block; margin-bottom:0.3rem; font-weight:600; color:#fff;">Spotify Client ID:</label>
          <input type="text" id="setup-spotify-client-id" placeholder="e.g. 4a2b8c9d0e..." required style="width:100%; box-sizing:border-box; background:#222; border:1px solid #444; border-radius:6px; color:#fff; padding:0.6rem 0.8rem;">
        </div>

        <div style="margin-bottom:1rem;">
          <label style="display:block; margin-bottom:0.3rem; font-weight:600; color:#fff;">Spotify Client Secret:</label>
          <input type="password" id="setup-spotify-client-secret" placeholder="e.g. f1e2d3c4b5..." required style="width:100%; box-sizing:border-box; background:#222; border:1px solid #444; border-radius:6px; color:#fff; padding:0.6rem 0.8rem;">
        </div>

        <p id="setup-spotify-feedback" class="import-status muted" style="margin-bottom:1rem;"></p>

        <div style="display:flex; justify-content:flex-end; gap:0.6rem;">
          <button type="button" class="btn secondary small" onclick="closeModal()">Cancel</button>
          <button type="submit" id="save-spotify-btn" class="btn small">Save &amp; Configure</button>
        </div>
      </form>
    </div>
  `;

  openModal("Spotify Developer Credentials Setup", "Configure Client Credentials for YouTube → Spotify URI Matching", content);
}
window.openSpotifySetupModal = openSpotifySetupModal;

async function submitSpotifyCredentials(e) {
  e.preventDefault();
  const clientId = $("setup-spotify-client-id").value.trim();
  const clientSecret = $("setup-spotify-client-secret").value.trim();
  const feedback = $("setup-spotify-feedback");
  const saveBtn = $("save-spotify-btn");

  if (!clientId || !clientSecret) {
    feedback.textContent = "Please fill in both fields.";
    feedback.className = "import-status error";
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";
  feedback.textContent = "Saving credentials…";
  feedback.className = "import-status muted";

  try {
    await api("/api/setup/spotify-credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    });

    feedback.textContent = "✅ Spotify credentials saved successfully!";
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
window.submitSpotifyCredentials = submitSpotifyCredentials;


async function loadLinks() {
  const container = $("links-list");
  if (!container) return;
  let links;
  try {
    links = await api("/api/links");
  } catch (err) {
    container.innerHTML = `<span class="import-status error">Failed to load playlists: ${escapeHtml(err.message)}</span>`;
    return;
  }
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
      let errDetail = "check backend logs";
      if (latest.errors && latest.errors.length) {
        const r = latest.errors[0].reason;
        if (r) errDetail = r;
      }
      statusEl.textContent = `Last sync failed: ${errDetail}`;
    }

    if (inspectBtn) {
      inspectBtn.classList.remove("hidden");
      inspectBtn.onclick = () => openRunInspection(latest);
    }
  }
}

function pollRunStatus(linkId) {
  let attempts = 0;
  const maxAttempts = 120; // 3 minutes max (120 * 1.5s)
  const interval = setInterval(async () => {
    attempts++;
    if (attempts > maxAttempts) {
      clearInterval(interval);
      refreshRunStatus(linkId);
      return;
    }
    try {
      const runs = await api(`/api/links/${linkId}/runs`);
      if (runs.length && runs[0].status !== "running") {
        clearInterval(interval);
        loadLinks(); // Refresh link list in case playlist ID was updated
      } else {
        refreshRunStatus(linkId);
      }
    } catch (e) {
      console.error(`Polling runs for link ${linkId} failed:`, e);
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
  if (!code) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(code).then(() => {
      $("copy-code-btn").textContent = "✅ Copied!";
      setTimeout(() => { $("copy-code-btn").textContent = "📋 Copy"; }, 2000);
    }).catch(() => {
      window.prompt("Copy this code manually:", code);
    });
  } else {
    window.prompt("Copy this code manually:", code);
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
    const maxAttempts = 60; // 60 × 5s = 5 minutes timeout

    const poll = setInterval(async () => {
      attempts++;

      if (attempts > maxAttempts) {
        clearInterval(poll);
        btn.disabled = false;
        btn.textContent = "Connect YT Music";
        box.classList.add("hidden");
        if (errBox) {
          errBox.textContent = "Authorization timed out after 5 minutes. Please try again.";
          errBox.classList.remove("hidden");
        }
        return;
      }

      try {
        await api("/api/ytmusic/complete-auth", { method: "POST" });
        clearInterval(poll);
        pollStatus.textContent = "✅ Connected! Refreshing…";
        pollStatus.style.color = "#1DB954";
        refreshStatus();
      } catch (e) {
        // Distinguish "not approved yet" (expected) from real server errors
        const isStillPending = e.message && (
          e.message.includes("428") ||
          e.message.toLowerCase().includes("pending") ||
          e.message.toLowerCase().includes("not approved") ||
          e.message.toLowerCase().includes("authorization_pending")
        );

        if (isStillPending) {
          if (pollStatus) {
            const remaining = Math.ceil((maxAttempts - attempts) * (device.interval || 5) / 60);
            pollStatus.textContent = `Waiting for you to enter the code on Google… (${remaining}min remaining)`;
          }
        } else {
          // Real error — stop polling
          clearInterval(poll);
          btn.disabled = false;
          btn.textContent = "Connect YT Music";
          box.classList.add("hidden");
          if (errBox) {
            errBox.textContent = `Authorization failed: ${e.message}`;
            errBox.classList.remove("hidden");
          }
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

// ---- Reverse Sync: YT Music -> Spotify URI CSV ----

async function openReverseSyncPreview(playlistRef) {
  const ref = (playlistRef || $("reverse-playlist-input")?.value || "").trim();
  const statusEl = $("reverse-status");
  if (!ref) {
    if (statusEl) {
      statusEl.textContent = "Please enter a YouTube Music playlist URL or ID.";
      statusEl.className = "import-status error";
    }
    return;
  }
  if (statusEl) {
    statusEl.textContent = "";
  }

  openModal(
    "Reverse Sync Match Preview",
    "Fetching YouTube playlist items and matching against Spotify catalog...",
    `<div style="text-align:center; padding: 2rem 0;">
       <p style="font-weight:600;">Resolving YouTube tracks to Spotify catalog URIs…</p>
       <p class="muted" style="font-size:0.8rem; margin-top:0.4rem;">Applying inverted title preprocessor, delimiter extraction, and candidate scoring.</p>
     </div>`
  );

  try {
    const result = await api("/api/reverse-sync/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist: ref }),
    });

    const items = result.details || [];
    const matchedCount = result.matched_count;
    const gapCount = result.gap_count;
    const total = result.total_tracks;
    const precision = result.match_precision;

    let noticeHtml = "";
    if (gapCount > 0) {
      noticeHtml = `
        <div style="background: rgba(255, 170, 0, 0.08); border: 1px solid rgba(255, 170, 0, 0.28); border-radius: 8px; padding: 0.75rem 1rem; margin-bottom: 1rem; font-size: 0.82rem; color: #ffbb33; line-height: 1.45;">
          ℹ️ <strong>Catalog Gap Detection:</strong> Detected <strong>${gapCount} YouTube track${gapCount > 1 ? "s" : ""}</strong> that did not clear the confidence threshold or were missing on Spotify. The export CSV will strictly include the <strong>${matchedCount} verified Spotify URIs</strong> to guarantee deterministic 1:1 importing.
        </div>
      `;
    }

    const subtitle = `Playlist: "${result.playlist_title}" &bull; Total: ${total} &bull; Matched URIs: ${matchedCount} (${precision}%) &bull; Gaps: ${gapCount}`;

    const renderTable = (filter) => {
      let filtered = items;
      if (filter === "matched") filtered = items.filter((d) => d.status === "matched");
      if (filter === "gaps") filtered = items.filter((d) => d.status !== "matched");

      if (filtered.length === 0) {
        return `${noticeHtml}<p class="muted" style="padding: 1.5rem 0; text-align:center;">No tracks under the "${filter}" filter.</p>`;
      }

      let html = noticeHtml + `
        <table class="telemetry-table">
          <thead>
            <tr>
              <th>YouTube Source Track</th>
              <th>Resolved Spotify Track &amp; URI</th>
              <th style="width: 100px;">Status</th>
              <th style="width: 130px;">Match Score</th>
            </tr>
          </thead>
          <tbody>
      `;

      filtered.forEach((item) => {
        let badge = "";
        let spotifyDisplay = "";
        const matchedTitle = item.matched_title || item.spotify_title || "";
        const matchedArtist = item.matched_artist || item.spotify_artist || "";
        const sourceTitle = item.yt_title || item.clean_title || item.source_title || "Unknown Title";
        const sourceArtist = item.yt_artist || item.clean_artist || (item.status === "matched" ? matchedArtist : "Unknown Artist");
        const scoreVal = (item.confidence !== undefined && item.confidence !== null)
          ? item.confidence
          : (item.score !== undefined ? item.score : null);

        if (item.status === "matched") {
          badge = `<span class="badge success">Resolved URI</span>`;
          spotifyDisplay = `
            <div style="font-weight:600; color:#fff;">${escapeHtml(matchedTitle)}</div>
            <div style="color:#888; font-size:0.75rem;">${escapeHtml(matchedArtist)}</div>
            <code style="color:#1ed760; font-size:0.72rem; background:#181818; padding:2px 4px; border-radius:3px;">${escapeHtml(item.spotify_uri || "")}</code>
          `;
        } else {
          badge = `<span class="badge warning">Catalog Gap</span>`;
          spotifyDisplay = `<span style="color:#666;">No Spotify candidate met threshold</span>`;
        }

        const scoreDisplay = item.status === "matched"
          ? `<span style="font-family:monospace; color:#1ed760; font-weight:600;">Score: ${scoreVal !== null ? scoreVal : "—"}</span>`
          : `<span style="color:#aaa; font-size:0.75rem;">Below 0.80</span>`;

        html += `
          <tr>
            <td>
              <div style="font-weight:600; color:#fff;">${escapeHtml(sourceTitle)}</div>
              <div style="color:#888; font-size:0.75rem;">${escapeHtml(sourceArtist)}</div>
            </td>
            <td>${spotifyDisplay}</td>
            <td>${badge}</td>
            <td>${scoreDisplay}</td>
          </tr>
        `;
      });

      html += `</tbody></table>`;
      return html;
    };

    const tabs = [
      { label: `All (${total})`, onClick: () => { $("modal-content").innerHTML = renderTable("all"); } },
      { label: `Matched Spotify URIs (${matchedCount})`, onClick: () => { $("modal-content").innerHTML = renderTable("matched"); } },
      { label: `Catalog Gaps (${gapCount})`, onClick: () => { $("modal-content").innerHTML = renderTable("gaps"); } },
    ];

    const footerHtml = `
      <button class="btn secondary small" onclick="closeModal()">Close</button>
      <button class="btn small" id="reverse-modal-export-btn" ${matchedCount === 0 ? "disabled" : ""}>
        📥 Download Spotify URI CSV (${matchedCount} tracks)
      </button>
    `;

    openModal(`Reverse Sync Preview: "${result.playlist_title}"`, subtitle, renderTable("all"), tabs, footerHtml);

    const modalExportBtn = $("reverse-modal-export-btn");
    if (modalExportBtn && matchedCount > 0) {
      modalExportBtn.onclick = () => {
        exportReverseSyncCsv(ref, result.playlist_title);
      };
    }
  } catch (err) {
    openModal(
      "Reverse Sync Preview Error",
      "Failed to resolve playlist",
      `<p style="color:#ff6b6b;">Error: ${escapeHtml(err.message)}</p>`
    );
  }
}
window.openReverseSyncPreview = openReverseSyncPreview;

async function exportReverseSyncCsv(playlistRef, playlistTitle) {
  const ref = (playlistRef || $("reverse-playlist-input")?.value || "").trim();
  const statusEl = $("reverse-status");
  const exportBtn = $("reverse-export-btn");

  if (!ref) {
    if (statusEl) {
      statusEl.textContent = "Please enter a YouTube Music playlist URL or ID.";
      statusEl.className = "import-status error";
    }
    return;
  }

  if (statusEl) {
    statusEl.textContent = "Generating Spotify URI CSV…";
    statusEl.className = "import-status muted";
  }
  if (exportBtn) exportBtn.disabled = true;

  try {
    const res = await fetch("/api/reverse-sync/export-csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist: ref }),
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText);
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;

    const disposition = res.headers.get("Content-Disposition");
    let filename = "playlist_spotify_uris.csv";
    if (disposition && disposition.indexOf("filename=") !== -1) {
      const match = disposition.match(/filename="?([^";]+)"?/);
      if (match && match[1]) filename = match[1];
    } else if (playlistTitle) {
      const safe = playlistTitle.replace(/[^a-zA-Z0-9_\- ]/g, "").trim();
      filename = `${safe || "playlist"}_spotify_uris.csv`;
    }

    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    if (statusEl) {
      statusEl.textContent = `✅ Downloaded "${filename}"!`;
      statusEl.className = "import-status success";
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = `Export failed: ${err.message}`;
      statusEl.className = "import-status error";
    }
  } finally {
    if (exportBtn) exportBtn.disabled = false;
  }
}
window.exportReverseSyncCsv = exportReverseSyncCsv;


// ---- Direct-to-Spotify Library Sync ----

async function triggerDirectSpotifySync() {
  const input = $("reverse-playlist-input");
  const statusEl = $("reverse-status");
  const directBtn = $("reverse-direct-btn");
  const resultBox = $("reverse-direct-result");
  const resultMeta = $("reverse-direct-meta");
  const resultLink = $("reverse-direct-link");

  const playlist = input ? input.value.trim() : "";
  if (!playlist) {
    if (statusEl) {
      statusEl.textContent = "Please enter a YouTube Music playlist URL or ID.";
      statusEl.className = "import-status error";
    }
    return;
  }

  if (resultBox) resultBox.classList.add("hidden");
  if (directBtn) {
    directBtn.disabled = true;
    directBtn.textContent = "✨ Syncing directly to Spotify…";
  }
  if (statusEl) {
    statusEl.textContent = "Resolving tracks and creating Spotify playlist…";
    statusEl.className = "import-status muted";
  }

  try {
    const data = await api("/api/reverse-sync/direct-sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlist }),
    });

    if (statusEl) {
      statusEl.textContent = `✅ Successfully created "${data.playlist_name}"!`;
      statusEl.className = "import-status success";
    }

    if (resultBox && resultMeta && resultLink) {
      resultMeta.textContent = `Added ${data.added_count} of ${data.total_tracks} tracks into your Spotify account (${data.precision_pct}% match precision).`;
      resultLink.href = data.playlist_url;
      resultBox.classList.remove("hidden");
    }
  } catch (err) {
    if (statusEl) {
      if (err.message && err.message.includes("401")) {
        statusEl.textContent = "⚠️ Please connect your Spotify account first (click 'Connect Spotify Account' above).";
      } else {
        statusEl.textContent = `Direct sync failed: ${err.message}`;
      }
      statusEl.className = "import-status error";
    }
  } finally {
    if (directBtn) {
      directBtn.disabled = false;
      directBtn.textContent = "✨ Sync Directly to Spotify";
    }
  }
}
window.triggerDirectSpotifySync = triggerDirectSpotifySync;


async function disconnectSpotifyUser() {
  try {
    await api("/api/spotify/logout", { method: "POST" });
    refreshStatus();
  } catch (e) {
    console.error("Failed to disconnect Spotify account:", e);
  }
}
window.disconnectSpotifyUser = disconnectSpotifyUser;


const revDirectBtn = $("reverse-direct-btn");
if (revDirectBtn) {
  revDirectBtn.addEventListener("click", () => triggerDirectSpotifySync());
}

const revPreviewBtn = $("reverse-preview-btn");
if (revPreviewBtn) {
  revPreviewBtn.addEventListener("click", () => openReverseSyncPreview());
}

const revExportBtn = $("reverse-export-btn");
if (revExportBtn) {
  revExportBtn.addEventListener("click", () => exportReverseSyncCsv());
}

// Check URL parameters for tab navigation and auth redirects
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get("tab") === "move-to-spotify" || urlParams.get("spotify_connected") || urlParams.get("spotify_error")) {
  switchTab("move-to-spotify");
  const statusEl = $("reverse-status");
  if (urlParams.get("spotify_connected") && statusEl) {
    statusEl.textContent = "✅ Spotify account connected successfully! You can now sync directly.";
    statusEl.className = "import-status success";
  } else if (urlParams.get("spotify_error") && statusEl) {
    statusEl.textContent = `⚠️ Spotify authorization error: ${urlParams.get("spotify_error")}`;
    statusEl.className = "import-status error";
  }
}

function openManualModal() {
  const sections = {
    quickstart: `
      <div style="font-size:0.88rem; line-height:1.6; color:#ddd;">
        <h4 style="color:#fff; margin-top:0;">⚡ 1-Click Launch & Overview</h4>
        <p>This tool lets you transfer playlists seamlessly between <strong>Spotify</strong> and <strong>YouTube Music</strong> without subscriptions or track limits.</p>
        <div style="background:#161616; border:1px solid #333; border-radius:8px; padding:1rem; margin:1rem 0;">
          <strong style="color:#fff;">How to Launch the App:</strong>
          <ul style="margin:0.5rem 0 0 0; padding-left:1.2rem; color:#bbb;">
            <li><strong>Windows:</strong> Double-click <code>run.bat</code>.</li>
            <li><strong>Mac / Linux:</strong> Open terminal, run <code>bash run.sh</code>.</li>
            <li>Opens automatically at <code>http://127.0.0.1:8000</code>.</li>
          </ul>
        </div>
        <div style="background:#161616; border:1px solid #333; border-radius:8px; padding:1rem; margin:1rem 0;">
          <strong style="color:#fff;">Choose Your Direction:</strong>
          <ul style="margin:0.5rem 0 0 0; padding-left:1.2rem; color:#bbb;">
            <li><span style="color:#ff0033; font-weight:600;">▶ Move to YT Music:</span> Transfer exported Spotify playlists into your YouTube Music library with 99%+ audio matching.</li>
            <li><span style="color:#1ed760; font-weight:600;">🟢 Move to Spotify:</span> Paste any YouTube Music playlist link and sync it directly into your Spotify account or download a 1-click import CSV.</li>
          </ul>
        </div>
      </div>
    `,
    forward: `
      <div style="font-size:0.88rem; line-height:1.6; color:#ddd;">
        <h4 style="color:#ff0033; margin-top:0;">▶ Spotify → YouTube Music Transfer</h4>
        <ol style="padding-left:1.2rem; margin:0.5rem 0;">
          <li style="margin-bottom:0.75rem;">
            <strong>Step 1: Connect YouTube Music</strong><br>
            Click <em>Connect YT Music</em>. Open the Google link displayed, enter the user code, and grant permission. (Takes 30 seconds).
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Step 2: Export Spotify Playlist CSV</strong><br>
            Open <a href="https://exportify.net" target="_blank" rel="noopener" style="color:#1ed760; text-decoration:underline;">exportify.net ↗</a> in your browser. Log in and click <strong>Export</strong> on any playlist to download its <code>.csv</code> file.
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Step 3: Drop CSV &amp; Import</strong><br>
            Drag and drop the downloaded <code>.csv</code> file into Section 2 of our app and click <strong>Import</strong>.
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Step 4: Sync &amp; Enjoy</strong><br>
            Click <em>Pre-Sync Preview</em> to inspect matches, or click <em>Sync now</em>. Once complete, click <strong>Open in YT Music ↗</strong> to listen!
          </li>
        </ol>
      </div>
    `,
    reverse: `
      <div style="font-size:0.88rem; line-height:1.6; color:#ddd;">
        <h4 style="color:#1ed760; margin-top:0;">🟢 YouTube Music → Spotify Transfer</h4>
        <ol style="padding-left:1.2rem; margin:0.5rem 0;">
          <li style="margin-bottom:0.75rem;">
            <strong>Step 1: Connect Your Spotify Account</strong><br>
            Under the <em>Move to Spotify</em> tab, click <strong>Connect Spotify Account</strong> and approve the permissions.
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Step 2: Paste Playlist Link</strong><br>
            Copy any YouTube Music playlist URL (e.g. <code>https://music.youtube.com/playlist?list=...</code>) and paste it into the input box.
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Step 3: 1-Click Direct Sync</strong><br>
            Click <strong>✨ Sync Directly to Spotify</strong>. The app matches every song with high precision, creates the playlist in your Spotify account, and injects the tracks automatically!
          </li>
          <li style="margin-bottom:0.75rem;">
            <strong>Alternative: CSV / Desktop Paste</strong><br>
            Click <em>📥 Export Spotify CSV</em>. You can open the file, copy the URIs, and press <kbd>Ctrl+V</kbd> inside an empty playlist in the Spotify Desktop app!
          </li>
        </ol>
      </div>
    `,
    faq: `
      <div style="font-size:0.88rem; line-height:1.6; color:#ddd;">
        <h4 style="color:#fff; margin-top:0;">⚠️ Common Questions &amp; Troubleshooting</h4>
        <div style="margin-bottom:1rem;">
          <strong style="color:#1ed760;">Q: Do I or my friends need Spotify Premium?</strong><br>
          <span style="color:#bbb;">No! Spotify Free accounts can transfer, create playlists, and add tracks via our tool without paying a subscription.</span>
        </div>
        <div style="margin-bottom:1rem;">
          <strong style="color:#1ed760;">Q: Why did YouTube Music say "Session expired" after a week?</strong><br>
          <span style="color:#bbb;">Because Google Cloud personal test projects refresh tokens for 7 days. Just click <em>Connect YT Music</em>, enter the new code at <code>google.com/device</code>, and your account reconnects in 10 seconds.</span>
        </div>
        <div style="margin-bottom:1rem;">
          <strong style="color:#1ed760;">Q: Where is the complete written manual?</strong><br>
          <span style="color:#bbb;">The full beginner-friendly installation and user guide is saved directly in your project folder at <code>INSTALLATION_GUIDE.md</code>.</span>
        </div>
      </div>
    `,
  };

  const tabs = [
    { label: "⚡ Quick Start", onClick: () => { $("modal-content").innerHTML = sections.quickstart; } },
    { label: "▶ Move to YT Music", onClick: () => { $("modal-content").innerHTML = sections.forward; } },
    { label: "🟢 Move to Spotify", onClick: () => { $("modal-content").innerHTML = sections.reverse; } },
    { label: "⚠️ FAQ & Tips", onClick: () => { $("modal-content").innerHTML = sections.faq; } },
  ];

  openModal("📖 Spotify ⇄ YT Music Sync: User Manual", "Everything you need to know about using this tool", sections.quickstart, tabs);
}
window.openManualModal = openManualModal;

refreshStatus().catch(err => {
  console.error("Initial status check failed:", err);
  const ytStatus = $("ytmusic-status");
  if (ytStatus) {
    ytStatus.textContent = "Server unreachable — is the backend running?";
    ytStatus.className = "status error";
  }
});


