from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.app.routes import router
from src.logic.manager import Manager
from src.config import config
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Torbox Plex Manager")

# Mount static files
app.mount("/static", StaticFiles(directory="src/app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="src/app/templates")

# Include Router
app.include_router(router)

# Scheduler
scheduler = AsyncIOScheduler()
manager = Manager()

def run_sync_watchlist():
    logger.info("Running Watchlist Sync...")
    manager.sync_watchlist()
    # Also trigger running series sync after watchlist
    manager.sync_running_series()

def run_process_pending():
    logger.info("Processing Pending Items...")
    manager.process_pending()

def run_process_downloads():
    logger.info("Processing Downloads...")
    manager.process_downloads()

def run_retry_failed():
    logger.info("Retrying Failed Downloads...")
    manager.retry_failed_downloads()

@app.on_event("startup")
async def startup_event():
    # Start scheduler
    interval = config.get().scan_interval
    scheduler.add_job(run_sync_watchlist, 'interval', minutes=interval)
    scheduler.add_job(run_process_pending, 'interval', minutes=2)
    scheduler.add_job(run_process_downloads, 'interval', minutes=1)

    # Retry logic every hour
    scheduler.add_job(run_retry_failed, 'interval', minutes=60)

    scheduler.start()
    logger.info("Scheduler started.")

@app.get("/health")
async def health():
    return {"status": "ok"}
