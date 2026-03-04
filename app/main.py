from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import PlayerStatsResponse
from app.services import (
    ALLOWED_SORT_KEYS,
    get_active_player_stats,
    get_current_season,
    get_recent_seasons,
    get_team_vs_team,
    get_teams_directory,
    sort_rows,
)

app = FastAPI(title="NBA Active Player Stats")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

SORT_LABELS = {
    "player_name": "PLAYER NAME",
    "team": "TEAM",
    "gp": "GAMES PLAYED",
    "ppg": "POINTS PER GAME (PPG)",
    "rpg": "REBOUNDS PER GAME (RPG)",
    "apg": "ASSISTS PER GAME (APG)",
    "spg": "STEALS PER GAME (SPG)",
    "bpg": "BLOCKS PER GAME (BPG)",
    "plus_minus": "PLUS/MINUS",
    "fg_pct": "FIELD GOAL % (FG%)",
    "ts_pct": "TRUE SHOOTING % (TS%)",
    "ft_pct": "FREE THROW % (FT%)",
    "pf_pg": "FOULS PER GAME",
}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_season": get_current_season(),
            "sort_options": [{"key": key, "label": SORT_LABELS.get(key, key.upper())} for key in sorted(ALLOWED_SORT_KEYS)],
        },
    )


@app.get("/head-to-head", response_class=HTMLResponse)
def head_to_head_page(request: Request):
    default_season = get_current_season()
    seasons = get_recent_seasons()
    return templates.TemplateResponse(
        "head_to_head.html",
        {
            "request": request,
            "default_season": default_season,
            "seasons": seasons,
            "teams": get_teams_directory(),
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


@app.get("/api/head-to-head")
def head_to_head(
    season_1: str = Query(default_factory=get_current_season),
    team1_id: int = Query(..., ge=1),
    season_2: str = Query(default_factory=get_current_season),
    team2_id: int = Query(..., ge=1),
):
    try:
        return get_team_vs_team(season1=season_1, team1_id=team1_id, season2=season_2, team2_id=team2_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc
