from datetime import datetime
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.models import PlayerStatsResponse
from app.services import (
    ALLOWED_SORT_KEYS,
    calculate_award_rankings,
    get_active_player_stats,
    get_award_metric_groups,
    get_award_presets,
    get_current_season,
    get_player_career_stats,
    get_player_directory,
    get_player_similarity,
    get_recent_seasons,
    get_team_lineups,
    get_lineup_sort_options,
    get_games_on_this_day,
    get_breakout_games,
    get_game_explainer_analysis,
    get_game_explainer_games,
    search_games,
    get_team_vs_team,
    get_teams_directory,
    sort_rows,
)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="NBA Active Player Stats")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
        request=request,
        name="index.html",
        context={
            "request": request,
            "default_season": get_current_season(),
            "sort_options": [{"key": key, "label": SORT_LABELS.get(key, key.upper())} for key in sorted(ALLOWED_SORT_KEYS)],
        },
    )


@app.get("/players-playoffs", response_class=HTMLResponse)
def players_playoffs_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="players_playoffs.html",
        context={
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
        request=request,
        name="head_to_head.html",
        context={
            "request": request,
            "default_season": default_season,
            "seasons": seasons,
            "teams": get_teams_directory(),
        },
    )


@app.get("/awards-formula", response_class=HTMLResponse)
def awards_formula_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="awards_formula.html",
        context={
            "request": request,
            "default_season": get_current_season(),
            "seasons": get_recent_seasons(),
            "metric_groups": get_award_metric_groups(),
            "presets": get_award_presets(),
        },
    )


@app.get("/lineups", response_class=HTMLResponse)
@app.get("/lineups/", response_class=HTMLResponse)
@app.get("/lineup", response_class=HTMLResponse)
@app.get("/lineup/", response_class=HTMLResponse)
def lineups_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="lineups.html",
        context={
            "request": request,
            "default_season": get_current_season(),
            "teams": get_teams_directory(),
            "lineup_sort_options": get_lineup_sort_options(),
        },
    )


@app.get("/assets/player-similarity.js")
def player_similarity_asset():
    return FileResponse(BASE_DIR / "static" / "player_similarity.js", media_type="application/javascript")


@app.get("/game-finder", response_class=HTMLResponse)
def game_finder_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="game_finder.html",
        context={
            "request": request,
            "default_season": get_current_season(),
            "default_month": 3,
            "default_day": 17,
        },
    )


@app.get("/game-explainer", response_class=HTMLResponse)
def game_explainer_page(request: Request):
    default_season = get_current_season()
    return templates.TemplateResponse(
        request=request,
        name="game_explainer.html",
        context={
            "request": request,
            "default_season": default_season,
            "seasons": get_recent_seasons(),
            "teams": get_teams_directory(),
            "default_date": datetime.utcnow().strftime("%Y-%m-%d"),
        },
    )


@app.get("/player-similarity", response_class=HTMLResponse)
def player_similarity_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="player_similarity.html",
        context={
            "request": request,
            "default_season": get_current_season(),
            "seasons": get_recent_seasons(),
        },
    )


@app.get("/player-career", response_class=HTMLResponse)
def player_career_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="player_career.html",
        context={
            "request": request,
            "default_player_name": "Keegan Murray",
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


@app.get("/api/players-playoffs", response_model=PlayerStatsResponse)
def list_players_playoffs(
    season: str = Query(default_factory=get_current_season),
    sort_by: str = Query("ppg"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    try:
        rows = get_active_player_stats(season=season, season_type="Playoffs")
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
            "season_type": "Playoffs",
        },
        "data": paged,
    }


@app.get("/api/player-directory")
def player_directory(active_only: bool = Query(False)):
    try:
        return {"data": get_player_directory(active_only=active_only)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/player-career")
def player_career(player_name: str = Query(..., min_length=2)):
    try:
        return get_player_career_stats(player_name=player_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


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


@app.get("/api/lineups")
def lineups(
    team_id: int = Query(..., ge=1),
    top_n: int = Query(20, ge=1, le=100),
    min_minutes: float = Query(0, ge=0),
    min_games: int = Query(0, ge=0),
    sort_by: str = Query("NET_RATING"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    try:
        return get_team_lineups(
            team_id=team_id,
            season=get_current_season(),
            top_n=top_n,
            min_minutes=min_minutes,
            min_games=min_games,
            sort_by=sort_by,
            order=order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/game-explainer/games")
def game_explainer_games(
    date: str | None = Query(None),
    team1_id: int | None = Query(None, ge=1),
    team2_id: int | None = Query(None, ge=1),
    season_start: str | None = Query(None),
    season_end: str | None = Query(None),
    season_type: str = Query("Regular Season"),
):
    try:
        return get_game_explainer_games(
            date=date,
            team1_id=team1_id,
            team2_id=team2_id,
            season_start=season_start,
            season_end=season_end,
            season_type=season_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/game-explainer/analysis")
def game_explainer_analysis(game_id: str = Query(..., min_length=6)):
    try:
        return get_game_explainer_analysis(game_id=game_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/game-finder/search")
def game_finder_search(
    season: str = Query(default_factory=get_current_season),
    season_type: str = Query("Regular Season"),
    pts_min: int | None = Query(None, ge=0),
    fg3m_min: int | None = Query(None, ge=0),
    ast_min: int | None = Query(None, ge=0),
    reb_min: int | None = Query(None, ge=0),
    player: str | None = Query(None),
    date: str | None = Query(None),
    top_n: int = Query(100, ge=1, le=500),
):
    try:
        return search_games(
            season=season,
            season_type=season_type,
            filters={
                "pts_min": pts_min,
                "fg3m_min": fg3m_min,
                "ast_min": ast_min,
                "reb_min": reb_min,
                "player": player,
                "date": date,
            },
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/game-finder/on-this-day")
def game_finder_on_this_day(
    month: int = Query(..., ge=1, le=12),
    day: int = Query(..., ge=1, le=31),
    season_type: str = Query("Regular Season"),
    years: int = Query(20, ge=1, le=30),
    top_n: int = Query(50, ge=1, le=500),
):
    try:
        return get_games_on_this_day(month=month, day=day, season_type=season_type, years=years, top_n=top_n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/game-finder/breakouts")
def game_finder_breakouts(
    season: str = Query(default_factory=get_current_season),
    season_type: str = Query("Regular Season"),
    min_breakout_score: float = Query(15, ge=0),
    player_name: str | None = Query(None),
    top_n: int = Query(100, ge=1, le=500),
):
    try:
        return get_breakout_games(
            season=season,
            season_type=season_type,
            min_breakout_score=min_breakout_score,
            player_name=player_name,
            top_n=top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Upstream data fetch failed: {exc}") from exc


@app.get("/api/player-similarity")
def player_similarity(
    season: str = Query(default_factory=get_current_season),
    player_name: str = Query(..., min_length=2),
    top_n: int = Query(5, ge=1, le=25),
    min_minutes: int = Query(800, ge=0),
    include_shot_diet: bool = Query(True),
    archetype_only: bool = Query(False),
):
    try:
        return get_player_similarity(
            season=season,
            player_name=player_name,
            top_n=top_n,
            min_minutes=min_minutes,
            include_shot_diet=include_shot_diet,
            archetype_only=archetype_only,
        )
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
