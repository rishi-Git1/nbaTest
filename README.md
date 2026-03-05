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
  `player_name`, `team`, `gp`, `ppg`, `rpg`, `apg`, `spg`, `bpg`, `plus_minus`, `fg_pct`, `ts_pct`, `ft_pct`, `three_pt_pct`, `pf_pg`
- `order`: `asc` or `desc`
- `limit`: 1-1000
- `offset`: 0+

Example:

```bash
curl "http://127.0.0.1:8000/api/players?season=2024-25&sort_by=ppg&order=desc&limit=25"
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

Includes team-level comparisons with winner indicators in the UI. For `FOULS/G`, `TOV/G`, and `DEF RATING`, lower values are treated as better.
