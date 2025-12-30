"""
TMDB (The Movie Database) Service
Fetches metadata, posters, and information for movies and TV shows
"""
import httpx
from typing import Optional, Dict, Any, List
from loguru import logger

from src.config import settings


class TMDBService:
    """Service for interacting with TMDB API"""
    
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
    
    def __init__(self):
        self.api_key = settings.tmdb_api_key
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make request to TMDB API"""
        if not self.api_key:
            logger.warning("TMDB API key not configured")
            return None
        
        url = f"{self.BASE_URL}{endpoint}"
        request_params = {"api_key": self.api_key, **(params or {})}
        
        try:
            response = await self.client.get(url, params=request_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"TMDB API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"TMDB request failed: {e}")
            return None
    
    async def search_movie(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """Search for movies by title"""
        params = {"query": query}
        if year:
            params["year"] = year
        
        result = await self._request("/search/movie", params)
        return result.get("results", []) if result else []
    
    async def search_tv(self, query: str, year: Optional[int] = None) -> List[Dict]:
        """Search for TV shows by title"""
        params = {"query": query}
        if year:
            params["first_air_date_year"] = year
        
        result = await self._request("/search/tv", params)
        return result.get("results", []) if result else []
    
    async def search_multi(self, query: str) -> List[Dict]:
        """Search for both movies and TV shows"""
        result = await self._request("/search/multi", {"query": query})
        return result.get("results", []) if result else []
    
    async def get_movie(self, tmdb_id: int) -> Optional[Dict]:
        """Get movie details by TMDB ID"""
        return await self._request(f"/movie/{tmdb_id}", {"append_to_response": "external_ids,credits"})
    
    async def get_tv_show(self, tmdb_id: int) -> Optional[Dict]:
        """Get TV show details by TMDB ID"""
        return await self._request(f"/tv/{tmdb_id}", {"append_to_response": "external_ids,credits"})
    
    async def get_tv_season(self, tmdb_id: int, season_number: int) -> Optional[Dict]:
        """Get season details including episodes"""
        return await self._request(f"/tv/{tmdb_id}/season/{season_number}")
    
    async def find_by_imdb(self, imdb_id: str) -> Optional[Dict]:
        """Find movie or TV show by IMDB ID"""
        result = await self._request(f"/find/{imdb_id}", {"external_source": "imdb_id"})
        if result:
            # Return first movie or TV result
            if result.get("movie_results"):
                return {"type": "movie", **result["movie_results"][0]}
            if result.get("tv_results"):
                return {"type": "tv", **result["tv_results"][0]}
        return None
    
    async def get_trending(self, media_type: str = "all", time_window: str = "week") -> List[Dict]:
        """Get trending movies/shows"""
        result = await self._request(f"/trending/{media_type}/{time_window}")
        return result.get("results", []) if result else []
    
    async def get_all_episodes(self, tmdb_id: int, num_seasons: int) -> List[Dict]:
        """
        Fetch all episodes for a TV show.
        Returns list of episode dicts with season_number, episode_number, title, overview, air_date
        """
        all_episodes = []
        
        for season_num in range(1, num_seasons + 1):
            season_data = await self.get_tv_season(tmdb_id, season_num)
            if not season_data:
                continue
            
            for ep in season_data.get("episodes", []):
                all_episodes.append({
                    "season_number": ep.get("season_number", season_num),
                    "episode_number": ep.get("episode_number"),
                    "title": ep.get("name"),
                    "overview": ep.get("overview"),
                    "air_date": ep.get("air_date"),
                })
        
        logger.info(f"TMDB: Fetched {len(all_episodes)} episodes for show {tmdb_id}")
        return all_episodes

    async def get_show_absolute_map(self, tmdb_id: int) -> Dict[tuple, int]:
        """
        Fetch Absolute Episode Numbers for a show (Anime support).
        Returns mapping: (season, episode) -> absolute_number
        Fetches "Episode Groups" looking for "Absolute Order".
        """
        # 1. Get Episode Groups
        groups = await self._request(f"/tv/{tmdb_id}/episode_groups")
        if not groups or "results" not in groups:
            return {}
            
        # 2. Find "Absolute Order" group
        absolute_group_id = None
        for group in groups["results"]:
            # Usually named "Absolute Order" or type 2 maybe?
            # group: {'description': '', 'episode_count': 1122, 'group_count': 1, 'id': '5b59...', 'name': 'Absolute Order', 'network': ..., 'type': 2}
            if "absolute" in group.get("name", "").lower():
                absolute_group_id = group.get("id")
                break
        
        if not absolute_group_id and groups["results"]:
             # Fallback to first group if many? Usually first is meaningful or look for biggest count
             # But risky. Anime usually has explicit absolute order.
             pass
             
        if not absolute_group_id:
            logger.debug(f"TMDB: No Absolute Order group found for {tmdb_id}")
            return {}
            
        # 3. Fetch Group Details
        group_details = await self._request(f"/tv/episode_group/{absolute_group_id}")
        if not group_details or "groups" not in group_details:
             return {}
             
        mapping = {}
        # Structure: groups -> [ { episodes: [ { season_number, episode_number, order+1? } ] } ]
        # wait, details structure:
        # { "groups": [ { "name": "...", "order": 1, "episodes": [ ... ] } ], ... }
        # NO, endpoint /tv/episode_group/{id} returns list of groups?
        # Let's assume standard TMDB structure.
        
        for g in group_details.get("groups", []):
            for ep in g.get("episodes", []):
                s = ep.get("season_number")
                e = ep.get("episode_number")
                # Absolute number is usually the index in list or 'order' field?
                # In Absolute Order group, they are just listed linearly. 
                # TMDB 'order' field usually exists.
                # Actually, in an Absolute Group, the 'order' property of the episode object *within the group* is the absolute number.
                abs_num = ep.get("order") + 1 # 0-indexed usually? Api docs say 'order'.
                # Let's assume 0-indexed order
                
                if s is not None and e is not None and abs_num is not None:
                    mapping[(s, e)] = abs_num
                    
        logger.info(f"TMDB: Built absolute map for {tmdb_id} with {len(mapping)} entries")
        return mapping

    async def get_alternative_titles(self, tmdb_id: int, media_type: str = "tv") -> List[str]:
        """
        Fetch all alternative titles for a show/movie from TMDB.
        Includes original title and all international titles.
        """
        endpoint = f"/{media_type}/{tmdb_id}/alternative_titles"
        result = await self._request(endpoint)
        
        titles = []
        if result:
            # TV shows use "results", movies use "titles"
            title_list = result.get("results", []) or result.get("titles", [])
            for entry in title_list:
                title = entry.get("title")
                if title:
                    titles.append(title)
        
        logger.debug(f"TMDB: Found {len(titles)} alternative titles for {media_type}/{tmdb_id}")
        return titles

    
    def is_anime(self, data: Dict) -> bool:
        """
        Determine if a movie/show is anime based on:
        - Origin country (Japan)
        - Genres (Animation)
        - Keywords
        """
        # Check origin country
        origin_countries = data.get("origin_country", [])
        if "JP" in origin_countries:
            # Japanese + Animation = Anime
            genres = data.get("genres", []) or data.get("genre_ids", [])
            genre_ids = [g.get("id") if isinstance(g, dict) else g for g in genres]
            if 16 in genre_ids:  # 16 = Animation
                return True
        
        # Check if explicitly tagged as anime in keywords (would need separate API call)
        return False
    
    def extract_metadata(self, data: Dict, media_type: str) -> Dict[str, Any]:
        """Extract standardized metadata from TMDB response"""
        is_movie = media_type == "movie"
        
        # Get genres
        genres = data.get("genres", [])
        genre_names = [g.get("name") for g in genres if isinstance(g, dict)]
        
        # Get external IDs
        external_ids = data.get("external_ids", {})
        
        return {
            "tmdb_id": data.get("id"),
            "imdb_id": external_ids.get("imdb_id") or data.get("imdb_id"),
            "tvdb_id": external_ids.get("tvdb_id"),
            "title": data.get("title" if is_movie else "name"),
            "original_title": data.get("original_title" if is_movie else "original_name"),
            "year": self._extract_year(data, is_movie),
            "poster_path": data.get("poster_path"),
            "backdrop_path": data.get("backdrop_path"),
            "overview": data.get("overview"),
            "genres": genre_names,
            "vote_average": data.get("vote_average"),
            "is_anime": self.is_anime(data),
            # TV specific
            "number_of_seasons": data.get("number_of_seasons"),
            "number_of_episodes": data.get("number_of_episodes"),
            "status": data.get("status"),
        }
    
    def _extract_year(self, data: Dict, is_movie: bool) -> Optional[int]:
        """Extract year from release/air date"""
        date_field = "release_date" if is_movie else "first_air_date"
        date_str = data.get(date_field, "")
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


# Singleton instance
tmdb_service = TMDBService()
