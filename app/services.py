import os
import threading
import time
from datetime import datetime
from typing import Any

from nba_api.stats.endpoints import leaguedashlineups, leaguedashplayerbiostats, leaguedashplayerstats, leaguedashteamstats
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


def _fetch_per_game_stats(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star=season_type,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Base",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _fetch_advanced_stats(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    endpoint = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        season_type_all_star=season_type,
        per_mode_detailed="PerGame",
        measure_type_detailed_defense="Advanced",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def _fetch_player_bio_stats(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    endpoint = leaguedashplayerbiostats.LeagueDashPlayerBioStats(
        season=season,
        season_type_all_star=season_type,
        per_mode_simple="PerGame",
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


def _compose_rows(
    per_game: list[dict[str, Any]],
    advanced: list[dict[str, Any]],
    bio_stats: list[dict[str, Any]],
    season: str,
) -> list[dict[str, Any]]:
    active_map = _active_players_map()
    advanced_by_id = {int(row["PLAYER_ID"]): row for row in advanced}
    bio_by_id = {int(row["PLAYER_ID"]): row for row in bio_stats if row.get("PLAYER_ID") is not None}

    rows: list[dict[str, Any]] = []
    for row in per_game:
        player_id = int(row["PLAYER_ID"])
        if player_id not in active_map:
            continue

        adv = advanced_by_id.get(player_id, {})
        bio = bio_by_id.get(player_id, {})
        rows.append(
            {
                "player_id": player_id,
                "player_name": row.get("PLAYER_NAME") or active_map[player_id],
                "team": row.get("TEAM_ABBREVIATION"),
                "team_id": int(row.get("TEAM_ID", 0)) if row.get("TEAM_ID") else None,
                "position": _normalize_position(
                    bio.get("PLAYER_POSITION")
                    or row.get("PLAYER_POSITION")
                    or row.get("POSITION")
                ),
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


def get_active_player_stats(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    season_type_key = season_type.lower().replace(" ", "_")
    key = (season, f"active_player_stats:{season_type_key}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        per_game = _fetch_per_game_stats(season, season_type=season_type)
        advanced = _fetch_advanced_stats(season, season_type=season_type)
        bio_stats = _fetch_player_bio_stats(season, season_type=season_type)
        rows = _compose_rows(per_game, advanced, bio_stats, season)
        cache.set(key, rows)
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[nba_stats] fetch failed for season={season} season_type={season_type}: {type(exc).__name__}: {exc}")
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


LINEUP_SORT_LABELS = {
    "MIN": "Minutes Together",
    "GP": "Games Played",
    "W": "Wins",
    "L": "Losses",
    "W_PCT": "Win %",
    "OFF_RATING": "Off Rating",
    "DEF_RATING": "Def Rating",
    "NET_RATING": "Net Rating",
    "AST_PCT": "AST%",
    "OREB_PCT": "OREB%",
    "DREB_PCT": "DREB%",
    "REB_PCT": "REB%",
    "TS_PCT": "TS%",
    "EFG_PCT": "eFG%",
    "TOV_PCT": "TOV%",
    "PACE": "Pace",
    "PIE": "PIE",
    "PLUS_MINUS": "+/-",
}


def get_lineup_sort_options() -> list[dict[str, str]]:
    return [{"key": key, "label": label} for key, label in LINEUP_SORT_LABELS.items()]


def _fetch_lineups_for_team(season: str, team_id: int) -> list[dict[str, Any]]:
    endpoint = leaguedashlineups.LeagueDashLineups(
        season=season,
        season_type_all_star="Regular Season",
        team_id_nullable=str(team_id),
        per_mode_detailed="Totals",
        measure_type_detailed_defense="Advanced",
        group_quantity="5",
    )
    return endpoint.get_data_frames()[0].to_dict("records")


def get_team_lineups(
    team_id: int,
    season: str,
    top_n: int,
    min_minutes: float,
    min_games: int,
    sort_by: str,
    order: str,
) -> dict[str, Any]:
    if sort_by not in LINEUP_SORT_LABELS:
        raise ValueError(f"Invalid lineup sort_by '{sort_by}'.")

    key = (season, f"lineups:{team_id}")
    rows = cache.get(key)
    if rows is None:
        try:
            rows = _fetch_lineups_for_team(season=season, team_id=team_id)
            cache.set(key, rows)
        except Exception as exc:  # noqa: BLE001
            stale = cache.get_stale(key)
            if stale is None:
                raise
            print(f"[nba_stats] lineups fetch failed, returning stale cache: {exc}")
            rows = stale

    teams_by_id = {int(t["id"]): t for t in get_teams_directory()}
    team_info = teams_by_id.get(int(team_id), {"id": int(team_id), "full_name": f"TEAM {team_id}", "abbreviation": "N/A"})

    filtered = [
        row
        for row in rows
        if float(row.get("MIN", 0) or 0) >= float(min_minutes)
        and int(float(row.get("GP", 0) or 0)) >= int(min_games)
    ]

    reverse = order.lower() == "desc"

    def lineup_sort_key(item: dict[str, Any]):
        value = item.get(sort_by)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf") if reverse else float("inf")

    filtered = sorted(filtered, key=lineup_sort_key, reverse=reverse)
    top_rows = filtered[:top_n]

    normalized = []
    for idx, row in enumerate(top_rows, start=1):
        normalized.append(
            {
                "rank": idx,
                "lineup": row.get("GROUP_NAME") or row.get("GROUP_ID") or "N/A",
                "min": _normalize_float(row.get("MIN")),
                "gp": int(row.get("GP", 0)) if row.get("GP") is not None else None,
                "off_rating": _normalize_float(row.get("OFF_RATING")),
                "def_rating": _normalize_float(row.get("DEF_RATING")),
                "net_rating": _normalize_float(row.get("NET_RATING")),
                "ast_pct": _normalize_float(row.get("AST_PCT")),
                "reb_pct": _normalize_float(row.get("REB_PCT")),
                "efg_pct": _normalize_float(row.get("EFG_PCT")),
                "ts_pct": _normalize_float(row.get("TS_PCT")),
                "pie": _normalize_float(row.get("PIE")),
            }
        )

    return {
        "meta": {
            "season": season,
            "team_id": team_info["id"],
            "team_name": team_info["full_name"],
            "team_abbreviation": team_info["abbreviation"],
            "top_n": top_n,
            "min_minutes": min_minutes,
            "min_games": min_games,
            "sort_by": sort_by,
            "order": order,
            "total": len(filtered),
        },
        "data": normalized,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_shot_diet_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """Build a stable, always-available shot-diet proxy from player season stats.

    - three_rate: share of FGA that are 3PA (`three_par`).
    - paint_rate and midrange_rate split remaining 2PA using a free-throw-rate proxy
      (players who draw more FTs are typically more rim/paint oriented).
    """
    result: dict[int, dict[str, float]] = {}
    for row in rows:
        player_id = int(_safe_float(row.get("player_id"), 0))
        if not player_id:
            continue

        three_rate = min(1.0, max(0.0, _safe_float(row.get("three_par"), 0.0)))
        two_point_rate = 1.0 - three_rate

        # Paint share proxy of 2PA derived from FTr; bounded to avoid extreme outputs.
        ftr = min(1.0, max(0.0, _safe_float(row.get("ftr"), 0.0)))
        paint_share_of_twos = min(0.85, max(0.2, 0.25 + (ftr * 0.9)))

        paint_rate = two_point_rate * paint_share_of_twos
        midrange_rate = max(0.0, 1.0 - three_rate - paint_rate)

        result[player_id] = {
            "three_rate": three_rate,
            "paint_rate": paint_rate,
            "midrange_rate": midrange_rate,
        }

    return result


def _normalize_matrix(values: list[list[float]]) -> list[list[float]]:
    if not values:
        return []

    cols = len(values[0])
    means = [sum(row[c] for row in values) / len(values) for c in range(cols)]
    stds = []
    for c in range(cols):
        var = sum((row[c] - means[c]) ** 2 for row in values) / len(values)
        stds.append(var**0.5 if var > 0 else 1.0)

    return [[(row[c] - means[c]) / stds[c] for c in range(cols)] for row in values]


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = sum(a * a for a in vec_a) ** 0.5
    mag_b = sum(b * b for b in vec_b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _fit_archetypes(feature_rows: list[list[float]], n_clusters: int = 6, iterations: int = 15) -> list[int]:
    # Lightweight K-means implementation (no sklearn dependency).
    if not feature_rows:
        return []

    n_clusters = max(1, min(n_clusters, len(feature_rows)))
    centroids = [feature_rows[i][:] for i in range(n_clusters)]
    labels = [0 for _ in feature_rows]

    for _ in range(iterations):
        for i, row in enumerate(feature_rows):
            best_cluster = 0
            best_dist = float("inf")
            for c, center in enumerate(centroids):
                dist = sum((row[k] - center[k]) ** 2 for k in range(len(row)))
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = c
            labels[i] = best_cluster

        for c in range(n_clusters):
            members = [feature_rows[i] for i, label in enumerate(labels) if label == c]
            if not members:
                continue
            centroids[c] = [sum(row[k] for row in members) / len(members) for k in range(len(members[0]))]

    return labels


def get_player_similarity(
    season: str,
    player_name: str,
    top_n: int,
    min_minutes: int,
    include_shot_diet: bool,
    archetype_only: bool,
) -> dict[str, Any]:
    rows = get_active_player_stats(season=season)
    filtered = [
        row
        for row in rows
        if int(_safe_float(row.get("gp"), 0) * _safe_float(row.get("mpg"), 0)) >= int(min_minutes)
    ]

    if len(filtered) < 2:
        raise ValueError("Not enough eligible players for similarity. Lower min_minutes or try another season.")

    target_idx = next((i for i, row in enumerate(filtered) if row.get("player_name", "").lower() == player_name.lower()), None)
    if target_idx is None:
        raise ValueError(f"Player '{player_name}' not found in eligible player pool for {season}.")

    base_features = ["ppg", "apg", "rpg", "spg", "bpg", "tov_pct", "ts_pct", "usg_pct", "ast_pct", "reb_pct"]
    feature_weights = {
        "ppg": 1.0,
        "apg": 1.15,
        "rpg": 0.9,
        "spg": 0.8,
        "bpg": 0.8,
        "tov_pct": -0.6,
        "ts_pct": 1.05,
        "usg_pct": 1.0,
        "ast_pct": 1.0,
        "reb_pct": 0.8,
    }

    shot_map: dict[int, dict[str, float]] = {}
    shot_diet_included = False
    if include_shot_diet:
        try:
            shot_map = _build_shot_diet_map(filtered)
            if shot_map:
                base_features += ["three_rate", "paint_rate", "midrange_rate"]
                feature_weights.update(
                    {
                        "three_rate": 1.0,
                        "paint_rate": 0.9,
                        "midrange_rate": 0.8,
                    }
                )
                shot_diet_included = True
        except Exception:
            shot_diet_included = False

    matrix: list[list[float]] = []
    for row in filtered:
        player_id = int(_safe_float(row.get("player_id"), 0))
        shot = shot_map.get(player_id, {})
        vector = []
        for key in base_features:
            if key in shot:
                vector.append(_safe_float(shot.get(key), 0.0))
            else:
                vector.append(_safe_float(row.get(key), 0.0))
        matrix.append(vector)

    matrix = _normalize_matrix(matrix)
    for i, vec in enumerate(matrix):
        matrix[i] = [vec[j] * feature_weights.get(base_features[j], 1.0) for j in range(len(base_features))]

    labels: list[int] | None = None
    if archetype_only and len(filtered) >= 12:
        archetype_features = ["usg_pct", "ast_pct", "reb_pct", "ts_pct"]
        if shot_diet_included:
            archetype_features += ["three_rate", "midrange_rate", "paint_rate"]

        archetype_matrix = []
        for row in filtered:
            player_id = int(_safe_float(row.get("player_id"), 0))
            shot = shot_map.get(player_id, {})
            archetype_matrix.append([
                _safe_float(shot.get(key), 0.0) if key in shot else _safe_float(row.get(key), 0.0) for key in archetype_features
            ])

        labels = _fit_archetypes(_normalize_matrix(archetype_matrix), n_clusters=6)

    target_vec = matrix[target_idx]
    candidates: list[dict[str, Any]] = []
    target_cluster = labels[target_idx] if labels else None

    for i, row in enumerate(filtered):
        if i == target_idx:
            continue
        if labels and archetype_only and labels[i] != target_cluster:
            continue
        score = _cosine_similarity(target_vec, matrix[i])
        candidates.append(
            {
                "player_name": row.get("player_name"),
                "team": row.get("team"),
                "similarity": round(score, 4),
                "archetype": f"Cluster {labels[i] + 1}" if labels else None,
                "ppg": row.get("ppg"),
                "apg": row.get("apg"),
                "rpg": row.get("rpg"),
                "ts_pct": row.get("ts_pct"),
                "usg_pct": row.get("usg_pct"),
            }
        )

    candidates = sorted(candidates, key=lambda r: r["similarity"], reverse=True)
    top_rows = candidates[:top_n]
    for rank, row in enumerate(top_rows, start=1):
        row["rank"] = rank

    return {
        "meta": {
            "season": season,
            "target_player_name": filtered[target_idx].get("player_name"),
            "candidate_count": len(candidates),
            "top_n": top_n,
            "min_minutes": min_minutes,
            "shot_diet_requested": include_shot_diet,
            "shot_diet_included": shot_diet_included,
            "archetype_only": archetype_only,
            "target_archetype": f"Cluster {target_cluster + 1}" if target_cluster is not None else None,
            "features": base_features,
            "shot_diet_source": "season-stats-proxy" if shot_diet_included else None,
        },
        "data": top_rows,
    }
