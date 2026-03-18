# NBA Active Player Stats (Starter)

This project is a starter NBA stats site powered by [`nba_api`](https://pypi.org/project/nba_api/).

## Python version support

- Recommended: **Python 3.13 (64-bit)** on Windows.
- This project now pins `numpy`/`pandas` to versions that publish Python 3.13 wheels for faster installs.
- If you are on **32-bit Python**, pip may try to compile NumPy from source (slow/fails). Use a **64-bit** Python install.

## Features in v1

- Fetches active NBA players and regular-season per-game stats.
- Merges base + advanced stat sets to include:
  - PPG, RPG, APG, SPG, BPG
  - Plus-minus
  - FG%, FT%, TS%
  - Fouls per game
- Sortable/paginated API endpoint.
- Minimal frontend table with sort controls.
- Added a **Players (Playoffs)** page (`/players-playoffs`) with the same controls/table as the players page, backed by playoff-only stats.
- Players page includes an **Advanced Statistics** mode with additional sortable metrics (e.g., TS%, 3PAr, FTr, ORB%/DRB%/TRB%, AST%/STL%/BLK%/TOV%/USG%, OFF/DEF/NET rating, PIE).
- Added an **Awards Formula** page (`/awards-formula`) to score players via custom 0-100 metric weights, team rating weight, and award presets (MVP/DPOY/CUSTOM).
- Added a **Lineups** page (`/lineups`) for current-season team lineup filtering (Top N, minimum minutes together, sortable lineup stats).
- Added a **Player Similarity** page (`/player-similarity`) that computes weighted cosine similarity using normalized player stats, optional shot-diet features, and optional archetype-only comparisons.
- Added a **Game Finder** page (`/game-finder`) for custom stat-based game search, “On This Day” results across recent seasons, and breakout game detection.
- Added a **Player Career Stats** page (`/player-career`) for simple player-name lookup with career averages, season-by-season team history, and an advanced stats toggle.
- In-memory TTL caching with stale fallback on upstream fetch failure.

## Run locally (PowerShell, Python 3.13)

```powershell
cd C:\path\to\nbaTest

# Verify installed interpreters and pick 3.13-64
py -0p

# Fresh virtual environment
py -3.13-64 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --only-binary=:all: numpy pandas
pip install -r requirements.txt

python -m uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

If `Activate.ps1` is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```


## New in this update

- Added a **Team Head-to-Head page** at `/head-to-head` with:
  - Team + season selector controls (each team can use a different season)
  - Team-level per-game comparison metrics
  - Active-player lists for each selected team
- Added top-right navigation buttons between the Players page and Head-to-Head page.
- Updated search/sort UI labels to a more professional uppercase style.

## API

### `GET /api/players`

Query parameters:

- `season` (default current, e.g. `2024-25`)
- `sort_by` one of:
  `player_name`, `team`, `gp`, `ppg`, `rpg`, `apg`, `spg`, `bpg`, `plus_minus`, `fg_pct`, `ts_pct`, `ft_pct`, `three_pt_pct`, `pf_pg`, `mpg`, `off_rating`, `def_rating`, `net_rating`, `ast_pct`, `oreb_pct`, `dreb_pct`, `reb_pct`, `stl_pct`, `blk_pct`, `tov_pct`, `usg_pct`, `efg_pct`, `three_par`, `ftr`, `pie`
- `order`: `asc` or `desc`
- `limit`: 1-1000
- `offset`: 0+

Example:

```bash
curl "http://127.0.0.1:8000/api/players?season=2024-25&sort_by=ppg&order=desc&limit=25"
```



### `GET /api/players-playoffs`

Same query parameters and sorting behavior as `GET /api/players`, but pulls **Playoffs** season type data from `nba_api`.

Example:

```bash
curl "http://127.0.0.1:8000/api/players-playoffs?season=2024-25&sort_by=ppg&order=desc&limit=25"
```

## Caching

- Env var: `NBA_CACHE_TTL_SECONDS` (default `900`)
- Keyed by `(season, dataset)`
- Returns stale cached data if live upstream fetch fails.


### `GET /api/head-to-head`

Query parameters:

- `season_1` (team 1 season)
- `team1_id`
- `season_2` (team 2 season)
- `team2_id`

Includes team-level comparisons with winner indicators in the UI. For `FOULS/G`, `TOV/G`, and `DEF RATING`, lower values are treated as better. Team record appears as the final comparison row and uses win% internally for winner indication.


### `POST /api/awards-formula`

JSON body:

- `season`
- `award` (`CUSTOM`, `MVP`, `DPOY`)
- `weights` (object of metric->0..100)
- `team_rating_weight` (0..100, uses team `W_PCT`)
- `min_gp`
- `top_n`

Notes:

- `def_rating`, `pf_pg`, and `tov_pct` are treated as lower-is-better.


### `GET /api/lineups`

Query parameters:

- `team_id`
- `season` (defaults to current season)
- `top_n` (1..100)
- `min_minutes`
- `min_games`
- `sort_by` (e.g. `NET_RATING`, `OFF_RATING`, `DEF_RATING`, `MIN`, `TS_PCT`, `PIE`)
- `order` (`asc` or `desc`)

Returns normalized lineup rows with metrics such as MIN, GP, OFF/DEF/NET rating, AST%, REB%, eFG%, TS%, and PIE for the selected team.




### `GET /api/game-finder/search`

Query filters on a season/season type game log:

- `season`
- `season_type` (`Regular Season` or `Playoffs`)
- `pts_min`, `fg3m_min`, `ast_min`, `reb_min`
- `player`
- `date` (`YYYY-MM-DD`)
- `top_n`

Returns top matching games sorted by points and game score.

### `GET /api/game-finder/on-this-day`

Find top performances on a calendar day across recent seasons.

- `month`, `day`
- `season_type`
- `years` (how many recent seasons to include)
- `top_n`

Results include computed `game_score`.

### `GET /api/game-finder/breakouts`

Find breakout games where game output significantly exceeds player averages.

- `season`, `season_type`
- `min_breakout_score`
- `player_name` (optional)
- `top_n`

Results include `game_score` and `breakout_score`.

### `GET /api/player-similarity`

Query parameters:

- `season`
- `player_name`
- `top_n` (1..25)
- `min_minutes` (minimum total minutes filter, e.g. 800)
- `include_shot_diet` (`true`/`false`)
- `archetype_only` (`true`/`false`)

Response metadata includes `shot_diet_source` (currently `season-stats-proxy`) when shot diet is enabled.

Returns top similar players based on weighted cosine similarity over z-score normalized features (box/advanced stats + optional shot-diet proxy rates for 3PT share, paint share, and midrange share).

### `GET /api/player-directory`

Returns player names/IDs for datalist suggestions.

- `active_only` (`true`/`false`, default `false`)

### `GET /api/player-career`

Query parameters:

- `player_name`

Returns:

- `meta` with resolved player name/ID and season count
- `career` row with career per-game averages
- `seasons` rows with season, team, and the same base/advanced stat fields used by the page toggle

This page uses `PlayerCareerStats` for season totals, then derives per-game career averages and merges advanced season metrics from `LeagueDashPlayerStats`.
