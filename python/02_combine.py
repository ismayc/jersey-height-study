"""Assemble the cached per-team-season roster files into one tidy CSV.

Kept separate from the harvest so the analysis never depends on the network, and
so a partially complete harvest can still be analyzed.

polars throughout. Every column is read as a string so that jersey "00" survives
as text rather than being inferred to the integer 0; typing happens once, in the
analysis step, where the rules are documented.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
from nba_api.stats.static import teams

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_rosters"
OUT_CSV = ROOT / "data" / "nba_rosters.csv"

TEAM_BY_ID = {t["id"]: t for t in teams.get_teams()}


def main() -> int:
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        raise SystemExit(f"No cached rosters in {RAW_DIR}. Run 01_harvest_rosters.py first.")

    frames: list[pl.DataFrame] = []
    for path in files:
        season_start, team_id = path.stem.split("_")
        df = pl.read_csv(path, infer_schema_length=0)
        if df.height == 0:
            continue  # franchise did not exist that season
        team = TEAM_BY_ID.get(int(team_id), {})
        frames.append(df.with_columns(
            season_start=pl.lit(int(season_start), dtype=pl.Int32),
            team_abbrev=pl.lit(team.get("abbreviation", "")),
            team_full=pl.lit(team.get("full_name", "")),
        ))

    combined = pl.concat(frames, how="diagonal_relaxed")
    combined.write_csv(OUT_CSV)

    seasons = combined["season_start"].unique().sort()
    print(f"{len(files):,} cached team-seasons -> {combined.height:,} player-season rows")
    print(f"Seasons {seasons[0]}-{seasons[-1]} ({len(seasons)} distinct)")
    print(f"Wrote {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
