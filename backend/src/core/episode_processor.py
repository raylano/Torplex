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
from src.services import tmdb_service, torrentio_scraper, downloader, symlink_service
from src.core.quality import quality_ranker


class EpisodeProcessor:
    """
    Processes TV show episodes individually.
    Each episode goes through: REQUESTED -> INDEXED -> SCRAPED -> DOWNLOADED -> SYMLINKED -> COMPLETED
    """
    
    async def create_episodes_for_show(self, show: MediaItem, session: AsyncSession) -> int:
        """
        Fetch episodes from TMDB and create Episode records.
        Returns number of episodes created.
        """
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
        
        # Fetch episodes from TMDB
        episodes_data = await tmdb_service.get_all_episodes(
            show.tmdb_id, 
            show.number_of_seasons
        )
        
        created = 0
        for ep_data in episodes_data:
            episode = Episode(
                show_id=show.id,
                season_number=ep_data["season_number"],
                episode_number=ep_data["episode_number"],
                title=ep_data.get("title"),
                overview=ep_data.get("overview"),
                air_date=ep_data.get("air_date"),
                state=MediaState.REQUESTED,
            )
            session.add(episode)
            created += 1
        
        await session.commit()
        logger.info(f"Created {created} episodes for {show.title}")
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
        """Scrape torrents for a single episode"""
        logger.info(f"Scraping: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        if not show.imdb_id:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        # Scrape for this specific episode
        torrents = await torrentio_scraper.scrape_episode(
            show.imdb_id,
            episode.season_number,
            episode.episode_number
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
        """Add episode torrent to debrid"""
        logger.info(f"Downloading: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        info_hash = episode.file_path
        if not info_hash:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        provider, debrid_id = await downloader.add_torrent(info_hash)
        
        if provider and debrid_id:
            episode.state = MediaState.DOWNLOADED
            await session.commit()
            logger.info(f"Added to {provider}: S{episode.season_number}E{episode.episode_number}")
            return MediaState.DOWNLOADED
        
        episode.state = MediaState.FAILED
        await session.commit()
        return MediaState.FAILED
    
    async def _symlink_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """Create symlink for episode"""
        logger.info(f"Symlinking: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        # Use the episode-specific search function (only searches shows/anime folders)
        source_path = symlink_service.find_episode(
            show.title,
            episode.season_number,
            episode.episode_number
        )
        
        # NO fallback to find_by_infohash - that searches movies too!
        
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
