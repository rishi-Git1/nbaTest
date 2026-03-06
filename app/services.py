import os
import threading
import time
from datetime import datetime
from typing import Any

from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats
from nba_api.stats.static import players, teams

ALLOWED_SORT_KEYS = {
    "player_name",
    "team",
    "gp",
    "ppg",
    "rpg",
    "apg",
    "spg",
    "bpg",
    "plus_minus",
    "fg_pct",
    "ts_pct",
    "ft_pct",
    "three_pt_pct",
    "pf_pg",
    # Advanced-style sorting keys
    "mpg",
    "off_rating",
    "def_rating",
    "net_rating",
    "ast_pct",
    "oreb_pct",
    "dreb_pct",
    "reb_pct",
    "stl_pct",
    "blk_pct",
    "tov_pct",
    "usg_pct",
    "efg_pct",
    "three_par",
    "ftr",
    "pie",
}

AWARD_BASE_METRICS = [
    "gp",
    "ppg",
    "rpg",
    "apg",
    "spg",
    "bpg",
    "plus_minus",
    "fg_pct",
    "ts_pct",
    "ft_pct",
    "three_pt_pct",
    "pf_pg",
]

AWARD_ADV_METRICS = [
    "mpg",
    "ts_pct",
    "three_par",
    "ftr",
    "oreb_pct",
    "dreb_pct",
    "reb_pct",
    "ast_pct",
    "stl_pct",
    "blk_pct",
    "tov_pct",
    "usg_pct",
    "off_rating",
    "def_rating",
    "net_rating",
    "efg_pct",
    "pie",
]

AWARD_METRIC_LABELS = {
    "gp": "GP",
    "ppg": "PPG",
    "rpg": "RPG",
    "apg": "APG",
    "spg": "SPG",
    "bpg": "BPG",
    "plus_minus": "+/-",
    "fg_pct": "FG%",
    "ts_pct": "TS%",
    "ft_pct": "FT%",
    "three_pt_pct": "3P%",
    "pf_pg": "FOULS/G",
    "mpg": "MP",
    "three_par": "3PAr",
    "ftr": "FTr",
    "oreb_pct": "ORB%",
    "dreb_pct": "DRB%",
    "reb_pct": "TRB%",
    "ast_pct": "AST%",
    "stl_pct": "STL%",
    "blk_pct": "BLK%",
    "tov_pct": "TOV%",
    "usg_pct": "USG%",
    "off_rating": "OFF RTG",
    "def_rating": "DEF RTG",
    "net_rating": "NET RTG",
    "efg_pct": "eFG%",
    "pie": "PIE",
}

LOWER_IS_BETTER_METRICS = {"def_rating", "pf_pg", "tov_pct"}

AWARD_PRESETS: dict[str, dict[str, Any]] = {
    "CUSTOM": {"weights": {}, "team_rating_weight": 0, "min_gp": 0},
    "MVP": {
        "weights": {
            "ppg": 85,
            "apg": 65,
            "rpg": 45,
            "ts_pct": 80,
            "plus_minus": 55,
            "usg_pct": 50,
            "net_rating": 45,
            "pie": 65,
        },
        "team_rating_weight": 45,
        "min_gp": 55,
    },
    "DPOY": {
        "weights": {
            "bpg": 80,
            "spg": 75,
            "def_rating": 90,
            "blk_pct": 70,
            "stl_pct": 70,
            "dreb_pct": 55,
            "pf_pg": 35,
            "tov_pct": 20,
            "net_rating": 35,
        },
        "team_rating_weight": 30,
        "min_gp": 50,
    },
}

_DEFAULT_TTL = int(os.getenv("NBA_CACHE_TTL_SECONDS", "900"))


class _SimpleCache:
    def __init__(self, ttl_seconds: int = _DEFAULT_TTL):
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple[str, str]) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            timestamp, payload = item
            if (time.time() - timestamp) > self.ttl_seconds:
                return None
            return payload

    def set(self, key: tuple[str, str], payload: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), payload)

    def get_stale(self, key: tuple[str, str]) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            return item[1] if item else None


cache = _SimpleCache()


def get_current_season() -> str:
    now = datetime.utcnow()
    year = now.year
    start_year = year if now.month >= 10 else year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def get_recent_seasons(count: int = 12) -> list[str]:
    current = get_current_season()
    start = int(current.split("-")[0])
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(start, start - count, -1)]


def get_award_metric_groups() -> dict[str, Any]:
    return {
        "base": [{"key": key, "label": AWARD_METRIC_LABELS[key]} for key in AWARD_BASE_METRICS],
        "advanced": [{"key": key, "label": AWARD_METRIC_LABELS[key]} for key in AWARD_ADV_METRICS],
        "lower_is_better": sorted(list(LOWER_IS_BETTER_METRICS)),
    }


