/**
 * Production Operational Dashboard - Client Logic
 * Lovable Automation Platform (~40 sites/day)
 */

let allJobs = [];
let activeJobId = null;
let selectedJobIds = new Set();
let lovableTimerInterval = null;
let activeLovableStartedAt = null;
let confirmCallback = null;

// ==========================================
// 1. Toast & Modal Notification Helpers
// ==========================================

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast-message toast-${type}`;
  toast.innerHTML = `
    <span class="toast-dot"></span>
    <span class="toast-text">${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-fadeout");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function confirmAction(title, message, onConfirm) {
  const modal = document.getElementById("confirmModal");
  if (!modal) {
    if (confirm(message)) onConfirm();
    return;
  }
  document.getElementById("confirm-modal-title").innerText = title;
  document.getElementById("confirm-modal-message").innerText = message;
  confirmCallback = onConfirm;
  document.getElementById("confirm-modal-btn").onclick = () => {
    if (confirmCallback) confirmCallback();
    closeConfirmModal();
  };
  modal.style.display = "flex";
}

function closeConfirmModal() {
  const modal = document.getElementById("confirmModal");
  if (modal) modal.style.display = "none";
  confirmCallback = null;
}

function openUploadModal() {
  const modal = document.getElementById("uploadModal");
  if (modal) modal.style.display = "flex";
}

function closeUploadModal() {
  const modal = document.getElementById("uploadModal");
  if (modal) modal.style.display = "none";
  const input = document.getElementById("csvFileInput");
  if (input) input.value = "";
}

async function openExportsModal() {
  const modal = document.getElementById("exportsModal");
  if (modal) modal.style.display = "flex";

  const tbody = document.getElementById("exportsListBody");
  if (!tbody) return;

  tbody.innerHTML = `
    <tr>
      <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">
        Loading exported reports...
      </td>
    </tr>
  `;

  try {
    const res = await fetch("/api/csv/exports");
    const data = await res.json();
    const exports = data.exports || [];

    if (exports.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--text-muted); padding: 32px;">
            No exported CSV files found. Click "Export New CSV Now" to generate one.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = exports.map(file => `
      <tr>
        <td style="font-weight: 700; color: var(--text-primary); font-family: var(--font-mono); font-size: 13px;">
          📄 ${escapeHtml(file.filename)}
        </td>
        <td style="color: var(--text-secondary); font-size: 13px;">
          ${escapeHtml(file.modified_at)}
        </td>
        <td style="color: var(--text-secondary); font-size: 13px; font-family: var(--font-mono);">
          ${escapeHtml(file.size_formatted)}
        </td>
        <td style="text-align: right;">
          <a class="btn btn-subtle" href="${escapeHtml(file.download_url)}" download style="padding: 6px 14px; font-size: 12px; text-decoration: none;">
            <span class="btn-icon">↓</span> Download
          </a>
        </td>
      </tr>
    `).join("");
  } catch (err) {
    tbody.innerHTML = `
      <tr>
        <td colspan="4" style="text-align: center; color: var(--accent-danger); padding: 24px;">
          Failed to load exported CSV list.
        </td>
      </tr>
    `;
  }
}

function closeExportsModal() {
  const modal = document.getElementById("exportsModal");
  if (modal) modal.style.display = "none";
}

function openScheduleModal() {
  const modal = document.getElementById("scheduleModal");
  if (!modal) return;

  // Set today's date
  const now = new Date();
  const dateStr = now.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const dateEl = document.getElementById("schedule-today-date");
  if (dateEl) dateEl.innerText = dateStr;

  // Target metrics calculation
  const completed = parseInt(document.getElementById("stat-completed")?.innerText || "0", 10);
  const target = 40;
  const progressPercent = Math.min(100, Math.round((completed / target) * 100));
  const remaining = Math.max(0, target - completed);
  const estHoursLeft = (remaining * 10 / 60).toFixed(1);

  const fillEl = document.getElementById("schedule-progress-fill");
  if (fillEl) fillEl.style.width = `${progressPercent}%`;

  const percentEl = document.getElementById("schedule-progress-percent");
  if (percentEl) percentEl.innerText = `${progressPercent}%`;

  const compEl = document.getElementById("schedule-completed-count");
  if (compEl) compEl.innerText = `${completed} / ${target}`;

  const remEl = document.getElementById("schedule-remaining-count");
  if (remEl) remEl.innerText = remaining;

  const estEl = document.getElementById("schedule-est-hours");
  if (estEl) estEl.innerText = `${estHoursLeft} hrs`;

  // Active batch info
  const pending = parseInt(document.getElementById("stat-pending")?.innerText || "0", 10);
  const activeGen = (parseInt(document.getElementById("stat-design")?.innerText || "0", 10) +
                     parseInt(document.getElementById("stat-lovable-gen")?.innerText || "0", 10) +
                     parseInt(document.getElementById("stat-vercel")?.innerText || "0", 10));

  const batchActiveEl = document.getElementById("schedule-batch-active");
  if (batchActiveEl) batchActiveEl.innerText = activeGen;

  const batchQueueEl = document.getElementById("schedule-batch-queued");
  if (batchQueueEl) batchQueueEl.innerText = pending;

  modal.style.display = "flex";
}

