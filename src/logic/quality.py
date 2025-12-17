import re
from src.config import config

class QualityManager:
    def __init__(self):
        self.profile = config.get().quality_profile.lower()
        self.allow_4k = config.get().allow_4k

    def filter_items(self, items, is_anime=False):
        """
        Filters a list of Prowlarr/Indexer items based on quality profile.
        Items are expected to be dicts with 'title', 'size', 'indexer', etc.
        """
        ranked_items = []
        for item in items:
            title = item.get('title', '').lower()
            score = 0

            # Resolution scoring
            is_4k = '2160p' in title or '4k' in title or 'uhd' in title

            if is_4k:
                if not self.allow_4k:
                    # Skip 4K entirely if not allowed
                    continue
                else:
                    score += 100

            if '1080p' in title:
                score += 100 # High priority for 1080p
            elif '720p' in title:
                score += 50
            elif '480p' in title or 'sd' in title:
                score += 10 # Low priority

            # Codec scoring (prefer x265/HEVC for efficiency, or x264 for compat)
            if 'x265' in title or 'hevc' in title:
                score += 5

            # HDR/DV
            if 'hdr' in title or 'dolby vision' in title or 'dv' in title:
                score += 5

            # Anime specific scoring
            if is_anime:
                # Prefer Dual Audio or Dubbed
                if 'dual' in title or 'dual-audio' in title:
                    score += 200 # High priority
                elif 'dub' in title or 'dubbed' in title:
                    score += 150

            ranked_items.append((score, item))

        # Sort by score desc
        ranked_items.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in ranked_items]

    def extract_hash(self, magnet_link):
        # xt=urn:btih:HASH
        if not magnet_link: return None
        match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
        if match:
            return match.group(1).lower()
        return None