def get_award_presets() -> dict[str, dict[str, Any]]:
    return AWARD_PRESETS


def _fetch_per_game_stats(season: str) -> list[dict[str, Any]]:
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Base",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _fetch_advanced_stats(season: str) -> list[dict[str, Any]]:
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _fetch_team_base_stats(season: str) -> list[dict[str, Any]]:
    endpoint = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Base",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _fetch_team_advanced_stats(season: str) -> list[dict[str, Any]]:
    endpoint = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        season_type_all_star="Regular Season",
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _active_players_map() -> dict[int, str]:
    active = players.get_active_players()
    return {int(p["id"]): p["full_name"] for p in active}



def get_teams_directory() -> list[dict[str, Any]]:
    all_teams = teams.get_teams()
    normalized = [
        {
            "id": int(team["id"]),
            "abbreviation": team["abbreviation"],
            "full_name": team["full_name"],
        }
        for team in all_teams
    ]
    return sorted(normalized, key=lambda t: t["full_name"])


def _normalize_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    n = _normalize_float(numerator)
    d = _normalize_float(denominator)
    if n is None or d in (None, 0):
        return None
    return round(n / d, 3)


def _normalize_position(position: Any) -> str | None:
    if position is None:
        return None
    raw = str(position).strip().upper()
    if not raw:
        return None

    # Common values from nba_api: PG, SG, SF, PF, C, G, F, G-F, F-G, F-C, C-F
    mapping = {
        "G": "PG/SG",
        "F": "SF/PF",
        "PG": "PG",
        "SG": "SG",
        "SF": "SF",
        "PF": "PF",
        "C": "C",
        "G-F": "PG/SG/SF",
        "F-G": "SF/SG/PG",
        "F-C": "PF/C",
        "C-F": "C/PF",
        "PG-SG": "PG/SG",
        "SG-PG": "SG/PG",
        "SF-PF": "SF/PF",
        "PF-SF": "PF/SF",
        "SG-SF": "SG/SF",
        "SF-SG": "SF/SG",
    }
    return mapping.get(raw, raw.replace("-", "/"))


def _compose_rows(per_game: list[dict[str, Any]], advanced: list[dict[str, Any]], season: str) -> list[dict[str, Any]]:
    active_map = _active_players_map()
    advanced_by_id = {int(row["PLAYER_ID"]): row for row in advanced}

    rows: list[dict[str, Any]] = []
    for row in per_game:
        player_id = int(row["PLAYER_ID"])
        if player_id not in active_map:
            continue

        adv = advanced_by_id.get(player_id, {})
        rows.append(
            {
                "player_id": player_id,
                "player_name": row.get("PLAYER_NAME") or active_map[player_id],
                "team": row.get("TEAM_ABBREVIATION"),
                "team_id": int(row.get("TEAM_ID", 0)) if row.get("TEAM_ID") else None,
                "position": _normalize_position(row.get("PLAYER_POSITION") or row.get("POSITION")),
                "gp": int(row.get("GP", 0)) if row.get("GP") is not None else None,
                # Base stats
                "ppg": _normalize_float(row.get("PTS")),
                "rpg": _normalize_float(row.get("REB")),
                "apg": _normalize_float(row.get("AST")),
                "spg": _normalize_float(row.get("STL")),
                "bpg": _normalize_float(row.get("BLK")),
                "plus_minus": _normalize_float(row.get("PLUS_MINUS")),
                "fg_pct": _normalize_float(row.get("FG_PCT")),
                "ts_pct": _normalize_float(adv.get("TS_PCT")),
                "ft_pct": _normalize_float(row.get("FT_PCT")),
                "three_pt_pct": _normalize_float(row.get("FG3_PCT")),
                "pf_pg": _normalize_float(row.get("PF")),
                # Advanced-style fields
                "mpg": _normalize_float(row.get("MIN")),
                "off_rating": _normalize_float(adv.get("OFF_RATING")),
                "def_rating": _normalize_float(adv.get("DEF_RATING")),
                "net_rating": _normalize_float(adv.get("NET_RATING")),
                "ast_pct": _normalize_float(adv.get("AST_PCT")),
                "oreb_pct": _normalize_float(adv.get("OREB_PCT")),
                "dreb_pct": _normalize_float(adv.get("DREB_PCT")),
                "reb_pct": _normalize_float(adv.get("REB_PCT")),
                "stl_pct": _normalize_float(adv.get("STL_PCT")),
                "blk_pct": _normalize_float(adv.get("BLK_PCT")),
                "tov_pct": _normalize_float(adv.get("TM_TOV_PCT")),
                "usg_pct": _normalize_float(adv.get("USG_PCT")),
                "efg_pct": _normalize_float(adv.get("EFG_PCT")),
                "three_par": _safe_div(row.get("FG3A"), row.get("FGA")),
                "ftr": _safe_div(row.get("FTA"), row.get("FGA")),
                "pie": _normalize_float(adv.get("PIE")),
            }
        )

    return rows


