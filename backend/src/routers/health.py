"""
Health Check Router
"""
from fastapi import APIRouter
from datetime import datetime

from src.config import settings
from src.services.filesystem import symlink_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
    }


@router.get("/stats")
async def get_stats():
    """Get system statistics"""
    from sqlalchemy import select, func
    from src.database import async_session
    from src.models import MediaItem, MediaState
    
    async with async_session() as session:
        # Count by state
        result = await session.execute(
            select(MediaItem.state, func.count(MediaItem.id))
            .group_by(MediaItem.state)
        )
        state_counts = {state: count for state, count in result.all()}
    
    return {
        "providers": {
            "real_debrid": settings.has_real_debrid,
            "torbox": settings.has_torbox,
            "plex": settings.has_plex,
            "prowlarr": settings.has_prowlarr,
            "tmdb": bool(settings.tmdb_api_key),
        },
        "mount_status": symlink_service.verify_mount(),
        "counts": {
            "requested": state_counts.get(MediaState.REQUESTED, 0),
            "indexed": state_counts.get(MediaState.INDEXED, 0),
            "scraped": state_counts.get(MediaState.SCRAPED, 0),
            "downloading": state_counts.get(MediaState.DOWNLOADING, 0),
            "downloaded": state_counts.get(MediaState.DOWNLOADED, 0),
            "symlinked": state_counts.get(MediaState.SYMLINKED, 0),
            "completed": state_counts.get(MediaState.COMPLETED, 0),
            "failed": state_counts.get(MediaState.FAILED, 0),
            "paused": state_counts.get(MediaState.PAUSED, 0),
        },
        "total": sum(state_counts.values()),
    }
