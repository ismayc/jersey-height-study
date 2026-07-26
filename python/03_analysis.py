"""NBA jersey numbers and player heights over time --- Python analysis (polars + plotly).

Deliberately an independent implementation of R/03_analysis.R rather than a port:
same metric definitions, written from the definitions rather than from the R code,
so that 04_reconcile.py is a real check instead of a formality.

Outputs:
    output/results_python.csv     season-level metrics
    output/models_python.csv      fitted model coefficients
    output/bootstrap_python.csv   bootstrap CI for the era change in correlation
    figures/*_py.png              static figures
    figures/*_py.html             interactive versions (hover tooltips)

statsmodels is used for the weighted regressions; there is no polars-native
equivalent, and it is what gives standard errors and confidence intervals
comparable to R's lm().

Run:  python python/03_analysis.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import polars as pl
import statsmodels.api as sm
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "data" / "nba_rosters.csv"
OUT_DIR = ROOT / "output"
FIG_DIR = ROOT / "figures"
OUT_DIR.mkdir(exist_ok=True)
FIG_DIR.mkdir(exist_ok=True)

# Palette validated for colour-vision separation (see README).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"


def base_layout(title: str, subtitle: str, y_title: str | None) -> go.Layout:
    """Recessive chrome: hairline grid, no top/right spines, muted ticks."""
    return go.Layout(
        title=dict(text=f"<b>{title}</b><br><span style='font-size:12px;color:{INK2}'>"
                        f"{subtitle}</span>",
                   font=dict(size=17, color=INK), x=0, xanchor="left"),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif",
                  size=12, color=INK2),
        xaxis=dict(showgrid=True, gridcolor=GRID, gridwidth=0.5, zeroline=False,
                   linecolor=AXIS, linewidth=1, tickfont=dict(color=MUTED, size=11)),
        yaxis=dict(title=dict(text=y_title, font=dict(color=INK2, size=12)) if y_title else None,
                   showgrid=True, gridcolor=GRID, gridwidth=0.5, zeroline=False,
                   linecolor=AXIS, linewidth=1, tickfont=dict(color=MUTED, size=11)),
        showlegend=False,          # series are direct-labelled instead
        hovermode="x unified",
        margin=dict(l=70, r=130, t=80, b=50),
        width=900, height=500,
    )


def save(fig: go.Figure, stem: str) -> None:
    fig.write_image(FIG_DIR / f"{stem}.png", scale=2)
    fig.write_html(FIG_DIR / f"{stem}.html", include_plotlyjs="cdn")


def parse_height_expr(col: str) -> pl.Expr:
    """'6-9' -> 81.0. Anything unparseable becomes null."""
    feet = pl.col(col).str.extract(r"^(\d+)-", 1).cast(pl.Float64, strict=False)
    inches = pl.col(col).str.extract(r"-(\d+)$", 1).cast(pl.Float64, strict=False)
    return (feet * 12 + inches).alias("height_in")


def load_players() -> pl.DataFrame:
    """Load and clean. Cleaning decisions are documented in the README."""
    raw = pl.read_csv(DATA_CSV, infer_schema_length=0)
    df = (
        raw.with_columns(
            pl.col("season_start").cast(pl.Int32),
            parse_height_expr("HEIGHT"),
            pl.col("NUM").fill_null("").str.strip_chars().alias("jersey_raw"),
            pl.col("POSITION").fill_null("").str.slice(0, 1).alias("position_group"),
        )
        .with_columns(
            pl.col("jersey_raw").cast(pl.Float64, strict=False).alias("jersey_num")
        )
        .filter(pl.col("height_in").is_not_null())
        # A mid-season trade puts one player on two rosters; keep the first row.
        .unique(subset=["PLAYER_ID", "season_start"], keep="first", maintain_order=True)
    )
    return df


def season_metrics(players: pl.DataFrame) -> pl.DataFrame:
    numbered = players.filter(pl.col("jersey_num").is_not_null())

    height = (
        players.group_by("season_start")
        .agg(n=pl.len(), value=pl.col("height_in").mean())
        .with_columns(metric=pl.lit("mean_height_in"))
        .select("metric", "season_start", "value", "n")
    )

    nums = (
        numbered.group_by("season_start")
        .agg(
            n=pl.len(),
            share_above_55=(pl.col("jersey_num") > 55).mean(),
            share_zero=pl.col("jersey_raw").is_in(["0", "00"]).mean(),
            num6_count=(pl.col("jersey_num") == 6).sum().cast(pl.Float64),
            jersey_height_cor=pl.corr("jersey_num", "height_in"),
        )
        .unpivot(
            index=["season_start", "n"],
            on=["share_above_55", "share_zero", "num6_count", "jersey_height_cor"],
            variable_name="metric", value_name="value",
        )
        .select("metric", "season_start", "value", "n")
    )

    return pl.concat([height, nums]).sort(["metric", "season_start"])


def fit_models(results: pl.DataFrame) -> pl.DataFrame:
    """Piecewise height trend (knot at 1990), a regime-aware height model, and
    the correlation trend."""
    rows: list[dict] = []

    h = (results.filter(pl.col("metric") == "mean_height_in")
         .with_columns(post=(pl.col("season_start") - 1990).clip(lower_bound=0)))
    X1 = sm.add_constant(h.select("season_start", "post").to_numpy())
    m1 = sm.WLS(h["value"].to_numpy(), X1, weights=h["n"].to_numpy()).fit()

    # Regime-aware model: piecewise trend with knots at 1990 and the 2002 peak,
    # plus a LEVEL SHIFT at the 2019-20 measurement rule change. The shift term
    # turns the eyeballed "-0.61 in step" into a modelled estimate with a CI,
    # and keeps the trend slopes from being contaminated by the break.
    # (Fit comparison on this data: R^2 0.85 vs 0.30 for the single-knot model.)
    hr = h.with_columns(
        k1990=(pl.col("season_start") - 1990).clip(lower_bound=0),
        k2002=(pl.col("season_start") - 2002).clip(lower_bound=0),
        shift2019=(pl.col("season_start") >= 2019).cast(pl.Float64),
    )
    X1b = sm.add_constant(hr.select("season_start", "k1990", "k2002", "shift2019").to_numpy())
    m1b = sm.WLS(hr["value"].to_numpy(), X1b, weights=hr["n"].to_numpy()).fit()

    c = (results.filter(pl.col("metric") == "jersey_height_cor")
         .drop_nulls("value"))
    X2 = sm.add_constant(c.select("season_start").to_numpy())
    m2 = sm.WLS(c["value"].to_numpy(), X2, weights=c["n"].to_numpy()).fit()

    naming = {
        "height_piecewise": (m1, ["(Intercept)", "season_start", "post"]),
        "height_regime": (m1b, ["(Intercept)", "season_start", "k1990", "k2002", "shift2019"]),
        "jersey_height_cor_trend": (m2, ["(Intercept)", "season_start"]),
    }
    for model_name, (model, terms) in naming.items():
        ci = model.conf_int()
        for i, term in enumerate(terms):
            rows.append({
                "model": model_name,
                "term": term,
                "estimate": float(model.params[i]),
                "std.error": float(model.bse[i]),
                "statistic": float(model.tvalues[i]),
                "p.value": float(model.pvalues[i]),
                "conf.low": float(ci[i][0]),
                "conf.high": float(ci[i][1]),
            })
    return pl.DataFrame(rows)


def within_player_changes(players: pl.DataFrame) -> pl.DataFrame:
    """Year-over-year listed-height change for players present in both seasons.

    This is the composition-free check on the 2019-20 measurement step: the
    aggregate mean can move because WHO plays changed, but a continuing player's
    listed height only moves when the measurement itself does. In the median
    offseason ~2% of continuing players' listed heights change (no other
    offseason since 1980 exceeds 27%, and most sit under 5%); if the rule
    change is real it should show up as a majority of continuing players
    'shrinking' in a single offseason.
    """
    seasons = players["season_start"].unique().sort().to_list()
    rows = []
    for s0, s1 in zip(seasons, seasons[1:]):
        a = players.filter(pl.col("season_start") == s0).select("PLAYER_ID", h0="height_in")
        b = players.filter(pl.col("season_start") == s1).select("PLAYER_ID", h1="height_in")
        j = a.join(b, on="PLAYER_ID", how="inner").with_columns(
            delta=pl.col("h1") - pl.col("h0"))
        if j.height == 0:
            continue
        rows.append({
            "pair_start": s0,
            "n_matched": j.height,
            "mean_delta": float(j["delta"].mean()),
            "share_shrunk": float((j["delta"] < 0).mean()),
            "share_same": float((j["delta"] == 0).mean()),
            "share_grew": float((j["delta"] > 0).mean()),
        })
    return pl.DataFrame(rows)


def era_bootstrap(players: pl.DataFrame, reps: int = 2000, seed: int = 2026) -> pl.DataFrame | None:
    """Bootstrap the change in jersey/height correlation, last 5 vs first 5 seasons."""
    numbered = players.filter(pl.col("jersey_num").is_not_null())
    seasons = numbered["season_start"].unique().sort().to_list()
    if len(seasons) < 12:
        print("Fewer than 12 seasons available; skipping era bootstrap.")
        return None

    a = numbered.filter(pl.col("season_start").is_in(seasons[:5])).select(
        "jersey_num", "height_in").to_numpy()
    b = numbered.filter(pl.col("season_start").is_in(seasons[-5:])).select(
        "jersey_num", "height_in").to_numpy()
    if len(a) < 30 or len(b) < 30:
        return None

    rng = np.random.default_rng(seed)
    diffs = np.empty(reps)
    for i in range(reps):
        ia = rng.integers(0, len(a), len(a))
        ib = rng.integers(0, len(b), len(b))
        diffs[i] = (np.corrcoef(b[ib, 0], b[ib, 1])[0, 1]
                    - np.corrcoef(a[ia, 0], a[ia, 1])[0, 1])

    lo, hi = np.quantile(diffs, [0.025, 0.975])
    print(f"Bootstrap correlation change: {diffs.mean():.3f} [{lo:.3f}, {hi:.3f}]")
    return pl.DataFrame([{
        "quantity": "cor_diff_last5_minus_first5",
        "estimate": float(diffs.mean()), "ci_lo": float(lo), "ci_hi": float(hi),
        "reps": reps,
    }])


def make_figures(players: pl.DataFrame, results: pl.DataFrame) -> None:
    # --- Figure 1: mean height with a t-based 95% band. One series, no legend.
    h = (players.group_by("season_start")
         .agg(n=pl.len(), mean=pl.col("height_in").mean(), sd=pl.col("height_in").std())
         .sort("season_start"))
    n = h["n"].to_numpy()
    se = h["sd"].to_numpy() / np.sqrt(n)
    crit = stats.t.ppf(0.975, n - 1)
    x = h["season_start"].to_list()
    mean, lo, hi = h["mean"].to_numpy(), h["mean"].to_numpy() - crit * se, h["mean"].to_numpy() + crit * se

    fig = go.Figure(layout=base_layout(
        "Most of the height &#8220;decline&#8221; is a 2019 measurement change",
        "Mean listed height per season, with 95% confidence band", "Height (inches)"))
    fig.add_trace(go.Scatter(x=x + x[::-1], y=list(hi) + list(lo)[::-1], fill="toself",
                             fillcolor="rgba(42,120,214,0.18)", line=dict(width=0),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=mean, mode="lines", line=dict(color=BLUE, width=2),
                             name="Mean height",
                             hovertemplate="%{x}: %{y:.2f} in<extra></extra>"))
    # The single largest year-over-year move in the series is a rule change, not a
    # basketball trend. Marking it keeps the chart from telling a false story.
    if 2019 in x:
        fig.add_vline(x=2019, line=dict(color=ORANGE, width=1.5, dash="dot"))
        fig.add_annotation(x=2019, y=max(hi), yanchor="bottom", xanchor="right", xshift=-6,
                           text="2019-20: measured heights,<br>no shoes, required",
                           showarrow=False, align="right",
                           font=dict(color=ORANGE, size=11))
    save(fig, "fig1_height_trend_py")

    # --- Figure 2: by position, direct-labelled at the right edge.
    pos = (players.filter(pl.col("position_group").is_in(["G", "F", "C"]))
           .group_by("season_start", "position_group")
           .agg(value=pl.col("height_in").mean())
           .sort("season_start"))
    colours = {"G": BLUE, "F": ORANGE, "C": AQUA}
    names = {"G": "Guards", "F": "Forwards", "C": "Centers"}

    fig = go.Figure(layout=base_layout(
        "Guards grew taller as the center–guard gap narrowed",
        "Mean listed height per season by position group", "Height (inches)"))
    for grp in ["G", "F", "C"]:
        sub = pos.filter(pl.col("position_group") == grp).sort("season_start")
        if sub.height == 0:
            continue
        fig.add_trace(go.Scatter(
            x=sub["season_start"].to_list(), y=sub["value"].to_list(), mode="lines",
            line=dict(color=colours[grp], width=2), name=names[grp],
            hovertemplate=f"{names[grp]} %{{x}}: %{{y:.2f}} in<extra></extra>"))
        fig.add_annotation(x=sub["season_start"][-1], y=sub["value"][-1], text=names[grp],
                           showarrow=False, xanchor="left", xshift=8,
                           font=dict(color=colours[grp], size=13))
    save(fig, "fig2_height_by_position_py")

    # --- Figure 3: number conventions.
    fig = go.Figure(layout=base_layout(
        "Jersey number conventions have loosened",
        "Share of numbered players per season", "Share of numbered players"))
    for metric, colour, label in (("share_above_55", BLUE, "Number above 55"),
                                  ("share_zero", ORANGE, "Wearing 0 or 00")):
        sub = results.filter(pl.col("metric") == metric).sort("season_start")
        if sub.height == 0:
            continue
        fig.add_trace(go.Scatter(
            x=sub["season_start"].to_list(), y=sub["value"].to_list(), mode="lines",
            line=dict(color=colour, width=2), name=label,
            hovertemplate=f"{label} %{{x}}: %{{y:.1%}}<extra></extra>"))
        fig.add_annotation(x=sub["season_start"][-1], y=sub["value"][-1], text=label,
                           showarrow=False, xanchor="left", xshift=8,
                           font=dict(color=colour, size=13))
    fig.update_yaxes(tickformat=".0%")
    save(fig, "fig3_number_conventions_py")

    # --- Figure 4: jersey/height correlation.
    cors = results.filter(pl.col("metric") == "jersey_height_cor").sort("season_start")
    if cors.height:
        fig = go.Figure(layout=base_layout(
            "The link between jersey number and height has faded",
            "Per-season correlation between jersey number and listed height",
            "Pearson correlation"))
        fig.add_hline(y=0, line=dict(color=AXIS, width=1))
        fig.add_trace(go.Scatter(
            x=cors["season_start"].to_list(), y=cors["value"].to_list(), mode="lines",
            line=dict(color=BLUE, width=2), name="Correlation",
            hovertemplate="%{x}: r = %{y:.3f}<extra></extra>"))
        save(fig, "fig4_jersey_height_cor_py")


def main() -> int:
    players = load_players()
    seasons = players["season_start"]
    print(f"Loaded {players.height:,} player-seasons across {seasons.n_unique()} seasons "
          f"({seasons.min()}-{seasons.max()})")

    results = season_metrics(players)
    results.write_csv(OUT_DIR / "results_python.csv")

    fit_models(results).write_csv(OUT_DIR / "models_python.csv")

    within_player_changes(players).write_csv(OUT_DIR / "within_player_python.csv")

    boot = era_bootstrap(players)
    if boot is not None:
        boot.write_csv(OUT_DIR / "bootstrap_python.csv")

    make_figures(players, results)
    print(f"Python analysis complete: {seasons.n_unique()} seasons; "
          f"wrote results, models, and 4 figures (PNG + interactive HTML).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
