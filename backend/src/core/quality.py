"""
Quality Ranking System
Ranks torrents based on quality, codec, and anime-specific criteria
"""
import re
from typing import List, Optional
from dataclasses import dataclass
from loguru import logger

from src.services.scrapers.torrentio import TorrentResult


@dataclass
class QualityScore:
    """Quality scoring breakdown"""
    resolution_score: int = 0
    quality_score: int = 0
    codec_score: int = 0
    audio_score: int = 0
    size_score: int = 0
    seeders_score: int = 0
    total: int = 0


class QualityRanker:
    """Ranks torrents by quality with anime-specific preferences"""
    
    # Resolution scores (higher = better)
    RESOLUTION_SCORES = {
        "2160p": 400, "4K": 400, "UHD": 400,
        "1080p": 300,
        "720p": 200,
        "480p": 100,
    }
    
    # Quality/source scores
    QUALITY_SCORES = {
        "REMUX": 500,
        "BluRay": 400, "BDRip": 350,
        "WEB-DL": 300, "WEBDL": 300,
        "WEBRip": 250,
        "HDTV": 200,
        "HDRip": 150,
        "DVDRip": 100,
        "CAM": 10, "TS": 20, "TC": 30,
    }
    
    # Codec scores
    CODEC_SCORES = {
        "x265": 100, "HEVC": 100, "H.265": 100, "H265": 100,
        "AV1": 90,
        "x264": 50, "H.264": 50, "H264": 50,
        "VP9": 40,
    }
    
    # Audio scores
    AUDIO_PATTERNS = [
        (r"Atmos", 100),
        (r"DTS-HD\s*MA", 90),
        (r"TrueHD", 85),
        (r"DTS-HD", 80),
        (r"DTS", 70),
        (r"DD\+|DDP|E-?AC-?3", 60),  # Dolby Digital Plus
        (r"AC-?3|DD", 50),
        (r"AAC", 40),
        (r"MP3", 20),
    ]
    
    # Anime-specific patterns worth bonus points (higher = more preferred)
    ANIME_BONUSES = {
        "dual_audio": 2000,     # Dual audio = best (English + Japanese)
        "english_audio": 1500,  # Explicitly English dubbed
        "dubbed": 1000,         # Generic "dubbed" marker
        "subbed": 100,          # Subbed only (least preferred)
    }
    
    # Preferred release groups for anime
    PREFERRED_ANIME_GROUPS = [
        "SubsPlease", "Erai-raws", "ASW", "Judas", "Ember",
        "Anime Time", "Anime Land", "HorribleSubs",
    ]
    
    
    def rank_torrents(
        self,
        torrents: List[TorrentResult],
        is_anime: bool = False,
        cached_providers: Optional[dict] = None,
        dubbed_only: bool = False
    ) -> List[TorrentResult]:
        """
        Rank torrents by quality score.
        
        Args:
            torrents: List of torrent results
            is_anime: Whether content is anime (enables dual-audio preference)
            cached_providers: Dict mapping info_hash -> list of providers where cached
            dubbed_only: If True, severely penalize non-dubbed content (Anime only)
        
        Returns:
            Sorted list of torrents (best first)
        """
        cached_providers = cached_providers or {}
        
        scored_torrents = []
        for torrent in torrents:
            score = self.calculate_score(torrent, is_anime, cached_providers, dubbed_only)
            scored_torrents.append((torrent, score))
        
        # Sort by total score, descending
        scored_torrents.sort(key=lambda x: x[1].total, reverse=True)
        
        return [t[0] for t in scored_torrents]
    
    def calculate_score(
        self,
        torrent: TorrentResult,
        is_anime: bool = False,
        cached_providers: Optional[dict] = None,
        dubbed_only: bool = False
    ) -> QualityScore:
        """Calculate quality score for a single torrent"""
        cached_providers = cached_providers or {}
        
        score = QualityScore()
        
        # Resolution score
        if torrent.resolution:
            score.resolution_score = self.RESOLUTION_SCORES.get(torrent.resolution, 0)
        
        # Quality/source score
        if torrent.quality:
            for quality, points in self.QUALITY_SCORES.items():
                if quality.lower() in torrent.quality.lower():
                    score.quality_score = points
                    break
        
        # Codec score
        if torrent.codec:
            for codec, points in self.CODEC_SCORES.items():
                if codec.lower() in torrent.codec.lower():
                    score.codec_score = points
                    break
        
        # Audio score (search in title)
        for pattern, points in self.AUDIO_PATTERNS:
            if re.search(pattern, torrent.title, re.IGNORECASE):
                score.audio_score = points
                break
        
        # Size score (prefer reasonable sizes, not too small)
        if torrent.size_bytes:
            size_gb = torrent.size_bytes / (1024 ** 3)
            if size_gb >= 1 and size_gb <= 30:
                score.size_score = 50
            elif size_gb > 30:
                score.size_score = 30  # Still good, but large
            else:
                score.size_score = 10  # Suspiciously small
        
        # Seeders score
        # Seeders score - significant boost to prefer healthy torrents
        # Only relevant if NOT cached or Usenet (cached/usenet are instant)
        start_penalty = -500 if (not is_cached and not torrent.is_usenet) else 0
        
        if torrent.seeders is not None:
            if torrent.seeders >= 100:
                score.seeders_score = 200
            elif torrent.seeders >= 50:
                score.seeders_score = 150
            elif torrent.seeders >= 20:
                score.seeders_score = 100
            elif torrent.seeders >= 5:
                score.seeders_score = 50
            elif torrent.seeders > 0:
                # 1-4 seeders: No bonus, but apply penalty if not cached
                if not is_cached and not torrent.is_usenet:
                    score.seeders_score = -500 # Discourage dead torrents
            else:
                score.seeders_score = -1000 # 0 seeders is very bad
        elif not is_cached and not torrent.is_usenet:
             # Unknown seeds on uncached torrent -> assume bad
             score.seeders_score = -500
        
        # Calculate base total
        score.total = (
            score.resolution_score +
            score.quality_score +
            score.codec_score +
            score.audio_score +
            score.size_score +
            score.seeders_score
        )
        
        # Penalty for non-English releases (ITA, FRA, GER etc without ENG)
        title_lower = torrent.title.lower()
        has_foreign_only = any(lang in title_lower for lang in ['ita', 'italian', 'fra', 'french', 'ger', 'german', 'spa', 'spanish'])
        has_english = any(eng in title_lower for eng in ['eng', 'english', 'multi'])
        if has_foreign_only and not has_english:
            score.total -= 500  # Penalize foreign-only releases
        
        # Anime bonuses - strongly prefer English audio
        if is_anime:
            is_dubbed_or_dual = False
            
            if torrent.is_dual_audio:
                score.total += self.ANIME_BONUSES["dual_audio"]
                is_dubbed_or_dual = True
            elif torrent.is_dubbed:
                score.total += self.ANIME_BONUSES["dubbed"]
                is_dubbed_or_dual = True
            else:
                # Check for explicit English audio markers in title
                english_markers = ['english dub', 'eng dub', 'english audio', 'english dubbed', 
                                   'dub[', 'dubbed', 'english]', '[eng]', '(eng)', 'english.dub']
                if any(marker in title_lower for marker in english_markers):
                    score.total += self.ANIME_BONUSES["english_audio"]
                    is_dubbed_or_dual = True
            
            # Penalty for Japanese-only releases when user prefers English
            japanese_only_markers = ['raw', 'japanese only', 'jap only', 'no subs', 'raws', '[raw]']
            if any(marker in title_lower for marker in japanese_only_markers):
                score.total -= 800  # Strong penalty for raw/Japanese-only
            
            # Prefer known good anime groups
            if torrent.release_group:
                for group in self.PREFERRED_ANIME_GROUPS:
                    if group.lower() in torrent.release_group.lower():
                        score.total += 200
                        break
            
            # DUBBED ONLY LOGIC
            if dubbed_only:
                if is_dubbed_or_dual:
                    score.total += 5000  # Massive boost for dubbed content
                else:
                    score.total -= 10000 # Massive penalty for subbed/raw content
                    
        
        # Cache bonus (massive - always prefer cached)
        if torrent.info_hash:
            info_hash = torrent.info_hash.lower()
            if info_hash in cached_providers and cached_providers[info_hash]:
                score.total += 10000  # Cached is always better
                
                # Slight preference for Real-Debrid if both cached
                if "real_debrid" in cached_providers[info_hash]:
                    score.total += 10
        elif torrent.is_usenet:
            # Usenet is effectively "cached" (available immediately)
            # Give it a high score so it competes with cached torrents
            score.total += 10000
        
        return score
    
    def get_best_for_anime(
        self,
        torrents: List[TorrentResult],
        cached_providers: Optional[dict] = None,
        dubbed_only: bool = False
    ) -> Optional[TorrentResult]:
        """
        Get best torrent for anime with priority:
        1. Cached + Dual-Audio
        2. Cached + Dubbed
        3. Dual-Audio (non-cached)
        4. Dubbed (non-cached)
        5. Cached (any)
        6. Best quality (non-cached)
        """
        ranked = self.rank_torrents(
            torrents, 
            is_anime=True, 
            cached_providers=cached_providers,
            dubbed_only=dubbed_only
        )
        return ranked[0] if ranked else None
    
    def get_best_for_movie_or_show(
        self,
        torrents: List[TorrentResult],
        cached_providers: Optional[dict] = None
    ) -> Optional[TorrentResult]:
        """Get best torrent for non-anime content (cache + quality priority)"""
        ranked = self.rank_torrents(torrents, is_anime=False, cached_providers=cached_providers)
        return ranked[0] if ranked else None


# Singleton instance
quality_ranker = QualityRanker()
