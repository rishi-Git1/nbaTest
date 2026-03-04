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
    "pf_pg",
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


def _compose_rows(per_game: list[dict[str, Any]], advanced: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                "gp": int(row.get("GP", 0)) if row.get("GP") is not None else None,
                "ppg": _normalize_float(row.get("PTS")),
                "rpg": _normalize_float(row.get("REB")),
                "apg": _normalize_float(row.get("AST")),
                "spg": _normalize_float(row.get("STL")),
                "bpg": _normalize_float(row.get("BLK")),
                "plus_minus": _normalize_float(row.get("PLUS_MINUS")),
                "fg_pct": _normalize_float(row.get("FG_PCT")),
                "ts_pct": _normalize_float(adv.get("TS_PCT")),
                "ft_pct": _normalize_float(row.get("FT_PCT")),
                "pf_pg": _normalize_float(row.get("PF")),
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
        rows = _compose_rows(per_game, advanced)
        cache.set(key, rows)
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"[nba_stats] fetch failed for season={season}: {type(exc).__name__}: {exc}")
        stale = cache.get_stale(key)
        if stale is not None:
            return stale
        raise


def get_team_vs_team(season: str, team1_id: int, team2_id: int) -> dict[str, Any]:
    if team1_id == team2_id:
        raise ValueError("Please select two different teams.")

    key = (season, f"head_to_head:{team1_id}:{team2_id}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        team_base = _fetch_team_base_stats(season)
        team_adv = _fetch_team_advanced_stats(season)
        players_all = get_active_player_stats(season)

        teams_by_id = {int(t["id"]): t for t in get_teams_directory()}
        team_base_by_id = {int(row["TEAM_ID"]): row for row in team_base}
        team_adv_by_id = {int(row["TEAM_ID"]): row for row in team_adv}

        def team_summary(team_id: int) -> dict[str, Any]:
            base = team_base_by_id.get(team_id)
            if not base:
                raise ValueError(f"No team stats found for team_id={team_id} in season {season}.")
            adv = team_adv_by_id.get(team_id, {})
            info = teams_by_id.get(team_id, {"full_name": f"TEAM {team_id}", "abbreviation": "N/A"})
            return {
                "team_id": team_id,
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
                "pf_pg": _normalize_float(base.get("PF")),
            }

        def team_players(team_id: int) -> list[dict[str, Any]]:
            rows = [row for row in players_all if row.get("team_id") == team_id]
            return sorted(rows, key=lambda r: (r.get("ppg") is None, -(r.get("ppg") or 0), r.get("player_name", "")))

        payload = {
            "meta": {"season": season, "team1_id": team1_id, "team2_id": team2_id},
            "team_1": {"summary": team_summary(team1_id), "players": team_players(team1_id)},
            "team_2": {"summary": team_summary(team2_id), "players": team_players(team2_id)},
        }
        cache.set(key, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        print(
            f"[nba_stats] head_to_head failed season={season} team1={team1_id} team2={team2_id}: "
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
