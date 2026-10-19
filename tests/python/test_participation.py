"""Tests for python/11_participation_check.py."""
from __future__ import annotations

import polars as pl
import pytest


def ldps(rows):
    return pl.DataFrame(rows, schema=["PLAYER_ID", "PLAYER_NAME", "GP"], orient="row")


def test_compare_finds_missing_and_unplayed(participation):
    l = ldps([(1, "A", 50), (2, "B", 30), (3, "C", 20)])
    r = participation.compare({1, 2, 9}, l, allowed=set())
    assert r["missing"]["PLAYER_ID"].to_list() == [3]
    assert r["flagged"].height == 1
    assert r["unplayed"] == 1  # 9 is on a roster but never appeared
    assert r["missing_gp_share"] == pytest.approx(20 / 100)


def test_compare_allowlist_clears_flag(participation):
    l = ldps([(1, "A", 50), (3, "C", 20)])
    r = participation.compare({1}, l, allowed={3})
    assert r["missing"].height == 1 and r["flagged"].height == 0 and r["allowlisted"] == 1


def test_compare_dedupes_traded_players(participation):
    l = ldps([(1, "A", 50), (1, "A", 10)])
    assert participation.compare({1}, l, set())["ldps_players"] == 1


def test_compare_edge_empty_ldps(participation):
    r = participation.compare({1}, ldps([]).cast({"PLAYER_ID": pl.Int64, "GP": pl.Int64}), set())
    assert r["missing"].height == 0 and r["missing_gp_share"] == 0.0


def test_season_arg(participation):
    assert participation.season_arg("nba", 2024) == "2024-25"
    assert participation.season_arg("nba", 1999) == "1999-00"  # edge: century rollover
    assert participation.season_arg("wnba", 2025) == "2025"


@pytest.fixture()
def isolated(participation, tmp_path, monkeypatch):
    """Point the check at a temp cache, roster, and allowlist."""
    monkeypatch.setattr(participation, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(participation, "ALLOWLIST", tmp_path / "allow.csv")
    roster = tmp_path / "nba.csv"
    pl.DataFrame({"PLAYER_ID": ["1", "2"], "season_start": ["2000", "2000"]}).write_csv(roster)
    monkeypatch.setitem(participation.ROSTERS, "nba", roster)
    return tmp_path


def run(participation, *extra):
    return participation.main(["--league", "nba", "--from", "2000", "--to", "2000", *extra])


def test_uncached_season_skips_loudly_with_exit_zero(participation, isolated, capsys):
    assert run(participation) == 0
    out = capsys.readouterr().out
    assert "NOT RUN" in out and "THE CHECK DID NOT RUN" in out


def test_require_all_makes_a_skip_fail(participation, isolated):
    assert run(participation, "--require-all") == 2


def test_flags_exit_nonzero_only_when_asked(participation, isolated, capsys):
    cache = participation.CACHE_DIR
    cache.mkdir(parents=True)
    pl.DataFrame({"PLAYER_ID": [1, 2, 3], "PLAYER_NAME": ["a", "b", "c"], "GP": [10, 10, 5]}) \
        .write_csv(participation.cache_path("nba", 2000))
    assert run(participation) == 0                       # report only
    assert "FLAG" in capsys.readouterr().out
    assert run(participation, "--fail-on-flags") == 1


def test_allowlist_file_clears_the_flag(participation, isolated):
    participation.CACHE_DIR.mkdir(parents=True)
    pl.DataFrame({"PLAYER_ID": [1, 2, 3], "PLAYER_NAME": ["a", "b", "c"], "GP": [10, 10, 5]}) \
        .write_csv(participation.cache_path("nba", 2000))
    pl.DataFrame({"league": ["nba"], "season_start": [2000], "player_id": [3],
                  "player_name": ["c"], "note": ["x"]}).write_csv(participation.ALLOWLIST)
    assert run(participation, "--fail-on-flags") == 0


def test_seed_reduces_columns(participation, isolated, tmp_path):
    src = tmp_path / "full.csv"
    pl.DataFrame({"PLAYER_ID": [1], "PLAYER_NAME": ["a"], "TEAM_ID": [5],
                  "TEAM_ABBREVIATION": ["X"], "GP": [3], "MIN": [1.5], "PTS": [9]}).write_csv(src)
    out = participation.seed("nba", 2000, src)
    assert pl.read_csv(out).columns == ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID",
                                        "TEAM_ABBREVIATION", "GP", "MIN"]


def test_seeded_2024_nba_matches_the_audit(participation):
    """The seeded 2024-25 NBA file reproduces the audit: 41 of 569 players missing, all allowlisted."""
    path = participation.cache_path("nba", 2024)
    if not path.exists() or not participation.ROSTERS["nba"].exists():
        pytest.skip("seed or roster data not present")
    r = participation.compare(participation.roster_ids_by_season("nba")[2024], pl.read_csv(path),
                              {p for (lg, s, p) in participation.load_allowlist()
                               if lg == "nba" and s == 2024})
    assert r["ldps_players"] == 569 and r["missing"].height == 41 and r["flagged"].height == 0
