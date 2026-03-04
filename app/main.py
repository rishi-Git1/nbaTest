from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import PlayerStatsResponse
from app.services import ALLOWED_SORT_KEYS, get_active_player_stats, get_current_season, sort_rows

app = FastAPI(title="NBA Active Player Stats")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_season": get_current_season(),
            "sort_keys": sorted(ALLOWED_SORT_KEYS),
        },
    )


@app.get("/api/players", response_model=PlayerStatsResponse)
def list_players(
    season: str = Query(default_factory=get_current_season),
    sort_by: str = Query("ppg"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    try:
        rows = get_active_player_stats(season=season)
        sorted_rows = sort_rows(rows, sort_by=sort_by, order=order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc

    total = len(sorted_rows)
    paged = sorted_rows[offset : offset + limit]
    return {
        "meta": {
            "season": season,
            "sort_by": sort_by,
            "order": order,
            "limit": limit,
            "offset": offset,
            "total": total,
        },
        "data": paged,
    }
