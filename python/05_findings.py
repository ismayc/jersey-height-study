"""Generate the Findings section of the study README from the computed results.

Written so no number in the write-up is typed by hand. Every figure quoted in the
prose is read from output/, which means the narrative cannot drift away from the
analysis when the data is refreshed.

Run:  python python/05_findings.py
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
README = ROOT / "README.md"
MARKER = "## Findings"


def fmt_season(year: int) -> str:
    return f"{year}-{str(year + 1)[-2:]}"


def series(results: pl.DataFrame, metric: str) -> pl.DataFrame:
    return results.filter(pl.col("metric") == metric).drop_nulls("value").sort("season_start")


def build() -> str:
    results = pl.read_csv(OUT / "results_python.csv")
    models = pl.read_csv(OUT / "models_python.csv")

    height = series(results, "mean_height_in")
    above55 = series(results, "share_above_55")
    zero = series(results, "share_zero")
    cor = series(results, "jersey_height_cor")
    num6 = series(results, "num6_count")

    first_season = int(height["season_start"][0])
    last_season = int(height["season_start"][-1])

    peak_row = height.sort("value", descending=True).row(0, named=True)
    h_first, h_last = float(height["value"][0]), float(height["value"][-1])
    peak_season, peak_val = int(peak_row["season_start"]), float(peak_row["value"])
    n_seasons = height.height

    # Decompose the post-peak decline to separate the 2019-20 measurement-rule
    # change from any genuine drift.
    by_year = dict(zip(height["season_start"].to_list(), height["value"].to_list()))
    d2002, d2018 = by_year[peak_season], by_year[2018]
    d2019, d2024 = by_year[2019], by_year[last_season]

    # Largest single-season drops, so the 2019 step can be put in context.
    years = sorted(by_year)
    drops = sorted(((y, by_year[y] - by_year[p]) for p, y in zip(years, years[1:])),
                   key=lambda t: t[1])
    second_year, second_drop = next((y, v) for y, v in drops if y != 2019)

    hm = models.filter(pl.col("model") == "height_piecewise")
    slope_pre = float(hm.filter(pl.col("term") == "season_start")["estimate"][0])
    post = hm.filter(pl.col("term") == "post")
    slope_post_delta = float(post["estimate"][0]) if post.height else float("nan")
    slope_post = slope_pre + slope_post_delta

    # Regime-aware model: the 2019 measurement step as a fitted level shift.
    rm = models.filter(pl.col("model") == "height_regime")
    shift = rm.filter(pl.col("term") == "shift2019").row(0, named=True)

    # Within-player check on the same step: continuing players only, so roster
    # composition cannot explain it.
    wp = pl.read_csv(OUT / "within_player_python.csv").sort("pair_start")
    wp2018 = wp.filter(pl.col("pair_start") == 2018).row(0, named=True)
    wp_other = wp.filter(pl.col("pair_start") != 2018)
    typical_shrunk = float(wp_other["share_shrunk"].median())

    cm = models.filter(pl.col("model") == "jersey_height_cor_trend")
    cor_slope = float(cm.filter(pl.col("term") == "season_start")["estimate"][0])
    cor_p = float(cm.filter(pl.col("term") == "season_start")["p.value"][0])
    # Never print "p = 0.0000"; it reads as exactly zero, which it never is.
    p_text = "p < 0.0001" if cor_p < 1e-4 else f"p = {cor_p:.4f}"

    a55_first, a55_last = float(above55["value"][0]), float(above55["value"][-1])
    z_first, z_last = float(zero["value"][0]), float(zero["value"][-1])
    cor_first, cor_last = float(cor["value"][0]), float(cor["value"][-1])

    boot_path = OUT / "bootstrap_python.csv"
    boot_line = ""
    if boot_path.exists():
        b = pl.read_csv(boot_path).row(0, named=True)
        boot_line = (
            f"A bootstrap of the change between the first and last five seasons puts it at "
            f"**{b['estimate']:+.3f}** (95% CI [{b['ci_lo']:+.3f}, {b['ci_hi']:+.3f}], "
            f"{int(b['reps']):,} resamples). "
            + ("The interval excludes zero, so the weakening is not an artifact of sampling."
               if b["ci_hi"] < 0 or b["ci_lo"] > 0 else
               "The interval includes zero, so this analysis cannot claim the change is real.")
        )

    # Validation check: number 6 was retired league-wide ahead of 2022-23. Existing
    # wearers were grandfathered, so the expected signature is a decline starting
    # that season rather than a single-season cliff.
    recent6 = num6.filter(pl.col("season_start") >= 2018)
    if recent6.height and int(recent6["season_start"][-1]) >= 2023:
        counts = " → ".join(
            f"**{int(v)}** ({fmt_season(int(s))})"
            for s, v in zip(recent6["season_start"], recent6["value"])
        )
        # Compare like with like: the four seasons immediately before the rule,
        # not the 45-season average, which is dragged down by smaller early rosters.
        pre6 = num6.filter(pl.col("season_start").is_between(2018, 2021))["value"].mean()
        post6 = num6.filter(pl.col("season_start") >= 2023)["value"].mean()
        v6 = (f"Players wearing number 6, by season: {counts}.\n\n"
              f"The count averaged **{pre6:.1f}** per season across the four seasons before "
              f"the rule (2018-19 to 2021-22) and **{post6:.1f}** in the two seasons after it "
              f"took full effect. That is the expected signature: the NBA retired number 6 "
              f"league-wide for Bill Russell ahead of 2022-23 but grandfathered existing "
              f"wearers, so the decline is an attrition curve rather than a cliff.\n\n"
              f"The pipeline was never told about this rule. Reproducing a known external "
              f"fact from the data is the cheapest evidence available that the harvest, "
              f"de-duplication, and number parsing are behaving.")
    else:
        v6 = "Number 6 validation check needs seasons on both sides of 2022-23."

    return f"""{MARKER}

