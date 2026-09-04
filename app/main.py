"""FastAPI application entrypoint with dashboard and background worker manager."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.routes_csv import router as csv_router
from api.routes_jobs import router as jobs_router
from api.routes_stats import router as stats_router
from api.routes_orchestrator import router as orchestrator_router
from app.config import settings
from database.migrations import init_db
from utils.logger import logger
from workers.manager import get_worker_manager

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

worker_manager = get_worker_manager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init database and launch background workers."""
    logger.info("Initializing Lovable Automation Platform...")
    init_db(settings.database_path)

    # Start background worker loops
    await worker_manager.start_all()
    yield
    # Gracefully stop workers on shutdown
    logger.info("Shutting down Lovable Automation Platform...")
    await worker_manager.stop_all()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Mount static files and templates
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Include API Routers
app.include_router(jobs_router)
app.include_router(csv_router)
app.include_router(stats_router)
app.include_router(orchestrator_router)


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    """Serve the automation dashboard."""
    return templates.TemplateResponse(request, "index.html")


@app.get("/healthz")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "workers": worker_manager.get_status(),
    }
