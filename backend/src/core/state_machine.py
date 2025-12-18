"""
State Machine
Handles media item lifecycle transitions
"""
from datetime import datetime
from typing import Optional, Tuple
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MediaItem, MediaState, MediaType
from src.services import (
    tmdb_service,
    torrentio_scraper,
    prowlarr_scraper,
    downloader,
    symlink_service,
    plex_service,
)
from src.core.quality import quality_ranker


class StateMachine:
    """
    Handles state transitions for media items.
    
    States:
    REQUESTED -> INDEXED -> SCRAPED -> DOWNLOADING -> DOWNLOADED -> SYMLINKED -> COMPLETED
                                                                              |
                                                                              v
                                                                           FAILED
    """
    
    async def process_item(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """
        Process a media item through the pipeline.
        Returns the new state.
        """
        try:
            if item.state == MediaState.REQUESTED:
                return await self._index_item(item, session)
            
            elif item.state == MediaState.INDEXED:
                return await self._scrape_item(item, session)
            
            elif item.state == MediaState.SCRAPED:
                return await self._download_item(item, session)
            
            elif item.state == MediaState.DOWNLOADING:
                return await self._check_download(item, session)
            
            elif item.state == MediaState.DOWNLOADED:
                return await self._create_symlink(item, session)
            
            elif item.state == MediaState.SYMLINKED:
                return await self._complete_item(item, session)
            
            else:
                logger.debug(f"Item {item.title} in terminal state: {item.state}")
                return item.state
                
        except Exception as e:
            logger.error(f"Error processing {item.title}: {e}")
            item.state = MediaState.FAILED
            item.last_error = str(e)
            item.retry_count += 1
            await session.commit()
            return MediaState.FAILED
    
    async def _index_item(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Fetch metadata from TMDB"""
        logger.info(f"Indexing: {item.title}")
        
        # Try to find by IMDB ID first
        if item.imdb_id:
            data = await tmdb_service.find_by_imdb(item.imdb_id)
            if data:
                metadata = tmdb_service.extract_metadata(data, data.get("type", "movie"))
                self._apply_metadata(item, metadata)
                item.state = MediaState.INDEXED
                await session.commit()
                return MediaState.INDEXED
        
        # Search by title
        is_tv = item.type in [MediaType.SHOW, MediaType.ANIME_SHOW]
        
        if is_tv:
            results = await tmdb_service.search_tv(item.title, item.year)
        else:
            results = await tmdb_service.search_movie(item.title, item.year)
        
        if results:
            # Use first result
            result = results[0]
            tmdb_id = result.get("id")
            
            # Get full details
            if is_tv:
                full_data = await tmdb_service.get_tv_show(tmdb_id)
            else:
                full_data = await tmdb_service.get_movie(tmdb_id)
            
            if full_data:
                media_type = "tv" if is_tv else "movie"
                metadata = tmdb_service.extract_metadata(full_data, media_type)
                self._apply_metadata(item, metadata)
                item.state = MediaState.INDEXED
                await session.commit()
                return MediaState.INDEXED
        
        logger.warning(f"Could not find metadata for: {item.title}")
        item.state = MediaState.FAILED
        item.last_error = "Metadata not found on TMDB"
        await session.commit()
        return MediaState.FAILED
    
    def _apply_metadata(self, item: MediaItem, metadata: dict):
        """Apply TMDB metadata to item"""
        item.tmdb_id = metadata.get("tmdb_id") or item.tmdb_id
        item.imdb_id = metadata.get("imdb_id") or item.imdb_id
        item.tvdb_id = metadata.get("tvdb_id") or item.tvdb_id
        item.title = metadata.get("title") or item.title
        item.original_title = metadata.get("original_title")
        item.year = metadata.get("year") or item.year
        item.poster_path = metadata.get("poster_path")
        item.backdrop_path = metadata.get("backdrop_path")
        item.overview = metadata.get("overview")
        item.genres = metadata.get("genres")
        item.vote_average = metadata.get("vote_average")
        item.number_of_seasons = metadata.get("number_of_seasons")
        item.number_of_episodes = metadata.get("number_of_episodes")
        item.status = metadata.get("status")
        
        # Update anime flag based on TMDB data
        if metadata.get("is_anime"):
            if item.type == MediaType.MOVIE:
                item.type = MediaType.ANIME_MOVIE
            elif item.type == MediaType.SHOW:
                item.type = MediaType.ANIME_SHOW
            item.is_anime = True
    
    async def _scrape_item(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Scrape for torrents"""
        logger.info(f"Scraping: {item.title}")
        
        if not item.imdb_id:
            item.state = MediaState.FAILED
            item.last_error = "No IMDB ID available for scraping"
            await session.commit()
            return MediaState.FAILED
        
        # Get torrents from Torrentio
        torrents = await torrentio_scraper.scrape_movie(item.imdb_id)
        
        # Also try Prowlarr if configured
        if prowlarr_scraper.is_configured:
            prowlarr_results = await prowlarr_scraper.search_movie(
                item.title, item.year, item.imdb_id
            )
            torrents.extend(prowlarr_results)
        
        if not torrents:
            logger.warning(f"No torrents found for: {item.title}")
            item.state = MediaState.FAILED
            item.last_error = "No torrents found"
            await session.commit()
            return MediaState.FAILED
        
        logger.info(f"Found {len(torrents)} torrents for {item.title}")
        
        # Check cache status
        info_hashes = [t.info_hash for t in torrents]
        cache_status = await downloader.check_cache_all(info_hashes)
        
        # Rank and select best torrent
        if item.is_anime:
            best = quality_ranker.get_best_for_anime(torrents, cache_status)
        else:
            best = quality_ranker.get_best_for_movie_or_show(torrents, cache_status)
        
        if best:
            # Store selected torrent info on item (simplified - in real impl would use TorrentInfo model)
            item.file_path = best.info_hash  # Temporarily store hash here
            providers = cache_status.get(best.info_hash.lower(), [])
            is_cached = len(providers) > 0
            
            logger.info(f"Selected: {best.title[:50]}... (cached: {is_cached})")
            
            item.state = MediaState.SCRAPED
            await session.commit()
            return MediaState.SCRAPED
        
        item.state = MediaState.FAILED
        item.last_error = "No suitable torrent found"
        await session.commit()
        return MediaState.FAILED
    
    async def _download_item(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Add torrent to debrid service"""
        logger.info(f"Downloading: {item.title}")
        
        info_hash = item.file_path  # Retrieved from scrape step
        if not info_hash:
            item.state = MediaState.FAILED
            item.last_error = "No torrent hash available"
            await session.commit()
            return MediaState.FAILED
        
        # Add to debrid
        provider, debrid_id = await downloader.add_torrent(info_hash)
        
        if provider and debrid_id:
            logger.info(f"Added to {provider}: {debrid_id}")
            item.state = MediaState.DOWNLOADED
            await session.commit()
            return MediaState.DOWNLOADED
        
        item.state = MediaState.FAILED
        item.last_error = "Failed to add to any debrid provider"
        await session.commit()
        return MediaState.FAILED
    
    async def _check_download(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Check download progress (for non-cached torrents)"""
        # For cached torrents, this is usually instant
        # For now, just transition to DOWNLOADED
        item.state = MediaState.DOWNLOADED
        await session.commit()
        return MediaState.DOWNLOADED
    
    async def _create_symlink(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Create symlink to media file"""
        logger.info(f"Creating symlink: {item.title}")
        
        info_hash = item.file_path
        if not info_hash:
            item.state = MediaState.FAILED
            item.last_error = "No info hash for symlink"
            await session.commit()
            return MediaState.FAILED
        
        # Find file in mount (try by hash first, then title)
        source_path = symlink_service.find_by_infohash(info_hash, title=item.title)
        
        if not source_path:
            logger.warning(f"File not found in mount for: {item.title}")
            # File might not be ready yet - retry later
            item.retry_count += 1
            if item.retry_count >= 5:
                item.state = MediaState.FAILED
                item.last_error = "File not found in mount after retries"
            await session.commit()
            return item.state
        
        # Create symlink
        success, symlink_path = symlink_service.create_symlink(item, source_path)
        
        if success and symlink_path:
            item.file_path = str(source_path)
            item.symlink_path = str(symlink_path)
            item.state = MediaState.SYMLINKED
            await session.commit()
            return MediaState.SYMLINKED
        
        item.state = MediaState.FAILED
        item.last_error = "Failed to create symlink"
        await session.commit()
        return MediaState.FAILED
    
    async def _complete_item(self, item: MediaItem, session: AsyncSession) -> MediaState:
        """Mark as complete and trigger Plex refresh"""
        logger.info(f"Completing: {item.title}")
        
        # Trigger Plex library refresh
        if plex_service.token:
            await plex_service.refresh_library()
        
        item.state = MediaState.COMPLETED
        item.completed_at = datetime.utcnow()
        await session.commit()
        
        logger.success(f"✅ Completed: {item.title}")
        return MediaState.COMPLETED


# Singleton instance
state_machine = StateMachine()