function closeScheduleModal() {
  const modal = document.getElementById("scheduleModal");
  if (modal) modal.style.display = "none";
}

async function refreshDashboard(btn) {
  const refreshBtn = btn || document.getElementById("hero-refresh-btn");
  if (refreshBtn) refreshBtn.classList.add("spinning");
  try {
    await Promise.all([
      fetchStats(),
      fetchJobs(),
      fetchOrchestratorStatus(),
    ]);
    showToast("Dashboard telemetry & jobs refreshed", "info");
  } catch (err) {
    showToast("Failed to refresh dashboard", "danger");
  } finally {
    if (refreshBtn) {
      setTimeout(() => refreshBtn.classList.remove("spinning"), 600);
    }
  }
}

function closeJobDetailsModal() {
  const modal = document.getElementById("jobDetailsModal");
  if (modal) modal.style.display = "none";
  activeJobId = null;
}

// ==========================================
// 2. Fetching Stats, Health & Orchestrator
// ==========================================

async function fetchStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const data = await res.json();

    // 11 Core Main Dashboard Metrics
    setElementText("stat-total", data.total_jobs ?? 0);
    setElementText("stat-pending", data.pending ?? 0);
    setElementText("stat-design", data.design_research ?? 0);
    setElementText("stat-design-ready", data.design_ready ?? 0);
    setElementText("stat-waiting-lovable", data.waiting_for_lovable ?? 0);
    setElementText("stat-lovable-gen", data.lovable_generating ?? 0);
    setElementText("stat-publishing", data.publishing ?? 0);
    setElementText("stat-github-sync", data.github_syncing ?? 0);
    setElementText("stat-vercel", data.vercel_deploying ?? 0);
    setElementText("stat-completed", data.completed ?? 0);
    setElementText("stat-failed", data.failed ?? 0);

    // Visual Pipeline Stage Counts
    setElementText("pipe-design-count", data.design_research ?? 0);
    const lovablePipelineCount = (data.waiting_for_lovable || 0) + (data.lovable_generating || 0) + (data.publishing || 0);
    setElementText("pipe-lovable-count", lovablePipelineCount);
    setElementText("pipe-github-count", data.github_syncing ?? 0);
    setElementText("pipe-vercel-count", data.vercel_deploying ?? 0);
    setElementText("pipe-completed-count", data.completed ?? 0);
  } catch (err) {
    console.error("Failed to fetch stats:", err);
  }
}

async function fetchOrchestratorStatus() {
  try {
    const res = await fetch("/api/orchestrator/status");
    if (!res.ok) return;
    const data = await res.json();

    const health = data.health || {};
    const status = (health.status || "STOPPED").toUpperCase();

    // Top Header Status Pill
    const pill = document.getElementById("orchestrator-status-pill");
    const stateText = document.getElementById("orchestrator-state-text");
    if (pill && stateText) {
      stateText.innerText = status;
      pill.className = `orchestrator-status-badge ${status.toLowerCase()}`;
    }

    // Toggle global button states
    const btnStart = document.getElementById("btn-start-all");
    const btnPause = document.getElementById("btn-pause-all");
    const btnResume = document.getElementById("btn-resume-all");
    const btnStop = document.getElementById("btn-stop-all");

    if (status === "RUNNING") {
      if (btnStart) btnStart.style.display = "none";
      if (btnPause) btnPause.style.display = "inline-flex";
      if (btnResume) btnResume.style.display = "none";
      if (btnStop) {
        btnStop.disabled = false;
        btnStop.classList.remove("disabled");
      }
    } else if (status === "PAUSED") {
      if (btnStart) btnStart.style.display = "none";
      if (btnPause) btnPause.style.display = "none";
      if (btnResume) btnResume.style.display = "inline-flex";
      if (btnStop) {
        btnStop.disabled = false;
        btnStop.classList.remove("disabled");
      }
    } else {
      if (btnStart) btnStart.style.display = "inline-flex";
      if (btnPause) btnPause.style.display = "none";
      if (btnResume) btnResume.style.display = "none";
      if (btnStop) {
        btnStop.disabled = true;
        btnStop.classList.add("disabled");
      }
    }

    // Fleet Status Updates
    updateFleetPanel(health, data.workers);

    // Current Lovable Job Panel
    updateCurrentLovableJob(data.active_lovable_job);

    // Design Buffer Panel
    updateDesignBuffer(data.ready_buffer_jobs || []);
  } catch (err) {
    console.error("Failed to fetch orchestrator status:", err);
  }
}

function updateFleetPanel(health, workers) {
  const workersData = health.workers || {};
  const metrics = health.metrics || {};

  const lovableInfo = workersData.lovable || {};
  const vercelInfo = workersData.vercel || {};
  const queues = health.queues || {};

  // Lovable state
  const lovableRunning = lovableInfo.running > 0;
  const lovablePaused = lovableInfo.paused > 0;
  const lovableEl = document.getElementById("fleet-lovable-state");
  if (lovableEl) {
    lovableEl.innerText = lovablePaused ? "PAUSED" : (lovableRunning ? "RUNNING" : "STOPPED");
    lovableEl.className = `state-pill ${lovablePaused ? "paused" : (lovableRunning ? "running" : "stopped")}`;
  }

  // Vercel state
  const vercelRunning = vercelInfo.running > 0;
  const vercelPaused = vercelInfo.paused > 0;
  const vercelEl = document.getElementById("fleet-vercel-state");
  if (vercelEl) {
    vercelEl.innerText = vercelPaused ? "PAUSED" : (vercelRunning ? "RUNNING" : "STOPPED");
    vercelEl.className = `state-pill ${vercelPaused ? "paused" : (vercelRunning ? "running" : "stopped")}`;
  }

  setElementText("fleet-lovable-completed", document.getElementById("stat-completed")?.innerText || "0");
  setElementText("fleet-lovable-failed", document.getElementById("stat-failed")?.innerText || "0");

  setElementText("fleet-vercel-active", document.getElementById("stat-vercel")?.innerText || "0");
  setElementText("fleet-vercel-queued", queues.vercel_queue_depth ?? "0");
  setElementText("fleet-vercel-completed", document.getElementById("stat-completed")?.innerText || "0");
}

function updateCurrentLovableJob(job) {
  const container = document.getElementById("current-lovable-content");
  const badge = document.getElementById("current-lovable-badge");
  if (!container || !badge) return;

  if (!job) {
    if (lovableTimerInterval) {
      clearInterval(lovableTimerInterval);
      lovableTimerInterval = null;
    }
    activeLovableStartedAt = null;
    badge.innerText = "IDLE";
    badge.className = "badge";
    container.innerHTML = `
      <div class="empty-focus-state">
        <p>Lovable worker is currently idle or waiting for next ready design.</p>
        <small style="color: var(--text-muted); display: block; margin-top: 6px;">
          (Sequential single-generation mutex active)
        </small>
      </div>
    `;
    return;
  }

  badge.innerText = job.lovable_status || "GENERATING";
  badge.className = `badge badge-${(job.lovable_status || "info").toLowerCase()}`;

  activeLovableStartedAt = job.started_at ? new Date(job.started_at).getTime() : new Date(job.updated_at).getTime();

  container.innerHTML = `
    <div class="active-lovable-details">
      <div class="lovable-card-row">
        <span class="l-label">Queue Position:</span>
        <span class="l-value font-mono"><strong>#${job.queue_position}</strong></span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Website URL:</span>
        <span class="l-value"><strong>${escapeHtml(job.website_url)}</strong></span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Business Name:</span>
        <span class="l-value">${escapeHtml(job.business_name || "-")}</span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Design Reference:</span>
        <span class="l-value font-italic">${escapeHtml(job.design_reference_title || "Modern Reference")}</span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Lovable Project:</span>
        <span class="l-value font-mono">${escapeHtml(job.lovable_project_id || "Provisioning...")}</span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Current Stage:</span>
        <span class="l-value"><span class="badge badge-purple">${escapeHtml(job.lovable_status || "PROCESSING")}</span></span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Started At:</span>
        <span class="l-value">${formatTime(job.started_at || job.updated_at)}</span>
      </div>
      <div class="lovable-card-row">
        <span class="l-label">Elapsed Time:</span>
        <span class="l-value font-mono highlight-elapsed" id="current-lovable-elapsed">00:00</span>
      </div>
      <div class="lovable-throughput-impact">
        <span class="impact-label">&#x26A1; Throughput Impact:</span>
        <span class="impact-desc">1 active sequential slot (100% capacity) &mdash; subsequent jobs waiting in buffer</span>
      </div>
    </div>
  `;

  updateElapsedTimer();
  if (!lovableTimerInterval) {
    lovableTimerInterval = setInterval(updateElapsedTimer, 1000);
  }
}

function updateElapsedTimer() {
  const el = document.getElementById("current-lovable-elapsed");
  if (!el || !activeLovableStartedAt) return;

  const now = Date.now();
  const diffSec = Math.max(0, Math.floor((now - activeLovableStartedAt) / 1000));
  const mins = Math.floor(diffSec / 60);
  const secs = diffSec % 60;
  const hours = Math.floor(mins / 60);

  if (hours > 0) {
    const remMins = mins % 60;
    el.innerText = `${hours.toString().padStart(2, "0")}:${remMins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  } else {
    el.innerText = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
}

function updateDesignBuffer(bufferJobs) {
  const meter = document.getElementById("buffer-meter-pill");
  const list = document.getElementById("buffer-jobs-list");
  if (!meter || !list) return;

  meter.innerText = `${bufferJobs.length} / 3 READY`;
  if (bufferJobs.length >= 3) {
    meter.className = "buffer-meter full";
  } else {
    meter.className = "buffer-meter";
  }

  if (bufferJobs.length === 0) {
    list.innerHTML = `<div class="empty-focus-state">No ready designs in buffer. Research workers running ahead...</div>`;
    return;
  }

  list.innerHTML = bufferJobs
    .map(
      (job) => `
      <div class="buffer-item" onclick="openJobDetailsModal('${job.id}')">
        <div class="buffer-item-left">
          <span class="buffer-pos">#${job.queue_position}</span>
          <div class="buffer-details">
            <span class="buffer-url">${escapeHtml(job.website_url)}</span>
            <span class="buffer-ref">${escapeHtml(job.design_reference_title || "Reference Identified")}</span>
          </div>
        </div>
        <span class="badge badge-cyan">READY</span>
      </div>
    `
    )
    .join("");
}

// ==========================================
// 3. Jobs Table, Search, and Filtering
// ==========================================

async function fetchJobs() {
  try {
    const res = await fetch("/api/jobs?limit=150");
    if (!res.ok) return;
    allJobs = await res.json();

    // Prune any selected IDs that no longer exist in allJobs
    const currentIds = new Set(allJobs.map((j) => j.id));
    for (const id of selectedJobIds) {
      if (!currentIds.has(id)) {
        selectedJobIds.delete(id);
      }
    }

    filterJobsTable();
  } catch (err) {
    console.error("Failed to fetch jobs:", err);
  }
}

function filterJobsTable() {
  const searchInput = document.getElementById("job-search-input");
  const filterSelect = document.getElementById("status-filter-select");
  const tbody = document.getElementById("jobs-tbody");
  const countLabel = document.getElementById("table-total-count");
  if (!tbody) return;

  const query = (searchInput?.value || "").trim().toLowerCase();
  const statusFilter = (filterSelect?.value || "ALL").toUpperCase();

  const filtered = allJobs.filter((job) => {
    // Search query check
    if (query) {
      const url = (job.website_url || "").toLowerCase();
      const name = (job.business_name || "").toLowerCase();
      if (!url.includes(query) && !name.includes(query)) return false;
    }

    // Status filter check
    if (statusFilter === "ALL") return true;
    if (statusFilter === "PENDING") return job.overall_status === "PENDING";
    if (statusFilter === "PROCESSING") return job.overall_status === "PROCESSING";
    if (statusFilter === "DESIGN_READY") return job.design_status === "DESIGN_READY";
    if (statusFilter === "GENERATING") {
      return ["PREPARING", "SUBMITTING", "GENERATING", "VERIFYING"].includes(job.lovable_status);
    }
    if (statusFilter === "DEPLOYING") {
      return ["WAITING", "CONFIGURING", "DEPLOYING", "VERIFYING"].includes(job.vercel_status);
    }
    if (statusFilter === "COMPLETED") return job.overall_status === "COMPLETED";
    if (statusFilter === "FAILED") return job.overall_status === "FAILED";
    if (statusFilter === "CANCELLED") return job.overall_status === "CANCELLED";

    return true;
  });

  if (countLabel) {
    countLabel.innerText = `(${filtered.length} of ${allJobs.length} jobs)`;
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="14" class="table-placeholder">
          No matching redesign jobs found.
        </td>
      </tr>
    `;
    updateSelectionUI();
    return;
  }

  tbody.innerHTML = filtered
    .map((job) => {
      const overallBadge = getStatusBadge(job.overall_status);
      const designBadge = getStageBadge(job.design_status);
      const lovableBadge = getStageBadge(job.lovable_status);
      const githubBadge = getStageBadge(job.github_status);
      const vercelBadge = getStageBadge(job.vercel_status);

      const lovableLink = job.lovable_published_url
        ? `<a class="table-link" href="${escapeHtml(job.lovable_published_url)}" target="_blank" onclick="event.stopPropagation()">View App &rarr;</a>`
        : "-";

      const vercelLink = job.vercel_deployment_url
        ? `<a class="table-link font-bold" href="${escapeHtml(job.vercel_deployment_url)}" target="_blank" onclick="event.stopPropagation()">Live Prod &rarr;</a>`
        : "-";

      const duration = job.total_duration_seconds ? `${job.total_duration_seconds}s` : "-";
      const retries = job.retry_count ?? 0;
      const updated = formatTime(job.updated_at);
      const isChecked = selectedJobIds.has(job.id) ? "checked" : "";

      // Action buttons
      let actionButtons = `
        <button class="btn btn-xs btn-outline" onclick="openJobDetailsModal('${job.id}')">View</button>
      `;

      if (job.overall_status === "FAILED" || job.design_status === "DESIGN_FAILED" || job.lovable_status === "FAILED" || job.vercel_status === "FAILED") {
        actionButtons += `
          <button class="btn btn-xs btn-danger" onclick="retryJob('${job.id}')">Retry</button>
        `;
      }

      if (["PENDING", "PROCESSING"].includes(job.overall_status)) {
        actionButtons += `
          <button class="btn btn-xs btn-outline" onclick="confirmAction('Cancel Job #${job.queue_position}', 'Are you sure you want to cancel this job?', () => cancelJob('${job.id}'))">&times;</button>
        `;
      }

      actionButtons += `
        <button class="btn btn-xs btn-xs-danger" onclick="confirmAction('Delete Job #${job.queue_position}', 'Permanently delete redesign job for ${escapeHtml(job.business_name || job.website_url)}?', () => deleteSingleJob('${job.id}'))" title="Delete job">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="vertical-align: middle;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
        </button>
      `;

      return `
        <tr onclick="openJobDetailsModal('${job.id}')" style="cursor: pointer;">
          <td style="text-align: center; cursor: pointer;" onclick="event.stopPropagation(); const cb = this.querySelector('.job-cb'); if (event.target !== cb) { cb.checked = !cb.checked; onJobCheckboxChange(cb); }">
            <input type="checkbox" class="job-cb job-checkbox" value="${job.id}" ${isChecked} onchange="onJobCheckboxChange(this)">
          </td>
          <td class="font-mono">#${job.queue_position}</td>
          <td>
            <strong>${escapeHtml(job.business_name || job.website_url)}</strong>
            <div class="sub-url">${escapeHtml(job.website_url)}</div>
          </td>
          <td>${overallBadge}</td>
          <td>${designBadge}</td>
          <td>${lovableBadge}</td>
          <td>${githubBadge}</td>
          <td>${vercelBadge}</td>
          <td>${lovableLink}</td>
          <td>${vercelLink}</td>
          <td class="font-mono">${duration}</td>
          <td class="font-mono">${retries}</td>
          <td class="font-mono" style="font-size: 11px; color: var(--text-muted);">${updated}</td>
          <td style="text-align: center;" onclick="event.stopPropagation()">
            <div style="display: flex; gap: 4px; justify-content: center;">
              ${actionButtons}
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  updateSelectionUI();
}

// ==========================================
// 4. Job Details Modal & Audit Event Timeline
// ==========================================

async function openJobDetailsModal(jobId) {
  activeJobId = jobId;
  const modal = document.getElementById("jobDetailsModal");
  if (!modal) return;
  modal.style.display = "flex";

  try {
    // Fetch Job Data & Events simultaneously
    const [jobRes, eventsRes] = await Promise.all([
      fetch(`/api/jobs/${jobId}`),
      fetch(`/api/jobs/${jobId}/events`),
    ]);

    if (!jobRes.ok) {
      showToast("Failed to load job details", "danger");
      return;
    }

    const job = await jobRes.json();
    const events = eventsRes.ok ? await eventsRes.json() : [];

    // Header Info
    setElementText("modal-job-uid", `JOB #${job.queue_position} • ID: ${job.id}`);
    setElementText("modal-website-url", job.website_url);

    // Failure Alert Banner
    const failureBanner = document.getElementById("modal-failure-banner");
    if (job.overall_status === "FAILED" || job.last_error || job.design_error || job.lovable_error || job.vercel_error) {
      if (failureBanner) {
        failureBanner.style.display = "flex";
        setElementText("modal-failure-stage", `Failed Stage: ${job.overall_status}`);
        setElementText(
          "modal-failure-message",
          job.last_error || job.lovable_error || job.vercel_error || job.design_error || "Unknown execution failure occurred."
        );
        setElementText(
          "modal-failure-meta",
          `Retries: ${job.retry_count || 0} | Last Event: ${formatTime(job.updated_at)}`
        );
      }
    } else if (failureBanner) {
      failureBanner.style.display = "none";
    }

    // Execution Overview Items
    setElementText("modal-queue-pos", `#${job.queue_position}`);
    setElementText("modal-business-name", job.business_name || "-");
    setElementHtml("modal-overall-status", getStatusBadge(job.overall_status));
    setElementText("modal-lovable-project", job.lovable_project_id || "-");

    setElementHtml(
      "modal-lovable-link",
      job.lovable_published_url
        ? `<a class="table-link" href="${escapeHtml(job.lovable_published_url)}" target="_blank">${escapeHtml(job.lovable_published_url)} &rarr;</a>`
        : "-"
    );

    setElementHtml(
      "modal-github-link",
      job.github_repository_url
        ? `<a class="table-link" href="${escapeHtml(job.github_repository_url)}" target="_blank">${escapeHtml(job.github_repository || "GitHub Repo")} &rarr;</a>`
        : "-"
    );

    setElementHtml(
      "modal-vercel-link",
      job.vercel_deployment_url
        ? `<a class="table-link font-bold" href="${escapeHtml(job.vercel_deployment_url)}" target="_blank">${escapeHtml(job.vercel_deployment_url)} &rarr;</a>`
        : "-"
    );

    // Design Reference Box
    setElementText("modal-ref-title", job.design_reference_title || "No Reference Identified");
    setElementText(
      "modal-ref-meta",
      `Source: ${job.design_reference_source || "Dribbble"} | Score: ${job.design_score != null ? job.design_score.toFixed(2) : "N/A"}`
    );
    setElementText("modal-ref-reason", job.design_reason || "No rationale recorded.");

    const refUrlEl = document.getElementById("modal-ref-url");
    if (refUrlEl) {
      if (job.design_reference_url) {
        refUrlEl.href = job.design_reference_url;
        refUrlEl.style.display = "inline";
      } else {
        refUrlEl.style.display = "none";
      }
    }

    // Stage Durations Breakdown
    setElementText("modal-dur-design", job.design_duration_seconds ? `${job.design_duration_seconds}s` : "-");
    setElementText("modal-dur-lovable", job.lovable_generation_duration_seconds ? `${job.lovable_generation_duration_seconds}s` : "-");
    setElementText("modal-dur-publish", job.lovable_publish_duration_seconds ? `${job.lovable_publish_duration_seconds}s` : "-");
    setElementText("modal-dur-sync", job.github_sync_duration_seconds ? `${job.github_sync_duration_seconds}s` : "-");
    setElementText("modal-dur-vercel", job.vercel_duration_seconds ? `${job.vercel_duration_seconds}s` : "-");
    setElementText("modal-dur-verify", job.verification_duration_seconds ? `${job.verification_duration_seconds}s` : "-");
    setElementText("modal-dur-total", job.total_duration_seconds ? `${job.total_duration_seconds}s` : "-");

    // Timeline Events
    renderEventTimeline(events);
  } catch (err) {
    console.error("Failed to load job modal:", err);
    showToast("Error loading job details", "danger");
  }
}

function renderEventTimeline(events) {
  const container = document.getElementById("modal-timeline-list");
  if (!container) return;

  if (!events || events.length === 0) {
    container.innerHTML = `<div class="empty-timeline">No audit timeline events recorded for this job.</div>`;
    return;
  }

  container.innerHTML = events
    .map((evt) => {
      const type = evt.event_type || "EVENT";
      const time = formatTime(evt.created_at);
      let payloadHtml = "";

      if (evt.payload) {
        try {
          const parsed = typeof evt.payload === "string" ? JSON.parse(evt.payload) : evt.payload;
          const entries = Object.entries(parsed).filter(([k, v]) => v !== null && v !== "");
          if (entries.length > 0) {
            payloadHtml = `
              <div class="timeline-meta">
                ${entries.map(([k, v]) => `<div><span class="font-mono">${escapeHtml(k)}:</span> ${escapeHtml(String(v))}</div>`).join("")}
              </div>
            `;
          }
        } catch (e) {
          payloadHtml = `<div class="timeline-meta">${escapeHtml(String(evt.payload))}</div>`;
        }
      }

      return `
        <div class="timeline-item">
          <div class="timeline-bullet"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="timeline-title">${escapeHtml(type)}</span>
              <span class="timeline-time">${time}</span>
            </div>
            ${payloadHtml}
          </div>
        </div>
      `;
    })
    .join("");
}

function retryActiveJob() {
  if (activeJobId) {
    retryJob(activeJobId);
  }
}

// ==========================================
// 5. Orchestrator & Job Action Operations
// ==========================================

async function controlOrchestrator(action) {
  try {
    const res = await fetch(`/api/orchestrator/${action}`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || `Orchestrator ${action} succeeded`, "success");
      fetchOrchestratorStatus();
      fetchStats();
    } else {
      showToast(data.detail || `Failed to execute ${action}`, "danger");
    }
  } catch (err) {
    showToast(`Network error calling orchestrator ${action}`, "danger");
  }
}

