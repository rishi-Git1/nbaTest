import os
import threading
import time
from datetime import datetime
from typing import Any

import pandas as pd

from nba_api.stats.endpoints import boxscoreadvancedv2, boxscoreadvancedv3, boxscoretraditionalv2, boxscoretraditionalv3, leaguegamefinder, leaguedashlineups, leaguedashplayerbiostats, leaguedashplayerstats, leaguedashteamstats, playercareerstats
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


def get_player_directory(active_only: bool = False) -> list[dict[str, Any]]:
    source = players.get_active_players() if active_only else players.get_players()
    directory = [
        {
            "player_id": int(player["id"]),
            "player_name": player["full_name"],
            "is_active": bool(player.get("is_active", active_only)),
        }
        for player in source
        if player.get("full_name")
    ]
    return sorted(directory, key=lambda item: item["player_name"])


def _resolve_player_lookup(player_name: str) -> dict[str, Any]:
    normalized = _normalize_player_name_for_match(player_name)
    if not normalized:
        raise ValueError("A player name is required.")

    directory = get_player_directory(active_only=False)
    exact_match = next((player for player in directory if _normalize_player_name_for_match(player["player_name"]) == normalized), None)
    if exact_match is not None:
        return exact_match

    contains_matches = [player for player in directory if normalized in _normalize_player_name_for_match(player["player_name"])]
    if len(contains_matches) == 1:
        return contains_matches[0]
    if len(contains_matches) > 1:
        suggestions = ", ".join(match["player_name"] for match in contains_matches[:5])
        raise ValueError(f"Multiple players matched '{player_name}'. Try one of: {suggestions}")

    raise ValueError(f"Player '{player_name}' was not found.")


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_total_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 3)


