"""WNBA extension: jersey numbers and heights, the NCAA digit rule, and league age.
Python implementation (polars + plotly).

Written from the definitions below, independently of R/08_wnba_analysis.R, so
that python/09_reconcile_wnba.py is a real check. Cleaning follows
python/03_analysis.py exactly: HEIGHT "6-9" parsed to inches and rows without a
height dropped, NUM read as text and cast to a number (blank or non-numeric
entries drop out of number-based metrics only), first row kept per
(PLAYER_ID, season_start).

Three parts:
  1. WNBA replication of the NBA season metrics, plus share_digit69 (share of
     numbered players wearing a number that contains any digit 6-9), and the
     era bootstrap of the correlation change (last 5 vs first 5 seasons).
  2. The NCAA digit rule as a natural experiment. NCAA basketball permitted
     numbers 0-99 starting with the 2023-24 season, so rookies whose last
     college season was 2023-24 or later (WNBA rookie seasons 2024-2026, NBA
     rookie seasons 2024-25 and 2025-26) are the first exposed classes.
  3. League age: NBA season_start - 1946, WNBA season_start - 1997.

Every table is sorted on its keys before it is written or bootstrapped: polars
group_by and join row order is not stable between runs.

Outputs (output/wnba/):
    season_metrics_python.csv   league, metric, season_start, league_age, value, n, included
    era_bootstrap_python.csv    WNBA correlation change, last 5 minus first 5 seasons
    rookie_status_python.csv    rookie identification audit, per league and season
    school_class_python.csv     NCAA classification counts, per league and rookie status
    rookie_shares_python.csv    6-9 digit share per league, group, and window
    rookie_classes_python.csv   6-9 digit share per league, group, and season
    rookie_bootstrap_python.csv bootstrap CIs for exposed-minus-earlier contrasts
Figures: figures/fig7..fig13 (interactive HTML, one panel each).

Run:  python python/08_wnba_analysis.py
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT_DIR = ROOT / "output" / "wnba"
FIG_DIR = ROOT / "figures"

# ---- Definitions (judgment calls; each is documented in the README) ---------
# First season of each league; league age = season_start - this. It is also the
# inaugural season, in which every player is a first appearance, so it is never
# a rookie class.
LEAGUE_START = {"nba": 1946, "wnba": 1997}
# Number-based metrics count for a season only when at least this share of its
# players (height parsed, de-duplicated) have a parseable jersey number. Early
# NBA rosters are missing NUM for up to three quarters of players.
COVERAGE_MIN = 0.90
# First rookie season whose last college season was 2023-24 or later (NCAA
# permitted numbers 0-99 starting with 2023-24). Rookie classes from here on
# are "exposed".
EXPOSED_FIRST = {"nba": 2024, "wnba": 2024}
# The primary comparison window: this many rookie classes immediately before
# exposure. A second comparison uses every earlier rookie class.
PRE_WINDOW = 10
REPS = 2000
SEED = 2026

# SCHOOL values that are not an NCAA school: blank, "none", or "unknown"
# entries (in recent seasons these are all international players), US high
# schools and prep academies, junior colleges, pro and development pathways
# (G League Ignite, Overtime Elite), plus an exact-match list of international
# clubs, countries, and cities kept in data/school_non_ncaa.csv.
NON_NCAA_BLANK = {"", "none", "no college", "unknown"}
NON_NCAA_PATTERN = re.compile(
    r"\bHS\b|High School|\bPrep\b|Preparatory|Academy \([A-Z]{2}\)"
    r"|G League|Ignite|Overtime Elite"
    r"|\bC\.C\.|\bJ\.C\.|\bCC\b|Community College|Junior College")

# Palette, matching 03_analysis.py.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
LEAGUE_COLOUR = {"nba": BLUE, "wnba": ORANGE}
LEAGUE_LABEL = {"nba": "NBA", "wnba": "WNBA"}

KEEP_COLS = ["PLAYER_ID", "PLAYER", "NUM", "HEIGHT", "EXP", "SCHOOL", "season_start"]


# ---- Pure functions (unit-tested in tests/python/test_wnba.py) --------------

def has_digit_69(raw: str | None) -> bool | None:
    """True when a jersey number contains any digit 6-9; None when missing."""
    if raw is None or raw.strip() == "":
        return None
    return re.search(r"[6-9]", raw.strip()) is not None


def league_age(season_start: int, league: str) -> int:
    """Seasons since the league's first season: NBA 1946 -> 0, WNBA 1997 -> 0."""
    return season_start - LEAGUE_START[league]


