import re
from src.config import config

class QualityManager:
    def __init__(self):
        self.profile = config.get().quality_profile.lower()
        self.allow_4k = config.get().allow_4k

    def filter_items(self, items, is_anime=False):
        """
        Filters and ranks Prowlarr/Indexer items.
        - Regular content: Prioritizes by seeders (peers)
        - Anime: Prioritizes dual-audio, then seeders
        """
        ranked_items = []
        for item in items:
            title = item.get('title', '').lower()
            seeders = item.get('seeders', 0) or item.get('peers', 0) or 0
            
            # Start with base score from seeders
            score = 0
            
            # Resolution filtering (skip 4K if not allowed)
            is_4k = '2160p' in title or '4k' in title or 'uhd' in title
            if is_4k and not self.allow_4k:
                continue

            # Quality bonuses (smaller than peer influence for regular content)
            if '1080p' in title:
                score += 50
            elif '720p' in title:
                score += 25
            elif is_4k:
                score += 60

            # Codec bonus
            if 'x265' in title or 'hevc' in title:
                score += 10

            # HDR bonus
            if 'hdr' in title or 'dolby vision' in title or 'dv' in title:
                score += 5

            if is_anime:
                # ANIME: Dual-audio is most important (overrides peer count)
                has_dual = 'dual' in title or 'dual-audio' in title or 'multi' in title
                has_dub = 'dub' in title or 'dubbed' in title
                
                if has_dual:
                    score += 10000  # Dual-audio is king for anime
                elif has_dub:
                    score += 5000   # Dubbed is second
                
                # Then add seeders (but much lower weight than dual-audio)
                score += seeders
            else:
                # REGULAR: Seeders are most important
                score += seeders * 10  # Multiply to make it primary factor
            
            ranked_items.append((score, seeders, item))

        # Sort by score desc, then by seeders desc as tiebreaker
        ranked_items.sort(key=lambda x: (x[0], x[1]), reverse=True)
        
        # Log top 3 for debugging
        if ranked_items:
            print(f"Top candidates (is_anime={is_anime}):")
            for i, (score, seeds, itm) in enumerate(ranked_items[:3]):
                print(f"  #{i+1}: score={score}, seeders={seeds}, title={itm.get('title', '')[:60]}...")
        
        return [x[2] for x in ranked_items]

    def extract_hash(self, magnet_link):
        # xt=urn:btih:HASH
        if not magnet_link: return None
        match = re.search(r'xt=urn:btih:([a-zA-Z0-9]+)', magnet_link)
        if match:
            return match.group(1).lower()
        return None
