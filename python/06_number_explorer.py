"""Exploratory jersey-number analysis, season by season.

Two views the main study's conventions figure aggregates away:

  1. the median jersey number by season (with quartiles), 1980-81 through
     2024-25;
  2. the full number distribution per season, browsable with a slider
     (one frame per season) and a play button.

Number-parsing rules, applied identically everywhere and gated below:
  - "0" and "00" are POOLED into a single 0/00 bucket. They are distinct
    uniforms on a roster but the same number choice culturally, and the
    pooling is noted on every surface that shows it.
  - A handful of entries list several numbers for one season ("3-12-44");
    the first listed is used.
  - Blank/missing numbers are dropped and counted.

Outputs:  output/number_by_season.csv     per-season median/quartiles/shares
          output/number_explorer_validation.csv
          figures/fig5_median_number.html
          figures/fig6_number_histogram.html (slider + play)

Run:  python python/06_number_explorer.py           full build
      python python/06_number_explorer.py --check   offline gate replay
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nba_rosters.csv"
OUT = ROOT / "output"
FIG = ROOT / "figures"


def load_numbers() -> tuple[pl.DataFrame, dict]:
    raw = pl.read_csv(DATA, infer_schema_length=0)
    parsed = (raw.with_columns(num_txt=pl.col("NUM").str.strip_chars())
              .with_columns(first_tok=pl.col("num_txt")
                            .str.extract(r"^(\d+)", 1)))
    dropped = parsed.filter(pl.col("first_tok").is_null()).height
    multi = parsed.filter(pl.col("num_txt").str.contains(r"^\d+-")).height
    # first-token rule: "0-6" and "00-10" (multi-number seasons) pool too
    pooled_00 = parsed.filter(pl.col("num_txt")
                              .str.contains(r"^00(-|$)")).height
    pooled_0 = parsed.filter(pl.col("num_txt")
                             .str.contains(r"^0(-|$)")).height
    df = (parsed.filter(pl.col("first_tok").is_not_null())
          .with_columns(number=pl.col("first_tok").cast(pl.Int64),
                        season_start=pl.col("season_start").cast(pl.Int64))
          .select("season_start", "number", "PLAYER", "team_abbrev"))
    notes = {"dropped_blank": dropped, "multi_number_entries": multi,
             "pooled_0": pooled_0, "pooled_00": pooled_00,
             "kept": df.height, "raw": raw.height}
    return df, notes


def by_season(df: pl.DataFrame) -> pl.DataFrame:
    return (df.group_by("season_start")
            .agg(n=pl.len(),
                 median_number=pl.col("number").median(),
                 q25=pl.col("number").quantile(0.25),
                 q75=pl.col("number").quantile(0.75),
                 share_0_00=(pl.col("number") == 0).mean(),
                 share_50_plus=(pl.col("number") >= 50).mean())
            .sort("season_start")
            .with_columns(season=pl.format("{}-{}",
                                           pl.col("season_start"),
                                           (pl.col("season_start") + 1)
                                           .cast(pl.String)
                                           .str.slice(2, 2))))


def gates(df: pl.DataFrame, seasons: pl.DataFrame, notes: dict
          ) -> pl.DataFrame:
    rows = [
        {"check": "kept + dropped rows account for every roster row",
         "value": abs(notes["kept"] + notes["dropped_blank"]
                      - notes["raw"]), "threshold": 0},
        {"check": "per-season counts sum to the kept total",
         "value": abs(int(seasons["n"].sum()) - notes["kept"]),
         "threshold": 0},
        {"check": "pooled 0/00 bucket equals the raw '0' + '00' counts",
         "value": abs(df.filter(pl.col("number") == 0).height
                      - (notes["pooled_0"] + notes["pooled_00"])),
         "threshold": 0},
        {"check": "independent median re-derivation agrees (max |diff|)",
         "value": float(max(
             abs(float(seasons.filter(pl.col("season_start") == s)
                       ["median_number"][0])
                 - float(sorted(df.filter(pl.col("season_start") == s)
                                ["number"].to_list())[
                     len(df.filter(pl.col("season_start") == s)) // 2]
                     if len(df.filter(pl.col("season_start") == s)) % 2
                     else (lambda v, m: (v[m - 1] + v[m]) / 2)(
                         sorted(df.filter(pl.col("season_start") == s)
                                ["number"].to_list()),
                         len(df.filter(pl.col("season_start") == s)) // 2)))
             for s in seasons["season_start"].to_list())),
         "threshold": 1e-9},
    ]
    return pl.DataFrame(rows).with_columns(
        passed=pl.col("value") <= pl.col("threshold"))


def figures(df: pl.DataFrame, seasons: pl.DataFrame) -> None:
    import plotly.graph_objects as go

    # --- fig5: median with quartile band ------------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["q75"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["q25"], mode="lines",
        line=dict(width=0), fill="tonexty",
        fillcolor="rgba(30,58,95,0.12)", name="25th-75th percentile",
        hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=seasons["season"], y=seasons["median_number"],
        mode="lines+markers", name="median number",
        line=dict(color="#1E3A5F", width=2), marker=dict(size=5),
        customdata=seasons.select("share_0_00", "share_50_plus").to_numpy(),
        hovertemplate=("%{x}<br>median %{y}<br>0/00 share "
                       "%{customdata[0]:.1%} · 50+ share "
                       "%{customdata[1]:.1%}<extra></extra>")))
    fig.update_layout(
        title="Median jersey number by season, 1980-81 through 2024-25 "
              "(0 and 00 pooled)",
        xaxis_title="season", yaxis_title="jersey number",
        template="plotly_white", legend=dict(orientation="h", y=1.02,
                                             x=0, yanchor="bottom"))
    fig.update_xaxes(tickvals=[s for s in seasons["season"]
                               if int(s[:4]) % 5 == 0])
    fig.write_html(FIG / "fig5_median_number.html", include_plotlyjs="cdn")

    # --- fig6: per-season histogram with slider + play ----------------------
    # When exactly one player wore a number that season, hover names him.
    counts = (df.group_by("season_start", "number")
              .agg(n=pl.len(),
                   lone=pl.when(pl.len() == 1)
                   .then(pl.format("<br>only wearer: {} ({})",
                                   pl.col("PLAYER").first(),
                                   pl.col("team_abbrev").first()))
                   .otherwise(pl.lit(""))
                   .first()))
    season_list = sorted(seasons["season_start"].to_list())
    label = {s: seasons.filter(pl.col("season_start") == s)["season"][0]
             for s in season_list}
    xs = list(range(100))
    ticktext = ["0/00"] + [str(i) for i in range(1, 100)]

    def bars(s: int) -> tuple[list[int], list[list[str]]]:
        rows = {num: (n, lone) for num, n, lone in
                counts.filter(pl.col("season_start") == s)
                .select("number", "n", "lone").iter_rows()}
        ys = [rows.get(i, (0, ""))[0] for i in xs]
        custom = [[ticktext[i], rows.get(i, (0, ""))[1]] for i in xs]
        return ys, custom

    ymax = int(counts.group_by("season_start", "number").agg(
        pl.col("n").sum()).select(pl.col("n").max())[0, 0]) + 4

    def frame_bar(s: int) -> go.Bar:
        ys, custom = bars(s)
        return go.Bar(x=xs, y=ys, marker_color="#1E3A5F",
                      customdata=custom,
                      hovertemplate="number %{customdata[0]}<br>"
                      "%{y} players%{customdata[1]}<extra></extra>")

    frames = [go.Frame(name=label[s], data=[frame_bar(s)])
              for s in season_list]
    first = season_list[0]
    fig = go.Figure(data=frames[0].data, frames=frames)
    fig.update_layout(
        title="Who wears what: jersey-number distribution, one season at a "
              "time (0 and 00 pooled into the first bar)",
        xaxis=dict(title="jersey number", tickmode="array",
                   tickvals=list(range(0, 100, 5)),
                   ticktext=[ticktext[i] for i in range(0, 100, 5)]),
        yaxis=dict(title="players", range=[0, ymax]),
        template="plotly_white",
        updatemenus=[dict(type="buttons", x=0, y=1.12, xanchor="left",
                          buttons=[
                              dict(label="Play", method="animate",
                                   args=[None, dict(
                                       frame=dict(duration=350,
                                                  redraw=True),
                                       fromcurrent=True)]),
                              dict(label="Pause", method="animate",
                                   args=[[None], dict(
                                       mode="immediate",
                                       frame=dict(duration=0))]),
                          ])],
        sliders=[dict(
            active=0, x=0, len=1.0,
            currentvalue=dict(prefix="season: "),
            steps=[dict(label=label[s], method="animate",
                        args=[[label[s]],
                              dict(mode="immediate",
                                   frame=dict(duration=0, redraw=True))])
                   for s in season_list])])
    fig.write_html(FIG / "fig6_number_histogram.html",
                   include_plotlyjs="cdn")


def main(argv: list[str]) -> int:
    df, notes = load_numbers()
    seasons = by_season(df)
    checks = gates(df, seasons, notes)

    if "--check" in argv:
        committed = pl.read_csv(OUT / "number_by_season.csv")
        drift = (seasons.sort("season_start")["median_number"]
                 - committed.sort("season_start")["median_number"]
                 ).abs().max()
        ok = bool(checks["passed"].all()) and float(drift) < 1e-9
        print("NUMBER EXPLORER CHECK "
              + ("PASSED" if ok else "FAILED")
              + f" ({checks.height} gates; committed medians reproduce, "
                f"max drift {float(drift):.2e})")
        return 0 if ok else 1

    seasons.drop("season").write_csv(OUT / "number_by_season.csv")
    checks.write_csv(OUT / "number_explorer_validation.csv")
    print(f"parsing notes: {notes}")
    with pl.Config(tbl_rows=-1, fmt_str_lengths=60):
        print(seasons.select("season", "n", "median_number", "share_0_00"))
        print(checks)
    figures(df, seasons)

    ok = bool(checks["passed"].all())
    print("NUMBER EXPLORER VALIDATION " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
