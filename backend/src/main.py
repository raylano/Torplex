"""
Torplex - Media Automation Platform
Main FastAPI Application
"""
import contextlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import sys

from src.config import settings
from src.database import init_db
from src.routers import media, search, settings as settings_router, health
from src.core.scheduler import scheduler

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 Starting Torplex...")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    # Start background scheduler
    scheduler.start()
    logger.info("✅ Scheduler started")
    
    logger.info(f"🎬 Torplex is running! API: http://0.0.0.0:8000")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Torplex...")
    scheduler.shutdown()
    logger.info("✅ Scheduler stopped")


app = FastAPI(
    title="Torplex",
    description="Media Automation Platform with Real-Debrid & Torbox support",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(media.router, prefix="/api", tags=["Media"])
app.include_router(search.router, prefix="/api", tags=["Search"])
app.include_router(settings_router.router, prefix="/api", tags=["Settings"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Torplex",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs"
    }
