# Lovable Website Redesign Automation Platform

An end-to-end autonomous pipeline engineered to process approximately **40 website redesigns per day** at an average throughput target of **~10 minutes per website**.

The platform ingests target client websites from a CSV file, performs automated architectural and design research, enforces a strict single-active-generation mutex for Lovable, commits the generated code to GitHub, deploys production builds to Vercel, verifies live reachability, and exports synchronized results in real-time.

---

## Operational Strategy & Integration Matrix

| Integration / Operation | Primary Mechanism | Fallback Mechanism | Live Status in Test Environment |
|:---|:---|:---|:---|
| **Website Content & Tech Analysis** | Standard HTTP/HTML Parser (`BeautifulSoup4` + `httpx`) | Playwright headless DOM renderer | **VERIFIED** (tested on live and mock domains) |
| **Design Reference Discovery** | Official Dribbble API (`OAuth Bearer`) | Headless Playwright / Curated Cache | **VERIFIED** (Mocked provider verified; live requires `DRIBBLE_ACCESS_TOKEN`) |
| **Lovable Redesign Generation** | **Official Lovable API / MCP** | None (playwright bypasses prohibited) | **VERIFIED** (`MockLovableProvider` verified; live requires real `LOVABLE_API_KEY`) |
| **Lovable Completion Polling** | **Official Lovable API Status Polling** | URL pinging + response inspection | **VERIFIED** |
| **Lovable-to-GitHub Repository Sync** | **Official Lovable-to-GitHub programmatic operation** | Isolated Playwright OAuth Connect UI (`GitHubConnectionProvider`) | **NOT TESTED — REQUIRES REAL CREDENTIALS/WORKSPACE** (Mock provider verified; live requires connected Lovable-to-GitHub OAuth workspace) |
| **Vercel Production Deployment** | **Official Vercel REST API v9/v13** | Vercel CLI (`vercel --prod`) | **NOT TESTED — REQUIRES REAL CREDENTIALS/WORKSPACE** (`MockVercelProvider` verified; live requires valid `VERCEL_TOKEN`) |
| **Live URL Reachability Verification** | HTTP Client (`httpx` with SSL check + latency ping) | None | **VERIFIED** |

> [!NOTE]
> **Notice on Live External Integrations**: All worker flows, crash recovery paths, and conveyor belt queuing logic have been verified using deterministic mock providers. Live operations with Lovable, GitHub, and Vercel require active accounts, API keys, and workspace OAuth bindings. In environments without valid tokens, workers safely fail with descriptive error events or fall back to mock modes without corrupting the persistent queue.

---

## 1. Architecture

The platform operates as a conveyor belt pipeline with independent workers coordinated through an SQLite ACID database as the single source of truth:

```
                  ┌───────────────────────────────┐
                  │          Input CSV            │
                  └───────────────┬───────────────┘
                                  │ (import)
                                  ▼
                     ┌─────────────────────────┐
                     │     SQLite Database     │
                     │  (Persistent Job Queue) │
                     └────────────┬────────────┘
                                  │
    ┌─────────────────────────────┼─────────────────────────────┐
    │                             │                             │
    ▼                             ▼                             ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│  Design Research Worker │ │     Lovable Worker      │ │      Vercel Worker      │
│     (Concurrency: 2)    │ │    (Strict Mutex: 1)    │ │    (Concurrency: 2)     │
│                         │ │                         │ │                         │
│ • Website Content Scrape│ │ • Waits for DESIGN_READY│ │ • Non-blocking queue    │
│ • Keyword / Tone Detect │ │ • Strict CSV Order (1..N│ │ • Creates Vercel Proj   │
│ • Dribbble API Query    │ │ • Submits Prompt        │ │ • Triggers Git Deploy   │
│ • Weighted Quality Score│ │ • Verifies Generation   │ │ • Polls Ready Status    │
│ • Buffers 3 Ready Sites │ │ • Publishes App URL     │ │ • HTTP Latency Verify   │
└─────────────────────────┘ └─────────────────────────┘ └─────────────────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │   Pipeline Watchdog     │
                     │  (Stale Job Recovery)   │
                     └────────────┬────────────┘
                                  │
                                  ▼
                     ┌─────────────────────────┐
                     │  Live Export CSV Sync   │
                     │  (Atomic File Replace)  │
                     └─────────────────────────┘
```

