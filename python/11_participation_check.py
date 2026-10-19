"""Participation check: does CommonTeamRoster list everyone who played?

CommonTeamRoster is a snapshot of who is on a team when the roster is read, so a
player who appeared for a team and left before the snapshot can be missing from
the harvest (October 19, 2026 audit: NBA 2024-25, 41 of 569 players in
LeagueDashPlayerStats were absent from the roster harvest; WNBA 2025, 21 of 182).

This check compares, for each league and season, the players in the roster
harvest (data/nba_rosters.csv, data/wnba_rosters.csv) with the players in
LeagueDashPlayerStats (one call per season, cached in data/participation/).

  * missing    in LeagueDashPlayerStats, not on any roster: a player the study
               never saw. Listed in data/participation_allowlist.csv (player_id
               with a note) when the gap is understood and accepted; otherwise a
               FLAG.
  * unplayed   on a roster, not in LeagueDashPlayerStats: never appeared in a
               game. Informational.

It SKIPS LOUDLY: a season whose LeagueDashPlayerStats is not cached is reported
as "NOT RUN", with a summary count. The exit code is 0 unless a flag asks for
more:
    --fail-on-flags   exit 1 if any season has a missing player not allowlisted
    --require-all     exit 2 if any requested season was NOT RUN

Offline by default. --fetch makes the one call per uncached season (polite:
about 1.2 seconds between calls, retries with backoff, refuses to cache an empty
or implausibly short response). stats.nba.com may hang; use --timeout.

    python python/11_participation_check.py                    # offline report
    python python/11_participation_check.py --fetch --league nba --from 2015
    python python/11_participation_check.py --seed nba 2024 path/to/ldps.csv
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "participation"
ALLOWLIST = ROOT / "data" / "participation_allowlist.csv"
ROSTERS = {"nba": ROOT / "data" / "nba_rosters.csv", "wnba": ROOT / "data" / "wnba_rosters.csv"}
# LeagueDashPlayerStats exists from 1996-97 (NBA) and 1997 (WNBA).
FIRST_SEASON = {"nba": 1996, "wnba": 1997}
LAST_SEASON = {"nba": 2025, "wnba": 2026}
MIN_PLAYERS = {"nba": 200, "wnba": 50}  # a response shorter than this is a failed call
KEEP = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GP", "MIN"]
SLEEP = 1.2
MAX_RETRIES = 4


def season_arg(league: str, season_start: int) -> str:
    """2024 -> '2024-25' for the NBA, '2025' for the WNBA."""
    return f"{season_start}-{str(season_start + 1)[-2:]}" if league == "nba" else str(season_start)


def cache_path(league: str, season_start: int, cache_dir: Path | None = None) -> Path:
    return (cache_dir or CACHE_DIR) / f"ldps_{league}_{season_start}.csv"


def load_allowlist(path: Path | None = None) -> set[tuple[str, int, int]]:
    path = path or ALLOWLIST
    if not path.exists():
        return set()
    d = pl.read_csv(path, infer_schema_length=0)
    return {(r["league"], int(r["season_start"]), int(r["player_id"]))
            for r in d.iter_rows(named=True)}


def compare(roster_ids: set[int], ldps: pl.DataFrame,
            allowed: set[int]) -> dict:
    """Pure comparison of one season. ldps needs PLAYER_ID, PLAYER_NAME, GP."""
    ldps = ldps.unique(subset=["PLAYER_ID"], keep="first")
    ldps_ids = set(ldps["PLAYER_ID"].to_list())
    missing = ldps.filter(~pl.col("PLAYER_ID").is_in(list(roster_ids)))
    allowed_df = missing.filter(pl.col("PLAYER_ID").is_in(list(allowed)))
    flagged = missing.filter(~pl.col("PLAYER_ID").is_in(list(allowed)))
    return {
        "roster_players": len(roster_ids),
        "ldps_players": len(ldps_ids),
        "missing": missing.sort("GP", descending=True),
        "allowlisted": allowed_df.height,
        "flagged": flagged.sort("GP", descending=True),
        "unplayed": len(roster_ids - ldps_ids),
        "missing_gp_share": (float(missing["GP"].sum()) / float(ldps["GP"].sum())
                             if ldps.height and ldps["GP"].sum() else 0.0),
    }


def roster_ids_by_season(league: str) -> dict[int, set[int]]:
    path = ROSTERS[league]
    if not path.exists():
        return {}
    d = pl.read_csv(path, infer_schema_length=0, columns=["PLAYER_ID", "season_start"])
    out: dict[int, set[int]] = {}
    for sid, pid in d.select("season_start", "PLAYER_ID").iter_rows():
        out.setdefault(int(sid), set()).add(int(pid))
    return out


def reduce_ldps(df: pl.DataFrame) -> pl.DataFrame:
    return df.select([c for c in KEEP if c in df.columns]).with_columns(
        pl.col("PLAYER_ID").cast(pl.Int64))


def seed(league: str, season_start: int, src: Path) -> Path:
    df = reduce_ldps(pl.read_csv(src))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = cache_path(league, season_start)
    df.write_csv(out)
    print(f"Seeded {out} ({df.height} players) from {src}")
    return out


def fetch(league: str, season_start: int, timeout: int) -> bool:
    """One LeagueDashPlayerStats call; cache only a plausible response."""
    from nba_api.stats.endpoints import LeagueDashPlayerStats
    from nba_api.stats.library import http
    # nba_api's shipped User-Agent hangs on stats.nba.com; see 07_harvest_more_rosters.py
    http.STATS_HEADERS["User-Agent"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                        "AppleWebKit/537.36")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = LeagueDashPlayerStats(
                season=season_arg(league, season_start),
                league_id_nullable="00" if league == "nba" else "10",
                per_mode_detailed="Totals", timeout=timeout)
            df = reduce_ldps(pl.from_pandas(resp.get_data_frames()[0]))
            time.sleep(SLEEP + random.uniform(0, 0.4))
            if df.height < MIN_PLAYERS[league]:
                raise ValueError(f"only {df.height} players (need {MIN_PLAYERS[league]}+)")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            df.write_csv(cache_path(league, season_start))
            return True
        except Exception as exc:  # noqa: BLE001 - endpoint raises many error types
            wait = SLEEP * (2 ** attempt) + random.uniform(0, 1)
            print(f"    retry {attempt}/{MAX_RETRIES} {league} {season_start}: "
                  f"{type(exc).__name__}: {exc} (waiting {wait:.1f}s)", flush=True)
            time.sleep(wait)
    print(f"    FAILED to fetch {league} {season_start}; nothing cached", flush=True)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--league", choices=["nba", "wnba", "both"], default="both")
    ap.add_argument("--from", dest="first", type=int, help="first season_start")
    ap.add_argument("--to", dest="last", type=int, help="last season_start")
    ap.add_argument("--fetch", action="store_true", help="call the network for uncached seasons")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--seed", nargs=3, metavar=("LEAGUE", "SEASON_START", "CSV"))
    ap.add_argument("--fail-on-flags", action="store_true")
    ap.add_argument("--require-all", action="store_true")
    ap.add_argument("--top", type=int, default=5, help="missing players to list per season")
    args = ap.parse_args(argv)

    if args.seed:
        seed(args.seed[0], int(args.seed[1]), Path(args.seed[2]))

    leagues = ["nba", "wnba"] if args.league == "both" else [args.league]
    allowlist = load_allowlist()
    ran = skipped = flagged_seasons = 0
    for league in leagues:
        by_season = roster_ids_by_season(league)
        lo = args.first or FIRST_SEASON[league]
        hi = args.last or LAST_SEASON[league]
        for ss in range(max(lo, FIRST_SEASON[league]), hi + 1):
            path = cache_path(league, ss)
            if not path.exists() and args.fetch:
                fetch(league, ss, args.timeout)
            tag = f"{league.upper():4s} {season_arg(league, ss):8s}"
            if not path.exists():
                skipped += 1
                print(f"{tag} NOT RUN: LeagueDashPlayerStats not cached ({path.name})")
                continue
            if ss not in by_season:
                skipped += 1
                print(f"{tag} NOT RUN: no roster rows for this season in {ROSTERS[league].name}")
                continue
            ldps = pl.read_csv(path)
            allowed = {p for (lg, s, p) in allowlist if lg == league and s == ss}
            r = compare(by_season[ss], ldps, allowed)
            ran += 1
            n_flag = r["flagged"].height
            flagged_seasons += n_flag > 0
            status = "FLAG" if n_flag else "ok"
            print(f"{tag} {status}: {r['ldps_players']} players in LeagueDashPlayerStats, "
                  f"{r['missing'].height} not on any roster "
                  f"({r['missing_gp_share']:.2%} of games played), "
                  f"{r['allowlisted']} allowlisted, {n_flag} unexplained; "
                  f"{r['unplayed']} rostered players never appeared")
            for row in r["flagged"].head(args.top).iter_rows(named=True):
                print(f"       missing: {row['PLAYER_NAME']} ({row.get('TEAM_ABBREVIATION')}, "
                      f"GP {row['GP']}, id {row['PLAYER_ID']})")

    total = ran + skipped
    print()
    print(f"Participation check: {ran} of {total} league-seasons compared, "
          f"{flagged_seasons} with unexplained missing players.")
    if skipped:
        print(f"*** THE CHECK DID NOT RUN for {skipped} of {total} league-seasons "
              f"(LeagueDashPlayerStats not cached). Run with --fetch when "
              f"stats.nba.com is reachable. ***")
    if args.require_all and skipped:
        return 2
    if args.fail_on_flags and flagged_seasons:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
