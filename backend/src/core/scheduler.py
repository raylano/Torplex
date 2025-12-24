"""
Background Scheduler
Runs periodic tasks for media processing
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select

from src.config import settings
from src.database import async_session
from src.models import MediaItem, MediaState, MediaType
from src.core.state_machine import state_machine
from src.core.episode_processor import episode_processor
from src.services.content import plex_service, tmdb_service


scheduler = AsyncIOScheduler()


async def process_pending_items():
    """Process all items that need work"""
    async with async_session() as session:
        # Get media items that need processing
        # Note: TV shows in INDEXED state are handled specially below
        processable_states = [
            MediaState.REQUESTED,
            MediaState.INDEXED,
            MediaState.SCRAPED,
            MediaState.DOWNLOADING,
            MediaState.DOWNLOADED,
            MediaState.SYMLINKED,
        ]
        
        result = await session.execute(
            select(MediaItem)
            .where(MediaItem.state.in_(processable_states))
            .order_by(MediaItem.created_at)
            .limit(10)
        )
        items = result.scalars().all()
        
        if items:
            logger.info(f"Processing {len(items)} pending items...")
        
        for item in items:
            try:
                # For TV shows, create episodes after indexing
                is_tv_show = item.type in [MediaType.SHOW, MediaType.ANIME_SHOW]
                
                if is_tv_show and item.state == MediaState.INDEXED:
                    # Create episode records for this show
                    created = await episode_processor.create_episodes_for_show(item, session)
                    
                    if created > 0:
                        logger.info(f"TV Show {item.title}: created {created} episodes")
                    
                    # Move show to COMPLETED - episodes are processed separately
                    # The show itself is "done" - individual episodes track their own status
                    item.state = MediaState.COMPLETED
                    await session.commit()
                    logger.info(f"TV Show {item.title} ready - {created} episodes queued for processing")
                    continue
                
                # For movies, process normally
                new_state = await state_machine.process_item(item, session)
                logger.debug(f"{item.title}: {item.state} -> {new_state}")
                
            except Exception as e:
                logger.error(f"Error processing {item.title}: {e}")


async def process_pending_episodes():
    """Process TV show episodes individually"""
    async with async_session() as session:
        # Get pending episodes with their parent shows
        pending = await episode_processor.get_pending_episodes(session, limit=10)
        
        if pending:
            logger.info(f"Processing {len(pending)} pending episodes...")
        
        for episode, show in pending:
            try:
                new_state = await episode_processor.process_episode(episode, show, session)
                logger.debug(f"{show.title} S{episode.season_number}E{episode.episode_number}: -> {new_state}")
            except Exception as e:
                logger.error(f"Error processing episode: {e}")


async def sync_plex_watchlist():
    """Sync items from Plex Watchlist"""
    if not plex_service.token:
        return
    
    logger.info("Syncing Plex Watchlist...")
    
    watchlist_items = await plex_service.get_watchlist()
    
    if not watchlist_items:
        return
    
    async with async_session() as session:
        for plex_item in watchlist_items:
            try:
                # Extract IDs
                ids = plex_service.extract_ids(plex_item)
                
                # Check if already in database
                imdb_id = ids.get("imdb_id")
                if imdb_id:
                    result = await session.execute(
                        select(MediaItem).where(MediaItem.imdb_id == imdb_id)
                    )
                    existing = result.scalar_one_or_none()
                    
                    if existing:
                        continue  # Already tracking this
                
                # Create new media item
                title = plex_item.get("title", "Unknown")
                media_type = plex_item.get("type", "movie")
                year = plex_item.get("year")
                
                from src.models import MediaType
                if media_type == "show":
                    item_type = MediaType.SHOW
                else:
                    item_type = MediaType.MOVIE
                
                new_item = MediaItem(
                    title=title,
                    year=year,
                    type=item_type,
                    imdb_id=ids.get("imdb_id"),
                    tmdb_id=int(ids["tmdb_id"]) if ids.get("tmdb_id") else None,
                    state=MediaState.REQUESTED,
                )
                
                session.add(new_item)
                logger.info(f"Added from Plex Watchlist: {title}")
                
            except Exception as e:
                logger.error(f"Error adding watchlist item: {e}")
        
        await session.commit()


async def retry_failed_items():
    """Retry failed items that haven't exceeded retry limit"""
    async with async_session() as session:
        result = await session.execute(
            select(MediaItem)
            .where(MediaItem.state == MediaState.FAILED)
            .where(MediaItem.retry_count < 5)
            .order_by(MediaItem.updated_at)
            .limit(5)
        )
        items = result.scalars().all()
        
        for item in items:
            logger.info(f"Retrying failed item: {item.title} (attempt {item.retry_count + 1})")
            item.state = MediaState.REQUESTED
            item.last_error = None
        
        await session.commit()


async def cleanup_stale_torrents():
    """Clean up torrents stuck at 0% for more than 24 hours"""
    from src.services.downloaders import real_debrid_service
    
    if not real_debrid_service.is_configured:
        return
    
    logger.info("Running stale torrent cleanup...")
    deleted = await real_debrid_service.cleanup_stale_torrents(max_age_hours=24)
    
    if deleted > 0:
        logger.info(f"Cleaned up {deleted} stale torrents (stuck at 0% for >24h)")


def setup_scheduler():
    """Configure scheduled jobs"""
    # Process pending items every minute
    scheduler.add_job(
        process_pending_items,
        IntervalTrigger(seconds=settings.library_scan_interval),
        id="process_pending",
        name="Process Pending Items",
        replace_existing=True,
    )
    
    # Process pending episodes every 30 seconds
    scheduler.add_job(
        process_pending_episodes,
        IntervalTrigger(seconds=30),
        id="process_episodes",
        name="Process Pending Episodes",
        replace_existing=True,
    )
    
    # Sync Plex Watchlist every 5 minutes
    if settings.has_plex:
        scheduler.add_job(
            sync_plex_watchlist,
            IntervalTrigger(seconds=settings.watchlist_scan_interval),
            id="sync_watchlist",
            name="Sync Plex Watchlist",
            replace_existing=True,
        )
    
    # Retry failed items every 10 minutes
    scheduler.add_job(
        retry_failed_items,
        IntervalTrigger(minutes=10),
        id="retry_failed",
        name="Retry Failed Items",
        replace_existing=True,
    )
    
    # Cleanup stale torrents every 6 hours
    scheduler.add_job(
        cleanup_stale_torrents,
        IntervalTrigger(hours=6),
        id="cleanup_stale",
        name="Cleanup Stale Torrents",
        replace_existing=True,
    )
    
    logger.info("Scheduler configured with jobs")


# Setup on import
setup_scheduler()
