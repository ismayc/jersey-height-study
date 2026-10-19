"""Decide whether a CommonTeamRoster response may be trusted.

CommonTeamRoster returns an empty frame for a franchise that did not exist in a
season. It can return the same empty frame for a throttled, failed, or
truncated call. Before October 19, 2026 the harvest cached every empty frame as
"franchise did not exist" and the combine step skipped it, so a bad call would
have vanished without a trace.

This module holds the one rule both steps now share:

  * an EMPTY roster is accepted only when the team did not play that season,
    judged against data/franchise_active_seasons.csv (built by
    12_build_active_seasons.py from an independent team-season table);
  * an empty roster for a team that did play, or for a season the table does
    not cover (so "did not exist" cannot be shown), is a problem;
  * a NON-EMPTY roster for a team the table says did not play is also a problem
    (the table or the cache is wrong, and either way a person should look).

validate_roster() returns None when the response is acceptable, or a one-line
reason when it is not. Callers refuse to cache on a reason and fail with the
list.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_CSV = ROOT / "data" / "franchise_active_seasons.csv"


@lru_cache(maxsize=None)
def _load(path: Path) -> tuple[dict[str, frozenset[tuple[int, int]]], dict[str, tuple[int, int]]]:
    if not path.exists():
        raise SystemExit(f"Active-seasons table missing: {path}. "
                         "Run python/12_build_active_seasons.py.")
    d = pl.read_csv(path)
    active: dict[str, frozenset[tuple[int, int]]] = {}
    coverage: dict[str, tuple[int, int]] = {}
    for league in d["league"].unique().to_list():
        sub = d.filter(pl.col("league") == league)
        active[league] = frozenset(zip(sub["team_id"].to_list(), sub["season_start"].to_list()))
        coverage[league] = (int(sub["season_start"].min()), int(sub["season_start"].max()))
    return active, coverage


def validate_roster(league: str, team_id: int, season_start: int, n_rows: int,
                    path: Path | None = None) -> str | None:
    """None if the response is acceptable, else the reason it is not."""
    active, coverage = _load(path or ACTIVE_CSV)
    if league not in active:
        return f"league {league!r} not in the active-seasons table"
    lo, hi = coverage[league]
    covered = lo <= season_start <= hi
    played = (team_id, season_start) in active[league]
    tag = f"{league} team {team_id} season {season_start}"
    if n_rows == 0:
        if not covered:
            return (f"{tag}: empty roster, season outside the active-seasons table "
                    f"({lo}-{hi}); cannot show the franchise did not exist")
        if played:
            return f"{tag}: empty roster, but the team played that season (failed or truncated call?)"
        return None
    if covered and not played:
        return f"{tag}: {n_rows} players, but the table says the team did not play"
    return None


def audit_cache(raw_dir: Path, league: str, path: Path | None = None) -> list[str]:
    """Every problem in one cache directory (files named <season>_<team>.csv)."""
    problems = []
    for f in sorted(raw_dir.glob("*.csv")):
        season, team = (int(x) for x in f.stem.split("_"))
        with f.open(newline="") as fh:
            n = max(sum(1 for _ in csv.reader(fh)) - 1, 0)  # minus the header row
        why = validate_roster(league, team, season, n, path)
        if why:
            problems.append(f"{f.name}: {why}")
    return problems


def require_clean(raw_dir: Path, league: str, path: Path | None = None) -> None:
    """Exit with the full list if the cache holds an unacceptable roster."""
    problems = audit_cache(raw_dir, league, path)
    if problems:
        lines = "\n  ".join(problems)
        raise SystemExit(f"{len(problems)} cached roster(s) in {raw_dir} are not trustworthy. "
                         f"Delete these files and re-run the harvest:\n  {lines}")
