"""Unit tests for jersey-height-study/python/03_analysis.py pure functions."""
from __future__ import annotations

import polars as pl


def test_parse_height_basic(jersey):
    df = pl.DataFrame({"HEIGHT": ["6-9", "7-0", "5-11", "", "junk", None]})
    out = df.with_columns(jersey.parse_height_expr("HEIGHT"))["height_in"].to_list()
    assert out == [81.0, 84.0, 71.0, None, None, None]


def test_season_metrics_definitions(jersey):
    # Two seasons; season 2000: heights 72/84 with jerseys 0 and 56;
    # season 2001 adds a blank jersey (kept for height, dropped for numbers)
    # and a "00" (counts toward share_zero).
    players = pl.DataFrame({
        "season_start": [2000, 2000, 2001, 2001, 2001],
        "height_in": [72.0, 84.0, 72.0, 84.0, 78.0],
        "jersey_raw": ["0", "56", "00", "6", ""],
    }).with_columns(
        jersey_num=pl.col("jersey_raw").cast(pl.Float64, strict=False))
    res = jersey.season_metrics(players)

    def val(metric, season):
        return res.filter((pl.col("metric") == metric)
                          & (pl.col("season_start") == season))["value"][0]

    # mean height uses ALL rows, numbered or not
    assert val("mean_height_in", 2001) == 78.0
    # blank jersey drops out of number-based metrics
    n_2001 = res.filter((pl.col("metric") == "share_zero")
                        & (pl.col("season_start") == 2001))["n"][0]
    assert n_2001 == 2
    # "00" counts as zero; "0" too
    assert val("share_zero", 2000) == 0.5
    assert val("share_zero", 2001) == 0.5
    # 56 > 55 counts; the boundary itself would not
    assert val("share_above_55", 2000) == 0.5
    # number 6 count
    assert val("num6_count", 2001) == 1.0


def test_within_player_changes(jersey):
    # Player A shrinks 1 inch, player B unchanged, player C only in season 1.
    players = pl.DataFrame({
        "PLAYER_ID": ["A", "B", "C", "A", "B"],
        "season_start": [2000, 2000, 2000, 2001, 2001],
        "height_in": [80.0, 75.0, 82.0, 79.0, 75.0],
    })
    wp = jersey.within_player_changes(players).row(0, named=True)
    assert wp["pair_start"] == 2000
    assert wp["n_matched"] == 2
    assert wp["share_shrunk"] == 0.5
    assert wp["share_same"] == 0.5
    assert wp["share_grew"] == 0.0
    assert abs(wp["mean_delta"] - (-0.5)) < 1e-12


def test_era_bootstrap_needs_12_seasons(jersey):
    players = pl.DataFrame({
        "season_start": list(range(2000, 2011)),   # only 11 seasons
        "height_in": [78.0] * 11,
        "jersey_num": [10.0] * 11,
    })
    assert jersey.era_bootstrap(players) is None