async function controlWorker(workerType, action) {
  try {
    const res = await fetch(`/api/orchestrator/workers/${workerType}/${action}`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message || `Worker ${workerType} ${action} succeeded`, "success");
      fetchOrchestratorStatus();
    } else {
      showToast(data.detail || `Worker action failed`, "danger");
    }
  } catch (err) {
    showToast(`Network error controlling ${workerType}`, "danger");
  }
}

async function retryJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/retry`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(`Job retried successfully`, "success");
      fetchStats();
      fetchJobs();
      fetchOrchestratorStatus();
      if (activeJobId === jobId) {
        openJobDetailsModal(jobId);
      }
    } else {
      showToast(data.detail || "Failed to retry job", "danger");
    }
  } catch (err) {
    showToast("Network error retrying job", "danger");
  }
}

async function cancelJob(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(`Job cancelled`, "warning");
      fetchStats();
      fetchJobs();
      fetchOrchestratorStatus();
      if (activeJobId === jobId) {
        openJobDetailsModal(jobId);
      }
    } else {
      showToast(data.detail || "Failed to cancel job", "danger");
    }
  } catch (err) {
    showToast("Network error cancelling job", "danger");
  }
}

// ==========================================
// Job Selection & Deletion Handlers
// ==========================================

function toggleSelectAllJobs(masterCb) {
  const checkboxes = document.querySelectorAll(".job-cb");
  checkboxes.forEach((cb) => {
    const id = parseInt(cb.value, 10);
    if (masterCb.checked) {
      selectedJobIds.add(id);
      cb.checked = true;
    } else {
      selectedJobIds.delete(id);
      cb.checked = false;
    }
  });
  updateSelectionUI();
}

function onJobCheckboxChange(input) {
  if (input) {
    const id = parseInt(input.value, 10);
    if (input.checked) {
      selectedJobIds.add(id);
    } else {
      selectedJobIds.delete(id);
    }
  }
  updateSelectionUI();
}

function updateSelectionUI() {
  const checkboxes = document.querySelectorAll(".job-cb");
  const deleteSelectedBtn = document.getElementById("btn-delete-selected");
  const countSpan = document.getElementById("selected-jobs-count");
  const masterCb = document.getElementById("select-all-jobs-cb");

  const totalVisible = checkboxes.length;
  let checkedVisibleCount = 0;

  checkboxes.forEach((cb) => {
    const id = parseInt(cb.value, 10);
    if (selectedJobIds.has(id)) {
      cb.checked = true;
      checkedVisibleCount++;
    } else {
      cb.checked = false;
    }
  });

  const totalSelected = selectedJobIds.size;
  if (countSpan) countSpan.innerText = totalSelected;

  if (deleteSelectedBtn) {
    deleteSelectedBtn.style.display = totalSelected > 0 ? "inline-flex" : "none";
  }

  if (masterCb) {
    if (totalVisible === 0 || checkedVisibleCount === 0) {
      masterCb.checked = false;
      masterCb.indeterminate = false;
    } else if (checkedVisibleCount === totalVisible) {
      masterCb.checked = true;
      masterCb.indeterminate = false;
    } else {
      masterCb.checked = false;
      masterCb.indeterminate = true;
    }
  }
}

async function deleteSingleJob(jobId) {
  const numericId = parseInt(jobId, 10);
  try {
    const res = await fetch(`/api/jobs/${jobId}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      showToast("Job permanently deleted", "success");
      selectedJobIds.delete(numericId);
      updateSelectionUI();
      if (activeJobId === jobId || activeJobId === numericId) {
        closeJobDetailsModal();
      }
      await Promise.all([fetchJobs(), fetchStats()]);
    } else {
      showToast(data.detail || "Failed to delete job", "danger");
    }
  } catch (err) {
    showToast("Network error deleting job", "danger");
  }
}

