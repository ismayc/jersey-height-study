"""Harvest the rosters the WNBA extension needs: every WNBA season, and the
NBA's own early seasons.

Two sets, same endpoint as 01_harvest_rosters.py (CommonTeamRoster: one
request per team-season, ~12-15 players, with NUM, HEIGHT, SCHOOL and EXP):

  wnba       WNBA 1997-2026. The team list for each season comes from
             LeagueGameFinder (LeagueID 10), so franchises that later folded
             (Houston, Sacramento, Charlotte, ...) are included. nba_api's
             static team list holds current franchises only, which is the
             limitation the NBA harvest carries; the WNBA's folded teams are
             too large a share of its early seasons to drop.
  nba-early  NBA 1946-47 to 1979-80, for the league-age comparison (the NBA
             at WNBA ages 0-29). LeagueGameFinder returns no games before the
             1980s, so the team list comes from FranchiseHistory, current and
             defunct franchises both; every team is asked for every season in
             its span, and a season it did not play caches an empty file.

Resumable and cached, one CSV per team-season, then combined:
    data/raw_rosters_wnba/<year>_<team_id>.csv       -> data/wnba_rosters.csv
    data/raw_rosters_nba_early/<year>_<team_id>.csv  -> data/nba_early_rosters.csv

Usage:
    python python/07_harvest_more_rosters.py wnba [--start 1997 --end 2026]
    python python/07_harvest_more_rosters.py nba-early [--start 1946 --end 1979]
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import pandas as pd
import polars as pl
from nba_api.stats.endpoints import CommonTeamRoster, FranchiseHistory, LeagueGameFinder
from nba_api.stats.library import http

from roster_guard import require_clean, validate_roster

# nba_api's shipped Firefox/72 User-Agent hangs on stats.nba.com; a generic one
# returns at once (basketball-analysis-tools' nba_api_compat.fix_user_agent).
http.STATS_HEADERS["User-Agent"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                    "AppleWebKit/537.36")

ROOT = Path(__file__).resolve().parents[1]
SETS = {
    "wnba": (ROOT / "data" / "raw_rosters_wnba", ROOT / "data" / "wnba_rosters.csv",
             1997, 2026),
    "nba-early": (ROOT / "data" / "raw_rosters_nba_early",
                  ROOT / "data" / "nba_early_rosters.csv", 1946, 1979),
}

BASE_SLEEP = 0.6
MAX_RETRIES = 4
TIMEOUT = 45


def nba_season(start_year: int) -> str:
    """1946 -> '1946-47'."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def call(fn, what: str):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            out = fn()
            time.sleep(BASE_SLEEP + random.uniform(0, 0.3))
            return out
        except Exception as exc:  # noqa: BLE001 - endpoint raises many error types
            wait = BASE_SLEEP * (2 ** attempt) + random.uniform(0, 1)
            print(f"    retry {attempt}/{MAX_RETRIES} {what}: "
                  f"{type(exc).__name__} (waiting {wait:.1f}s)", flush=True)
            time.sleep(wait)
    print(f"    FAILED {what}", flush=True)
    return None


def wnba_teams(year: int) -> list[int] | None:
    df = call(lambda: LeagueGameFinder(
        season_nullable=str(year), league_id_nullable="10",
        season_type_nullable="Regular Season", timeout=60).get_data_frames()[0],
        f"WNBA {year} team list")
    if df is None:
        return None
    # 2005's game list carries a row with no TEAM_ID; it names no team
    return sorted(int(t) for t in df["TEAM_ID"].dropna().unique())


def nba_franchise_spans() -> dict[int, tuple[int, int]]:
    cur, dead = call(lambda: FranchiseHistory(league_id="00", timeout=60)
                     .get_data_frames(), "NBA franchise history")
    spans: dict[int, tuple[int, int]] = {}
    for _, r in pd.concat([cur, dead]).iterrows():
        tid, lo, hi = int(r["TEAM_ID"]), int(r["START_YEAR"]), int(r["END_YEAR"])
        a, b = spans.get(tid, (lo, hi))
        spans[tid] = (min(a, lo), max(b, hi))
    return spans


def fetch_roster(raw_dir: Path, team_id: int, year: int, league: str) -> bool:
    cache = raw_dir / f"{year}_{team_id}.csv"
    if cache.exists():
        n = max(len(pl.read_csv(cache, infer_schema_length=0)), 0)
        why = validate_roster(league, team_id, year, n)
        if why is None:
            return True
        print(f"    discarding cache {cache.name}: {why}", flush=True)
    if league == "wnba":
        fn = lambda: CommonTeamRoster(team_id=team_id, season=str(year),  # noqa: E731
                                      league_id_nullable="10", timeout=TIMEOUT)
    else:
        fn = lambda: CommonTeamRoster(team_id=team_id, season=nba_season(year),  # noqa: E731
                                      timeout=TIMEOUT)
    df = call(lambda: fn().get_data_frames()[0], f"{league} {year} team {team_id}")
    if df is None:
        return False
    # An empty frame is cached (no retry next run) only when the team did not
    # play that season; any other empty frame is a failed call, not cached.
    why = validate_roster(league, team_id, year, len(df))
    if why is not None:
        print(f"    REFUSED to cache: {why}", flush=True)
        return False
    df.to_csv(cache, index=False)
    return True


def combine(raw_dir: Path, out_csv: Path, league: str = "nba") -> int:
    require_clean(raw_dir, league)  # exits with the list if an empty file is not shown to be empty
    frames = []
    for path in sorted(raw_dir.glob("*.csv")):
        year, team_id = path.stem.split("_")
        df = pl.read_csv(path, infer_schema_length=0)  # text: "00" stays "00"
        if df.height == 0:
            continue
        frames.append(df.with_columns(season_start=pl.lit(int(year), dtype=pl.Int32),
                                      team_id=pl.lit(int(team_id), dtype=pl.Int64)))
    combined = pl.concat(frames, how="diagonal_relaxed")
    combined.write_csv(out_csv)
    years = combined["season_start"].unique().sort()
    print(f"{combined.height:,} player-season rows, seasons {years[0]}-{years[-1]} "
          f"({len(years)} distinct) -> {out_csv}")
    return combined.height


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("set", choices=sorted(SETS))
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    args = ap.parse_args()
    raw_dir, out_csv, start, end = SETS[args.set]
    start = args.start or start
    end = args.end or end
    raw_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    spans = nba_franchise_spans() if args.set == "nba-early" else None
    for year in range(start, end + 1):
        if args.set == "wnba":
            team_ids = wnba_teams(year)
            if team_ids is None:
                failures += 1
                continue
            league = "wnba"
        else:
            team_ids = sorted(t for t, (lo, hi) in spans.items() if lo <= year <= hi)
            league = "nba"
        ok = sum(fetch_roster(raw_dir, t, year, league) for t in team_ids)
        failures += len(team_ids) - ok
        print(f"  {year}: {ok}/{len(team_ids)} team rosters", flush=True)

    combine(raw_dir, out_csv, "wnba" if args.set == "wnba" else "nba")
    print(f"Failed requests: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
