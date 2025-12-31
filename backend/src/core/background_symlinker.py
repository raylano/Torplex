import asyncio
import logging
from typing import List
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.database import async_session
from src.models import MediaItem, MediaState, Episode, MediaType
from src.services.filesystem.symlink import symlink_service

logger = logging.getLogger(__name__)

class BackgroundSymlinkService:
    """
    Service that runs periodically to check if pending media items 
    are physically available on disk, independent of the main scraper loop.
    """
    
    def __init__(self):
        self.is_running = False
        
    async def run_check(self):
        """Run a full check of pending items"""
        if self.is_running:
            logger.warning("Background symlink check already running, skipping.")
            return
            
        self.is_running = True
        logger.info("♻️ Starting background symlink check...")
        
        try:
            async with async_session() as session:
                # 1. Fetch all items that are NOT completed but have metadata
                # We check REQUESTED (might have files but not scraped) and PROCESSING
                stmt = select(MediaItem).options(
                    selectinload(MediaItem.episodes)
                ).where(
                    and_(
                        MediaItem.state != MediaState.COMPLETED,
                        MediaItem.state != MediaState.FAILED
                    )
                )
                
                result = await session.execute(stmt)
                items = result.scalars().all()
                
                logger.info(f"Checking {len(items)} active media items for local files...")
                
                for item in items:
                    await self._check_item(item, session)
                    
        except Exception as e:
            logger.error(f"Error in background symlink check: {e}")
        finally:
            self.is_running = False
            logger.info("✅ Background symlink check finished.")

    async def _check_item(self, item: MediaItem, session):
        """Check a single media item for files"""
        try:
            if item.type == MediaType.SHOW:
                await self._check_show(item, session)
            else:
                await self._check_movie(item, session)
        except Exception as e:
            logger.error(f"Error checking item {item.title}: {e}")

    async def _check_show(self, item: MediaItem, session):
        """Check episodes for a show"""
        # We only care about episodes that are NOT completed
        pending_episodes = [e for e in item.episodes if e.state != MediaState.COMPLETED]
        
        if not pending_episodes:
            return

        for episode in pending_episodes:
            # Skip if we don't have basic metadata
            if not episode.season_number or not episode.episode_number:
                continue
                
            # Try to find file
            # We assume we don't know the torrent name, so we search generically?
            # actually find_episode_in_torrent needs a torrent name.
            # But duplicate logic exists in `find_episode` (generic search).
            
            # If we have a torrent_hash/name from a previous scrape attempt (even if failed download), use it?
            # Often we don't have it if 429 happened before scraping.
            
            # So we use the "Generic" search: `symlink_service.find_episode`
            # This searches the whole mount for anything matching SxxExx
            
            found_path = await symlink_service.find_episode(
                item.title, 
                episode.season_number, 
                episode.episode_number,
                episode.absolute_episode_number
            )
            
            if found_path:
                logger.info(f"✨ Background found file for {item.title} S{episode.season_number}E{episode.episode_number}: {found_path.name}")
                
                # Link it
                target = await symlink_service.create_symlink(
                    found_path,
                    item,
                    episode=episode
                )
                
                if target:
                    episode.state = MediaState.COMPLETED
                    episode.file_path = str(target)
                    session.add(episode)
                    await session.commit() 
            
            # Yield to event loop to not freeze server
            await asyncio.sleep(0.1)

    async def _check_movie(self, item: MediaItem, session):
        # Movie logic is simpler, similar to show
        pass

# Global instance
background_symlinker = BackgroundSymlinkService()
