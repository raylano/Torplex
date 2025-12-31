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
from src.core.background_symlinker import background_symlinker
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
            # Store title before try block - session may be invalid after error
            item_title = item.title
            try:
                # For TV shows, create episodes after indexing
                is_tv_show = item.type in [MediaType.SHOW, MediaType.ANIME_SHOW]
                
                if is_tv_show and item.state == MediaState.INDEXED:
                    # Create episode records for this show
                    created = await episode_processor.create_episodes_for_show(item, session)
                    
                    if created > 0:
                        logger.info(f"TV Show {item_title}: created {created} episodes")
                    
                    # Move show to SCRAPED state - this takes it out of the INDEXED loop
                    # The show's actual "completion" status is computed from its episodes
                    # SCRAPED is safe because TV shows don't go through download/symlink individually
                    item.state = MediaState.SCRAPED
                    await session.commit()
                    logger.info(f"TV Show {item_title} ready - {created} episodes queued for processing")
                    continue
                
                # Skip TV shows that are past INDEXED - their episodes are processed separately
                # Only movies should go through the download/symlink process directly
                if is_tv_show and item.state in [MediaState.SCRAPED, MediaState.DOWNLOADING, 
                                                  MediaState.DOWNLOADED, MediaState.SYMLINKED]:
                    logger.debug(f"Skipping TV show {item_title} in {item.state} - episodes process separately")
                    continue
                
                # For movies (and rare edge cases), process normally
                new_state = await state_machine.process_item(item, session)
                logger.debug(f"{item_title}: {item.state} -> {new_state}")
                
            except Exception as e:
                logger.error(f"Error processing {item_title}: {e}")


from sqlalchemy.orm.exc import StaleDataError, ObjectDeletedError

# ... imports ...


async def process_episodes_scrape():
    """JOB: Scrape new episodes (Fast Discovery)"""
    async with async_session() as session:
        # Increased limit for throughput
        try:
            pending = await episode_processor.get_episodes_to_scrape(session, limit=20)
            if pending:
                logger.info(f"🔎 Scraping {len(pending)} episodes...")
        except Exception as e:
            logger.error(f"Error fetching scrape items: {e}")
            return
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
            except (StaleDataError, ObjectDeletedError):
                logger.warning(f"Item vanished during scrape (concurrent delete?): {show.title}")
                await session.rollback()
            except Exception as e:
                logger.error(f"Scrape error: {e}")
                await session.rollback()

async def process_episodes_download():
    """JOB: Add to Debrid (Safe Speed)"""
    async with async_session() as session:
        # Increased limit
        try:
            pending = await episode_processor.get_episodes_to_download(session, limit=20)
            if pending:
                logger.info(f"📥 Downloading {len(pending)} episodes...")
        except Exception as e:
             logger.error(f"Error fetching download items: {e}")
             return
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
            except (StaleDataError, ObjectDeletedError):
                logger.warning(f"Item vanished during download (concurrent delete?): {show.title}")
                await session.rollback()
            except Exception as e:
                logger.error(f"Download error: {e}")
                await session.rollback()

async def process_episodes_symlink():
    """JOB: Symlink Files (Very Fast)"""
    async with async_session() as session:
        # Huge batch size for local operations
        try:
            pending = await episode_processor.get_episodes_to_symlink(session, limit=100)
            if pending:
                logger.info(f"🔗 Symlinking {len(pending)} episodes...")
        except Exception as e:
            logger.error(f"Error fetching symlink items: {e}")
            return
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
            except (StaleDataError, ObjectDeletedError):
                logger.warning(f"Item vanished during symlink (concurrent delete?): {show.title}")
                await session.rollback()
            except Exception as e:
                logger.error(f"Symlink error: {e}")
                await session.rollback()

async def sync_plex_watchlist():
    """JOB: Sync Plex Watchlist to DB"""
    async with async_session() as session:
        try:
            await plex_service.sync_watchlist(session)
        except Exception as e:
            logger.error(f"Plex Sync error: {e}")

async def retry_failed_items():
    """JOB: Retry items that failed > 24h ago"""
    async with async_session() as session:
        try:
            # Placeholder for retry logic - currently just logs to avoid crash
            # TODO: Implement proper retry logic based on updated_at
            pass
        except Exception as e:
            logger.error(f"Retry error: {e}")

async def cleanup_stale_torrents():
    """JOB: Cleanup stuck downloads"""
    try:
        from src.services import downloader
        # Assuming downloader has a cleanup method, if not this is safe enough
        # await downloader.cleanup_stale()
        pass
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def setup_scheduler():
    """Configure scheduled jobs"""
    # ...
    
    # 0. Process Pending Items (Every 10s)
    scheduler.add_job(
        process_pending_items,
        IntervalTrigger(seconds=10),
        id="process_pending",
        name="Process Pending Items",
        replace_existing=True,
        max_instances=1,
    )

    # 1. Scraper Job (Every 15s)
    scheduler.add_job(
        process_episodes_scrape,
        IntervalTrigger(seconds=15),
        id="scrape_episodes",
        name="Scrape Episodes",
        replace_existing=True,
        max_instances=10, # Increased concurrency
    )

    # 2. Downloader Job (Every 60s)
    scheduler.add_job(
        process_episodes_download,
        IntervalTrigger(seconds=10), # Decreased interval
        id="download_episodes",
        name="Download Episodes",
        replace_existing=True,
        max_instances=10, 
    )

    # 3. Symlink Job (Every 5s)
    scheduler.add_job(
        process_episodes_symlink,
        IntervalTrigger(seconds=5),
        id="symlink_episodes",
        name="Symlink Episodes",
        replace_existing=True,
        max_instances=20, # Higher concurrency for local IO
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
    
    # Retry failed items once daily (every 24 hours)
    scheduler.add_job(
        retry_failed_items,
        IntervalTrigger(hours=24),
        id="retry_failed",
        name="Daily Retry Failed Items",
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
    
    # Background Symlink Check (Every 15 minutes) - Independent of API
    scheduler.add_job(
        background_symlinker.run_check,
        IntervalTrigger(minutes=15),
        id="bg_symlink_check",
        name="Background File Check",
        replace_existing=True,
        max_instances=1
    )
    
    logger.info("Scheduler configured with jobs")


# Setup on import
setup_scheduler()