Covering {fmt_season(first_season)} through {fmt_season(last_season)}. Every number
below is generated by `python/05_findings.py` from `output/`, not typed by hand.

### 1. Height rose, peaked — and then mostly changed measuring tape

Mean listed height went from **{h_first:.2f} in** in {fmt_season(first_season)} to
**{h_last:.2f} in** in {fmt_season(last_season)}, peaking at **{peak_val:.2f} in** in
{fmt_season(peak_season)}. The piecewise fit puts the pre-1990 trend at
**{slope_pre:+.4f} in/season** and the post-1990 trend at **{slope_post:+.4f} in/season**.

**The obvious read of that is wrong, and this is the most important result here.**
Decomposing the {d2002 - d2024:.3f} in decline from {fmt_season(peak_season)} to
{fmt_season(last_season)}:

| Period | Change | Note |
|---|---|---|
| {fmt_season(peak_season)} → {fmt_season(2018)} | **{d2018 - d2002:+.3f} in** | gradual, over 16 seasons |
| {fmt_season(2018)} → {fmt_season(2019)} | **{d2019 - d2018:+.3f} in** | **one season** |
| {fmt_season(2019)} → {fmt_season(last_season)} | **{d2024 - d2019:+.3f} in** | flat to slightly rising |

That single {fmt_season(2019)} step is **{abs(d2019 - d2018) / abs(d2024 - d2002):.0%} of the
entire decline**, and it is the largest year-over-year move in all
{n_seasons} seasons — {abs(d2019 - d2018) / abs(second_drop):.1f}× the next largest
({second_drop:+.3f} in, {fmt_season(second_year)}).

{fmt_season(2019)} is exactly when the NBA began requiring measured heights without
shoes. The league did not get shorter that summer; the ruler changed. Players have
been *slightly taller* since.

Two further checks pin that attribution down:

- **Modelled, not eyeballed.** A regime-aware model (piecewise trend, knots at
  1990 and 2002, plus a level-shift term at 2019) estimates the rule-change step
  at **{shift['estimate']:+.3f} in** (95% CI [{shift['conf.low']:+.3f}, {shift['conf.high']:+.3f}]).
  Fitting the shift explicitly also stops the break from contaminating the trend
  slopes on either side of it.
- **Within-player, so roster turnover cannot explain it.** Among the
  **{wp2018['n_matched']}** players rostered in both {fmt_season(2018)} and {fmt_season(2019)},
  **{wp2018['share_shrunk']:.0%}** got shorter on paper, with a mean change of
  **{wp2018['mean_delta']:+.2f} in** — against a typical offseason, where the median
  share of continuing players whose listed height changes downward is
  **{typical_shrunk:.0%}**. The same players, measured two ways, account for
  essentially the whole aggregate step.

The defensible claim is narrow: heights rose into the early 2000s, drifted down
modestly through the 2010s ({d2018 - d2002:+.3f} in over 16 seasons), and have been
stable since. Anyone quoting the raw peak-to-today number as a basketball trend is
quoting a measurement change.

### 2. Number conventions loosened

Numbers above 55 went from **{a55_first:.1%}** of numbered players to **{a55_last:.1%}**.
Players wearing 0 or 00 went from **{z_first:.1%}** to **{z_last:.1%}**.

### 3. The jersey/height link has weakened

The per-season correlation between jersey number and listed height moved from
**{cor_first:+.3f}** to **{cor_last:+.3f}**, trending **{cor_slope:+.5f} per season**
({p_text}). {boot_line}

Interpretation, with the caveat from limitation 5: the old convention of big men in
the 50s and guards in single digits has decayed. Whether that is looser number
rules, positional convergence, or both, this analysis cannot separate.

### 4. Validation: the Bill Russell check

{v6}
"""


def main() -> int:
    text = README.read_text()
    head = text.split(MARKER)[0].rstrip()
    README.write_text(head + "\n\n" + build())
    print(f"Updated Findings in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
