"""Build data/franchise_active_seasons.csv: which team played which season.

Source: ../playoff-series-study/data/team_seasons.csv (one row per team and
season with regular-season games, built from LeagueGameFinder in that repo).
It is independent of CommonTeamRoster, which is the point: roster_guard.py uses
this table to decide whether an empty CommonTeamRoster response is a franchise
that did not exist (accept) or a failed call (refuse).

Output columns: league ("nba" or "wnba"), team_id, season_start. That table's
SEASON is the year the season ends for the NBA (1947 = 1946-47) and the single
year for the WNBA, so season_start is SEASON - 1 for the NBA and SEASON for the
WNBA, matching the file names under data/raw_rosters*/.

Run:  python python/12_build_active_seasons.py
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT.parent / "playoff-series-study" / "data" / "team_seasons.csv"
OUT = ROOT / "data" / "franchise_active_seasons.csv"


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"Source table not found: {SRC}")
    d = pl.read_csv(SRC, infer_schema_length=0).with_columns(
        pl.col("TEAM_ID").cast(pl.Int64), pl.col("SEASON").cast(pl.Int64))
    out = d.select(
        league=pl.when(pl.col("LEAGUE") == "10").then(pl.lit("wnba")).otherwise(pl.lit("nba")),
        team_id=pl.col("TEAM_ID"),
        season_start=pl.when(pl.col("LEAGUE") == "10").then(pl.col("SEASON"))
        .otherwise(pl.col("SEASON") - 1),
    ).unique().sort("league", "season_start", "team_id")
    out.write_csv(OUT)
    print(f"Wrote {out.height:,} team-seasons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
