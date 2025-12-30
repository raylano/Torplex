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


async def process_episodes_scrape():
    """JOB: Scrape new episodes (Fast Discovery)"""
    async with async_session() as session:
        pending = await episode_processor.get_episodes_to_scrape(session, limit=5)
        if pending:
            logger.info(f"🔎 Scraping {len(pending)} episodes...")
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
                import asyncio
                await asyncio.sleep(2) # Small delay between scrapes
            except Exception as e:
                logger.error(f"Scrape error: {e}")

async def process_episodes_download():
    """JOB: Add to Debrid (Safe Speed)"""
    async with async_session() as session:
        pending = await episode_processor.get_episodes_to_download(session, limit=5)
        if pending:
            logger.info(f"📥 Downloading {len(pending)} episodes...")
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
                import asyncio
                await asyncio.sleep(5) # Respect API limits
            except Exception as e:
                logger.error(f"Download error: {e}")

async def process_episodes_symlink():
    """JOB: Symlink Files (Very Fast)"""
    async with async_session() as session:
        pending = await episode_processor.get_episodes_to_symlink(session, limit=20)
        # Don't log if empty to avoid spamming logs every 5s
        if pending:
            logger.info(f"🔗 Symlinking {len(pending)} episodes...")
        
        for episode, show in pending:
            try:
                await episode_processor.process_episode(episode, show, session)
                # No sleep needed, file operations are local
            except Exception as e:
                logger.error(f"Symlink error: {e}")

async def sync_plex_watchlist():
    """Sync items from Plex Watchlist"""
    if not plex_service.token:
        return
    
    logger.info("Syncing Plex Watchlist...")
    
    watchlist_items = await plex_service.get_watchlist()
    
    if not watchlist_items:
        return
    
    added_count = 0
    
    async with async_session() as session:
        for plex_item in watchlist_items:
            try:
                # Extract IDs
                ids = plex_service.extract_ids(plex_item)
                title = plex_item.get("title", "Unknown")
                year = plex_item.get("year")
                
                # Check if already in database by IMDB ID
                imdb_id = ids.get("imdb_id")
                existing = None
                
                if imdb_id:
                    result = await session.execute(
                        select(MediaItem).where(MediaItem.imdb_id == imdb_id)
                    )
                    existing = result.scalars().first()
                
                # If no IMDB ID or not found, check by title + year
                if not existing:
                    from sqlalchemy import and_
                    result = await session.execute(
                        select(MediaItem).where(
                            and_(
                                MediaItem.title == title,
                                MediaItem.year == year
                            )
                        )
                    )
                    existing = result.scalars().first()
                
                if existing:
                    continue  # Already tracking this
                
                # Create new media item
                media_type = plex_item.get("type", "movie")
                
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
                added_count += 1
                logger.info(f"Added from Plex Watchlist: {title}")
                
            except Exception as e:
                logger.error(f"Error adding watchlist item: {e}")
        
        await session.commit()
    
    if added_count > 0:
        logger.info(f"Watchlist sync complete: added {added_count} new items")
    else:
        logger.debug("Watchlist sync complete: no new items")


async def retry_failed_items():
    """
    Daily retry of failed items.
    Resets FAILED items back to INDEXED so they get re-scraped.
    This gives them a fresh chance with potentially new torrents available.
    """
    async with async_session() as session:
        # Retry failed media items (movies)
        result = await session.execute(
            select(MediaItem)
            .where(MediaItem.state == MediaState.FAILED)
            .where(MediaItem.retry_count < 10)  # Max 10 daily retries total
            .order_by(MediaItem.updated_at)
            .limit(20)
        )
        items = result.scalars().all()
        
        items_retried = 0
        for item in items:
            logger.info(f"🔄 Daily retry: {item.title} (attempt {item.retry_count + 1}/10)")
            # Reset to INDEXED so it gets re-scraped with fresh torrents
            item.state = MediaState.INDEXED
            item.last_error = None
            item.retry_count += 1
            items_retried += 1
        
        # Retry failed episodes
        from src.models import Episode
        ep_result = await session.execute(
            select(Episode)
            .where(Episode.state == MediaState.FAILED)
            .order_by(Episode.updated_at)
            .limit(50)  # More episodes can be retried at once
        )
        episodes = ep_result.scalars().all()
        
        eps_retried = 0
        for ep in episodes:
            logger.info(f"🔄 Daily retry episode: Show ID {ep.show_id} S{ep.season_number}E{ep.episode_number}")
            # Reset to SCRAPED for re-download/symlink attempt
            # or INDEXED if we want full rescrape
            ep.state = MediaState.INDEXED
            eps_retried += 1
        
        await session.commit()
        
        if items_retried > 0 or eps_retried > 0:
            logger.info(f"✅ Daily retry complete: {items_retried} items, {eps_retried} episodes queued for retry")


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
    # Process pending items (Shows/Movies processing)
    scheduler.add_job(
        process_pending_items,
        IntervalTrigger(seconds=settings.library_scan_interval),
        id="process_pending",
        name="Process Pending Items",
        replace_existing=True,
    )
    
    # 1. Scraper Job (Every 15s)
    scheduler.add_job(
        process_episodes_scrape,
        IntervalTrigger(seconds=15),
        id="scrape_episodes",
        name="Scrape Episodes",
        replace_existing=True,
    )

    # 2. Downloader Job (Every 60s)
    scheduler.add_job(
        process_episodes_download,
        IntervalTrigger(seconds=60),
        id="download_episodes",
        name="Download Episodes",
        replace_existing=True,
    )

    # 3. Symlink Job (Every 5s)
    scheduler.add_job(
        process_episodes_symlink,
        IntervalTrigger(seconds=5),
        id="symlink_episodes",
        name="Symlink Episodes",
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
    
    logger.info("Scheduler configured with jobs")


# Setup on import
setup_scheduler()
