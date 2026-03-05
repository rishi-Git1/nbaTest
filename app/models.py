from pydantic import BaseModel


class PlayerStatsRow(BaseModel):
    player_id: int
    player_name: str
    team: str | None = None
    gp: int | None = None

    # Base stats
    ppg: float | None = None
    rpg: float | None = None
    apg: float | None = None
    spg: float | None = None
    bpg: float | None = None
    plus_minus: float | None = None
    fg_pct: float | None = None
    ts_pct: float | None = None
    ft_pct: float | None = None
    three_pt_pct: float | None = None
    pf_pg: float | None = None

    # Advanced/player-impact style stats (where available)
    mpg: float | None = None
    off_rating: float | None = None
    def_rating: float | None = None
    net_rating: float | None = None
    ast_pct: float | None = None
    oreb_pct: float | None = None
    dreb_pct: float | None = None
    reb_pct: float | None = None
    stl_pct: float | None = None
    blk_pct: float | None = None
    tov_pct: float | None = None
    usg_pct: float | None = None
    efg_pct: float | None = None
    three_par: float | None = None
    ftr: float | None = None
    pie: float | None = None


class PlayerStatsResponse(BaseModel):
    meta: dict
    data: list[PlayerStatsRow]