def load_non_ncaa() -> frozenset[str]:
    return frozenset(pl.read_csv(DATA / "school_non_ncaa.csv", infer_schema_length=0)
                     ["SCHOOL"].to_list())


def classify_school(school: str | None, non_ncaa: frozenset[str]) -> str:
    """'ncaa' or 'non_ncaa' from the roster SCHOOL field (rules in the README)."""
    s = "" if school is None else school.strip()
    if s.lower() in NON_NCAA_BLANK or NON_NCAA_PATTERN.search(s) or s in non_ncaa:
        return "non_ncaa"
    return "ncaa"


def identify_rookies(players: pl.DataFrame, league_first_season: int) -> pl.DataFrame:
    """Add first_season and rookie_status ('rookie', 'veteran', 'excluded').

    rookie:   EXP == "R" AND this is the player's first season in the data.
    veteran:  EXP is a number (1, 2, ...).
    excluded: the league's inaugural season (everyone is a first appearance);
              EXP == "R" on a later roster (a drafted player who sat a season);
              EXP missing.
    """
    first = players.group_by("PLAYER_ID").agg(first_season=pl.col("season_start").min())
    exp = pl.col("EXP").fill_null("").str.strip_chars()
    return (players.join(first, on="PLAYER_ID", how="left")
            .with_columns(rookie_status=pl
                          .when(pl.col("season_start") == league_first_season).then(pl.lit("excluded"))
                          .when((exp == "R") & (pl.col("season_start") == pl.col("first_season")))
                          .then(pl.lit("rookie"))
                          .when(exp.str.contains(r"^\d+$")).then(pl.lit("veteran"))
                          .otherwise(pl.lit("excluded")))
            .sort(["season_start", "PLAYER_ID"]))


# ---- Loading ----------------------------------------------------------------

def parse_height_expr(col: str) -> pl.Expr:
    feet = pl.col(col).str.extract(r"^(\d+)-", 1).cast(pl.Float64, strict=False)
    inches = pl.col(col).str.extract(r"-(\d+)$", 1).cast(pl.Float64, strict=False)
    return (feet * 12 + inches).alias("height_in")


def load_players(league: str) -> pl.DataFrame:
    files = (["nba_early_rosters.csv", "nba_rosters.csv"] if league == "nba"
             else ["wnba_rosters.csv"])
    raw = pl.concat([pl.read_csv(DATA / f, infer_schema_length=0).select(KEEP_COLS)
                     for f in files])
    non_ncaa = load_non_ncaa()
    return (raw.with_columns(
                pl.col("season_start").cast(pl.Int32),
                parse_height_expr("HEIGHT"),
                pl.col("NUM").fill_null("").str.strip_chars().alias("jersey_raw"))
            .with_columns(pl.col("jersey_raw").cast(pl.Float64, strict=False).alias("jersey_num"))
            .filter(pl.col("height_in").is_not_null())
            .unique(subset=["PLAYER_ID", "season_start"], keep="first", maintain_order=True)
            .with_columns(
                digit69=pl.col("jersey_raw").str.contains(r"[6-9]"),
                school_class=pl.col("SCHOOL").map_elements(
                    lambda s: classify_school(s, non_ncaa), return_dtype=pl.Utf8,
                    skip_nulls=False),
                league=pl.lit(league))
            .sort(["season_start", "PLAYER_ID"]))


# ---- Part 1 and 3: season metrics -------------------------------------------

def season_metrics(players: pl.DataFrame, league: str) -> pl.DataFrame:
    numbered = players.filter(pl.col("jersey_num").is_not_null())
    cov = (players.group_by("season_start")
           .agg(n=pl.len(), value=pl.col("jersey_num").is_not_null().mean())
           .with_columns(metric=pl.lit("num_coverage")))
    height = (players.group_by("season_start")
              .agg(n=pl.len(), value=pl.col("height_in").mean())
              .with_columns(metric=pl.lit("mean_height_in")))
    nums = (numbered.group_by("season_start")
            .agg(n=pl.len(),
                 share_above_55=(pl.col("jersey_num") > 55).mean(),
                 share_zero=pl.col("jersey_raw").is_in(["0", "00"]).mean(),
                 share_digit69=pl.col("digit69").mean(),
                 jersey_height_cor=pl.corr("jersey_num", "height_in"))
            .unpivot(index=["season_start", "n"],
                     on=["share_above_55", "share_zero", "share_digit69", "jersey_height_cor"],
                     variable_name="metric", value_name="value"))
    cols = ["metric", "season_start", "value", "n"]
    out = pl.concat([cov.select(cols), height.select(cols), nums.select(cols)])
    included = cov.select("season_start", included=(pl.col("value") >= COVERAGE_MIN).cast(pl.Int32))
    return (out.join(included, on="season_start", how="left")
            .with_columns(league=pl.lit(league),
                          league_age=pl.col("season_start") - LEAGUE_START[league],
                          n=pl.col("n").cast(pl.Int64))
            .select("league", "metric", "season_start", "league_age", "value", "n", "included")
            .sort(["league", "metric", "season_start"]))


