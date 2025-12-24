"""
Episode Processor
Handles per-episode processing for TV shows
"""
from datetime import datetime
from typing import List, Optional
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MediaItem, Episode, MediaState, MediaType
from src.services import tmdb_service, downloader, symlink_service
from src.services.scrapers import scrape_episode as scrape_episode_all
from src.core.quality import quality_ranker


class EpisodeProcessor:
    """
    Processes TV show episodes individually.
    Each episode goes through: REQUESTED -> INDEXED -> SCRAPED -> DOWNLOADED -> SYMLINKED -> COMPLETED
    """
    
    async def create_episodes_for_show(self, show: MediaItem, session: AsyncSession) -> int:
        """
        Fetch episodes from TMDB and create Episode records.
        MOUNT-FIRST: Scans mount for existing files and pre-fills those as DOWNLOADED.
        Returns number of episodes created.
        """
        from src.services.filesystem.mount_scanner import mount_scanner
        
        if not show.tmdb_id or not show.number_of_seasons:
            logger.warning(f"Cannot create episodes: missing TMDB data for {show.title}")
            return 0
        
        # Check if episodes already exist
        existing = await session.execute(
            select(Episode).where(Episode.show_id == show.id)
        )
        if existing.scalars().first():
            logger.debug(f"Episodes already exist for {show.title}")
            return 0
        
        # MOUNT-FIRST: Scan mount for existing files
        logger.info(f"🔍 Scanning mount for existing '{show.title}' episodes...")
        existing_files = {}
        
        if mount_scanner.check_mount_available():
            existing_files = mount_scanner.find_all_episodes_for_show(show.title)
        else:
            logger.warning("Mount not available, skipping pre-scan")
        
        # Fetch episodes from TMDB
        episodes_data = await tmdb_service.get_all_episodes(
            show.tmdb_id, 
            show.number_of_seasons
        )
        
        created = 0
        pre_filled = 0
        
        for ep_data in episodes_data:
            season = ep_data["season_number"]
            episode_num = ep_data["episode_number"]
            
            # Check if this episode already exists in mount
            existing_file = existing_files.get((season, episode_num))
            
            # Also check for absolute numbering (season 1, absolute episode)
            # This handles anime where files use absolute numbers
            if not existing_file and season > 1:
                # Calculate absolute episode for lookup
                # This is a simplified approach - works for many anime
                pass  # TODO: Implement proper absolute conversion if needed
            
            if existing_file:
                # File exists! Create as DOWNLOADED (ready for symlink)
                episode = Episode(
                    show_id=show.id,
                    season_number=season,
                    episode_number=episode_num,
                    title=ep_data.get("title"),
                    overview=ep_data.get("overview"),
                    air_date=ep_data.get("air_date"),
                    state=MediaState.DOWNLOADED,  # Ready for symlink!
                    file_path=str(existing_file),
                )
                pre_filled += 1
            else:
                # File doesn't exist, needs scraping
                episode = Episode(
                    show_id=show.id,
                    season_number=season,
                    episode_number=episode_num,
                    title=ep_data.get("title"),
                    overview=ep_data.get("overview"),
                    air_date=ep_data.get("air_date"),
                    state=MediaState.REQUESTED,
                )
            
            session.add(episode)
            created += 1
        
        await session.commit()
        
        if pre_filled > 0:
            logger.success(f"✅ Created {created} episodes for {show.title} ({pre_filled} already in mount!)")
        else:
            logger.info(f"Created {created} episodes for {show.title} (none found in mount)")
        
        return created
    
    async def process_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """
        Process a single episode through the pipeline.
        """
        try:
            if episode.state == MediaState.REQUESTED:
                return await self._scrape_episode(episode, show, session)
            
            elif episode.state == MediaState.SCRAPED:
                return await self._download_episode(episode, show, session)
            
            elif episode.state == MediaState.DOWNLOADED:
                return await self._symlink_episode(episode, show, session)
            
            elif episode.state == MediaState.SYMLINKED:
                episode.state = MediaState.COMPLETED
                await session.commit()
                logger.success(f"✅ Completed: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
                return MediaState.COMPLETED
            
            return episode.state
            
        except Exception as e:
            logger.error(f"Error processing episode {show.title} S{episode.season_number}E{episode.episode_number}: {e}")
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
    
    async def _scrape_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """Scrape torrents for a single episode using all scrapers"""
        logger.info(f"Scraping: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        if not show.imdb_id:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        # Scrape using ALL scrapers (Torrentio + MediaFusion + Prowlarr)
        torrents = await scrape_episode_all(
            show.imdb_id,
            episode.season_number,
            episode.episode_number,
            title=show.title
        )
        
        if not torrents:
            logger.warning(f"No torrents found for {show.title} S{episode.season_number}E{episode.episode_number}")
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        logger.info(f"Found {len(torrents)} torrents for S{episode.season_number}E{episode.episode_number}")
        
        # Check cache and select best
        info_hashes = [t.info_hash for t in torrents]
        cache_status = await downloader.check_cache_all(info_hashes)
        
        if show.is_anime:
            best = quality_ranker.get_best_for_anime(torrents, cache_status)
        else:
            best = quality_ranker.get_best_for_movie_or_show(torrents, cache_status)
        
        if best:
            episode.file_path = best.info_hash
            episode.state = MediaState.SCRAPED
            await session.commit()
            logger.info(f"Selected: {best.title[:40]}...")
            return MediaState.SCRAPED
        
        episode.state = MediaState.FAILED
        await session.commit()
        return MediaState.FAILED
    
    async def _download_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """Add episode torrent to debrid and store torrent info for symlink"""
        logger.info(f"Downloading: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        info_hash = episode.file_path
        if not info_hash:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        # Try instant check first (Riven-style) - this also adds the torrent
        instant = await downloader.check_instant_via_add(info_hash)
        
        if instant and instant.get("cached"):
            # Store torrent name for symlink matching
            episode.torrent_name = instant.get("filename")
            episode.state = MediaState.DOWNLOADED
            await session.commit()
            logger.info(f"✅ Cached! Torrent: {episode.torrent_name[:40] if episode.torrent_name else 'N/A'}...")
            return MediaState.DOWNLOADED
        
        # Not cached - add normally and wait
        provider, debrid_id = await downloader.add_torrent(info_hash)
        
        if provider and debrid_id:
            episode.state = MediaState.DOWNLOADED
            await session.commit()
            logger.info(f"Added to {provider} (not cached, waiting): {debrid_id}")
            return MediaState.DOWNLOADED
        
        episode.state = MediaState.FAILED
        await session.commit()
        return MediaState.FAILED
    
    async def _symlink_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """Create symlink for episode"""
        logger.info(f"Symlinking: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        source_path = None
        
        # First try: Use stored torrent_name for direct path construction
        if episode.torrent_name:
            source_path = symlink_service.find_episode_in_torrent(
                episode.torrent_name,
                episode.season_number,
                episode.episode_number
            )
        
        # Second try: Episode-specific search in __all__ folder (with alternative titles)
        if not source_path:
            import json
            alt_titles = json.loads(show.alternative_titles or "[]") if show.alternative_titles else []
            source_path = symlink_service.find_episode(
                show.title,
                episode.season_number,
                episode.episode_number,
                alternative_titles=alt_titles
            )
        
        if not source_path:
            logger.warning(f"Episode file not found in mount: {show.title} S{episode.season_number}E{episode.episode_number}")
            # Don't create bad symlinks - retry later
            return episode.state
        
        # Create symlink
        success, symlink_path = symlink_service.create_symlink(
            show,
            source_path,
            season=episode.season_number,
            episode=episode.episode_number
        )
        
        if success and symlink_path:
            episode.symlink_path = str(symlink_path)
            episode.state = MediaState.SYMLINKED
            await session.commit()
            return MediaState.SYMLINKED
        
        episode.state = MediaState.FAILED
        await session.commit()
        return MediaState.FAILED
    
    async def get_pending_episodes(self, session: AsyncSession, limit: int = 10) -> List[tuple]:
        """Get episodes that need processing, with their parent show"""
        result = await session.execute(
            select(Episode, MediaItem)
            .join(MediaItem, Episode.show_id == MediaItem.id)
            .where(Episode.state.in_([
                MediaState.REQUESTED,
                MediaState.SCRAPED,
                MediaState.DOWNLOADED,
                MediaState.SYMLINKED,
            ]))
            .limit(limit)
        )
        return result.all()


# Singleton instance
episode_processor = EpisodeProcessor()