function deleteActiveJob() {
  if (activeJobId) {
    deleteSingleJob(activeJobId);
  }
}

function deleteSelectedJobs() {
  const jobIds = Array.from(selectedJobIds);
  if (jobIds.length === 0) {
    showToast("No jobs selected to delete", "warning");
    return;
  }

  confirmAction(
    `Delete ${jobIds.length} Selected Job${jobIds.length > 1 ? "s" : ""}`,
    `Are you sure you want to permanently delete the ${jobIds.length} selected job${jobIds.length > 1 ? "s" : ""}? This cannot be undone.`,
    async () => {
      try {
        const res = await fetch("/api/jobs/batch-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ job_ids: jobIds }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          showToast(`Deleted ${data.deleted_count || jobIds.length} job(s)`, "success");
          selectedJobIds.clear();
          updateSelectionUI();
          if (activeJobId && jobIds.includes(parseInt(activeJobId, 10))) {
            closeJobDetailsModal();
          }
          await Promise.all([fetchJobs(), fetchStats()]);
        } else {
          showToast(data.detail || "Failed to delete selected jobs", "danger");
        }
      } catch (err) {
        showToast("Network error deleting selected jobs", "danger");
      }
    }
  );
}

async function deleteAllJobs() {
  try {
    const res = await fetch("/api/jobs/delete-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      showToast(`Deleted all ${data.deleted_count ?? 0} job(s)`, "success");
      selectedJobIds.clear();
      updateSelectionUI();
      if (activeJobId) {
        closeJobDetailsModal();
      }
      await Promise.all([fetchJobs(), fetchStats()]);
    } else {
      showToast(data.detail || "Failed to delete all jobs", "danger");
    }
  } catch (err) {
    showToast("Network error deleting all jobs", "danger");
  }
}