def era_bootstrap(players: pl.DataFrame, league: str, reps: int = REPS,
                  seed: int = SEED) -> pl.DataFrame | None:
    """Change in jersey/height correlation, last 5 minus first 5 seasons."""
    numbered = (players.filter(pl.col("jersey_num").is_not_null())
                .sort(["season_start", "PLAYER_ID"]))
    seasons = numbered["season_start"].unique().sort().to_list()
    if len(seasons) < 12:
        return None
    a = numbered.filter(pl.col("season_start").is_in(seasons[:5])).select(
        "jersey_num", "height_in").to_numpy()
    b = numbered.filter(pl.col("season_start").is_in(seasons[-5:])).select(
        "jersey_num", "height_in").to_numpy()
    rng = np.random.default_rng(seed)
    diffs = np.empty(reps)
    for i in range(reps):
        ia = rng.integers(0, len(a), len(a))
        ib = rng.integers(0, len(b), len(b))
        diffs[i] = (np.corrcoef(b[ib, 0], b[ib, 1])[0, 1]
                    - np.corrcoef(a[ia, 0], a[ia, 1])[0, 1])
    lo, hi = np.quantile(diffs, [0.025, 0.975])
    cor_a = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    cor_b = float(np.corrcoef(b[:, 0], b[:, 1])[0, 1])
    return pl.DataFrame([{
        "league": league, "quantity": "cor_diff_last5_minus_first5",
        "first_lo": seasons[0], "first_hi": seasons[4],
        "last_lo": seasons[-5], "last_hi": seasons[-1],
        "cor_first5": cor_a, "cor_last5": cor_b, "observed": cor_b - cor_a,
        "estimate": float(diffs.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
        "reps": reps, "n_first": len(a), "n_last": len(b),
    }])


# ---- Part 2: the NCAA digit rule ---------------------------------------------

def rookie_frame(players: pl.DataFrame, league: str) -> pl.DataFrame:
    """Numbered player-seasons tagged with group and window.

    group:  ncaa_rookie, non_ncaa_rookie, veteran
    window: exposed  (season >= EXPOSED_FIRST)
            recent   (the PRE_WINDOW seasons before exposure)
            all_pre  (every season before exposure, inaugural season excluded)
    A recent row is also an all_pre row, so windows overlap by design.
    Seasons below the NUM coverage threshold are dropped (first appearance is
    still computed from every season).
    """
    exp_first = EXPOSED_FIRST[league]
    covered = (players.group_by("season_start")
               .agg(cov=pl.col("jersey_num").is_not_null().mean())
               .filter(pl.col("cov") >= COVERAGE_MIN)["season_start"])
    tagged = (identify_rookies(players, LEAGUE_START[league])
              .filter(pl.col("season_start").is_in(covered.to_list())
                      & pl.col("jersey_num").is_not_null()
                      & (pl.col("rookie_status") != "excluded"))
              .with_columns(group=pl.when(pl.col("rookie_status") == "veteran")
                            .then(pl.lit("veteran"))
                            .otherwise(pl.col("school_class") + "_rookie")))
    windows = [
        tagged.filter(pl.col("season_start") >= exp_first).with_columns(window=pl.lit("exposed")),
        tagged.filter(pl.col("season_start").is_between(exp_first - PRE_WINDOW, exp_first - 1))
        .with_columns(window=pl.lit("recent")),
        tagged.filter(pl.col("season_start") < exp_first).with_columns(window=pl.lit("all_pre")),
    ]
    return (pl.concat(windows).with_columns(league=pl.lit(league))
            .sort(["league", "group", "window", "season_start", "PLAYER_ID"]))


def rookie_status_audit(players: pl.DataFrame, league: str) -> pl.DataFrame:
    """Per season: EXP == "R" count, first-appearance count, and agreement."""
    t = identify_rookies(players, LEAGUE_START[league])
    exp_r = pl.col("EXP").fill_null("").str.strip_chars() == "R"
    first = pl.col("season_start") == pl.col("first_season")
    return (t.group_by("season_start")
            .agg(n=pl.len(), exp_r=exp_r.sum(), first_app=first.sum(),
                 both=(exp_r & first).sum(), exp_r_only=(exp_r & ~first).sum(),
                 first_only=(~exp_r & first).sum(),
                 rookies=(pl.col("rookie_status") == "rookie").sum(),
                 veterans=(pl.col("rookie_status") == "veteran").sum(),
                 excluded=(pl.col("rookie_status") == "excluded").sum())
            .with_columns(pl.exclude("season_start").cast(pl.Int64), league=pl.lit(league))
            .select("league", "season_start", "n", "exp_r", "first_app", "both",
                    "exp_r_only", "first_only", "rookies", "veterans", "excluded")
            .sort(["league", "season_start"]))


def school_class_counts(players: pl.DataFrame, league: str) -> pl.DataFrame:
    t = identify_rookies(players, LEAGUE_START[league])
    return (t.group_by("rookie_status", "school_class").agg(n=pl.len().cast(pl.Int64))
            .with_columns(league=pl.lit(league))
            .select("league", "rookie_status", "school_class", "n")
            .sort(["league", "rookie_status", "school_class"]))


def rookie_shares(frame: pl.DataFrame) -> pl.DataFrame:
    return (frame.group_by("league", "group", "window")
            .agg(n=pl.len().cast(pl.Int64), n_digit69=pl.col("digit69").sum().cast(pl.Int64),
                 share=pl.col("digit69").mean(),
                 season_lo=pl.col("season_start").min(), season_hi=pl.col("season_start").max())
            .sort(["league", "group", "window"]))


def rookie_classes(frame: pl.DataFrame) -> pl.DataFrame:
    return (frame.filter(pl.col("window") == "all_pre")
            .vstack(frame.filter(pl.col("window") == "exposed"))
            .group_by("league", "group", "season_start")
            .agg(n=pl.len().cast(pl.Int64), n_digit69=pl.col("digit69").sum().cast(pl.Int64),
                 share=pl.col("digit69").mean())
            .sort(["league", "group", "season_start"]))


# contrast name -> (group, pre window, control group or None)
CONTRASTS = {
    "ncaa_rookie_recent": ("ncaa_rookie", "recent", None),
    "non_ncaa_rookie_recent": ("non_ncaa_rookie", "recent", None),
    "veteran_recent": ("veteran", "recent", None),
    "ncaa_rookie_all_pre": ("ncaa_rookie", "all_pre", None),
    "non_ncaa_rookie_all_pre": ("non_ncaa_rookie", "all_pre", None),
    "veteran_all_pre": ("veteran", "all_pre", None),
    "did_ncaa_rookie_vs_veteran": ("ncaa_rookie", "recent", "veteran"),
    "did_ncaa_vs_non_ncaa_rookie": ("ncaa_rookie", "recent", "non_ncaa_rookie"),
}


def _cell(frame: pl.DataFrame, group: str, window: str) -> np.ndarray:
    return (frame.filter((pl.col("group") == group) & (pl.col("window") == window))
            .sort(["season_start", "PLAYER_ID"])["digit69"].cast(pl.Float64).to_numpy())


def rookie_bootstrap(frame: pl.DataFrame, league: str, reps: int = REPS,
                     seed: int = SEED) -> pl.DataFrame:
    """Share(exposed) - share(pre), optionally minus the same for a control group.

    Each cell is resampled independently (players with replacement within
    group and window), in the fixed order pre, exposed, control pre, control
    exposed. The estimate is the observed contrast; the CI is the 2.5% and
    97.5% percentiles of the bootstrap distribution.
    """
    rows = []
    for name, (group, pre_w, ctrl) in CONTRASTS.items():
        cells = [_cell(frame, group, pre_w), _cell(frame, group, "exposed")]
        if ctrl is not None:
            cells += [_cell(frame, ctrl, pre_w), _cell(frame, ctrl, "exposed")]
        row = {"league": league, "contrast": name, "group": group, "pre_window": pre_w,
               "control": ctrl or "", "n_pre": len(cells[0]), "n_exposed": len(cells[1]),
               "n_ctrl_pre": len(cells[2]) if ctrl else 0,
               "n_ctrl_exposed": len(cells[3]) if ctrl else 0,
               "observed": None, "ci_lo": None, "ci_hi": None, "reps": reps}
        if all(len(c) for c in cells):
            def contrast(cs):
                d = cs[1].mean() - cs[0].mean()
                return d - (cs[3].mean() - cs[2].mean()) if ctrl else d
            rng = np.random.default_rng(seed)
            draws = np.empty(reps)
            for i in range(reps):
                draws[i] = contrast([c[rng.integers(0, len(c), len(c))] for c in cells])
            lo, hi = np.quantile(draws, [0.025, 0.975])
            row.update(observed=float(contrast(cells)), ci_lo=float(lo), ci_hi=float(hi))
        rows.append(row)
    return pl.DataFrame(rows, schema_overrides={"observed": pl.Float64, "ci_lo": pl.Float64,
                                                "ci_hi": pl.Float64}).sort(["league", "contrast"])


# ---- Figures ------------------------------------------------------------------

def base_layout(title: str, subtitle: str, x_title: str | None, y_title: str | None) -> go.Layout:
    axis = dict(showgrid=True, gridcolor=GRID, gridwidth=0.5, zeroline=False,
                linecolor=AXIS, linewidth=1, tickfont=dict(color=MUTED, size=11))
    return go.Layout(
        title=dict(text=f"<b>{title}</b><br><span style='font-size:12px;color:{INK2}'>"
                        f"{subtitle}</span>",
                   font=dict(size=17, color=INK), x=0, xanchor="left"),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color=INK2),
        xaxis=dict(title=dict(text=x_title, font=dict(color=INK2, size=12)) if x_title else None,
                   **axis),
        yaxis=dict(title=dict(text=y_title, font=dict(color=INK2, size=12)) if y_title else None,
                   **axis),
        showlegend=False, hovermode="x unified",
        margin=dict(l=70, r=130, t=80, b=50), width=900, height=500)


