"""Harvest NBA team rosters (jersey number, height, position, age) by season.

Source: stats.nba.com CommonTeamRoster, via the nba_api package.

One request returns a full team-season roster (~15 players), which makes this the
cheapest endpoint for the question at hand: per-player endpoints would need
thousands of calls to assemble the same table.

The script is resumable. Every team-season is cached as its own CSV under
data/raw_rosters/, so an interrupted run picks up where it left off and the
analysis never needs to re-hit the network.

Usage:
    python 01_harvest_rosters.py [--start 1980] [--end 2024]
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import pandas as pd
from nba_api.stats.endpoints import CommonTeamRoster
from nba_api.stats.static import teams

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_rosters"
OUT_CSV = ROOT / "data" / "nba_rosters.csv"

# Politeness / reliability settings for a public endpoint.
BASE_SLEEP = 0.6
MAX_RETRIES = 4
TIMEOUT = 45


def season_label(start_year: int) -> str:
    """1996 -> '1996-97' (the format stats.nba.com expects)."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def fetch_team_season(team_id: int, team_name: str, start_year: int) -> pd.DataFrame | None:
    """Fetch one team-season roster, retrying with backoff on transient errors."""
    season = season_label(start_year)
    cache = RAW_DIR / f"{start_year}_{team_id}.csv"

    if cache.exists():
        return pd.read_csv(cache)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = CommonTeamRoster(team_id=team_id, season=season, timeout=TIMEOUT)
            df = resp.get_data_frames()[0]
            # A franchise that did not exist yet returns an empty frame; cache the
            # empty result so we do not retry it on the next run.
            df.to_csv(cache, index=False)
            time.sleep(BASE_SLEEP + random.uniform(0, 0.3))
            return df
        except Exception as exc:  # noqa: BLE001 - endpoint raises many error types
            wait = BASE_SLEEP * (2 ** attempt) + random.uniform(0, 1)
            print(f"    retry {attempt}/{MAX_RETRIES} {team_name} {season}: "
                  f"{type(exc).__name__} (waiting {wait:.1f}s)", flush=True)
            time.sleep(wait)

    print(f"    FAILED {team_name} {season}", flush=True)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1980)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    nba_teams = teams.get_teams()
    print(f"{len(nba_teams)} current franchises; seasons "
          f"{season_label(args.start)} to {season_label(args.end)}", flush=True)

    frames, failures = [], 0
    for start_year in range(args.start, args.end + 1):
        got = 0
        for team in nba_teams:
            df = fetch_team_season(team["id"], team["abbreviation"], start_year)
            if df is None:
                failures += 1
                continue
            if not df.empty:
                df = df.assign(season_start=start_year,
                               team_abbrev=team["abbreviation"],
                               team_full=team["full_name"])
                frames.append(df)
                got += len(df)
        print(f"  {season_label(start_year)}: {got} player-seasons", flush=True)

    if not frames:
        print("No data harvested.", file=sys.stderr)
        return 1

    combined = pd.concat(frames, ignore_index=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {len(combined):,} player-seasons to {OUT_CSV}")
    print(f"Failed team-seasons: {failures}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
