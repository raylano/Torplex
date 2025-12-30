"""
Downloaders Package
Orchestrates Real-Debrid and Torbox for cache checking and downloads
"""
from typing import List, Dict, Optional, Tuple
from loguru import logger
import asyncio

from src.services.downloaders.realdebrid import real_debrid_service, RealDebridService
from src.services.downloaders.torbox import torbox_service, TorboxService
from src.services.scrapers.torrentio import TorrentResult


class DownloaderOrchestrator:
    """
    Orchestrates multiple debrid services.
    Priority: Real-Debrid -> Torbox
    Uses direct add-and-check for Real-Debrid (instant availability endpoint is disabled).
    """
    
    def __init__(self):
        self.real_debrid = real_debrid_service
        self.torbox = torbox_service
    
    @property
    def available_providers(self) -> List[str]:
        """List of configured providers"""
        providers = []
        if self.real_debrid.is_configured:
            providers.append("real_debrid")
        if self.torbox.is_configured:
            providers.append("torbox")
        return providers
    
    async def check_cache_all(self, info_hashes: List[str]) -> Dict[str, List[str]]:
        """
        Check cache status on available providers.
        For Real-Debrid: Uses add-and-check method (instant availability endpoint disabled).
        For Torbox: Uses instant availability endpoint.
        Returns dict mapping info_hash -> list of providers where it's cached
        """
        if not info_hashes:
            return {}
        
        results: Dict[str, List[str]] = {h.lower(): [] for h in info_hashes}
        
        # Check Torbox instant availability (if configured)
        if self.torbox.is_configured:
            try:
                torbox_results = await self.torbox.check_instant_availability(info_hashes)
                for info_hash, is_cached in torbox_results.items():
                    if is_cached:
                        results[info_hash.lower()].append("torbox")
            except Exception as e:
                logger.error(f"Torbox cache check failed: {e}")
        
        # For Real-Debrid, we'll check via add-and-check when actually selecting torrents
        # This is because RD's instant availability endpoint is disabled
        # We mark them as potentially cached and verify during selection
        if self.real_debrid.is_configured:
            # OPTIMISTIC: Mark all hashes as available on Real-Debrid.
            # Rationale: User prefers RD (unlimited slots) over Torbox (limit 10).
            # Even if not cached, we want to try RD first.
            for h in info_hashes:
                results[h.lower()].append("real_debrid")
            logger.debug(f"Marked {len(info_hashes)} hashes as potentially available on Real-Debrid")
        
        # Log summary
        cached_on_torbox = sum(1 for v in results.values() if "torbox" in v)
        if cached_on_torbox > 0:
            logger.info(f"Cache check: {cached_on_torbox}/{len(info_hashes)} cached on Torbox")
        
        return results
    
    async def check_instant_via_add(self, info_hash: str) -> Optional[Dict]:
        """
        Riven-style instant availability check:
        1. Add torrent to RD
        2. Select video files
        3. Check if status is 'downloaded'
        
        Returns dict with torrent info if cached, None otherwise.
        """
        if not self.real_debrid.is_configured:
            return None
        
        torrent_id = None
        try:
            torrent_id = await self.real_debrid.add_magnet(info_hash)
            if not torrent_id:
                return None
            
            info = await self.real_debrid.get_torrent_info(torrent_id)
            if not info:
                if torrent_id:
                    await self.real_debrid.delete_torrent(torrent_id)
                return None
            
            # If waiting for file selection, select video files
            if info.get("status") == "waiting_files_selection":
                video_exts = ('.mkv', '.mp4', '.avi', '.mov', '.m4v')
                video_ids = [
                    str(f["id"]) for f in info.get("files", [])
                    if f.get("path", "").lower().endswith(video_exts)
                ]
                
                if not video_ids:
                    await self.real_debrid.delete_torrent(torrent_id)
                    return None
                
                await self.real_debrid.select_files(torrent_id, ",".join(video_ids))
                info = await self.real_debrid.get_torrent_info(torrent_id)
            
            # Check if instantly available
            if info.get("status") == "downloaded":
                logger.info(f"✅ Cached! {info.get('filename', '')[:40]}...")
                return {
                    "cached": True,
                    "torrent_id": torrent_id,
                    "filename": info.get("filename"),
                    "files": info.get("files", []),
                    "links": info.get("links", []),
                }
            
            # Not cached - delete torrent
            logger.debug(f"Not cached (status={info.get('status')}), deleting torrent")
            await self.real_debrid.delete_torrent(torrent_id)
            return None
            
        except Exception as e:
            logger.error(f"Instant check failed for {info_hash[:8]}: {e}")
            if torrent_id:
                try:
                    await self.real_debrid.delete_torrent(torrent_id)
                except:
                    pass
            return None
    
    async def add_torrent(
        self,
        info_hash: Optional[str],
        preferred_provider: Optional[str] = None,
        download_url: Optional[str] = None,
        is_usenet: bool = False
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Add media (torrent or usenet) to a debrid service.
        Returns (provider_name, debrid_id) or (None, None) on failure.
        
        Priority:
        1. Preferred provider if specified and configured
        2. Real-Debrid (Torrents only)
        3. Torbox (Torrents + Usenet)
        """
        providers_to_try = []
        
        # Determine valid providers based on type
        valid_providers = []
        if not is_usenet:
             if self.real_debrid.is_configured: valid_providers.append("real_debrid")
             if self.torbox.is_configured: valid_providers.append("torbox")
        else:
             # Usenet only supported by Torbox currently
             if self.torbox.is_configured: valid_providers.append("torbox")
        
        # Build priority list
        if preferred_provider and preferred_provider in valid_providers:
            providers_to_try.append(preferred_provider)
        
        for p in valid_providers:
            if p not in providers_to_try:
                providers_to_try.append(p)
        
        for provider_name in providers_to_try:
            try:
                if provider_name == "real_debrid" and not is_usenet and info_hash:
                    # Add magnet
                    torrent_id = await self.real_debrid.add_magnet(info_hash)
                    if torrent_id:
                        # Select all files so download starts automatically
                        await self.real_debrid.select_files(torrent_id, "all")
                        logger.info(f"Added torrent {info_hash[:8]}... to {provider_name} (files selected)")
                        return provider_name, str(torrent_id)
                        
                elif provider_name == "torbox":
                    result = None
                    if is_usenet and download_url:
                        result = await self.torbox.add_usenet(download_url)
                    elif info_hash:
                        result = await self.torbox.add_magnet(info_hash)
                    
                    if result:
                        type_label = "Usenet" if is_usenet else "Torrent"
                        identifier = download_url[:30] if is_usenet else info_hash[:8]
                        logger.info(f"Added {type_label} {identifier}... to {provider_name}")
                        return provider_name, str(result)
                        
            except Exception as e:
                logger.error(f"Failed to add item to {provider_name}: {e}")
                continue
        
        logger.error(f"Failed to add item to any provider")
        return None, None

    
    async def get_best_cached_torrent(
        self,
        torrents: List[TorrentResult],
        is_anime: bool = False
    ) -> Tuple[Optional[TorrentResult], Optional[str]]:
        """
        Find the best cached torrent from a list.
        Returns (best_torrent, provider) or (None, None) if none cached.
        
        Anime priority:
        1. Cached + Dual-Audio
        2. Cached + Dubbed
        3. Cached (any)
        
        Non-anime priority:
        1. Cached + Best quality
        """
        if not torrents:
            return None, None
        
        # Get cache status for all
        info_hashes = [t.info_hash for t in torrents if t.info_hash]
        cache_results = await self.check_cache_all(info_hashes)
        
        # Filter to only cached torrents OR Usenet items (assumed available)
        cached_torrents = []
        for t in torrents:
            # Usenet is always considered "cached"/available
            if t.is_usenet:
                cached_torrents.append((t, ["torbox"]))
                continue
            
            # Check torrent cache
            if t.info_hash and cache_results.get(t.info_hash.lower()):
                 cached_torrents.append((t, cache_results.get(t.info_hash.lower(), [])))
        
        if not cached_torrents:
            return None, None
        
        # Sort by quality
        def sort_key(item):
            torrent, providers = item
            score = 0
            
            # Anime-specific scoring
            if is_anime:
                if torrent.is_dual_audio:
                    score += 1000
                if torrent.is_dubbed:
                    score += 500
            
            # Quality scoring
            quality_scores = {
                "2160p": 400, "4K": 400, "UHD": 400,
                "1080p": 300,
                "720p": 200,
                "480p": 100,
            }
            score += quality_scores.get(torrent.resolution or "", 0)
            
            # Codec scoring
            if torrent.codec and "x265" in torrent.codec.lower():
                score += 50
            if torrent.codec and "hevc" in torrent.codec.lower():
                score += 50
            
            # Prefer Real-Debrid
            if "real_debrid" in providers:
                score += 10
            
            return score
        
        cached_torrents.sort(key=sort_key, reverse=True)
        best_torrent, providers = cached_torrents[0]
        
        # Prefer Real-Debrid if available
        best_provider = "real_debrid" if "real_debrid" in providers else providers[0]
        
        logger.info(f"Best cached torrent: {best_torrent.title[:50]}... on {best_provider}")
        return best_torrent, best_provider


# Singleton instance
downloader = DownloaderOrchestrator()


__all__ = [
    "real_debrid_service",
    "RealDebridService",
    "torbox_service",
    "TorboxService",
    "downloader",
    "DownloaderOrchestrator",
]