def save(fig: go.Figure, stem: str) -> None:
    fig.write_html(FIG_DIR / f"{stem}.html", include_plotlyjs="cdn")


def _line(fig, x, y, colour, label, fmt):
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=colour, width=2),
                             name=label, hovertemplate=f"{label} %{{x}}: %{{y:{fmt}}}<extra></extra>"))
    fig.add_annotation(x=x[-1], y=y[-1], text=label, showarrow=False, xanchor="left",
                       xshift=8, font=dict(color=colour, size=13))


def make_figures(metrics: pl.DataFrame, shares: pl.DataFrame) -> None:
    w = metrics.filter(pl.col("league") == "wnba")

    fig = go.Figure(layout=base_layout(
        "WNBA number conventions by season", "Share of numbered players per season",
        None, "Share of numbered players"))
    for metric, colour, label in (("share_above_55", BLUE, "Number above 55"),
                                  ("share_zero", ORANGE, "Wearing 0 or 00"),
                                  ("share_digit69", AQUA, "Any digit 6-9")):
        sub = w.filter(pl.col("metric") == metric).sort("season_start")
        _line(fig, sub["season_start"].to_list(), sub["value"].to_list(), colour, label, ".1%")
    fig.update_yaxes(tickformat=".0%")
    save(fig, "fig7_wnba_number_conventions")

    sub = w.filter(pl.col("metric") == "jersey_height_cor").sort("season_start")
    fig = go.Figure(layout=base_layout(
        "WNBA: jersey number and height, season by season",
        "Per-season correlation between jersey number and listed height", None,
        "Pearson correlation"))
    fig.add_hline(y=0, line=dict(color=AXIS, width=1))
    fig.add_trace(go.Scatter(x=sub["season_start"].to_list(), y=sub["value"].to_list(),
                             mode="lines", line=dict(color=ORANGE, width=2), name="WNBA",
                             hovertemplate="%{x}: r = %{y:.3f}<extra></extra>"))
    save(fig, "fig8_wnba_jersey_height_cor")

    for stem, metric, title, y_title, fmt in (
            ("fig9_league_age_cor", "jersey_height_cor",
             "Jersey number and height, by league age", "Pearson correlation", ".3f"),
            ("fig10_league_age_above55", "share_above_55",
             "Numbers above 55, by league age", "Share of numbered players", ".1%"),
            ("fig11_league_age_digit69", "share_digit69",
             "Numbers with a digit 6-9, by league age", "Share of numbered players", ".1%")):
        fig = go.Figure(layout=base_layout(
            title, "Seasons since each league's first season (NBA 1946-47, WNBA 1997); "
                   "seasons below the NUM coverage threshold are omitted",
            "League age (seasons)", y_title))
        if metric == "jersey_height_cor":
            fig.add_hline(y=0, line=dict(color=AXIS, width=1))
        for league in ("nba", "wnba"):
            sub = (metrics.filter((pl.col("league") == league) & (pl.col("metric") == metric)
                                  & (pl.col("included") == 1))
                   .sort("league_age"))
            _line(fig, sub["league_age"].to_list(), sub["value"].to_list(),
                  LEAGUE_COLOUR[league], LEAGUE_LABEL[league], fmt)
        if metric != "jersey_height_cor":
            fig.update_yaxes(tickformat=".0%")
        save(fig, stem)

    labels = {"ncaa_rookie": "NCAA rookies", "non_ncaa_rookie": "Non-NCAA rookies",
              "veteran": "Veterans"}
    for league, stem in (("wnba", "fig12_wnba_rookie_digit69"),
                         ("nba", "fig13_nba_rookie_digit69")):
        sub = (shares.filter((pl.col("league") == league) & (pl.col("window") != "all_pre"))
               .sort(["group", "window"], descending=[False, True]))
        x = [f"{labels[g]}<br>{lo}-{hi}" for g, lo, hi in
             zip(sub["group"], sub["season_lo"], sub["season_hi"])]
        colours = [ORANGE if wdw == "exposed" else BLUE for wdw in sub["window"]]
        fig = go.Figure(layout=base_layout(
            f"{LEAGUE_LABEL[league]}: numbers with a digit 6-9, before and after the NCAA change",
            "Share of numbered players; blue = earlier seasons, orange = exposed seasons",
            None, "Share wearing a 6-9 digit"))
        fig.add_trace(go.Bar(
            x=x, y=sub["share"].to_list(), marker=dict(color=colours),
            customdata=list(zip(sub["n_digit69"].to_list(), sub["n"].to_list())),
            hovertemplate="%{x}: %{y:.1%} (%{customdata[0]} of %{customdata[1]})<extra></extra>"))
        fig.update_layout(hovermode="closest")
        fig.update_yaxes(tickformat=".0%")
        save(fig, stem)


