"""Tests for python/roster_guard.py and its use by the harvest and combine steps.

An empty CommonTeamRoster response is accepted only when the team did not play
that season. Everything else must fail loudly rather than be cached and skipped.
"""
from __future__ import annotations

import pandas as pd
import polars as pl
import pytest

from conftest import load_script

ATL, CHA, NOP = 1610612737, 1610612766, 1610612740


@pytest.fixture()
def table(tmp_path):
    """League 'nba' covers 2000-2005; ATL played 2000-2005, CHA 2000-2001 and 2004-2005."""
    rows = [("nba", ATL, y) for y in range(2000, 2006)]
    rows += [("nba", CHA, y) for y in (2000, 2001, 2004, 2005)]
    path = tmp_path / "active.csv"
    pl.DataFrame(rows, schema=["league", "team_id", "season_start"], orient="row").write_csv(path)
    return path


def test_empty_for_team_that_did_not_play_is_accepted(guard, table):
    assert guard.validate_roster("nba", CHA, 2002, 0, table) is None  # gap years


def test_empty_for_team_that_played_is_refused(guard, table):
    why = guard.validate_roster("nba", ATL, 2003, 0, table)
    assert why and "played" in why  # the silent branch: a failed call looks like this


def test_empty_outside_table_coverage_is_refused(guard, table):
    # edge: cannot show the franchise did not exist when the table does not cover the season
    assert "outside" in guard.validate_roster("nba", ATL, 2006, 0, table)
    assert "outside" in guard.validate_roster("nba", ATL, 1999, 0, table)


def test_nonempty_for_team_that_did_not_play_is_refused(guard, table):
    assert "did not play" in guard.validate_roster("nba", CHA, 2002, 12, table)


def test_nonempty_outside_coverage_is_accepted(guard, table):
    # edge: a new season the table has not reached yet cannot contradict a real roster
    assert guard.validate_roster("nba", ATL, 2010, 14, table) is None


def test_normal_roster_accepted(guard, table):
    assert guard.validate_roster("nba", ATL, 2003, 15, table) is None


def test_unknown_league_refused(guard, table):
    assert "not in" in guard.validate_roster("gleague", ATL, 2003, 15, table)


def test_missing_table_exits(guard, tmp_path):
    with pytest.raises(SystemExit):
        guard.validate_roster("nba", ATL, 2003, 15, tmp_path / "nope.csv")


@pytest.fixture()
def cache(tmp_path):
    d = tmp_path / "cache"
    d.mkdir()
    return d


def write_roster(dirpath, season, team, n):
    df = pd.DataFrame({"PLAYER_ID": range(n), "PLAYER": ["x"] * n})
    df.to_csv(dirpath / f"{season}_{team}.csv", index=False)  # n=0 writes a header only


def test_audit_cache_lists_every_problem(guard, table, cache):
    write_roster(cache, 2002, CHA, 0)   # fine
    write_roster(cache, 2003, ATL, 0)   # bad: empty for a team that played
    write_roster(cache, 2002, ATL, 14)  # fine
    write_roster(cache, 2001, CHA, 0)   # bad: CHA played 2001
    problems = guard.audit_cache(cache, "nba", table)
    assert len(problems) == 2
    assert any(p.startswith(f"2003_{ATL}.csv") for p in problems)
    assert any(p.startswith(f"2001_{CHA}.csv") for p in problems)


def test_require_clean_exits_with_the_list(guard, table, cache):
    write_roster(cache, 2003, ATL, 0)
    with pytest.raises(SystemExit) as e:
        guard.require_clean(cache, "nba", table)
    assert f"2003_{ATL}.csv" in str(e.value)


def test_require_clean_passes_on_clean_cache(guard, table, cache):
    write_roster(cache, 2002, CHA, 0)
    write_roster(cache, 2002, ATL, 14)
    guard.require_clean(cache, "nba", table)


# ---- the real cache and table ----------------------------------------------

def test_real_caches_pass_the_guard(guard):
    """Every cached empty roster in the repo is a team-season the table says did not exist."""
    data = guard.ROOT / "data"
    for sub, league in (("raw_rosters", "nba"), ("raw_rosters_nba_early", "nba"),
                        ("raw_rosters_wnba", "wnba")):
        if (data / sub).exists():
            assert guard.audit_cache(data / sub, league) == []


