"""
Search Router
Search TMDB and request items
"""
from typing import Optional, List
from fastapi import APIRouter, Query
from pydantic import BaseModel
from loguru import logger

from src.services.content import tmdb_service

router = APIRouter()


class SearchResult(BaseModel):
    id: int
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    type: str  # "movie" or "tv"
    poster_path: Optional[str] = None
    backdrop_path: Optional[str] = None
    overview: Optional[str] = None
    vote_average: Optional[float] = None
    
    # Computed
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None


class TrendingResponse(BaseModel):
    results: List[SearchResult]


def parse_search_result(item: dict, media_type: str) -> SearchResult:
    """Parse TMDB response to SearchResult"""
    is_movie = media_type == "movie"
    
    # Extract year from date
    date_field = "release_date" if is_movie else "first_air_date"
    date_str = item.get(date_field, "")
    year = None
    if date_str and len(date_str) >= 4:
        try:
            year = int(date_str[:4])
        except ValueError:
            pass
    
    poster_path = item.get("poster_path")
    backdrop_path = item.get("backdrop_path")
    
    return SearchResult(
        id=item.get("id"),
        title=item.get("title" if is_movie else "name", "Unknown"),
        original_title=item.get("original_title" if is_movie else "original_name"),
        year=year,
        type=media_type,
        poster_path=poster_path,
        backdrop_path=backdrop_path,
        overview=item.get("overview"),
        vote_average=item.get("vote_average"),
        poster_url=f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
        backdrop_url=f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
    )


@router.get("/search")
async def search_media(
    query: str = Query(..., min_length=1),
    type: Optional[str] = Query(None, regex="^(movie|tv|all)$"),
) -> List[SearchResult]:
    """
    Search TMDB for movies and TV shows.
    
    Args:
        query: Search query
        type: Filter by type (movie, tv, or all)
    """
    results = []
    
    if type == "movie":
        movies = await tmdb_service.search_movie(query)
        results = [parse_search_result(m, "movie") for m in movies]
    
    elif type == "tv":
        shows = await tmdb_service.search_tv(query)
        results = [parse_search_result(s, "tv") for s in shows]
    
    else:
        # Search both
        multi_results = await tmdb_service.search_multi(query)
        for item in multi_results:
            media_type = item.get("media_type")
            if media_type in ["movie", "tv"]:
                results.append(parse_search_result(item, media_type))
    
    logger.info(f"Search '{query}': {len(results)} results")
    return results


@router.get("/search/movie/{tmdb_id}")
async def get_movie_details(tmdb_id: int):
    """Get full movie details from TMDB"""
    data = await tmdb_service.get_movie(tmdb_id)
    if not data:
        return {"error": "Movie not found"}
    
    return {
        **tmdb_service.extract_metadata(data, "movie"),
        "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None,
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get("backdrop_path") else None,
    }


@router.get("/search/tv/{tmdb_id}")
async def get_tv_details(tmdb_id: int):
    """Get full TV show details from TMDB"""
    data = await tmdb_service.get_tv_show(tmdb_id)
    if not data:
        return {"error": "TV show not found"}
    
    return {
        **tmdb_service.extract_metadata(data, "tv"),
        "poster_url": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None,
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{data.get('backdrop_path')}" if data.get("backdrop_path") else None,
    }


@router.get("/trending")
async def get_trending(
    type: str = Query("all", regex="^(all|movie|tv)$"),
    time_window: str = Query("week", regex="^(day|week)$"),
) -> TrendingResponse:
    """Get trending movies/shows"""
    results = await tmdb_service.get_trending(type, time_window)
    
    parsed = []
    for item in results:
        media_type = item.get("media_type", type if type != "all" else "movie")
        if media_type in ["movie", "tv"]:
            parsed.append(parse_search_result(item, media_type))
    
    return TrendingResponse(results=parsed)