def get_active_player_stats(season: str) -> list[dict[str, Any]]:
    key = (season, "active_player_stats")
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        per_game = _fetch_per_game_stats(season)
        advanced = _fetch_advanced_stats(season)
        rows = _compose_rows(per_game, advanced, season)
        cache.set(key, rows)
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[nba_stats] fetch failed for season={season}: {type(exc).__name__}: {exc}")
        stale = cache.get_stale(key)
        if stale is not None:
            return stale
        raise


def _team_win_pct_map(season: str) -> dict[int, float | None]:
    key = (season, "team_win_pct")
    cached = cache.get(key)
    if cached is not None:
        return cached

    base_rows = _fetch_team_base_stats(season)
    payload = {int(row["TEAM_ID"]): _normalize_float(row.get("W_PCT")) for row in base_rows}
    cache.set(key, payload)
    return payload


def _metric_min_max(rows: list[dict[str, Any]], metric: str) -> tuple[float | None, float | None]:
    values = [row.get(metric) for row in rows if row.get(metric) is not None]
    if not values:
        return None, None
    return min(values), max(values)


def _normalize_metric(value: float | None, min_val: float | None, max_val: float | None, lower_is_better: bool) -> float:
    if value is None or min_val is None or max_val is None:
        return 0.0
    if max_val == min_val:
        return 0.5
    raw = (value - min_val) / (max_val - min_val)
    return 1.0 - raw if lower_is_better else raw


def calculate_award_rankings(
    season: str,
    award: str,
    weights: dict[str, float],
    team_rating_weight: float,
    min_gp: int,
    top_n: int,
) -> dict[str, Any]:
    available = get_active_player_stats(season)
    eligible = [row for row in available if (row.get("gp") or 0) >= min_gp]

    award_upper = award.upper()

    if not eligible:
        raise ValueError("No eligible players found for the selected criteria.")

    valid_metric_keys = set(AWARD_METRIC_LABELS.keys())
    clean_weights: dict[str, float] = {}
    for metric, raw_weight in weights.items():
        if metric not in valid_metric_keys:
            continue
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if weight > 0:
            clean_weights[metric] = min(weight, 100.0)

    team_weight = max(0.0, min(float(team_rating_weight), 100.0))

    if not clean_weights and team_weight <= 0:
        raise ValueError("Please set at least one metric weight or team rating weight above 0.")

    metric_ranges = {
        metric: _metric_min_max(eligible, metric)
        for metric in clean_weights
    }

    team_win_pct = _team_win_pct_map(season)
    team_rows = [{"win_pct": team_win_pct.get(row.get("team_id") or -1)} for row in eligible]
    team_min, team_max = _metric_min_max(team_rows, "win_pct")

    total_weight = sum(clean_weights.values()) + team_weight
    scored_rows: list[dict[str, Any]] = []

    for row in eligible:
        contribution_map: dict[str, float] = {}
        weighted_sum = 0.0

        for metric, weight in clean_weights.items():
            min_val, max_val = metric_ranges[metric]
            norm = _normalize_metric(
                value=row.get(metric),
                min_val=min_val,
                max_val=max_val,
                lower_is_better=metric in LOWER_IS_BETTER_METRICS,
            )
            contribution = norm * weight
            weighted_sum += contribution
            contribution_map[metric] = round(contribution, 3)

        if team_weight > 0:
            win_pct = team_win_pct.get(row.get("team_id") or -1)
            team_norm = _normalize_metric(
                value=win_pct,
                min_val=team_min,
                max_val=team_max,
                lower_is_better=False,
            )
            team_contribution = team_norm * team_weight
            weighted_sum += team_contribution
            contribution_map["team_rating"] = round(team_contribution, 3)

        award_score = round((weighted_sum / total_weight) * 100, 3)

        scored_rows.append(
            {
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team": row["team"],
                "gp": row.get("gp"),
                "award_score": award_score,
                "team_win_pct": team_win_pct.get(row.get("team_id") or -1),
                "contributions": contribution_map,
            }
        )

    scored_rows = sorted(scored_rows, key=lambda r: r["award_score"], reverse=True)
    top_rows = scored_rows[:top_n]

    for idx, row in enumerate(top_rows, start=1):
        row["rank"] = idx

    return {
        "meta": {
            "season": season,
            "award": award_upper,
            "top_n": top_n,
            "min_gp": min_gp,
            "team_rating_weight": team_weight,
            "weights": clean_weights,
            "lower_is_better": sorted(list(LOWER_IS_BETTER_METRICS)),
            "eligible_players": len(eligible),
        },
        "data": top_rows,
    }


