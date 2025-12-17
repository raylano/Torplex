from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from src.database import db
from src.clients.tmdb import TMDBClient
from src.logic.manager import Manager
from src.config import config

router = APIRouter()
templates = Jinja2Templates(directory="src/app/templates")
tmdb = TMDBClient()
manager = Manager()

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard with stats and recent activity."""
    stats = db.get_stats()
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})

@router.get("/library/{filter_type}", response_class=HTMLResponse)
async def library(request: Request, filter_type: str):
    """Filtered library view (movies, series, completed, pending)."""
    items = db.get_library_items(filter_type)
    return templates.TemplateResponse("library.html", {
        "request": request, 
        "items": items, 
        "filter_type": filter_type
    })

@router.get("/media/{item_id}", response_class=HTMLResponse)
async def media_detail(request: Request, item_id: int):
    """Media item detail page with TMDB info."""
    item = db.get_item_by_id(item_id)
    if not item:
        return RedirectResponse(url="/")
    
    # Get TMDB details for poster and info
    details = None
    episodes = None
    
    if item['media_type'] == 'movie':
        details = tmdb.get_movie_details(item['tmdb_id'])
    elif item['media_type'] == 'episode':
        # Get show details and all episodes for this series
        if item['parent_tmdb_id']:
            details = tmdb.get_tv_details(item['parent_tmdb_id'])
            episodes = db.get_series_episodes(item['parent_tmdb_id'])
    
    # Convert details to dict for template
    details_dict = None
    if details:
        details_dict = {
            'overview': getattr(details, 'overview', ''),
            'vote_average': getattr(details, 'vote_average', None),
            'runtime': getattr(details, 'runtime', None),
            'genres': [{'name': g.name if hasattr(g, 'name') else g['name']} for g in getattr(details, 'genres', [])],
            'poster_path': getattr(details, 'poster_path', None)
        }
    
    # Add poster_path to item if from TMDB
    item_dict = dict(item)
    if details_dict and details_dict.get('poster_path'):
        item_dict['poster_path'] = details_dict['poster_path']
    
    return templates.TemplateResponse("media_detail.html", {
        "request": request,
        "item": item_dict,
        "details": details_dict,
        "episodes": episodes
    })

@router.get("/series", response_class=HTMLResponse)
async def series(request: Request):
    items = db.get_tracked_series()
    return templates.TemplateResponse("series.html", {"request": request, "items": items})

@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    results = []
    if q:
        # Search both movies and TV shows
        movie_results = tmdb.search_movie(q) or []
        tv_results = tmdb.search_tv(q) or []
        
        # Add media_type to each result
        for m in movie_results:
            # Skip if not a proper object
            if not hasattr(m, 'id'):
                continue
            try:
                results.append({
                    'id': m.id,
                    'title': getattr(m, 'title', 'Unknown'),
                    'year': getattr(m, 'release_date', '')[:4] if getattr(m, 'release_date', None) else '',
                    'media_type': 'movie',
                    'poster_path': getattr(m, 'poster_path', None),
                    'overview': getattr(m, 'overview', '')[:150] if getattr(m, 'overview', None) else ''
                })
            except Exception as e:
                print(f"Error processing movie result: {e}")
                continue
                
        for t in tv_results:
            # Skip if not a proper object
            if not hasattr(t, 'id'):
                continue
            try:
                results.append({
                    'id': t.id,
                    'title': getattr(t, 'name', 'Unknown'),
                    'year': getattr(t, 'first_air_date', '')[:4] if getattr(t, 'first_air_date', None) else '',
                    'media_type': 'tv',
                    'poster_path': getattr(t, 'poster_path', None),
                    'overview': getattr(t, 'overview', '')[:150] if getattr(t, 'overview', None) else ''
                })
            except Exception as e:
                print(f"Error processing TV result: {e}")
                continue
        
        # Sort by relevance (movies first, then TV)
        results.sort(key=lambda x: (0 if x['media_type'] == 'movie' else 1, x['title']))
        
    return templates.TemplateResponse("search.html", {"request": request, "results": results, "query": q})

@router.post("/add")
async def add_item(tmdb_id: str = Form(...), title: str = Form(...), year: str = Form(...), media_type: str = Form(...)):
    if media_type == 'movie':
        db.add_media_item(tmdb_id, title, media_type, year)
    else:
        # Manual add of Series
        details = tmdb.get_tv_details(tmdb_id)
        status = getattr(details, 'status', 'Returning Series') if details else 'Returning Series'
        db.add_tracked_series(tmdb_id, title, status)

    return HTMLResponse(content="<div class='alert alert-success'>Added!</div>", status_code=200)

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, message: str = None):
    """Settings page for configuring APIs and preferences."""
    cfg = config.get()
    return templates.TemplateResponse("settings.html", {
        "request": request, 
        "config": cfg,
        "message": message
    })

@router.post("/settings/save")
async def save_settings(
    tmdb_api_key: str = Form(""),
    plex_token: str = Form(""),
    prowlarr_url: str = Form(""),
    prowlarr_api_key: str = Form(""),
    debrid_service: str = Form("torbox"),
    torbox_api_key: str = Form(""),
    realdebrid_api_key: str = Form(""),
    quality_profile: str = Form("hd"),
    allow_4k: bool = Form(False),
    mount_path: str = Form("/mnt/torbox"),
    symlink_path: str = Form("/mnt/media")
):
    """Save settings to config file."""
    config.update({
        'tmdb_api_key': tmdb_api_key,
        'plex_token': plex_token,
        'prowlarr_url': prowlarr_url,
        'prowlarr_api_key': prowlarr_api_key,
        'debrid_service': debrid_service,
        'torbox_api_key': torbox_api_key,
        'realdebrid_api_key': realdebrid_api_key,
        'quality_profile': quality_profile,
        'allow_4k': allow_4k,
        'mount_path': mount_path,
        'symlink_path': symlink_path
    })
    return RedirectResponse(url="/settings?message=Settings+saved+successfully!", status_code=303)

@router.post("/retry/{item_id}")
async def retry_item(item_id: int):
    """Retry a failed item."""
    db.update_status(item_id, "PENDING")
    return HTMLResponse(content="<div class='alert alert-warning'>Retrying...</div>", status_code=200)

@router.get("/trigger")
async def trigger_run():
    """Manually trigger the manager loops."""
    try:
        manager.sync_watchlist()
        manager.sync_running_series()
        manager.process_pending()
        manager.process_downloads()
        return {"status": "Triggered"}
    except Exception as e:
        return {"error": str(e)}

