"""What the players CommonTeamRoster omits would do to one season's numbers.

11_participation_check.py finds players who appeared in a season
(LeagueDashPlayerStats) but are on no roster snapshot (CommonTeamRoster lists
who is on a team when it is read). For each season with both a cached
LeagueDashPlayerStats file and a cached PlayerIndex file, this adds the
missing players back, with height and jersey number from PlayerIndex, and
recomputes that season's metrics with 03_analysis.season_metrics.

PlayerIndex numbers matched the roster number for 532 of 534 rostered NBA
2024-25 players (October 19, 2026 audit), so they stand in for the number
worn. Only NBA 2024-25 is cached so far: data/participation/pidx_nba_2024.csv
(PERSON_ID, JERSEY_NUMBER, HEIGHT, POSITION, FROM_YEAR from PlayerIndex,
fetched by the audit on October 19, 2026).

Output: output/participation_impact.csv (season, metric, published, with
        missing players, delta, and both n)
Run:    python python/13_participation_impact.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
PART = ROOT / "data" / "participation"
OUT = ROOT / "output" / "participation_impact.csv"
COLS = ["PLAYER_ID", "season_start", "height_in", "jersey_raw", "jersey_num"]


def load(name: str, stem: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "python" / f"{stem}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def added_players(a, missing: pl.DataFrame, pidx: pl.DataFrame, season: int) -> pl.DataFrame:
    m = missing.join(pidx, left_on="PLAYER_ID", right_on="PERSON_ID", how="left")
    return (m.filter(pl.col("HEIGHT").is_not_null())
            .select(PLAYER_ID=pl.col("PLAYER_ID").cast(pl.Utf8), HEIGHT="HEIGHT",
                    NUM="JERSEY_NUMBER", season_start=pl.lit(season, dtype=pl.Int32))
            .with_columns(a.parse_height_expr("HEIGHT"),
                          pl.col("NUM").fill_null("").str.strip_chars().alias("jersey_raw"))
            .with_columns(pl.col("jersey_raw").cast(pl.Float64, strict=False).alias("jersey_num")))


def main() -> int:
    a = load("jersey_analysis", "03_analysis")
    pc = load("jersey_participation", "11_participation_check")
    players = a.load_players()
    rosters = pc.roster_ids_by_season("nba")
    rows = []
    for pidx_path in sorted(PART.glob("pidx_nba_*.csv")):
        season = int(pidx_path.stem.rsplit("_", 1)[1])
        ldps = pl.read_csv(pc.cache_path("nba", season)).with_columns(pl.col("PLAYER_ID").cast(pl.Int64))
        missing = pc.compare(rosters[season], ldps, set())["missing"]
        pidx = (pl.read_csv(pidx_path, infer_schema_length=0)
                .with_columns(pl.col("PERSON_ID").cast(pl.Int64)))
        base = players.filter(pl.col("season_start") == season).select(COLS)
        full = pl.concat([base, added_players(a, missing, pidx, season).select(COLS)])

        def metrics(d: pl.DataFrame) -> dict:
            r = a.season_metrics(d).filter(pl.col("season_start") == season)
            return {k: (v, n) for k, v, n in r.select("metric", "value", "n").iter_rows()}

        pub, now = metrics(base), metrics(full)
        rows += [{"season_start": season, "metric": k, "published": pub[k][0],
                  "with_missing": now[k][0], "delta": now[k][0] - pub[k][0],
                  "n_published": pub[k][1], "n_with_missing": now[k][1],
                  "players_missing": missing.height} for k in pub]
    table = pl.DataFrame(rows).sort(["season_start", "metric"])
    table.write_csv(OUT, float_precision=6)
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