def _team_summary_for_season(team_id: int, season: str) -> dict[str, Any]:
    base_key = (season, "team_base_stats")
    adv_key = (season, "team_adv_stats")

    base_rows = cache.get(base_key)
    adv_rows = cache.get(adv_key)

    if base_rows is None:
        base_rows = _fetch_team_base_stats(season)
        cache.set(base_key, base_rows)

    if adv_rows is None:
        adv_rows = _fetch_team_advanced_stats(season)
        cache.set(adv_key, adv_rows)

    teams_by_id = {int(t["id"]): t for t in get_teams_directory()}
    team_base_by_id = {int(row["TEAM_ID"]): row for row in base_rows}
    team_adv_by_id = {int(row["TEAM_ID"]): row for row in adv_rows}

    base = team_base_by_id.get(team_id)
    if not base:
        raise ValueError(f"No team stats found for team_id={team_id} in season {season}.")

    adv = team_adv_by_id.get(team_id, {})
    info = teams_by_id.get(team_id, {"full_name": f"TEAM {team_id}", "abbreviation": "N/A"})
    wins = int(base.get("W", 0))
    losses = int(base.get("L", 0))

    return {
        "team_id": team_id,
        "season": season,
        "team_name": info["full_name"],
        "abbreviation": info["abbreviation"],
        "gp": int(base.get("GP", 0)) if base.get("GP") is not None else None,
        "ppg": _normalize_float(base.get("PTS")),
        "rpg": _normalize_float(base.get("REB")),
        "apg": _normalize_float(base.get("AST")),
        "spg": _normalize_float(base.get("STL")),
        "bpg": _normalize_float(base.get("BLK")),
        "plus_minus": _normalize_float(base.get("PLUS_MINUS")),
        "fg_pct": _normalize_float(base.get("FG_PCT")),
        "ts_pct": _normalize_float(adv.get("TS_PCT")),
        "ft_pct": _normalize_float(base.get("FT_PCT")),
        "three_pt_pct": _normalize_float(base.get("FG3_PCT")),
        "pf_pg": _normalize_float(base.get("PF")),
        "tov_pg": _normalize_float(base.get("TOV")),
        "off_rating": _normalize_float(adv.get("OFF_RATING")),
        "def_rating": _normalize_float(adv.get("DEF_RATING")),
        "win_pct": _normalize_float(base.get("W_PCT")),
        "team_record": f"{wins}-{losses}",
    }


def get_team_vs_team(season1: str, team1_id: int, season2: str, team2_id: int) -> dict[str, Any]:
    key = (season1 + ":" + season2, f"head_to_head:{team1_id}:{team2_id}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        team_1_summary = _team_summary_for_season(team_id=team1_id, season=season1)
        team_2_summary = _team_summary_for_season(team_id=team2_id, season=season2)

        players_team_1 = [row for row in get_active_player_stats(season1) if row.get("team_id") == team1_id]
        players_team_2 = [row for row in get_active_player_stats(season2) if row.get("team_id") == team2_id]

        players_team_1 = sorted(
            players_team_1,
            key=lambda r: (r.get("ppg") is None, -(r.get("ppg") or 0), r.get("player_name", "")),
        )
        players_team_2 = sorted(
            players_team_2,
            key=lambda r: (r.get("ppg") is None, -(r.get("ppg") or 0), r.get("player_name", "")),
        )

        payload = {
            "meta": {
                "season_1": season1,
                "season_2": season2,
                "team1_id": team1_id,
                "team2_id": team2_id,
            },
            "team_1": {"summary": team_1_summary, "players": players_team_1},
            "team_2": {"summary": team_2_summary, "players": players_team_2},
        }
        cache.set(key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        print(
            f"[nba_stats] head_to_head failed season1={season1} team1={team1_id} season2={season2} team2={team2_id}: "
            f"{type(exc).__name__}: {exc}"
        )
        stale = cache.get_stale(key)
        if stale is not None:
            return stale
        raise


def sort_rows(rows: list[dict[str, Any]], sort_by: str, order: str) -> list[dict[str, Any]]:
    if sort_by not in ALLOWED_SORT_KEYS:
        raise ValueError(f"Invalid sort_by '{sort_by}'.")
    reverse = order.lower() == "desc"

    def sort_key(item: dict[str, Any]):
        value = item.get(sort_by)
        if value is None:
            return float("-inf") if reverse else float("inf")
        if isinstance(value, str):
            return value.lower()
        return value

    return sorted(rows, key=sort_key, reverse=reverse)
