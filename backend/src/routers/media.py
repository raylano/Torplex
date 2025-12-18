"""
Media Library Router
CRUD operations for media items
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from src.database import get_db
from src.models import MediaItem, Episode, MediaState, MediaType

router = APIRouter()


# Pydantic schemas
class MediaItemResponse(BaseModel):
    id: int
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    type: str
    state: str
    is_anime: bool
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    overview: Optional[str] = None
    genres: Optional[List[str]] = None
    vote_average: Optional[float] = None
    number_of_seasons: Optional[int] = None
    number_of_episodes: Optional[int] = None
    status: Optional[str] = None
    file_path: Optional[str] = None
    symlink_path: Optional[str] = None
    last_error: Optional[str] = None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    # Computed fields
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class MediaItemCreate(BaseModel):
    title: str
    year: Optional[int] = None
    type: str = "movie"
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    is_anime: bool = False


class MediaItemUpdate(BaseModel):
    state: Optional[str] = None
    is_anime: Optional[bool] = None


class PaginatedResponse(BaseModel):
    items: List[MediaItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


def serialize_media_item(item: MediaItem) -> dict:
    """Convert MediaItem to response dict with computed fields"""
    data = {
        "id": item.id,
        "imdb_id": item.imdb_id,
        "tmdb_id": item.tmdb_id,
        "title": item.title,
        "original_title": item.original_title,
        "year": item.year,
        "type": item.type.value if isinstance(item.type, MediaType) else item.type,
        "state": item.state.value if isinstance(item.state, MediaState) else item.state,
        "is_anime": item.is_anime,
        "poster_path": item.poster_path,
        "backdrop_path": item.backdrop_path,
        "overview": item.overview,
        "genres": item.genres,
        "vote_average": item.vote_average,
        "number_of_seasons": item.number_of_seasons,
        "number_of_episodes": item.number_of_episodes,
        "status": item.status,
        "file_path": item.file_path,
        "symlink_path": item.symlink_path,
        "last_error": item.last_error,
        "retry_count": item.retry_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "completed_at": item.completed_at,
        "poster_url": item.poster_url,
        "backdrop_url": item.backdrop_url,
    }
    return data


@router.get("/library", response_model=PaginatedResponse)
async def get_library(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    state: Optional[str] = None,
    is_anime: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get paginated library with filters"""
    query = select(MediaItem)
    
    # Apply filters
    if type:
        query = query.where(MediaItem.type == type)
    
    if state:
        query = query.where(MediaItem.state == state)
    
    if is_anime is not None:
        query = query.where(MediaItem.is_anime == is_anime)
    
    if search:
        search_term = f"%{search}%"
        query = query.where(
            or_(
                MediaItem.title.ilike(search_term),
                MediaItem.original_title.ilike(search_term),
            )
        )
    
    # Get total count
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * page_size
    query = query.order_by(MediaItem.updated_at.desc()).offset(offset).limit(page_size)
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    return {
        "items": [serialize_media_item(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/library/{item_id}", response_model=MediaItemResponse)
async def get_media_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single media item by ID"""
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    return serialize_media_item(item)


@router.post("/library", response_model=MediaItemResponse)
async def create_media_item(data: MediaItemCreate, db: AsyncSession = Depends(get_db)):
    """Create a new media item (manual request)"""
    # Determine media type
    type_map = {
        "movie": MediaType.MOVIE,
        "show": MediaType.SHOW,
        "anime_movie": MediaType.ANIME_MOVIE,
        "anime_show": MediaType.ANIME_SHOW,
    }
    media_type = type_map.get(data.type, MediaType.MOVIE)
    
    # Check for anime override
    if data.is_anime:
        if media_type == MediaType.MOVIE:
            media_type = MediaType.ANIME_MOVIE
        elif media_type == MediaType.SHOW:
            media_type = MediaType.ANIME_SHOW
    
    item = MediaItem(
        title=data.title,
        year=data.year,
        type=media_type,
        imdb_id=data.imdb_id,
        tmdb_id=data.tmdb_id,
        is_anime=data.is_anime,
        state=MediaState.REQUESTED,
    )
    
    db.add(item)
    await db.commit()
    await db.refresh(item)
    
    return serialize_media_item(item)


@router.patch("/library/{item_id}", response_model=MediaItemResponse)
async def update_media_item(
    item_id: int,
    data: MediaItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a media item"""
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    if data.state:
        try:
            item.state = MediaState(data.state)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {data.state}")
    
    if data.is_anime is not None:
        item.is_anime = data.is_anime
        # Update type if needed
        if data.is_anime:
            if item.type == MediaType.MOVIE:
                item.type = MediaType.ANIME_MOVIE
            elif item.type == MediaType.SHOW:
                item.type = MediaType.ANIME_SHOW
    
    await db.commit()
    await db.refresh(item)
    
    return serialize_media_item(item)


@router.delete("/library/{item_id}")
async def delete_media_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a media item"""
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Remove symlink if exists
    if item.symlink_path:
        from pathlib import Path
        from src.services.filesystem import symlink_service
        symlink_service.remove_symlink(Path(item.symlink_path))
    
    await db.delete(item)
    await db.commit()
    
    return {"message": "Deleted", "id": item_id}


@router.post("/library/{item_id}/retry")
async def retry_media_item(
    item_id: int, 
    mode: str = Query("force", description="Retry mode: force, symlink"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retry a media item with different modes:
    - force: Restart from beginning (REQUESTED state)
    - symlink: Only retry symlink creation (DOWNLOADED state)
    """
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    if mode == "symlink":
        item.state = MediaState.DOWNLOADED
    else:  # force
        item.state = MediaState.REQUESTED
    
    item.last_error = None
    item.retry_count = 0
    await db.commit()
    
    return {"message": f"Retry ({mode}) queued", "id": item_id, "new_state": item.state.value}


@router.get("/library/{item_id}/mount-files")
async def list_mount_files(item_id: int, db: AsyncSession = Depends(get_db)):
    """List available files in mount that could be symlinked"""
    from src.services.filesystem import symlink_service
    
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    # Search mount for matching files
    files = []
    mount_path = symlink_service.mount_path
    
    for subdir in ["movies", "shows", "anime", "__all__"]:
        search_path = mount_path / subdir
        if not search_path.exists():
            continue
        
        for folder in search_path.iterdir():
            if folder.is_dir():
                video_files = symlink_service._find_video_files(folder)
                for vf in video_files[:3]:  # Max 3 per folder
                    files.append({
                        "path": str(vf),
                        "name": vf.name,
                        "folder": folder.name,
                        "size_mb": round(vf.stat().st_size / (1024 * 1024), 1)
                    })
    
    return {"files": files[:50]}  # Max 50 files


@router.post("/library/{item_id}/manual-symlink")
async def manual_symlink(
    item_id: int,
    file_path: str = Query(..., description="Full path to source file"),
    db: AsyncSession = Depends(get_db)
):
    """Manually create symlink to a specific file"""
    from pathlib import Path
    from src.services.filesystem import symlink_service
    
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Media item not found")
    
    source = Path(file_path)
    if not source.exists():
        raise HTTPException(status_code=400, detail="Source file not found")
    
    success, symlink_path = symlink_service.create_symlink(item, source)
    
    if success:
        item.file_path = str(source)
        item.symlink_path = str(symlink_path)
        item.state = MediaState.SYMLINKED
        await db.commit()
        return {"message": "Symlink created", "symlink_path": str(symlink_path)}
    
    raise HTTPException(status_code=500, detail="Failed to create symlink")


# Episode endpoints

class EpisodeResponse(BaseModel):
    id: int
    season_number: int
    episode_number: int
    title: Optional[str] = None
    overview: Optional[str] = None
    air_date: Optional[str] = None
    state: str
    file_path: Optional[str] = None
    symlink_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class EpisodesListResponse(BaseModel):
    show_id: int
    show_title: str
    total_episodes: int
    completed_episodes: int
    episodes: List[EpisodeResponse]


@router.get("/library/{item_id}/episodes", response_model=EpisodesListResponse)
async def get_episodes(item_id: int, db: AsyncSession = Depends(get_db)):
    """Get all episodes for a TV show"""
    # Get the show
    result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    show = result.scalar_one_or_none()
    
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    
    if show.type not in [MediaType.SHOW, MediaType.ANIME_SHOW]:
        raise HTTPException(status_code=400, detail="Item is not a TV show")
    
    # Get episodes
    ep_result = await db.execute(
        select(Episode)
        .where(Episode.show_id == item_id)
        .order_by(Episode.season_number, Episode.episode_number)
    )
    episodes = ep_result.scalars().all()
    
    # Count completed
    completed = sum(1 for ep in episodes if ep.state == MediaState.COMPLETED)
    
    return {
        "show_id": show.id,
        "show_title": show.title,
        "total_episodes": len(episodes),
        "completed_episodes": completed,
        "episodes": [
            {
                "id": ep.id,
                "season_number": ep.season_number,
                "episode_number": ep.episode_number,
                "title": ep.title,
                "overview": ep.overview,
                "air_date": ep.air_date,
                "state": ep.state.value if isinstance(ep.state, MediaState) else ep.state,
                "file_path": ep.file_path,
                "symlink_path": ep.symlink_path,
                "created_at": ep.created_at,
                "updated_at": ep.updated_at,
            }
            for ep in episodes
        ],
    }


@router.post("/library/{item_id}/episodes/{episode_id}/retry")
async def retry_episode(
    item_id: int, 
    episode_id: int, 
    db: AsyncSession = Depends(get_db)
):
    """Retry a single failed episode"""
    result = await db.execute(
        select(Episode)
        .where(Episode.id == episode_id)
        .where(Episode.show_id == item_id)
    )
    episode = result.scalar_one_or_none()
    
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    episode.state = MediaState.REQUESTED
    await db.commit()
    
    return {
        "message": "Episode retry queued", 
        "episode_id": episode_id,
        "season": episode.season_number,
        "episode": episode.episode_number,
    }


@router.post("/library/{item_id}/retry-all-episodes")
async def retry_all_episodes(
    item_id: int,
    mode: str = Query("failed", description="Which episodes: failed, all"),
    db: AsyncSession = Depends(get_db)
):
    """Retry all (or failed) episodes of a series"""
    # Verify show exists
    show_result = await db.execute(select(MediaItem).where(MediaItem.id == item_id))
    show = show_result.scalar_one_or_none()
    
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    
    if show.type not in [MediaType.SHOW, MediaType.ANIME_SHOW]:
        raise HTTPException(status_code=400, detail="Not a TV show")
    
    # Get episodes to retry
    query = select(Episode).where(Episode.show_id == item_id)
    if mode == "failed":
        query = query.where(Episode.state == MediaState.FAILED)
    
    result = await db.execute(query)
    episodes = result.scalars().all()
    
    count = 0
    for ep in episodes:
        ep.state = MediaState.REQUESTED
        count += 1
    
    await db.commit()
    
    return {"message": f"Retry queued for {count} episodes", "count": count}


