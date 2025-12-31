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
    
    # Maximum retries before marking episode as FAILED
    MAX_SYMLINK_RETRIES = 5
    
    def __init__(self):
        # Track symlink retry attempts per episode (in-memory, resets on restart)
        self._symlink_retries: dict[str, int] = {}
        # Track failed download URLs/hashes to prevent retry loops
        self._failed_downloads: set[str] = set()
    
    # ... (skipping create_episodes_for_show and process_episode methods which are unchanged)
    
    async def process_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        # ... (same as original until _scrape_episode)
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
            await session.rollback()
            try:
                episode = await session.get(Episode, episode.id)
                if episode:
                    episode.state = MediaState.FAILED
                    await session.commit()
            except Exception as db_err:
                logger.error(f"Failed to save error state: {db_err}")
                await session.rollback()
            return MediaState.FAILED

    async def _scrape_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        # ... (start of method unchanged)
        logger.info(f"Scraping: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        if not show.imdb_id:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        # ... (formatting/absolute logic unchanged)
        if show.is_anime and not episode.absolute_episode_number and show.tmdb_id:
            try:
                from src.services.content.tmdb import tmdb_service
                abs_map = await tmdb_service.get_show_absolute_map(show.tmdb_id)
                if abs_map:
                    key = (episode.season_number, episode.episode_number)
                    if key in abs_map:
                        episode.absolute_episode_number = abs_map[key]
                        logger.info(f"Set Absolute Number {episode.absolute_episode_number} for {show.title} S{episode.season_number}E{episode.episode_number}")
                        await session.commit()
            except Exception as e:
                logger.warning(f"Failed to fetch absolute number: {e}")

        # Call scraper
        torrents = await scrape_episode_all(
            show.imdb_id,
            episode.season_number,
            episode.episode_number,
            title=show.title,
            absolute_episode_number=episode.absolute_episode_number
        )
        
        if not torrents:
            logger.warning(f"No torrents found for {show.title} S{episode.season_number}E{episode.episode_number}")
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        # FILTER BLACKLISTED ITEMS
        original_count = len(torrents)
        torrents = [t for t in torrents if t.download_url not in self._failed_downloads and (not t.info_hash or t.info_hash not in self._failed_downloads)]
        if len(torrents) < original_count:
            logger.info(f"Filtered {original_count - len(torrents)} blacklisted releases")
            
        if not torrents:
            logger.warning(f"All torrents blacklisted for {show.title} S{episode.season_number}E{episode.episode_number}")
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED

        logger.info(f"Found {len(torrents)} torrents for S{episode.season_number}E{episode.episode_number}")
        
        # ... (rest of method unchanged logic until return)
        # Check cache status
        info_hashes = [t.info_hash for t in torrents if t.info_hash]
        cache_status = await downloader.check_cache_all(info_hashes)
        
        if show.is_anime:
            ranked = quality_ranker.rank_torrents(torrents, is_anime=True, cached_providers=cache_status, dubbed_only=True)
        else:
            ranked = quality_ranker.rank_torrents(torrents, is_anime=False, cached_providers=cache_status)
        
        if not ranked:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        best = None
        is_cached = False
        
        for t in ranked[:5]:
            if t.is_usenet:
                best = t
                is_cached = True
                break
            if t.info_hash and cache_status.get(t.info_hash.lower()):
                best = t
                is_cached = True
                break
        
        if not best:
            for t in ranked[:5]:
                if not t.info_hash: continue
                rd_result = await downloader.check_instant_via_add(t.info_hash)
                if rd_result and rd_result.get("cached"):
                    best = t
                    is_cached = True
                    logger.info(f"✅ Found cached on RD: {t.title[:40]}...")
                    break
        
        if not best:
            best = ranked[0]
            logger.debug(f"No cached, taking best quality: {best.title[:40]}...")
        
        if best:
            if best.is_usenet:
                episode.file_path = f"usenet:{best.download_url}"
                logger.info(f"Selected Usenet: {best.title[:40]}...")
            else:
                episode.file_path = best.info_hash
                logger.info(f"Selected{'✓ CACHED' if is_cached else ''}: {best.title[:40]}...")
            
            episode.state = MediaState.SCRAPED
            await session.commit()
            return MediaState.SCRAPED
        
        episode.state = MediaState.FAILED
        await session.commit()
        return MediaState.FAILED

    async def _download_episode(self, episode: Episode, show: MediaItem, session: AsyncSession) -> MediaState:
        """Add episode torrent or usenet item to debrid"""
        logger.info(f"Downloading: {show.title} S{episode.season_number:02d}E{episode.episode_number:02d}")
        
        file_path_or_hash = episode.file_path
        if not file_path_or_hash:
            episode.state = MediaState.FAILED
            await session.commit()
            return MediaState.FAILED
        
        is_usenet = False
        info_hash = file_path_or_hash
        download_url = None
        
        if file_path_or_hash.startswith("usenet:"):
            is_usenet = True
            download_url = file_path_or_hash.split("usenet:", 1)[1]
            info_hash = None
            logger.info(f"Adding Usenet item: {download_url[:30]}...")

        # If standard torrent, try Riven-style instant check first
        if not is_usenet:
            existing_active = await session.execute(
                select(Episode).where(
                    Episode.show_id == show.id,
                    Episode.file_path == info_hash,
                    Episode.state.in_([MediaState.DOWNLOADED, MediaState.SYMLINKED, MediaState.COMPLETED]),
                    Episode.id != episode.id
                ).limit(1)
            )
            existing_ep = existing_active.scalars().first()
            
            if existing_ep and existing_ep.torrent_name:
                episode.torrent_name = existing_ep.torrent_name
                episode.state = MediaState.DOWNLOADED
                await session.commit()
                logger.info(f"♻️ Reusing active torrent from S{existing_ep.season_number}E{existing_ep.episode_number}: {episode.torrent_name[:40]}...")
                return MediaState.DOWNLOADED

            instant = await downloader.check_instant_via_add(info_hash)
            
            if instant and instant.get("cached"):
                episode.torrent_name = instant.get("filename")
                episode.state = MediaState.DOWNLOADED
                await session.commit()
                logger.info(f"✅ Cached! Torrent: {episode.torrent_name[:40] if episode.torrent_name else 'N/A'}...")
                return MediaState.DOWNLOADED
        
        # Add to debrid (Torbox or standard RD add)
        # WRAPPED IN TRY/CATCH FOR BLACKLISTING
        try:
            download_name = f"{show.title} S{episode.season_number:02d}E{episode.episode_number:02d}"
            
            provider, debrid_id = await downloader.add_torrent(
                info_hash, 
                download_url=download_url,
                is_usenet=is_usenet,
                name=download_name
            )
            
            if provider and debrid_id:
                episode.state = MediaState.DOWNLOADED
                await session.commit()
                logger.info(f"Added to {provider} (not cached, waiting): {debrid_id}")
                return MediaState.DOWNLOADED
                
        except Exception as e:
            logger.error(f"❌ Download failed: {e}")
            
            # BLACKLIST THIS ITEM
            bad_item = download_url if is_usenet else info_hash
            if bad_item:
                self._failed_downloads.add(bad_item)
                logger.warning(f"🚫 Blacklisted item (will retry with different release): {bad_item[:50]}...")
            
            # RESET TO REQUESTED TO TRIGGER NEW SCRAPE (and pick next best)
            episode.state = MediaState.REQUESTED
            episode.file_path = None
            await session.commit()
            return MediaState.REQUESTED
        
        episode.state = MediaState.FAILED
        await session.commit()
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
                # File exists! 
                
                # ANIME UPGRADE LOGIC:
                # If it's Anime, user prefers Dual/Dubbed. 
                # If existing file doesn't explicitly say "Dub" or "Dual", ignore it so we scrape a better one.
                is_dubbed_file = False
                if show.is_anime:
                    import re
                    # Simple regex for dubbed/dual audio indicators
                    # Added 'eng' to catch "ENG JAP" releases, using boundaries to avoid partial matches
                    if re.search(r'\b(dub|dual|multi|english|eng)\b', existing_file.name, re.IGNORECASE):
                        is_dubbed_file = True
                    
                    if not is_dubbed_file:
                        logger.info(f"Ignoring existing file for {show.title} S{season}E{episode_num}: Not Dubbed/Dual ({existing_file.name})")
                        # Skip strictly - this forces scraping
                        # We treat it as if file doesn't exist
                        existing_file = None
                
                if existing_file:
                    # Create as DOWNLOADED (ready for symlink!)
                    # Extract the parent folder name as "torrent_name" so symlink step can find it
                    parent_folder = existing_file.parent.name if existing_file.parent else existing_file.name
                    episode = Episode(
                        show_id=show.id,
                        season_number=season,
                        episode_number=episode_num,
                        title=ep_data.get("title"),
                        overview=ep_data.get("overview"),
                        air_date=ep_data.get("air_date"),
                        state=MediaState.DOWNLOADED,  # Ready for symlink!
                        file_path=str(existing_file),
                        torrent_name=parent_folder,  # Store folder name for symlink lookup
                    )
                    pre_filled += 1
            
            if not existing_file:
                # File doesn't exist OR was rejected (re-scrape needed)
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
