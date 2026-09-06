const $ = (id) => document.getElementById(id);

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
    row.innerHTML = `
      <div>
        <div class="pl-name">${escapeHtml(link.source_name)}</div>
        <div class="pl-meta">${link.track_count} tracks</div>
        <div class="run-status" id="run-status-${link.id}">—</div>
      </div>
      <button class="btn small secondary" data-link-id="${link.id}">Sync now</button>
    `;
    row.querySelector("button").addEventListener("click", () => triggerSync(link.id));
    container.appendChild(row);
    refreshRunStatus(link.id);
  }
}

async function triggerSync(linkId) {
  await api(`/api/links/${linkId}/sync`, { method: "POST" });
  pollRunStatus(linkId);
}

async function refreshRunStatus(linkId) {
  const runs = await api(`/api/links/${linkId}/runs`);
  const el = $(`run-status-${linkId}`);
  if (!el) return;
  if (runs.length === 0) {
    el.textContent = "Never synced";
    return;
  }
  const latest = runs[0];
  el.className = `run-status ${latest.status}`;
  if (latest.status === "running") {
    el.textContent = "Syncing…";
  } else if (latest.status === "done") {
    el.textContent = `Last sync: ${latest.added} added, ${latest.skipped} skipped`;
  } else {
    el.textContent = "Last sync failed — check backend logs";
  }
}

function pollRunStatus(linkId) {
  const interval = setInterval(async () => {
    const runs = await api(`/api/links/${linkId}/runs`);
    if (runs.length && runs[0].status !== "running") {
      clearInterval(interval);
    }
    refreshRunStatus(linkId);
  }, 2000);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
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

