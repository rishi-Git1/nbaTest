from pydantic import BaseModel


class PlayerStatsRow(BaseModel):
    player_id: int
    player_name: str
    team: str | None = None
    gp: int | None = None
    ppg: float | None = None
    rpg: float | None = None
    apg: float | None = None
    spg: float | None = None
    bpg: float | None = None
    plus_minus: float | None = None
    fg_pct: float | None = None
    ts_pct: float | None = None
    ft_pct: float | None = None
    pf_pg: float | None = None


class PlayerStatsResponse(BaseModel):
    meta: dict
    data: list[PlayerStatsRow]