def test_real_table_knows_the_charlotte_gap(guard):
    # Hornets left after 2001-02... the new Bobcats began 2004-05: 2002 and 2003 starts are empty.
    assert guard.validate_roster("nba", CHA, 2002, 0) is None
    assert guard.validate_roster("nba", CHA, 2003, 0) is None
    assert guard.validate_roster("nba", CHA, 2004, 0) is not None


# ---- harvest 01 and combine 02 use the guard --------------------------------

class FakeResp:
    def __init__(self, df):
        self.df = df

    def get_data_frames(self):
        return [self.df]


@pytest.fixture()
def harvest(tmp_path, monkeypatch):
    mod = load_script("python/01_harvest_rosters.py", "harvest01")
    monkeypatch.setattr(mod, "RAW_DIR", tmp_path)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod, "MAX_RETRIES", 2)
    return mod


def test_harvest_refuses_to_cache_empty_for_active_team(harvest, tmp_path, monkeypatch):
    monkeypatch.setattr(harvest, "CommonTeamRoster", lambda **kw: FakeResp(pd.DataFrame()))
    # Atlanta 2010: certainly played, so an empty response is a failed call
    assert harvest.fetch_team_season(ATL, "ATL", 2010) is None
    assert not list(tmp_path.glob("*.csv"))


def test_harvest_caches_empty_for_inactive_franchise(harvest, tmp_path, monkeypatch):
    monkeypatch.setattr(harvest, "CommonTeamRoster", lambda **kw: FakeResp(pd.DataFrame()))
    df = harvest.fetch_team_season(CHA, "CHA", 2002)  # the Charlotte gap
    assert df is not None and df.empty
    assert (tmp_path / f"2002_{CHA}.csv").exists()


def test_harvest_caches_real_roster(harvest, tmp_path, monkeypatch):
    full = pd.DataFrame({"PLAYER_ID": [1, 2], "PLAYER": ["a", "b"]})
    monkeypatch.setattr(harvest, "CommonTeamRoster", lambda **kw: FakeResp(full))
    assert len(harvest.fetch_team_season(ATL, "ATL", 2010)) == 2


def test_harvest_ignores_a_bad_cached_empty_and_refetches(harvest, tmp_path, monkeypatch):
    pd.DataFrame({"PLAYER_ID": []}).to_csv(tmp_path / f"2010_{ATL}.csv", index=False)
    full = pd.DataFrame({"PLAYER_ID": [1], "PLAYER": ["a"]})
    monkeypatch.setattr(harvest, "CommonTeamRoster", lambda **kw: FakeResp(full))
    assert len(harvest.fetch_team_season(ATL, "ATL", 2010)) == 1
    assert len(pd.read_csv(tmp_path / f"2010_{ATL}.csv")) == 1


def test_combine_fails_with_the_list_on_bad_empty(tmp_path, monkeypatch):
    comb = load_script("python/02_combine.py", "combine02")
    monkeypatch.setattr(comb, "RAW_DIR", tmp_path)
    monkeypatch.setattr(comb, "OUT_CSV", tmp_path / "out.csv")
    write_roster(tmp_path, 2010, ATL, 0)
    write_roster(tmp_path, 2010, NOP, 12)
    with pytest.raises(SystemExit) as e:
        comb.main()
    assert f"2010_{ATL}.csv" in str(e.value)
    assert not (tmp_path / "out.csv").exists()


def test_combine_skips_verified_empty(tmp_path, monkeypatch):
    comb = load_script("python/02_combine.py", "combine02b")
    monkeypatch.setattr(comb, "RAW_DIR", tmp_path)
    monkeypatch.setattr(comb, "OUT_CSV", tmp_path / "out.csv")
    write_roster(tmp_path, 2002, CHA, 0)   # franchise gap: legitimately empty
    write_roster(tmp_path, 2010, ATL, 3)
    assert comb.main() == 0
    assert pl.read_csv(tmp_path / "out.csv").height == 3