# ---- Main ---------------------------------------------------------------------

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)
    players = {lg: load_players(lg) for lg in ("nba", "wnba")}
    for lg, p in players.items():
        print(f"{LEAGUE_LABEL[lg]}: {p.height:,} player-seasons, "
              f"{p['season_start'].min()}-{p['season_start'].max()}")

    metrics = pl.concat([season_metrics(p, lg) for lg, p in players.items()]).sort(
        ["league", "metric", "season_start"])
    metrics.write_csv(OUT_DIR / "season_metrics_python.csv")

    boot = era_bootstrap(players["wnba"], "wnba")
    boot.write_csv(OUT_DIR / "era_bootstrap_python.csv")
    print(f"WNBA era bootstrap: {boot['estimate'][0]:+.3f} "
          f"[{boot['ci_lo'][0]:+.3f}, {boot['ci_hi'][0]:+.3f}]")

    pl.concat([rookie_status_audit(p, lg) for lg, p in players.items()]).write_csv(
        OUT_DIR / "rookie_status_python.csv")
    pl.concat([school_class_counts(p, lg) for lg, p in players.items()]).write_csv(
        OUT_DIR / "school_class_python.csv")

    frames = {lg: rookie_frame(p, lg) for lg, p in players.items()}
    shares = pl.concat([rookie_shares(f) for f in frames.values()]).sort(
        ["league", "group", "window"])
    shares.write_csv(OUT_DIR / "rookie_shares_python.csv")
    pl.concat([rookie_classes(f) for f in frames.values()]).sort(
        ["league", "group", "season_start"]).write_csv(OUT_DIR / "rookie_classes_python.csv")
    rb = pl.concat([rookie_bootstrap(f, lg) for lg, f in frames.items()]).sort(
        ["league", "contrast"])
    rb.write_csv(OUT_DIR / "rookie_bootstrap_python.csv")

    make_figures(metrics, shares)
    print("WNBA extension (Python) complete: wrote output/wnba/*_python.csv and 7 figures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
