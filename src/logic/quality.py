import re
from src.config import config

class QualityManager:
    def __init__(self):
        self.profile = config.get().quality_profile.lower()

    def filter_items(self, items, is_anime=False):
        """
        Filters a list of Prowlarr/Indexer items based on quality profile.
        Items are expected to be dicts with 'title', 'size', 'indexer', etc.
        """
        # Simple heuristic: Look for resolution in title
        # 4k/2160p
        # 1080p
        # 720p

        ranked_items = []
        for item in items:
            title = item.get('title', '').lower()
            score = 0

            # Resolution scoring
            if '2160p' in title or '4k' in title:
                score += 100 if '2160p' in self.profile or '4k' in self.profile else 10
            elif '1080p' in title:
                score += 100 if '1080p' in self.profile else 50
            elif '720p' in title:
                score += 20

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
                # Penalize raw if we want dubbed? Usually users want subs if not dubbed.
                # But request is specifically "dual-audio preffered or dubbed".

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
