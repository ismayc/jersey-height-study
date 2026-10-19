"""Unit tests for python/08_wnba_analysis.py pure functions."""
from __future__ import annotations

import polars as pl
import pytest


# ---- has_digit_69 ------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("00", False),   # edge: double zero has no 6-9 digit
    ("0", False),    # edge: single zero
    ("69", True),    # edge: both digits in range
    ("6", True),
    ("19", True),    # the 6-9 digit can be the second digit
    ("45", False),
    ("55", False),
    (" 7 ", True),   # stray whitespace does not hide the digit
])
def test_has_digit_69(wnba, raw, expected):
    assert wnba.has_digit_69(raw) is expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_has_digit_69_missing_is_unknown(wnba, raw):
    # edge: a missing NUM is unknown, not "no 6-9 digit"
    assert wnba.has_digit_69(raw) is None


def test_digit69_in_season_metrics(wnba):
    # "00", "0", "69", "16", and a missing NUM in one season: the missing one
    # counts for coverage and height, not for the number metrics.
    players = pl.DataFrame({
        "PLAYER_ID": ["a", "b", "c", "d", "e"],
        "season_start": [2000] * 5,
        "height_in": [70.0, 71.0, 72.0, 73.0, 74.0],
        "jersey_raw": ["00", "0", "69", "16", ""],
    }).with_columns(
        jersey_num=pl.col("jersey_raw").cast(pl.Float64, strict=False),
        digit69=pl.col("jersey_raw").str.contains(r"[6-9]"),
        season_start=pl.col("season_start").cast(pl.Int32))
    res = wnba.season_metrics(players, "wnba")

    def row(metric):
        return res.filter(pl.col("metric") == metric).row(0, named=True)

    assert row("share_digit69")["value"] == 0.5     # 69 and 16 of four numbered
    assert row("share_digit69")["n"] == 4
    assert row("share_zero")["value"] == 0.5        # "0" and "00"
    assert row("share_above_55")["value"] == 0.25   # only 69
    assert row("num_coverage")["value"] == 0.8      # four of five have a number
    assert row("num_coverage")["included"] == 0     # 0.8 is below the 0.9 threshold
    assert row("mean_height_in")["n"] == 5
    assert row("mean_height_in")["league_age"] == 3


# ---- league_age ----------------------------------------------------------------

def test_league_age(wnba):
    assert wnba.league_age(1946, "nba") == 0       # edge: the inaugural season
    assert wnba.league_age(1997, "wnba") == 0
    assert wnba.league_age(2026, "wnba") == 29
    assert wnba.league_age(1975, "nba") == 29      # same league age as WNBA 2026


def test_league_age_unknown_league(wnba):
    with pytest.raises(KeyError):
        wnba.league_age(2000, "g-league")


# ---- classify_school -----------------------------------------------------------

@pytest.mark.parametrize("school, expected", [
    (None, "non_ncaa"),                       # edge: missing SCHOOL
    ("", "non_ncaa"),
    ("   ", "non_ncaa"),
    ("None", "non_ncaa"),
    ("No College", "non_ncaa"),
    ("Unknown", "non_ncaa"),
    ("Lower Merion HS (PA)", "non_ncaa"),     # high school
    ("IMG Academy (FL)", "non_ncaa"),         # prep academy with a state code
    ("Athlete Institute Prep", "non_ncaa"),
    ("Blinn J.C.", "non_ncaa"),               # junior college
    ("Seward County CC", "non_ncaa"),
    ("G League Ignite", "non_ncaa"),
    ("Overtime Elite", "non_ncaa"),
    ("Real Madrid", "non_ncaa"),              # curated list
    ("Serbia-Montenegro", "non_ncaa"),
    (" Serbia-Montenegro", "non_ncaa"),       # leading space as in the feed
    ("Connecticut", "ncaa"),
    ("Virginia '96", "ncaa"),                 # year suffix
    ("Old Dominion '98/Portugal", "ncaa"),    # NCAA first, then abroad
    ("St. John's (NY)", "ncaa"),              # parentheses alone do not mean non-NCAA
    ("Air Force Academy", "ncaa"),            # "Academy" without a state code
    ("Arizona State", "ncaa"),
])
def test_classify_school(wnba, school, expected):
    assert wnba.classify_school(school, wnba.load_non_ncaa()) == expected


def test_non_ncaa_list_has_no_duplicates(wnba):
    rows = pl.read_csv(wnba.DATA / "school_non_ncaa.csv", infer_schema_length=0)
    assert rows.height == rows["SCHOOL"].n_unique()


# ---- identify_rookies ----------------------------------------------------------

def test_identify_rookies(wnba):
    players = pl.DataFrame({
        "PLAYER_ID": ["a", "a", "b", "b", "c", "d", "e", "f"],
        "season_start": [1997, 1998, 1998, 1999, 1999, 1999, 2000, 2000],
        "EXP": ["R", "1", "R", "R", "1", None, "R", "R"],
        "NUM": ["00", "0", "69", "69", None, "5", "", "7"],
    }).with_columns(pl.col("season_start").cast(pl.Int32))
    out = wnba.identify_rookies(players, 1997)
    status = {(r["PLAYER_ID"], r["season_start"]): r["rookie_status"]
              for r in out.iter_rows(named=True)}
    assert status[("a", 1997)] == "excluded"   # edge: inaugural season, never a class
    assert status[("a", 1998)] == "veteran"
    assert status[("b", 1998)] == "rookie"     # R and first appearance
    assert status[("b", 1999)] == "excluded"   # R again on a later roster
    assert status[("c", 1999)] == "veteran"    # first appearance but EXP 1
    assert status[("d", 1999)] == "excluded"   # EXP missing
    assert status[("e", 2000)] == "rookie"     # edge: missing NUM does not matter here
    assert out["season_start"].to_list() == sorted(out["season_start"].to_list())


# ---- bootstrap contrast ----------------------------------------------------------

def test_rookie_bootstrap_observed_and_empty_cell(wnba):
    # NCAA rookies: 1 of 4 before, 2 of 4 after -> +0.25. No non-NCAA rookies
    # exposed, so that contrast has no estimate.
    rows = []
    for i, d in enumerate([True, False, False, False]):
        rows.append(("ncaa_rookie", "recent", 2015, f"p{i}", d))
    for i, d in enumerate([True, True, False, False]):
        rows.append(("ncaa_rookie", "exposed", 2024, f"q{i}", d))
    for i, d in enumerate([False, True]):
        rows.append(("veteran", "recent", 2015, f"v{i}", d))
        rows.append(("veteran", "exposed", 2024, f"w{i}", d))
    rows.append(("non_ncaa_rookie", "recent", 2015, "x", True))
    frame = pl.DataFrame(rows, schema=["group", "window", "season_start", "PLAYER_ID", "digit69"],
                         orient="row")
    out = wnba.rookie_bootstrap(frame, "wnba", reps=200)
    by = {r["contrast"]: r for r in out.iter_rows(named=True)}
    assert by["ncaa_rookie_recent"]["observed"] == pytest.approx(0.25)
    assert by["did_ncaa_rookie_vs_veteran"]["observed"] == pytest.approx(0.25)
    assert by["non_ncaa_rookie_recent"]["observed"] is None
    assert by["non_ncaa_rookie_recent"]["n_exposed"] == 0
    lo, hi = by["ncaa_rookie_recent"]["ci_lo"], by["ncaa_rookie_recent"]["ci_hi"]
    assert lo <= 0.25 <= hi
