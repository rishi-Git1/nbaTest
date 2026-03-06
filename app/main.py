from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import PlayerStatsResponse
from app.services import (
    ALLOWED_SORT_KEYS,
    calculate_award_rankings,
    get_active_player_stats,
    get_award_metric_groups,
    get_award_presets,
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
    "three_pt_pct": "3-POINT % (3P%)",
    "pf_pg": "FOULS PER GAME",
    "mpg": "MINUTES PER GAME (MPG)",
    "off_rating": "OFFENSIVE RATING",
    "def_rating": "DEFENSIVE RATING",
    "net_rating": "NET RATING",
    "ast_pct": "ASSIST %",
    "oreb_pct": "OFF REB %",
    "dreb_pct": "DEF REB %",
    "reb_pct": "TOTAL REB %",
    "stl_pct": "STEAL %",
    "blk_pct": "BLOCK %",
    "tov_pct": "TURNOVER %",
    "usg_pct": "USAGE %",
    "efg_pct": "EFFECTIVE FG %",
    "three_par": "3PA RATE (3PAr)",
    "ftr": "FT RATE (FTr)",
    "pie": "PIE",
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


@app.get("/awards-formula", response_class=HTMLResponse)
def awards_formula_page(request: Request):
    return templates.TemplateResponse(
        "awards_formula.html",
        {
            "request": request,
            "default_season": get_current_season(),
            "seasons": get_recent_seasons(),
            "metric_groups": get_award_metric_groups(),
            "presets": get_award_presets(),
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


@app.post("/api/awards-formula")
def awards_formula(
    payload: dict = Body(...),
):
    try:
        season = payload.get("season") or get_current_season()
        award = str(payload.get("award") or "CUSTOM")
        weights = payload.get("weights") or {}
        team_rating_weight = float(payload.get("team_rating_weight") or 0)
        min_gp = int(payload.get("min_gp") or 0)
        top_n = int(payload.get("top_n") or 25)

        return calculate_award_rankings(
            season=season,
            award=award,
            weights=weights,
            team_rating_weight=team_rating_weight,
            min_gp=min_gp,
            top_n=max(1, min(top_n, 100)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc
