async function fetchStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("stat-total").innerText = data.total_jobs;
    document.getElementById("stat-pending").innerText = data.pending;
    document.getElementById("stat-design").innerText = data.design_research;
    document.getElementById("stat-waiting-lovable").innerText = data.waiting_for_lovable;
    document.getElementById("stat-lovable").innerText = data.lovable_processing;
    document.getElementById("stat-vercel").innerText = data.vercel_deployment;
    document.getElementById("stat-completed").innerText = data.completed;
    document.getElementById("stat-failed").innerText = data.failed;
  } catch (err) {
    console.error("Failed to fetch stats:", err);
  }
}

async function fetchJobs() {
  try {
    const res = await fetch("/api/jobs?limit=50");
    if (!res.ok) return;
    const jobs = await res.json();
    const tbody = document.getElementById("jobs-tbody");
    tbody.innerHTML = "";

    if (jobs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#8b949e; padding:24px;">No jobs enqueued yet. Upload a CSV to start the pipeline.</td></tr>';
      return;
    }

    jobs.forEach((j) => {
      const tr = document.createElement("tr");

      const overallBadge = `<span class="badge badge-${j.overall_status.toLowerCase()}">${j.overall_status}</span>`;
      const designBadge = `<span class="badge">${j.design_status}</span>`;
      const lovableBadge = `<span class="badge">${j.lovable_status}</span>`;
      const vercelBadge = `<span class="badge">${j.vercel_status}</span>`;

      let link = "-";
      if (j.vercel_deployment_url) {
        link = `<a class="table-link" href="${j.vercel_deployment_url}" target="_blank">Vercel Live</a>`;
      } else if (j.lovable_published_url) {
        link = `<a class="table-link" href="${j.lovable_published_url}" target="_blank">Lovable App</a>`;
      }

      const duration = j.total_duration_seconds ? `${j.total_duration_seconds}s` : "-";

      tr.innerHTML = `
        <td>#${j.csv_row_index + 1}</td>
        <td><strong>${j.website_url}</strong></td>
        <td>${overallBadge}</td>
        <td>${designBadge}</td>
        <td>${lovableBadge}</td>
        <td>${vercelBadge}</td>
        <td>${duration}</td>
        <td>${link}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to fetch jobs:", err);
  }
}

async function handleCsvUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById("csvFileInput");
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch("/api/csv/import", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (res.ok) {
      alert(`CSV imported: ${data.imported_count} jobs enqueued.`);
      closeUploadModal();
      fetchStats();
      fetchJobs();
    } else {
      alert(`Import error: ${data.detail || "Failed to import CSV"}`);
    }
  } catch (err) {
    alert("Network error while uploading CSV");
  }
}

function openUploadModal() {
  document.getElementById("uploadModal").style.display = "flex";
}

function closeUploadModal() {
  document.getElementById("uploadModal").style.display = "none";
}

window.addEventListener("DOMContentLoaded", () => {
  fetchStats();
  fetchJobs();
  setInterval(() => {
    fetchStats();
    fetchJobs();
  }, 3000);

  document.getElementById("uploadForm").addEventListener("submit", handleCsvUpload);
});