def _get_player_career_totals(player_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    key = (str(player_id), "player_career_totals")
    cached = cache.get(key)
    if cached is not None:
        return cached

    endpoint = playercareerstats.PlayerCareerStats(player_id=player_id, per_mode36="Totals")
    frames = endpoint.get_data_frames()
    if len(frames) < 2:
        raise ValueError("Career stats were unavailable for that player.")

    regular_seasons = frames[0].copy()
    career_totals = frames[1].copy()
    cache.set(key, (regular_seasons, career_totals))
    return regular_seasons, career_totals


def _get_advanced_rows_by_season(season: str) -> dict[int, dict[str, Any]]:
    key = (season, "advanced_rows_by_season")
    cached = cache.get(key)
    if cached is not None:
        return cached

    rows = _fetch_advanced_stats(season=season, season_type="Regular Season")
    payload = {int(row["PLAYER_ID"]): row for row in rows if row.get("PLAYER_ID") is not None}
    cache.set(key, payload)
    return payload


def _coerce_season_id(value: Any) -> str:
    season = str(value or "").strip()
    if len(season) == 5 and season.isdigit():
        start = int(season[-4:])
        return f"{start}-{str(start + 1)[-2:]}"
    return season


def _prepare_career_season_totals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        season = _coerce_season_id(row.get("SEASON_ID"))
        if not season or _safe_int(row.get("GP")) <= 0:
            continue
        grouped.setdefault(season, []).append(row)

    prepared: list[dict[str, Any]] = []
    numeric_fields = ["GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "PF"]
    for season, season_rows in grouped.items():
        if len(season_rows) == 1:
            prepared.append(season_rows[0])
            continue

        tot_row = next((row for row in season_rows if str(row.get("TEAM_ABBREVIATION") or "").upper() == "TOT"), None)
        if tot_row is not None:
            prepared.append(tot_row)
            continue

        merged = dict(season_rows[0])
        merged["SEASON_ID"] = season
        merged["TEAM_ABBREVIATION"] = "/".join(sorted({str(row.get("TEAM_ABBREVIATION") or "").strip() for row in season_rows if row.get("TEAM_ABBREVIATION")})) or None
        for field in numeric_fields:
            merged[field] = sum(float(row.get(field) or 0) for row in season_rows)
        prepared.append(merged)

    return sorted(prepared, key=lambda row: _coerce_season_id(row.get("SEASON_ID")))


def _base_season_row_from_totals(row: dict[str, Any]) -> dict[str, Any]:
    gp = _safe_int(row.get("GP"))
    minutes = float(row.get("MIN") or 0)
    fga = float(row.get("FGA") or 0)
    fg3a = float(row.get("FG3A") or 0)
    fta = float(row.get("FTA") or 0)
    pts = float(row.get("PTS") or 0)

    return {
        "season": _coerce_season_id(row.get("SEASON_ID")),
        "team": row.get("TEAM_ABBREVIATION") or row.get("TEAM_ID"),
        "gp": gp,
        "mpg": _normalize_float(minutes / gp) if gp else None,
        "ppg": _normalize_float(pts / gp) if gp else None,
        "rpg": _normalize_float(float(row.get("REB") or 0) / gp) if gp else None,
        "apg": _normalize_float(float(row.get("AST") or 0) / gp) if gp else None,
        "spg": _normalize_float(float(row.get("STL") or 0) / gp) if gp else None,
        "bpg": _normalize_float(float(row.get("BLK") or 0) / gp) if gp else None,
        "fg_pct": _safe_total_ratio(float(row.get("FGM") or 0), fga),
        "ft_pct": _safe_total_ratio(float(row.get("FTM") or 0), fta),
        "three_pt_pct": _safe_total_ratio(float(row.get("FG3M") or 0), fg3a),
        "pf_pg": _normalize_float(float(row.get("PF") or 0) / gp) if gp else None,
        "three_par": _safe_total_ratio(fg3a, fga),
        "ftr": _safe_total_ratio(fta, fga),
        "ts_pct": _safe_total_ratio(pts, 2 * (fga + 0.44 * fta)),
        "total_minutes": minutes,
        "total_fga": fga,
        "total_fg3a": fg3a,
        "total_fg3m": float(row.get("FG3M") or 0),
        "total_fta": fta,
        "total_points": pts,
        "total_fgm": float(row.get("FGM") or 0),
        "total_ftm": float(row.get("FTM") or 0),
    }


def _merge_career_advanced(base_row: dict[str, Any], advanced_row: dict[str, Any] | None) -> dict[str, Any]:
    merged = {k: v for k, v in base_row.items() if not k.startswith("total_")}
    adv = advanced_row or {}
    merged.update(
        {
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
            "pie": _normalize_float(adv.get("PIE")),
        }
    )
    return merged


def _weighted_average(values: list[tuple[float | None, float]]) -> float | None:
    valid = [(value, weight) for value, weight in values if value is not None and weight > 0]
    if not valid:
        return None
    total_weight = sum(weight for _, weight in valid)
    if total_weight == 0:
        return None
    return round(sum(value * weight for value, weight in valid) / total_weight, 3)


def get_player_career_stats(player_name: str) -> dict[str, Any]:
    player = _resolve_player_lookup(player_name)
    player_id = int(player["player_id"])
    regular_seasons_df, _career_totals_df = _get_player_career_totals(player_id)
    if regular_seasons_df.empty:
        raise ValueError(f"No career regular-season stats found for '{player['player_name']}'.")

    season_rows_raw = _prepare_career_season_totals(regular_seasons_df.to_dict("records"))
    season_base_rows = [_base_season_row_from_totals(row) for row in season_rows_raw]
    if not season_base_rows:
        raise ValueError(f"No career regular-season stats found for '{player['player_name']}'.")

    advanced_maps = {season_row["season"]: _get_advanced_rows_by_season(season_row["season"]) for season_row in season_base_rows}
    season_rows: list[dict[str, Any]] = []
    for base_row in season_base_rows:
        advanced_row = advanced_maps.get(base_row["season"], {}).get(player_id)
        season_rows.append(_merge_career_advanced(base_row, advanced_row))

    total_gp = sum(row["gp"] or 0 for row in season_base_rows)
    total_minutes = sum(row.get("total_minutes", 0) for row in season_base_rows)
    total_fga = sum(row.get("total_fga", 0) for row in season_base_rows)
    total_fg3a = sum(row.get("total_fg3a", 0) for row in season_base_rows)
    total_fta = sum(row.get("total_fta", 0) for row in season_base_rows)
    total_points = sum(row.get("total_points", 0) for row in season_base_rows)
    total_fgm = sum(row.get("total_fgm", 0) for row in season_base_rows)
    total_fg3m = sum(row.get("total_fg3m", 0) for row in season_base_rows)
    total_ftm = sum(row.get("total_ftm", 0) for row in season_base_rows)

    career_team_tokens: list[str] = []
    has_multi_team_season = False
    for row in season_base_rows:
        raw_team = str(row.get("team") or "").strip()
        if not raw_team:
            continue
        upper_team = raw_team.upper()
        if upper_team == "TOT" or "/" in raw_team:
            has_multi_team_season = True
        for token in raw_team.split("/"):
            cleaned = token.strip().upper()
            if cleaned and cleaned not in {"TOT", "MULTI"} and cleaned not in career_team_tokens:
                career_team_tokens.append(cleaned)

    career_team_label = career_team_tokens[0] if len(career_team_tokens) == 1 and not has_multi_team_season else "MULTI"
    career_base = {
        "season": "CAREER",
        "team": career_team_label,
        "gp": total_gp,
        "mpg": _normalize_float(total_minutes / total_gp) if total_gp else None,
        "ppg": _normalize_float(total_points / total_gp) if total_gp else None,
        "rpg": _weighted_average([(row.get("rpg"), row.get("gp") or 0) for row in season_base_rows]),
        "apg": _weighted_average([(row.get("apg"), row.get("gp") or 0) for row in season_base_rows]),
        "spg": _weighted_average([(row.get("spg"), row.get("gp") or 0) for row in season_base_rows]),
        "bpg": _weighted_average([(row.get("bpg"), row.get("gp") or 0) for row in season_base_rows]),
        "fg_pct": _safe_total_ratio(total_fgm, total_fga),
        "ft_pct": _safe_total_ratio(total_ftm, total_fta),
        "three_pt_pct": _safe_total_ratio(total_fg3m, total_fg3a),
        "pf_pg": _weighted_average([(row.get("pf_pg"), row.get("gp") or 0) for row in season_base_rows]),
        "three_par": _safe_total_ratio(total_fg3a, total_fga),
        "ftr": _safe_total_ratio(total_fta, total_fga),
        "ts_pct": _safe_total_ratio(total_points, 2 * (total_fga + 0.44 * total_fta)),
    }
    career_row = _merge_career_advanced(career_base, None)
    for key in ["off_rating", "def_rating", "net_rating", "ast_pct", "oreb_pct", "dreb_pct", "reb_pct", "stl_pct", "blk_pct", "tov_pct", "usg_pct", "efg_pct", "pie"]:
        career_row[key] = _weighted_average([(row.get(key), row.get("gp") or 0) for row in season_rows])

    season_rows = sorted(season_rows, key=lambda row: row.get("season") or "")
    return {
        "meta": {
            "player_id": player_id,
            "player_name": player["player_name"],
            "season_count": len(season_rows),
            "advanced_available": any(row.get("ts_pct") is not None or row.get("off_rating") is not None for row in season_rows),
        },
        "career": career_row,
        "seasons": season_rows,
    }



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


GAME_EXPLAINER_METRICS = [
    {"key": "pts", "label": "PTS", "lower_is_better": False},
    {"key": "reb", "label": "REB", "lower_is_better": False},
    {"key": "ast", "label": "AST", "lower_is_better": False},
    {"key": "tov", "label": "TOV", "lower_is_better": True},
    {"key": "pf", "label": "FOULS", "lower_is_better": True},
    {"key": "fg_pct", "label": "FG%", "lower_is_better": False},
    {"key": "fg3_pct", "label": "3P%", "lower_is_better": False},
    {"key": "ft_pct", "label": "FT%", "lower_is_better": False},
    {"key": "plus_minus", "label": "+/-", "lower_is_better": False},
    {"key": "off_rating", "label": "OFF RTG", "lower_is_better": False},
    {"key": "def_rating", "label": "DEF RTG", "lower_is_better": True},
    {"key": "net_rating", "label": "NET RTG", "lower_is_better": False},
    {"key": "pace", "label": "PACE", "lower_is_better": False},
]


def _season_range(start_season: str | None, end_season: str | None) -> list[str]:
    default = get_current_season()
    start_value = start_season or default
    end_value = end_season or start_value

    try:
        start_year = int(str(start_value).split("-")[0])
        end_year = int(str(end_value).split("-")[0])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("Invalid season range.") from exc

    low = min(start_year, end_year)
    high = max(start_year, end_year)
    return [f"{year}-{str(year + 1)[-2:]}" for year in range(high, low - 1, -1)]


def _fetch_game_explainer_game_rows(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    try:
        endpoint = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
            player_or_team_abbreviation="T",
        )
    except TypeError:
        endpoint = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
        )
    return endpoint.get_data_frames()[0].to_dict("records")


def _normalize_minutes_value(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    if ":" in text:
        parts = text.split(":")
        try:
            minutes = float(parts[0])
            seconds = float(parts[1]) if len(parts) > 1 else 0.0
            return round(minutes + seconds / 60.0, 3)
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _get_game_explainer_games_df(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    key = (season, f"game_explainer_games:{season_type.lower().replace(' ', '_')}")
    cached = cache.get(key)
    if cached is not None:
        return pd.DataFrame(cached)

    try:
        rows = _fetch_game_explainer_game_rows(season=season, season_type=season_type)
        df = pd.DataFrame(rows)
        if df.empty:
            cache.set(key, [])
            return df

        if "TEAM_ID" not in df.columns or "GAME_ID" not in df.columns:
            raise ValueError("Game data did not include required team fields.")

        df = df.copy()
        df["GAME_DATE"] = pd.to_datetime(df.get("GAME_DATE"), errors="coerce")
        df = df.dropna(subset=["GAME_DATE"])
        df = df.drop_duplicates(subset=["GAME_ID", "TEAM_ID"])
        for col in ["PTS"]:
            if col not in df.columns:
                df[col] = 0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        payload = df.to_dict("records")
        cache.set(key, payload)
        return df
    except Exception:
        stale = cache.get_stale(key)
        if stale is not None:
            return pd.DataFrame(stale)
        raise


def _build_unique_game_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []

    results: list[dict[str, Any]] = []
    for game_id, group in df.groupby("GAME_ID"):
        rows = group.to_dict("records")
        if not rows:
            continue

        rows = sorted(rows, key=lambda row: (0 if "vs." in str(row.get("MATCHUP") or "") else 1, str(row.get("TEAM_ABBREVIATION") or "")))
        home = next((row for row in rows if "vs." in str(row.get("MATCHUP") or "")), rows[0])
        away = next((row for row in rows if row is not home), rows[0] if len(rows) == 1 else rows[1])

        results.append(
            {
                "game_id": str(game_id),
                "game_date": home.get("GAME_DATE").strftime("%Y-%m-%d") if pd.notna(home.get("GAME_DATE")) else None,
                "season_id": str(home.get("SEASON_ID") or ""),
                "season": _coerce_season_id(home.get("SEASON_ID")),
                "matchup": f"{away.get('TEAM_ABBREVIATION', 'AWY')} @ {home.get('TEAM_ABBREVIATION', 'HME')}",
                "score": f"{away.get('TEAM_ABBREVIATION', 'AWY')} {int(away.get('PTS', 0))} - {int(home.get('PTS', 0))} {home.get('TEAM_ABBREVIATION', 'HME')}",
                "team_1_id": int(away.get("TEAM_ID")) if away.get("TEAM_ID") is not None else None,
                "team_2_id": int(home.get("TEAM_ID")) if home.get("TEAM_ID") is not None else None,
                "team_1_abbreviation": away.get("TEAM_ABBREVIATION"),
                "team_2_abbreviation": home.get("TEAM_ABBREVIATION"),
                "team_1_name": away.get("TEAM_NAME"),
                "team_2_name": home.get("TEAM_NAME"),
                "team_1_pts": int(away.get("PTS", 0)),
                "team_2_pts": int(home.get("PTS", 0)),
            }
        )

    return sorted(results, key=lambda row: (row.get("game_date") or "", row.get("game_id") or ""), reverse=True)


def get_game_explainer_games(
    date: str | None = None,
    team1_id: int | None = None,
    team2_id: int | None = None,
    season_start: str | None = None,
    season_end: str | None = None,
    season_type: str = "Regular Season",
) -> dict[str, Any]:
    if date:
        pd.to_datetime(date, errors="raise")
    elif not (team1_id and team2_id):
        raise ValueError("Provide either a date or both teams.")
    elif int(team1_id) == int(team2_id):
        raise ValueError("Choose two different teams for matchup search.")

    seasons = _season_range(season_start, season_end)
    frames = [_get_game_explainer_games_df(season=season, season_type=season_type) for season in seasons]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return {"meta": {"total": 0, "seasons": seasons, "season_type": season_type}, "data": []}

    combined = pd.concat(frames, ignore_index=True)
    if date:
        target_date = pd.to_datetime(date).date()
        combined = combined[combined["GAME_DATE"].dt.date == target_date]
    else:
        team_ids = {int(team1_id), int(team2_id)}
        combined = combined[combined["TEAM_ID"].isin(team_ids)]

    unique_games = _build_unique_game_rows(combined)
    if not date:
        unique_games = [row for row in unique_games if {row.get("team_1_id"), row.get("team_2_id")} == {int(team1_id), int(team2_id)}]

    return {
        "meta": {
            "date": date,
            "team1_id": team1_id,
            "team2_id": team2_id,
            "season_start": seasons[-1],
            "season_end": seasons[0],
            "season_type": season_type,
            "total": len(unique_games),
        },
        "data": unique_games,
    }


def _normalize_boxscore_traditional_v3(player_stats: pd.DataFrame, team_stats: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    player_df = player_stats.rename(
        columns={
            "personId": "PLAYER_ID",
            "teamId": "TEAM_ID",
            "teamTricode": "TEAM_ABBREVIATION",
            "minutes": "MIN",
            "points": "PTS",
            "reboundsTotal": "REB",
            "assists": "AST",
            "fieldGoalsMade": "FGM",
            "fieldGoalsAttempted": "FGA",
            "threePointersMade": "FG3M",
            "plusMinusPoints": "PLUS_MINUS",
        }
    ).copy()
    if "PLAYER_NAME" not in player_df.columns:
        player_df["PLAYER_NAME"] = (player_df.get("firstName", "").fillna("") + " " + player_df.get("familyName", "").fillna("")).str.strip()
        if "nameI" in player_df.columns:
            player_df.loc[player_df["PLAYER_NAME"] == "", "PLAYER_NAME"] = player_df.loc[player_df["PLAYER_NAME"] == "", "nameI"]

    team_df = team_stats.rename(
        columns={
            "teamId": "TEAM_ID",
            "teamName": "TEAM_NAME",
            "teamTricode": "TEAM_ABBREVIATION",
            "minutes": "MIN",
            "points": "PTS",
            "reboundsTotal": "REB",
            "assists": "AST",
            "turnovers": "TO",
            "foulsPersonal": "PF",
            "fieldGoalsPercentage": "FG_PCT",
            "threePointersPercentage": "FG3_PCT",
            "freeThrowsPercentage": "FT_PCT",
            "plusMinusPoints": "PLUS_MINUS",
            "gameId": "GAME_ID",
        }
    ).copy()
    return player_df, team_df


def _normalize_boxscore_advanced_v3(player_stats: pd.DataFrame, team_stats: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    player_df = player_stats.rename(
        columns={
            "personId": "PLAYER_ID",
            "teamId": "TEAM_ID",
            "usagePercentage": "USG_PCT",
            "trueShootingPercentage": "TS_PCT",
        }
    ).copy()
    team_df = team_stats.rename(
        columns={
            "teamId": "TEAM_ID",
            "teamName": "TEAM_NAME",
            "teamTricode": "TEAM_ABBREVIATION",
            "offensiveRating": "OFF_RATING",
            "defensiveRating": "DEF_RATING",
            "netRating": "NET_RATING",
            "pace": "PACE",
        }
    ).copy()
    return player_df, team_df


def _fetch_boxscore_traditional(game_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        endpoint = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        player_df = endpoint.player_stats.get_data_frame().copy()
        team_df = endpoint.team_stats.get_data_frame().copy()
        return player_df, team_df
    except Exception:
        endpoint = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        player_df = endpoint.player_stats.get_data_frame().copy()
        team_df = endpoint.team_stats.get_data_frame().copy()
        return _normalize_boxscore_traditional_v3(player_df, team_df)


def _fetch_boxscore_advanced(game_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        endpoint = boxscoreadvancedv2.BoxScoreAdvancedV2(game_id=game_id)
        player_df = endpoint.player_stats.get_data_frame().copy()
        team_df = endpoint.team_stats.get_data_frame().copy()
        return player_df, team_df
    except Exception:
        endpoint = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id)
        player_df = endpoint.player_stats.get_data_frame().copy()
        team_df = endpoint.team_stats.get_data_frame().copy()
        return _normalize_boxscore_advanced_v3(player_df, team_df)


def _game_explainer_winner(value1: Any, value2: Any, lower_is_better: bool) -> str:
    if value1 is None or value2 is None:
        return "none"
    if value1 == value2:
        return "tie"
    if lower_is_better:
        return "team_1" if value1 < value2 else "team_2"
    return "team_1" if value1 > value2 else "team_2"


def _normalize_game_explainer_team_rows(team_stats: pd.DataFrame, adv_team: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    merged = team_stats.merge(adv_team, on=["TEAM_ID"], how="left", suffixes=("", "_ADV"))
    if merged.empty or len(merged.index) < 2:
        raise ValueError("Team box score data was unavailable for that game. This usually means the game has no published full box score yet.")

    team_rows = []
    for _, row in merged.iterrows():
        team_rows.append(
            {
                "team_id": int(row.get("TEAM_ID")),
                "team_name": row.get("TEAM_NAME"),
                "team_abbreviation": row.get("TEAM_ABBREVIATION"),
                "pts": int(row.get("PTS", 0)),
                "reb": int(row.get("REB", 0)),
                "ast": int(row.get("AST", 0)),
                "tov": int(row.get("TO", row.get("TOV", 0))),
                "pf": int(row.get("PF", 0)),
                "fg_pct": _normalize_float(row.get("FG_PCT")),
                "fg3_pct": _normalize_float(row.get("FG3_PCT")),
                "ft_pct": _normalize_float(row.get("FT_PCT")),
                "plus_minus": _normalize_float(row.get("PLUS_MINUS")),
                "off_rating": _normalize_float(row.get("OFF_RATING")),
                "def_rating": _normalize_float(row.get("DEF_RATING")),
                "net_rating": _normalize_float(row.get("NET_RATING")),
                "pace": _normalize_float(row.get("PACE")),
            }
        )

    team_rows = sorted(team_rows, key=lambda row: row.get("pts") or 0, reverse=True)
    team_1 = team_rows[0]
    team_2 = team_rows[1]

    comparison_rows = []
    for metric in GAME_EXPLAINER_METRICS:
        value_1 = team_1.get(metric["key"])
        value_2 = team_2.get(metric["key"])
        comparison_rows.append(
            {
                "key": metric["key"],
                "label": metric["label"],
                "team_1_value": value_1,
                "team_2_value": value_2,
                "lower_is_better": metric["lower_is_better"],
                "winner": _game_explainer_winner(value_1, value_2, metric["lower_is_better"]),
            }
        )

    winner_team = team_1 if (team_1.get("pts") or 0) >= (team_2.get("pts") or 0) else team_2
    metadata = {
        "winner_team_name": winner_team.get("team_name"),
        "winner_team_abbreviation": winner_team.get("team_abbreviation"),
        "score": f"{team_1.get('team_abbreviation')} {team_1.get('pts')} - {team_2.get('pts')} {team_2.get('team_abbreviation')}",
        "matchup": f"{team_2.get('team_abbreviation')} @ {team_1.get('team_abbreviation')}",
    }
    return team_rows, comparison_rows, metadata


def _normalize_game_explainer_player_rows(player_stats: pd.DataFrame, adv_players: pd.DataFrame) -> list[dict[str, Any]]:
    merged = player_stats.merge(adv_players, on=["PLAYER_ID", "TEAM_ID"], how="left", suffixes=("", "_ADV"))
    rows = []
    for _, row in merged.iterrows():
        rows.append(
            {
                "player_id": int(row.get("PLAYER_ID")),
                "player_name": row.get("PLAYER_NAME"),
                "team_id": int(row.get("TEAM_ID")),
                "team_abbreviation": row.get("TEAM_ABBREVIATION"),
                "minutes": _normalize_minutes_value(row.get("MIN")),
                "minutes_display": row.get("MIN"),
                "pts": int(row.get("PTS", 0)),
                "reb": int(row.get("REB", 0)),
                "ast": int(row.get("AST", 0)),
                "fgm": int(row.get("FGM", 0)),
                "fga": int(row.get("FGA", 0)),
                "fg3m": int(row.get("FG3M", 0)),
                "plus_minus": _normalize_float(row.get("PLUS_MINUS")),
                "usg_pct": _normalize_float(row.get("USG_PCT")),
                "ts_pct": _normalize_float(row.get("TS_PCT")),
            }
        )

    rows.sort(key=lambda row: (-(row.get("pts") or 0), -(row.get("reb") or 0), -(row.get("ast") or 0), row.get("player_name") or ""))
    return rows


def _build_game_explainer_key_factors(comparison_rows: list[dict[str, Any]], team_rows: list[dict[str, Any]]) -> list[str]:
    team_lookup = {"team_1": team_rows[0], "team_2": team_rows[1]}
    factors = []
    scored = []
    for row in comparison_rows:
        value_1 = row.get("team_1_value")
        value_2 = row.get("team_2_value")
        if value_1 is None or value_2 is None or row.get("winner") in {"none", "tie"}:
            continue
        diff = abs(float(value_1) - float(value_2))
        scored.append((diff, row))

    for _, row in sorted(scored, key=lambda item: item[0], reverse=True)[:3]:
        winner = team_lookup[row["winner"]]
        loser = team_lookup["team_1" if row["winner"] == "team_2" else "team_2"]
        factors.append(
            f"{winner['team_name']} won {row['label']} ({winner.get(row['key'])} vs {loser.get(row['key'])})."
        )

    if not factors:
        factors.append("No standout edge was detected from the available box-score categories.")
    return factors


def get_game_explainer_analysis(game_id: str) -> dict[str, Any]:
    key = (str(game_id), "game_explainer_analysis")
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        player_stats, team_stats = _fetch_boxscore_traditional(game_id=game_id)
        adv_players, adv_team = _fetch_boxscore_advanced(game_id=game_id)

        team_rows, comparison_rows, metadata = _normalize_game_explainer_team_rows(team_stats=team_stats, adv_team=adv_team)
        player_rows = _normalize_game_explainer_player_rows(player_stats=player_stats, adv_players=adv_players)
        top_performers = player_rows[:5]
        game_date = None
        if "GAME_DATE_EST" in team_stats.columns and not team_stats.empty:
            game_date = pd.to_datetime(team_stats.iloc[0].get("GAME_DATE_EST"), errors="coerce")

        payload = {
            "meta": {
                "game_id": str(game_id),
                "game_date": game_date.strftime("%Y-%m-%d") if pd.notna(game_date) else None,
                **metadata,
            },
            "key_factors": _build_game_explainer_key_factors(comparison_rows, team_rows),
            "team_comparison": comparison_rows,
            "teams": team_rows,
            "top_performers": top_performers,
            "players": player_rows,
        }
        cache.set(key, payload)
        return payload
    except Exception:
        stale = cache.get_stale(key)
        if stale is not None:
            return stale
        raise


def _fetch_game_finder_rows(season: str, season_type: str = "Regular Season") -> list[dict[str, Any]]:
    # Prefer player game logs so PLAYER_NAME is available for search/breakouts.
    try:
        endpoint = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
            player_or_team_abbreviation="P",
        )
    except TypeError:
        # Compatibility fallback for nba_api versions without this parameter.
        endpoint = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable=season_type,
        )
    return endpoint.get_data_frames()[0].to_dict("records")


def _preprocess_game_finder_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    # Never invent fake names; keep only real player-name rows.
    if "PLAYER_NAME" not in df.columns:
        return pd.DataFrame(columns=df.columns)

    df["PLAYER_NAME"] = df["PLAYER_NAME"].astype(str).str.strip()
    df = df[~df["PLAYER_NAME"].str.lower().isin(["", "nan", "none", "unknown"])]
    if df.empty:
        return df

    if "MATCHUP" not in df.columns:
        df["MATCHUP"] = "N/A"

    # Some LeagueGameFinder responses can omit PLAYER_ID; derive stable IDs by name.
    if "PLAYER_ID" not in df.columns:
        df["PLAYER_ID"] = pd.factorize(df["PLAYER_NAME"])[0] + 1

    if "GAME_DATE" in df.columns:
        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.dropna(subset=["GAME_DATE"])
        df["MONTH_DAY"] = df["GAME_DATE"].dt.strftime("%m-%d")
    else:
        df["GAME_DATE"] = pd.NaT
        df["MONTH_DAY"] = ""

    dedupe_cols = [col for col in ["GAME_ID", "PLAYER_ID"] if col in df.columns]
    if dedupe_cols:
        df = df.drop_duplicates(subset=dedupe_cols)

    if "MIN" not in df.columns:
        df["MIN"] = 0
    df["MIN"] = pd.to_numeric(df["MIN"], errors="coerce").fillna(0)
    df = df[df["MIN"] > 10]

    numeric_cols = [
        "PTS", "REB", "AST", "FGM", "FGA", "FG3M", "FTA", "FTM", "OREB", "DREB", "STL", "BLK", "PF", "TOV",
    ]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def _get_game_finder_df(season: str, season_type: str = "Regular Season") -> pd.DataFrame:
    key = (season, f"game_finder:{season_type.lower().replace(' ', '_')}")
    cached = cache.get(key)
    if cached is not None:
        return pd.DataFrame(cached)

    try:
        rows = _fetch_game_finder_rows(season=season, season_type=season_type)
        df = _preprocess_game_finder_df(pd.DataFrame(rows))
        payload = df.to_dict("records")
        cache.set(key, payload)
        return df
    except Exception as exc:  # noqa: BLE001
        stale = cache.get_stale(key)
        if stale is not None:
            return pd.DataFrame(stale)
        raise


def _get_multi_season_game_finder_df(seasons: list[str], season_type: str = "Regular Season") -> pd.DataFrame:
    frames = [_get_game_finder_df(season=season, season_type=season_type) for season in seasons]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def add_game_score(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    for col in ["PTS", "FGM", "FGA", "FTA", "FTM", "OREB", "DREB", "STL", "AST", "BLK", "PF", "TOV"]:
        if col not in scored.columns:
            scored[col] = 0
        scored[col] = pd.to_numeric(scored[col], errors="coerce").fillna(0)

    scored["GAME_SCORE"] = (
        scored["PTS"]
        + 0.4 * scored["FGM"]
        - 0.7 * scored["FGA"]
        - 0.4 * (scored["FTA"] - scored["FTM"])
        + 0.7 * scored["OREB"]
        + 0.3 * scored["DREB"]
        + scored["STL"]
        + 0.7 * scored["AST"]
        + 0.7 * scored["BLK"]
        - 0.4 * scored["PF"]
        - scored["TOV"]
    )
    return scored


def _add_breakout_scores(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    player_avg = (
        df.groupby("PLAYER_ID", as_index=False)
        .agg({"PTS": "mean", "AST": "mean", "REB": "mean"})
        .rename(columns={"PTS": "PTS_AVG", "AST": "AST_AVG", "REB": "REB_AVG"})
    )

    merged = df.merge(player_avg, on="PLAYER_ID", how="left")
    merged["BREAKOUT_SCORE"] = (
        (merged["PTS"] - merged["PTS_AVG"]) * 1.5
        + (merged["AST"] - merged["AST_AVG"]) * 1.2
        + (merged["REB"] - merged["REB_AVG"]) * 1.0
    )
    return merged


def _normalize_player_name_for_match(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).casefold().split())


def _normalize_game_rows(df: pd.DataFrame, include_game_score: bool = False, include_breakout: bool = False) -> list[dict[str, Any]]:
    if df.empty:
        return []

    payload: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        item = {
            "player_name": row.get("PLAYER_NAME"),
            "game_date": row.get("GAME_DATE").strftime("%Y-%m-%d") if pd.notna(row.get("GAME_DATE")) else None,
            "matchup": row.get("MATCHUP"),
            "pts": int(row.get("PTS", 0)),
            "reb": int(row.get("REB", 0)),
            "ast": int(row.get("AST", 0)),
            "fgm": int(row.get("FGM", 0)),
            "fga": int(row.get("FGA", 0)),
            "fg3m": int(row.get("FG3M", 0)),
        }
        if include_game_score:
            item["game_score"] = round(float(row.get("GAME_SCORE", 0.0)), 3)
        if include_breakout:
            item["breakout_score"] = round(float(row.get("BREAKOUT_SCORE", 0.0)), 3)
        payload.append(item)
    return payload


def search_games(
    season: str,
    season_type: str,
    filters: dict[str, Any],
    top_n: int = 100,
) -> dict[str, Any]:
    df = _get_game_finder_df(season=season, season_type=season_type)
    result = df.copy()

    pts_min = filters.get("pts_min")
    fg3m_min = filters.get("fg3m_min")
    ast_min = filters.get("ast_min")
    reb_min = filters.get("reb_min")
    player = filters.get("player")
    date = filters.get("date")

    if pts_min is not None:
        result = result[result["PTS"] >= int(pts_min)]
    if fg3m_min is not None:
        result = result[result["FG3M"] >= int(fg3m_min)]
    if ast_min is not None:
        result = result[result["AST"] >= int(ast_min)]
    if reb_min is not None:
        result = result[result["REB"] >= int(reb_min)]
    if player:
        target_player = _normalize_player_name_for_match(player)
        result = result[result["PLAYER_NAME"].map(_normalize_player_name_for_match) == target_player]
    if date:
        target_date = pd.to_datetime(str(date), errors="coerce")
        if pd.notna(target_date):
            result = result[result["GAME_DATE"].dt.date == target_date.date()]

    result = add_game_score(result).sort_values(["PTS", "GAME_SCORE"], ascending=False)
    result = result.head(max(1, min(int(top_n), 500)))

    return {
        "meta": {
            "season": season,
            "season_type": season_type,
            "filters": {
                "pts_min": pts_min,
                "fg3m_min": fg3m_min,
                "ast_min": ast_min,
                "reb_min": reb_min,
                "player": player,
                "date": date,
            },
            "total": int(len(result)),
        },
        "data": _normalize_game_rows(result, include_game_score=True),
    }


def get_games_on_this_day(month: int, day: int, season_type: str = "Regular Season", years: int = 20, top_n: int = 50) -> dict[str, Any]:
    seasons = get_recent_seasons(count=max(1, years))
    df = _get_multi_season_game_finder_df(seasons=seasons, season_type=season_type)
    if df.empty:
        return {"meta": {"month": month, "day": day, "season_type": season_type, "total": 0}, "data": []}

    target = f"{int(month):02d}-{int(day):02d}"
    result = df[df["MONTH_DAY"] == target]
    result = add_game_score(result).sort_values("GAME_SCORE", ascending=False)
    result = result.head(max(1, min(int(top_n), 500)))

    return {
        "meta": {
            "month": int(month),
            "day": int(day),
            "season_type": season_type,
            "season_count": len(seasons),
            "total": int(len(result)),
        },
        "data": _normalize_game_rows(result, include_game_score=True),
    }


def get_breakout_games(
    season: str,
    season_type: str = "Regular Season",
    min_breakout_score: float = 15.0,
    player_name: str | None = None,
    top_n: int = 100,
) -> dict[str, Any]:
    df = _get_game_finder_df(season=season, season_type=season_type)
    if df.empty:
        return {"meta": {"season": season, "season_type": season_type, "total": 0}, "data": []}

    merged = _add_breakout_scores(df)
    result = merged[merged["BREAKOUT_SCORE"] > float(min_breakout_score)]

    if player_name:
        target_player = _normalize_player_name_for_match(player_name)
        result = result[result["PLAYER_NAME"].map(_normalize_player_name_for_match) == target_player]

    result = add_game_score(result).sort_values("BREAKOUT_SCORE", ascending=False)
    result = result.head(max(1, min(int(top_n), 500)))

    return {
        "meta": {
            "season": season,
            "season_type": season_type,
            "player_name": player_name,
            "min_breakout_score": float(min_breakout_score),
            "total": int(len(result)),
        },
        "data": _normalize_game_rows(result, include_game_score=True, include_breakout=True),
    }
