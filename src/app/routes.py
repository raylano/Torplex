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

@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = ""):
    results = []
    if q:
        # Search movies for now
        results = tmdb.search_movie(q)
    return templates.TemplateResponse("search.html", {"request": request, "results": results, "query": q})

@router.post("/add")
async def add_item(tmdb_id: str = Form(...), title: str = Form(...), year: str = Form(...), media_type: str = Form(...)):
    db.add_item(tmdb_id, title, media_type, year)
    # Trigger processing in background?
    # For now just add to DB, scheduler picks it up.
    return HTMLResponse(content="<div class='alert alert-success'>Added!</div>", status_code=200)

@router.get("/trigger")
async def trigger_run():
    # Manually trigger the manager loops
    try:
        manager.sync_watchlist()
        manager.process_pending()
        manager.process_downloads()
        return {"status": "Triggered"}
    except Exception as e:
        return {"error": str(e)}
