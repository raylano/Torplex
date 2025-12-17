"""
RTN (Rank Torrent Name) Wrapper
Provides intelligent torrent parsing, validation, and ranking.
"""
import re
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum

try:
    from RTN import RTN, Torrent, DefaultRanking
    from RTN.models import ParsedData
    RTN_AVAILABLE = True
except ImportError:
    RTN_AVAILABLE = False
    print("[RTN] rank-torrent-name not installed, using fallback parser")


class Quality(Enum):
    UHD_4K = "4k"
    FHD_1080P = "1080p"
    HD_720P = "720p"
    SD = "sd"
    UNKNOWN = "unknown"


@dataclass
class ParsedTorrent:
    """Parsed torrent information."""
    raw_title: str
    info_hash: str
    quality: Quality = Quality.UNKNOWN
    resolution: str = ""
    source: str = ""  # bluray, webrip, etc.
    codec: str = ""  # x264, x265, hevc
    year: Optional[int] = None
    seasons: List[int] = None
    episodes: List[int] = None
    is_pack: bool = False
    rank: int = 0
    
    def __post_init__(self):
        if self.seasons is None:
            self.seasons = []
        if self.episodes is None:
            self.episodes = []


class TorrentParser:
    """
    Intelligent torrent parser using RTN library with fallback.
    Handles quality detection, season/episode extraction, and ranking.
    """
    
    def __init__(self, quality_profile: str = "hd", allow_4k: bool = False):
        self.quality_profile = quality_profile
        self.allow_4k = allow_4k
        
        if RTN_AVAILABLE:
            # Configure RTN with quality preferences
            self.rtn = RTN(
                settings={
                    "require": [],
                    "exclude": [],
                    "preferred": ["bluray", "remux"] if quality_profile == "uhd" else ["bluray", "web-dl"],
                },
                ranking_model=DefaultRanking()
            )
        else:
            self.rtn = None
    
    def parse(self, raw_title: str, info_hash: str) -> ParsedTorrent:
        """Parse a torrent title and extract metadata."""
        
        if self.rtn and RTN_AVAILABLE:
            return self._parse_with_rtn(raw_title, info_hash)
        else:
            return self._parse_fallback(raw_title, info_hash)
    
    def _parse_with_rtn(self, raw_title: str, info_hash: str) -> ParsedTorrent:
        """Parse using RTN library."""
        try:
            torrent = self.rtn.rank(
                raw_title=raw_title,
                infohash=info_hash,
                correct_title="",  # We'll validate separately
                remove_trash=True
            )
            
            data = torrent.data
            
            # Determine quality
            quality = Quality.UNKNOWN
            if data.resolution:
                if "2160" in str(data.resolution) or "4k" in str(data.resolution).lower():
                    quality = Quality.UHD_4K
                elif "1080" in str(data.resolution):
                    quality = Quality.FHD_1080P
                elif "720" in str(data.resolution):
                    quality = Quality.HD_720P
                else:
                    quality = Quality.SD
            
            return ParsedTorrent(
                raw_title=raw_title,
                info_hash=info_hash.lower(),
                quality=quality,
                resolution=str(data.resolution) if data.resolution else "",
                source=data.source if hasattr(data, 'source') and data.source else "",
                codec=data.codec if hasattr(data, 'codec') and data.codec else "",
                year=data.year if hasattr(data, 'year') else None,
                seasons=list(data.seasons) if data.seasons else [],
                episodes=list(data.episodes) if data.episodes else [],
                is_pack=len(data.seasons) > 1 or len(data.episodes) > 1,
                rank=torrent.rank if hasattr(torrent, 'rank') else 0
            )
        except Exception as e:
            print(f"[RTN] Parse error: {e}, using fallback")
            return self._parse_fallback(raw_title, info_hash)
    
    def _parse_fallback(self, raw_title: str, info_hash: str) -> ParsedTorrent:
        """Fallback parser when RTN is not available."""
        title_lower = raw_title.lower()
        
        # Quality detection
        quality = Quality.UNKNOWN
        resolution = ""
        if "2160p" in title_lower or "4k" in title_lower or "uhd" in title_lower:
            quality = Quality.UHD_4K
            resolution = "2160p"
        elif "1080p" in title_lower:
            quality = Quality.FHD_1080P
            resolution = "1080p"
        elif "720p" in title_lower:
            quality = Quality.HD_720P
            resolution = "720p"
        elif "480p" in title_lower or "sd" in title_lower:
            quality = Quality.SD
            resolution = "480p"
        
        # Source detection
        source = ""
        for s in ["bluray", "blu-ray", "bdrip", "brrip", "remux"]:
            if s in title_lower:
                source = "bluray"
                break
        for s in ["webrip", "web-dl", "webdl", "web"]:
            if s in title_lower:
                source = "web"
                break
        
        # Season/Episode detection
        seasons = []
        episodes = []
        
        # S01E01 pattern
        se_match = re.findall(r's(\d+)e(\d+)', title_lower)
        for s, e in se_match:
            if int(s) not in seasons:
                seasons.append(int(s))
            if int(e) not in episodes:
                episodes.append(int(e))
        
        # Season only pattern (S01, Season 1)
        s_match = re.findall(r'(?:s|season\s?)(\d+)', title_lower)
        for s in s_match:
            if int(s) not in seasons:
                seasons.append(int(s))
        
        # Year detection
        year_match = re.search(r'[\.\s\[\(](\d{4})[\.\s\]\)]', raw_title)
        year = int(year_match.group(1)) if year_match else None
        
        # Codec detection
        codec = ""
        if "x265" in title_lower or "hevc" in title_lower or "h.265" in title_lower:
            codec = "x265"
        elif "x264" in title_lower or "h.264" in title_lower:
            codec = "x264"
        
        # Ranking (simple scoring)
        rank = 0
        if quality == Quality.FHD_1080P:
            rank += 100
        elif quality == Quality.UHD_4K:
            rank += 80 if self.allow_4k else -50
        elif quality == Quality.HD_720P:
            rank += 50
        
        if source == "bluray":
            rank += 50
        elif source == "web":
            rank += 30
        
        if codec == "x265":
            rank += 20
        
        return ParsedTorrent(
            raw_title=raw_title,
            info_hash=info_hash.lower(),
            quality=quality,
            resolution=resolution,
            source=source,
            codec=codec,
            year=year,
            seasons=sorted(seasons),
            episodes=sorted(episodes),
            is_pack=len(seasons) > 1 or len(episodes) > 1,
            rank=rank
        )
    
    def validate_for_movie(self, parsed: ParsedTorrent) -> bool:
        """Validate if torrent is suitable for a movie."""
        # Movies should NOT have season/episode info
        if parsed.seasons or parsed.episodes:
            return False
        return True
    
    def validate_for_episode(self, parsed: ParsedTorrent, season: int, episode: int) -> bool:
        """Validate if torrent matches requested season/episode."""
        # Must have the correct season
        if parsed.seasons and season not in parsed.seasons:
            return False
        
        # If episodes are detected, must include our episode
        if parsed.episodes and episode not in parsed.episodes:
            return False
        
        # If it's a pack (full season), it's valid
        if not parsed.episodes and season in parsed.seasons:
            return True
        
        return True
    
    def filter_by_quality(self, parsed: ParsedTorrent) -> bool:
        """Check if torrent matches quality preferences."""
        if parsed.quality == Quality.UHD_4K and not self.allow_4k:
            return False
        return True
    
    def rank_torrents(self, torrents: List[ParsedTorrent]) -> List[ParsedTorrent]:
        """Sort torrents by rank (highest first)."""
        return sorted(torrents, key=lambda t: t.rank, reverse=True)