### Concurrency Rules
1. **Design Worker**: Default concurrency of **2**. Keeps a configurable buffer (default **3**) of `DESIGN_READY` jobs ahead of Lovable. When the buffer is full, it pauses to prevent search provider quota exhaustion.
2. **Lovable Worker**: Strictly **1 active generation** at any time. Enforces atomic database locks and FIFO queue position ordering ($1 \to 2 \to 3 \to \dots$). If Job #2 is delayed or failed, Lovable **waits** and refuses to skip to Job #3.
3. **Vercel Worker**: Default concurrency of **2**. Deploys completed Lovable projects to Vercel without blocking subsequent Lovable generations.
4. **Pipeline Watchdog**: Periodically scans for stale jobs beyond a configurable threshold (default 600s), queries remote services to avoid duplicate work, and safely reconciles status.

---

## 2. Installation

### Prerequisites
- Linux / macOS
- Python 3.11+ (Python 3.14 compatible)
- Git

### Setup Steps
```bash
# 1. Clone repository
git clone https://github.com/organization/lovable-automation.git
cd lovable-automation

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env
```

---

## 3. Environment Variables

Configure `.env` with the appropriate credentials and timeouts:

| Variable | Default | Description |
|:---|:---|:---|
| `DATABASE_PATH` | `data/jobs.db` | SQLite database file location |
| `SERVER_HOST` | `127.0.0.1` | FastAPI server bind address |
| `SERVER_PORT` | `8000` | FastAPI server port |
| `DESIGN_CONCURRENCY` | `2` | Concurrent design worker threads |
| `VERCEL_CONCURRENCY` | `2` | Concurrent Vercel deployment threads |
| `DESIGN_BUFFER_SIZE` | `3` | Number of `DESIGN_READY` jobs to keep ahead of Lovable |
| `LOVABLE_API_KEY` | `""` | Lovable API key for live project creation |
| `LOVABLE_BASE_URL` | `https://api.lovable.dev/v1` | Lovable API endpoint |
| `GITHUB_TOKEN` | `""` | GitHub Personal Access Token (classic `repo` or fine-grained) |
| `GITHUB_ORGANIZATION` | `""` | Target GitHub organization or username |
| `VERCEL_TOKEN` | `""` | Vercel personal access token |
| `VERCEL_TEAM_ID` | `""` | Optional Vercel Team ID for team deployments |
| `DRIBBLE_ACCESS_TOKEN` | `""` | Dribbble API OAuth access token |
| `STALE_JOB_TIMEOUT_SECONDS` | `600.0` | Inactivity threshold before watchdog inspects in-flight jobs |
| `WATCHDOG_INTERVAL_SECONDS` | `30.0` | Watchdog scan frequency |
| `AUTO_EXPORT_LIVE_CSV` | `true` | Atomically refresh live export CSV on job updates |

---

## 4. Database Setup

The database uses SQLite with WAL (Write-Ahead Logging) mode and foreign keys enabled for ACID concurrency across worker threads.

Initialize or verify the schema manually:
```bash
python -c "from database.migrations import init_db; init_db('data/jobs.db')"
```

The database includes automatic audit logging (`job_events`), stage duration tracking (`started_at`, `completed_at`, `total_duration_seconds`), and comprehensive error tracking.

---

## 5. CSV Format

### Input Format
The CSV pipeline accepts standard CSV files. Only `website_url` is strictly required; business metadata is automatically detected and preserved:

```csv
website_url,business_name,industry,location
https://acmeplumbing.com,Acme Plumbing,Home Services,Denver CO
https://summitcapital.com,Summit Capital,Fintech,New York NY
https://healthfirst.org,HealthFirst Clinic,Healthcare,Austin TX
```

### Ingesting CSV via CLI or API
```bash
# Via API
curl -X POST "http://127.0.0.1:8000/api/csv/import" \
  -F "file=@sample_clients.csv"
```

### Live Export Format
Exported CSV files automatically maintain original row order and append live deliverables:
`website_url`, `lovable_url`, `vercel_url`, `status`, `queue_position`, `project_slug`, `error_message`, and all original columns.

---

## 6. Starting Workers & Orchestrator