async function handleCsvUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById("csvFileInput");
  if (!fileInput || !fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch("/api/csv/import", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`CSV imported: ${data.imported_count} jobs enqueued.`, "success");
      closeUploadModal();
      fetchStats();
      fetchJobs();
      fetchOrchestratorStatus();
    } else {
      showToast(`Import error: ${data.detail || "Failed to import CSV"}`, "danger");
    }
  } catch (err) {
    showToast("Network error uploading CSV", "danger");
  }
}

// ==========================================
// 6. Formatting & HTML Helpers
// ==========================================

function getStatusBadge(status) {
  if (!status) return `<span class="badge">UNKNOWN</span>`;
  const s = status.toUpperCase();
  let badgeClass = "badge";
  if (s === "COMPLETED") badgeClass = "badge badge-success";
  else if (s === "FAILED") badgeClass = "badge badge-danger";
  else if (s === "PROCESSING") badgeClass = "badge badge-warning";
  else if (s === "PENDING") badgeClass = "badge badge-outline";
  else if (s === "CANCELLED") badgeClass = "badge badge-danger";
  return `<span class="${badgeClass}">${escapeHtml(s)}</span>`;
}

function getStageBadge(status) {
  if (!status) return `<span class="badge">-</span>`;
  const s = status.toUpperCase();
  let badgeClass = "badge";
  if (["DESIGN_READY", "PUBLISHED", "DEPLOYED", "SYNCED"].includes(s)) badgeClass = "badge badge-success";
  else if (s.includes("FAILED")) badgeClass = "badge badge-danger";
  else if (["ANALYZING", "SEARCHING", "GENERATING", "PUBLISHING", "DEPLOYING", "SYNCING"].includes(s))
    badgeClass = "badge badge-purple";
  else if (s.includes("WAITING") || s.includes("QUEUED")) badgeClass = "badge badge-outline";
  return `<span class="${badgeClass}">${escapeHtml(s)}</span>`;
}

function setElementText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = text;
}

function setElementHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function formatTime(isoString) {
  if (!isoString) return "-";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return isoString;
  }
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ==========================================
// 7. Initialization & Auto-Polling
// ==========================================

window.addEventListener("DOMContentLoaded", () => {
  // Initial load
  fetchStats();
  fetchOrchestratorStatus();
  fetchJobs();

  // Periodic polling every 2.5 seconds
  setInterval(() => {
    fetchStats();
    fetchOrchestratorStatus();
    fetchJobs();
  }, 2500);

  // Bind CSV form
  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", handleCsvUpload);
  }
});
