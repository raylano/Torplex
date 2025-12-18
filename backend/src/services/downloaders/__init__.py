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
        Check cache status on all available providers.
        Returns dict mapping info_hash -> list of providers where it's cached
        """
        if not info_hashes:
            return {}
        
        results: Dict[str, List[str]] = {h.lower(): [] for h in info_hashes}
        
        # Check providers in parallel
        tasks = []
        
        if self.real_debrid.is_configured:
            tasks.append(("real_debrid", self.real_debrid.check_instant_availability(info_hashes)))
        
        if self.torbox.is_configured:
            tasks.append(("torbox", self.torbox.check_instant_availability(info_hashes)))
        
        if not tasks:
            logger.warning("No debrid providers configured")
            return results
        
        # Run all checks in parallel
        provider_results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        
        for i, (provider_name, _) in enumerate(tasks):
            result = provider_results[i]
            if isinstance(result, Exception):
                logger.error(f"Cache check failed for {provider_name}: {result}")
                continue
            
            for info_hash, is_cached in result.items():
                if is_cached:
                    results[info_hash.lower()].append(provider_name)
        
        # Log summary
        cached_on_any = sum(1 for v in results.values() if v)
        logger.info(f"Cache check: {cached_on_any}/{len(info_hashes)} cached on at least one provider")
        
        return results
    
    async def add_torrent(
        self,
        info_hash: str,
        preferred_provider: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Add torrent to a debrid service.
        Returns (provider_name, debrid_id) or (None, None) on failure.
        
        Priority:
        1. Preferred provider if specified and configured
        2. Real-Debrid
        3. Torbox
        """
        providers_to_try = []
        
        if preferred_provider:
            if preferred_provider == "real_debrid" and self.real_debrid.is_configured:
                providers_to_try.append("real_debrid")
            elif preferred_provider == "torbox" and self.torbox.is_configured:
                providers_to_try.append("torbox")
        
        # Add remaining providers as fallback
        if self.real_debrid.is_configured and "real_debrid" not in providers_to_try:
            providers_to_try.append("real_debrid")
        if self.torbox.is_configured and "torbox" not in providers_to_try:
            providers_to_try.append("torbox")
        
        for provider_name in providers_to_try:
            try:
                if provider_name == "real_debrid":
                    # Add magnet
                    torrent_id = await self.real_debrid.add_magnet(info_hash)
                    if torrent_id:
                        # Select all files so download starts automatically
                        await self.real_debrid.select_files(torrent_id, "all")
                        logger.info(f"Added torrent {info_hash[:8]}... to {provider_name} (files selected)")
                        return provider_name, str(torrent_id)
                        
                elif provider_name == "torbox":
                    result = await self.torbox.add_magnet(info_hash)
                    if result:
                        logger.info(f"Added torrent {info_hash[:8]}... to {provider_name}")
                        return provider_name, str(result)
                        
            except Exception as e:
                logger.error(f"Failed to add torrent to {provider_name}: {e}")
                continue
        
        logger.error(f"Failed to add torrent {info_hash[:8]}... to any provider")
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
        info_hashes = [t.info_hash for t in torrents]
        cache_results = await self.check_cache_all(info_hashes)
        
        # Filter to only cached torrents
        cached_torrents = [
            (t, cache_results.get(t.info_hash.lower(), []))
            for t in torrents
            if cache_results.get(t.info_hash.lower())
        ]
        
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
