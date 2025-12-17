from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from src.database import db
from src.clients.tmdb import TMDBClient
from src.logic.manager import Manager

router = APIRouter()
templates = Jinja2Templates(directory="src/app/templates")
tmdb = TMDBClient()
manager = Manager()

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    items = db.get_all_items()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@router.get("/series", response_class=HTMLResponse)
async def series(request: Request):
    items = db.get_tracked_series()
    return templates.TemplateResponse("series.html", {"request": request, "items": items})

@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    results = []
    if q:
        # Search movies for now, eventually both?
        results = tmdb.search_movie(q)
    return templates.TemplateResponse("search.html", {"request": request, "results": results, "query": q})

@router.post("/add")
async def add_item(tmdb_id: str = Form(...), title: str = Form(...), year: str = Form(...), media_type: str = Form(...)):
    if media_type == 'movie':
        db.add_media_item(tmdb_id, title, media_type, year)
    else:
        # Manual add of Series
        # We add to tracked_series, scheduler will explode it
        # Fetch status
        details = tmdb.get_tv_details(tmdb_id)
        status = getattr(details, 'status', 'Returning Series') if details else 'Returning Series'
        db.add_tracked_series(tmdb_id, title, status)

    return HTMLResponse(content="<div class='alert alert-success'>Added!</div>", status_code=200)

@router.get("/trigger")
async def trigger_run():
    # Manually trigger the manager loops
    try:
        manager.sync_watchlist()
        manager.sync_running_series()
        manager.process_pending()
        manager.process_downloads()
        return {"status": "Triggered"}
    except Exception as e:
        return {"error": str(e)}