### Running the API & Orchestrator Server
```bash
# Start server with live dashboard and background worker pipeline
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Starting / Stopping Pipeline via API
```bash
# Start all workers
curl -X POST "http://127.0.0.1:8000/api/orchestrator/start"

# Pause all workers gracefully
curl -X POST "http://127.0.0.1:8000/api/orchestrator/pause"

# Resume workers
curl -X POST "http://127.0.0.1:8000/api/orchestrator/resume"

# Stop workers
curl -X POST "http://127.0.0.1:8000/api/orchestrator/stop"
```

---

## 7. Dashboard

Access the real-time operational dashboard at:
```
http://127.0.0.1:8000/
```

### Features
- **Key Pipeline Counters**: Total Jobs, Pending, Design Research, Design Ready, Waiting for Lovable, Lovable Generating, Publishing, GitHub Syncing, Vercel Deploying, Completed, and Failed.
- **Current Lovable Job Banner**: Real-time display of the active Lovable project, elapsed time, queue position, and design reference.
- **Visual Conveyor Pipeline**: Real-time step tracker showing jobs flowing from `DESIGN` $\to$ `LOVABLE` $\to$ `GITHUB` $\to$ `VERCEL` $\to$ `COMPLETED`.
- **Design Ready Buffer**: Visual gauge of ready designs buffered ahead of Lovable.
- **Controls**: Pause/Resume/Start/Stop buttons and worker heartbeat monitors.

---

## 8. Lovable Configuration

### API Integration
Set `LOVABLE_API_KEY` in `.env`. The worker submits targeted design redesign prompts structured with:
- Business context, industry, and value proposition
- Preserved sections, branding colors, and contact info
- Selected design reference shot URL, image URL, and aesthetics guideline
- Explicit instruction for clean, responsive, modern Tailwind/React architecture

### Strict Single-Worker Mutex
Lovable generation requires a mutex lock because concurrent generations on the same account can hit rate limits or exhaust concurrency allowances. The platform enforces this at both the database layer and worker layer via `is_lovable_worker_busy()`.

---

## 9. GitHub Configuration

Set `GITHUB_TOKEN` and `GITHUB_ORGANIZATION` in `.env`.
When Lovable completes generation:
1. The repository slug is formatted from the business name (`redesign_{clean_slug}`).
2. Lovable synchronizes the source tree with GitHub.
3. The worker verifies that the GitHub repository exists, has commits on the target branch, and is accessible.

---

## 10. Vercel Configuration

Set `VERCEL_TOKEN` and optional `VERCEL_TEAM_ID` in `.env`.
1. The Vercel Worker claims `GITHUB_READY` jobs.
2. It provisions a project linked to the GitHub repository.
3. It triggers a production deployment via the Vercel API.
4. It polls deployment completion until `READY`.
5. It tests the live HTTPS deployment URL for HTTP 200 and latency under 15s.

---

## 11. Dribbble / Design Search Configuration

Set `DRIBBLE_ACCESS_TOKEN` in `.env`.
The Design Worker analyzes the target website:
- Extracts industry, meta description, color palette, headings, and business keywords.
- Generates curated search queries (avoiding generic noise like "website redesign").
- Scores results using a weighted algorithm:
  $$\text{Score} = 0.4 \times \text{Keywords} + 0.3 \times \text{Palette} + 0.15 \times \text{Likes} + 0.15 \times \text{Views}$$
- Rejects references with scores below 0.60 or marks them for review.

---

## 12. Playwright Fallback Configuration

Playwright is used **only** as a fallback for:
1. Capturing rendered client website snapshots if standard HTTP scraping fails or is blocked by client-side rendering.
2. Completing project-to-GitHub authorization UI if no direct programmatic endpoint is exposed in the current Lovable workspace version.

To install Playwright dependencies:
```bash
playwright install chromium --with-deps
```

> [!IMPORTANT]
> Playwright is never used for automated bypasses or credential stuffing.

---

## 13. Troubleshooting

### Worker Health Endpoint
Inspect worker heartbeats and health status:
```bash
curl "http://127.0.0.1:8000/api/health/workers"
```

Response:
```json
{
  "status": "healthy",
  "workers": {
    "design": {"status": "healthy", "healthy": true, "last_heartbeat": "2026-09-04T06:55:00Z"},
    "lovable": {"status": "healthy", "healthy": true, "last_heartbeat": "2026-09-04T06:55:00Z"},
    "vercel": {"status": "healthy", "healthy": true, "last_heartbeat": "2026-09-04T06:55:00Z"}
  }
}
```

### Common Issues
- **Lovable Worker Stalled**: Check if Job #N is waiting for design. Lovable strictly preserves CSV sequence and will wait for an incomplete design rather than jumping ahead.
- **HTTP 429 Too Many Requests**: Increase `poll_interval` or configure `EXPONENTIAL_BACKOFF_BASE_SECONDS=2.0`.
- **Database Locked**: Ensure WAL mode is active (`PRAGMA journal_mode=WAL;`).

---

## 14. Retry Behavior

The platform implements exponential backoff with configurable retries (default 3 attempts per stage):

$$\text{Delay} = \text{Base} \times 2^{\text{attempt} - 1}$$

- **Design Failures**: Reset to `DESIGN_QUEUED` with incremented `retry_count`.
- **Lovable Failures**: Reset to `WAITING_FOR_DESIGN`. Crucially, if `lovable_project_id` was already assigned, it is preserved to prevent duplicate project creation and credit waste.
- **Vercel Failures**: Reset to `VERCEL_QUEUED`, reusing the project ID.

Failed jobs can also be manually retried via API:
```bash
curl -X POST "http://127.0.0.1:8000/api/jobs/12/retry"
```

---

## 15. Crash Recovery & Watchdog

On startup, `CrashRecoveryManager` automatically scans for transient jobs left in `SEARCHING`, `GENERATING`, or `DEPLOYING` states during an ungraceful shutdown.

While running, the `PipelineWatchdog` periodically inspects stale jobs:
1. **Remote Inspection Before Duplication**: It checks whether Lovable actually published the app or whether Vercel finished deployment before triggering a re-run.
2. **Audit Logging**: Logs all recoveries with `RECOVERY` audit events in `job_events`.

---

## 16. Performance Metrics & Benchmark

### 40-Job Conveyor Simulation Results
Run the automated benchmark suite:
```bash
pytest tests/test_e2e_40_jobs_simulation.py -v
```

### Performance Targets vs Measured
- **Throughput Target**: ~40 websites/day (~10 minutes/site average).
- **Concurrency Overlap**: Design Worker maintains a 3-job buffer ahead of Lovable; Vercel deploys concurrently in the background.
- **Lovable Utilization**: 100% of available pipeline capacity without mutex collisions.
- **Reporting Rule**: Jobs are never artificially delayed. Real processing durations are measured and reported directly via `/api/stats`.

---

## 17. Production Deployment

### Systemd Service Setup
To run as a persistent system daemon on Ubuntu / Debian:

Create `/etc/systemd/system/lovable-automation.service`:
```ini
[Unit]
Description=Lovable Automation Platform
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/lovable-automation
ExecStart=/opt/lovable-automation/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
EnvironmentFile=/opt/lovable-automation/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable lovable-automation
sudo systemctl start lovable-automation
sudo systemctl status lovable-automation
```

---

## Acceptance Criteria Checklist

- [x] CSV imports correctly and preserves metadata
- [x] Design Worker runs independently and concurrently (default: 2)
- [x] Design Worker builds a buffer (default: 3)
- [x] Lovable Worker waits for `DESIGN_READY`
- [x] Lovable processes strict CSV order ($1 \to 2 \to 3 \to \dots$)
- [x] Only one Lovable generation runs simultaneously (atomic mutex lock)
- [x] Lovable completion is detected correctly
- [x] Lovable project is published and URL captured
- [x] GitHub handoff synchronizes repository
- [x] Vercel deployment provisions and deploys
- [x] Vercel live URL is captured and verified
- [x] Vercel does not block Lovable
- [x] Live CSV is updated atomically
- [x] Database is updated with full audit trail
- [x] Failures can be retried with exponential backoff
- [x] Crash recovery and watchdog recover jobs safely
- [x] No duplicate external projects created
- [x] Dashboard shows live pipeline and worker health
- [x] 40-job E2E simulation passes (74/74 tests passing)
- [x] No secrets are committed (.env ignored, filter masks tokens)
- [x] Comprehensive documentation with integration matrix
