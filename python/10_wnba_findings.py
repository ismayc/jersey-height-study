"""Generate the README's WNBA extension section from output/wnba/.

Owns one region, <!-- gen:wnba --> ... <!-- /gen:wnba -->, in the same way
python/05_findings.py owns its regions: the prose is fixed here and every
number, and every phrase that depends on a number ("excludes zero", "weaker
than the NBA's"), is computed from the committed outputs. Parameters (coverage
threshold, exposure season, window length, resamples) are read from
python/08_wnba_analysis.py, so the text cannot disagree with the code.

Run:    python python/10_wnba_findings.py            rewrite the region
        python python/10_wnba_findings.py --check    fail if the committed README
                                                     (abbr tags stripped) differs
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "wnba"
README = ROOT / "README.md"
REGION = re.compile(r"<!-- gen:wnba -->.*?<!-- /gen:wnba -->", re.S)
ABBR = re.compile(r'<abbr title="[^"]*">([^<]*)</abbr>')

_spec = importlib.util.spec_from_file_location("wnba_analysis", ROOT / "python" / "08_wnba_analysis.py")
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)

NSGA = ("NSGA release, June 9, 2023 (<https://nsga.org/?p=6571>): \"numbers 0 or 00 "
        "through 99 will be permitted in NCAA men's and women's basketball\"")
GROUP_LABEL = {"ncaa_rookie": "NCAA rookies", "non_ncaa_rookie": "Non-NCAA rookies",
               "veteran": "Veterans"}


def strip_abbr(text: str) -> str:
    return ABBR.sub(r"\1", text)


def fmt_season(year: int, league: str) -> str:
    """NBA seasons span two years (1980-81); WNBA seasons are one year (2024)."""
    return f"{year}-{str(year + 1)[-2:]}" if league == "nba" else str(year)


def span(lo: int, hi: int, league: str) -> str:
    return f"{fmt_season(lo, league)} to {fmt_season(hi, league)}"


def pts(x: float) -> str:
    return f"{x * 100:+.1f} points"


def excludes_zero(lo: float, hi: float) -> bool:
    return lo > 0 or hi < 0


def zero_phrase(py: dict, r: dict, short: bool = False) -> str:
    """Wording that needs both implementations' intervals to agree."""
    a, b = excludes_zero(py["ci_lo"], py["ci_hi"]), excludes_zero(r["ci_lo"], r["ci_hi"])
    if a and b:
        return "excludes zero"
    if not a and not b:
        return "includes zero"
    if short:
        return "borderline (R and Python disagree on zero)"
    return ("is borderline (one implementation's interval excludes zero and the "
            "other's does not)")


def join_list(items: list[str]) -> str:
    if len(items) <= 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def build() -> str:
    met = pl.read_csv(OUT / "season_metrics_python.csv")
    era = pl.read_csv(OUT / "era_bootstrap_python.csv").row(0, named=True)
    era_r = pl.read_csv(OUT / "era_bootstrap_r.csv").row(0, named=True)
    nba_boot = pl.read_csv(ROOT / "output" / "bootstrap_python.csv").row(0, named=True)
    audit = pl.read_csv(OUT / "rookie_status_python.csv")
    schools = pl.read_csv(OUT / "school_class_python.csv")
    shares = pl.read_csv(OUT / "rookie_shares_python.csv")
    rbp = {(r["league"], r["contrast"]): r
           for r in pl.read_csv(OUT / "rookie_bootstrap_python.csv").iter_rows(named=True)}
    rbr = {(r["league"], r["contrast"]): r
           for r in pl.read_csv(OUT / "rookie_bootstrap_r.csv").iter_rows(named=True)}

    def series(league: str, metric: str, covered: bool = True) -> pl.DataFrame:
        s = met.filter((pl.col("league") == league) & (pl.col("metric") == metric))
        if covered:
            s = s.filter(pl.col("included") == 1)
        return s.sort("season_start")

    # ---- Data and coverage -------------------------------------------------
    wh = series("wnba", "mean_height_in", covered=False)
    nh = series("nba", "mean_height_in", covered=False)
    w_first, w_last = int(wh["season_start"][0]), int(wh["season_start"][-1])
    n_first, n_last = int(nh["season_start"][0]), int(nh["season_start"][-1])
    w_n, n_n = int(wh["n"].sum()), int(nh["n"].sum())
    cov = met.filter(pl.col("metric") == "num_coverage").sort("league", "season_start")
    n_excl = cov.filter((pl.col("league") == "nba") & (pl.col("included") == 0))
    n_incl = cov.filter((pl.col("league") == "nba") & (pl.col("included") == 1))
    w_cov = cov.filter(pl.col("league") == "wnba")
    excl_lo, excl_hi = int(n_excl["season_start"].min()), int(n_excl["season_start"].max())
    excl_contiguous = n_excl.height == excl_hi - excl_lo + 1
    lowest_in = n_incl.sort("value").row(0, named=True)
    w_low = w_cov.sort("value").row(0, named=True)
    w_all_in = bool((w_cov["included"] == 1).all())

    # ---- Part 1: WNBA replication -----------------------------------------
    def first_last(metric: str) -> tuple[float, float]:
        s = series("wnba", metric)
        return float(s["value"][0]), float(s["value"][-1])

    h0, h1 = first_last("mean_height_in")
    a0, a1 = first_last("share_above_55")
    a_max = series("wnba", "share_above_55")["value"].max()
    z0, z1 = first_last("share_zero")
    d0, d1 = first_last("share_digit69")
    wc = series("wnba", "jersey_height_cor")
    c_lo_row = wc.sort("value").row(0, named=True)
    c_hi_row = wc.sort("value", descending=True).row(0, named=True)

    era_zero = zero_phrase(era, era_r)
    nba_est, nba_lo, nba_hi = nba_boot["estimate"], nba_boot["ci_lo"], nba_boot["ci_hi"]
    head1 = "1. WNBA replication"
    if era_zero == "includes zero":
        head1 = "1. The WNBA shows no collapse of the convention"
        rules_out = era["ci_lo"] > nba_est and era_r["ci_lo"] > nba_est
        verdict = ("**The WNBA shows none of the NBA's collapse.** "
                   + ("Its interval also rules out a drop as large as the NBA's "
                      f"({nba_est:+.3f}), so this is not just a small sample failing to "
                      "detect the same change."
                      if rules_out else
                      f"Its interval is wide enough to include a drop as large as the NBA's "
                      f"({nba_est:+.3f}), so the WNBA sample cannot rule that out."))
    elif era["observed"] < 0:
        if era["ci_lo"] > nba_hi:
            verdict = "**The WNBA shows a weaker version of the NBA's decline.**"
            head1 = "1. The WNBA shows a weaker version of the NBA's decline"
        elif era["ci_hi"] < nba_lo:
            verdict = "**The WNBA's decline is steeper than the NBA's.**"
        else:
            verdict = "**The WNBA's decline is comparable in size to the NBA's.**"
    else:
        verdict = "**The WNBA's correlation rose, the opposite of the NBA's collapse.**"

    # ---- Part 2: rookie identification and NCAA classes ----------------------
    def audit_sums(league: str) -> dict:
        a = audit.filter((pl.col("league") == league)
                         & (pl.col("season_start") > W.LEAGUE_START[league]))
        return {c: int(a[c].sum()) for c in ("exp_r", "first_app", "both", "exp_r_only",
                                               "first_only", "rookies")}

    aw, an = audit_sums("wnba"), audit_sums("nba")
    w_inaug = audit.filter((pl.col("league") == "wnba")
                           & (pl.col("season_start") == W.LEAGUE_START["wnba"])).row(0, named=True)

    def school_n(league: str, status: str, cls: str) -> int:
        s = schools.filter((pl.col("league") == league) & (pl.col("rookie_status") == status)
                           & (pl.col("school_class") == cls))
        return int(s["n"][0]) if s.height else 0

    exp_first = W.EXPOSED_FIRST["wnba"]
    nba_exp_first = W.EXPOSED_FIRST["nba"]
    w_exp_hi = int(w_last)

    def share_row(league: str, group: str, window: str) -> dict:
        return shares.filter((pl.col("league") == league) & (pl.col("group") == group)
                             & (pl.col("window") == window)).row(0, named=True)

    def table(league: str) -> str:
        lines = ["| Group | Earlier seasons | Exposed seasons | Change (95% CI) | Interval |",
                 "|---|---|---|---|---|"]
        for group in ("ncaa_rookie", "non_ncaa_rookie", "veteran"):
            pre = share_row(league, group, "recent")
            post = share_row(league, group, "exposed")
            b, br = rbp[(league, f"{group}_recent")], rbr[(league, f"{group}_recent")]
            lines.append(
                f"| {GROUP_LABEL[group]} | {pre['share']:.1%} ({pre['n_digit69']:,} of {pre['n']:,}, "
                f"{span(pre['season_lo'], pre['season_hi'], league)}) "
                f"| {post['share']:.1%} ({post['n_digit69']:,} of {post['n']:,}, "
                f"{span(post['season_lo'], post['season_hi'], league)}) "
                f"| {pts(b['observed'])} [{b['ci_lo'] * 100:+.1f}, {b['ci_hi'] * 100:+.1f}] "
                f"| {zero_phrase(b, br, short=True)} |")
        return "\n".join(lines)

    def contrast_txt(league: str, name: str) -> str:
        b, br = rbp[(league, name)], rbr[(league, name)]
        return (f"{pts(b['observed'])} (95% CI [{b['ci_lo'] * 100:+.1f}, "
                f"{b['ci_hi'] * 100:+.1f}], which {zero_phrase(b, br)})")

    def any_effect(league: str) -> bool:
        """True when the NCAA-rookie change and both difference-in-differences
        exclude zero in both implementations, all positive."""
        names = ["ncaa_rookie_recent", "did_ncaa_rookie_vs_veteran", "did_ncaa_vs_non_ncaa_rookie"]
        return all(zero_phrase(rbp[(league, n)], rbr[(league, n)]) == "excludes zero"
                   and rbp[(league, n)]["observed"] > 0 for n in names)

    w_post = share_row("wnba", "ncaa_rookie", "exposed")
    n_post = share_row("nba", "ncaa_rookie", "exposed")
    w_nn_post = share_row("wnba", "non_ncaa_rookie", "exposed")
    n_nn_post = share_row("nba", "non_ncaa_rookie", "exposed")
    w_b = rbp[("wnba", "ncaa_rookie_recent")]
    n_b = rbp[("nba", "ncaa_rookie_recent")]
    w_effect, n_effect = any_effect("wnba"), any_effect("nba")
    key = ["ncaa_rookie_recent", "did_ncaa_rookie_vs_veteran", "did_ncaa_vs_non_ncaa_rookie"]
    cleared = [(lg, n) for lg in ("wnba", "nba") for n in key
               if zero_phrase(rbp[(lg, n)], rbr[(lg, n)]) == "excludes zero"]
    if not w_effect and not n_effect:
        rule_verdict = (
            "**Neither league shows a detectable rise in 6-9 numbers among the first "
            "exposed NCAA classes.** "
            + ("No NCAA-rookie change, and no difference against either control, "
               "clears zero in either league."
               if not cleared else
               "Some contrasts clear zero (" + join_list([f"{lg.upper()} {n}" for lg, n in cleared])
               + "), but not the full set of the change and both control differences."))
    elif w_effect and n_effect:
        rule_verdict = ("**Both leagues show a rise in 6-9 numbers among exposed NCAA "
                        "rookies that clears both controls.**")
    else:
        which = "WNBA" if w_effect else "NBA"
        other = "NBA" if w_effect else "WNBA"
        rule_verdict = (f"**The {which} shows a rise among exposed NCAA rookies that clears "
                        f"both controls; the {other} cross-check does not replicate it.**")
    width_w = (w_b["ci_hi"] - w_b["ci_lo"]) * 100
    width_n = (n_b["ci_hi"] - n_b["ci_lo"]) * 100

    all_pre_w = share_row("wnba", "ncaa_rookie", "all_pre")
    all_pre_n = share_row("nba", "ncaa_rookie", "all_pre")

    # ---- Part 3: league age ----------------------------------------------------
    def age_window_mean(league: str, metric: str, lo: int, hi: int) -> float:
        s = series(league, metric).filter(pl.col("league_age").is_between(lo, hi))
        return float(s["value"].mean())

    both_ages = sorted(set(series("nba", "jersey_height_cor")["league_age"].to_list())
                       & set(series("wnba", "jersey_height_cor")["league_age"].to_list()))
    age_lo, age_hi = both_ages[0], both_ages[-1]
    early = (age_lo, age_lo + 4)
    late = (age_hi - 4, age_hi)
    age = {}
    for lg in ("nba", "wnba"):
        for metric in ("jersey_height_cor", "share_above_55", "share_digit69"):
            age[(lg, metric)] = (age_window_mean(lg, metric, *early),
                                 age_window_mean(lg, metric, *late))

    def direction(a: float, b: float, tol: float) -> str:
        return "rose" if b - a > tol else "fell" if a - b > tol else "held roughly level"

    nc, wc_ = age[("nba", "jersey_height_cor")], age[("wnba", "jersey_height_cor")]
    n6, w6 = age[("nba", "share_digit69")], age[("wnba", "share_digit69")]
    n55, w55 = age[("nba", "share_above_55")], age[("wnba", "share_above_55")]
    nba_age_last = int(series("nba", "jersey_height_cor")["league_age"].max())
    nba_late_cor = series("nba", "jersey_height_cor").filter(
        pl.col("league_age") > nba_age_last - 5)["value"].mean()

    excl_txt = (span(excl_lo, excl_hi, "nba") if excl_contiguous else
                join_list([fmt_season(int(s), "nba") for s in n_excl["season_start"]]))
    first_included = int(n_incl["season_start"].min())
    concentrated = (
        "Every excluded season comes before the first included one, so missing numbers "
        "are concentrated in the earliest rosters, and a season missing a large share "
        "of its numbers is measuring a different set of players, not a sample of the "
        "same one."
        if excl_hi < first_included else
        "Excluded seasons are interleaved with included ones, so the threshold is "
        "removing scattered gaps rather than an early era.")

    # The NBA's 6-9 share by decade, for the comparison-window caveat.
    n69 = series("nba", "share_digit69")
    d50 = float(n69.filter(pl.col("season_start").is_between(1950, 1959))["value"].mean())
    d70 = float(n69.filter(pl.col("season_start").is_between(1970, 1979))["value"].mean())
    decade_txt = (f"the NBA's 6-9 share averaged {d50:.1%} across its covered 1950s seasons "
                  f"and {d70:.1%} across the 1970s")

    # Where the WNBA started relative to where the NBA has ended up.
    gap = era["cor_first5"] - nba_late_cor
    start_txt = (f"The WNBA started ({era['cor_first5']:+.3f}) "
                 + ("near" if abs(gap) < 0.1 else "above" if gap > 0 else "below")
                 + f" the level the NBA has fallen to (its last five seasons average "
                   f"{nba_late_cor:+.3f})"
                 + (" and stayed there." if era_zero == "includes zero" else "."))

    # League-age conclusion, conditional on the directions computed above.
    nba_rose = direction(*nc, 0.05) == "rose"
    wnba_flat = direction(*wc_, 0.05) != "rose"
    nba_faded = nba_late_cor < nc[1] - 0.05
    if nba_rose and wnba_flat:
        head3 = ("3. League age: the NBA's convention strengthened as the league aged; "
                 "the WNBA's did not")
        age_conclusion = (
            "So the NBA's big-men-in-the-50s convention was weak at the earliest "
            f"well-covered league ages and strengthened through league age {age_hi}"
            + (" (it has since faded)" if nba_faded else "")
            + ", while the WNBA, at the same league ages, did not build one. The NBA's "
            f"seasons before league age {age_lo} fail the coverage threshold, so what the "
            "convention looked like in its very first seasons is not measured here.")
    else:
        head3 = "3. League age"
        age_conclusion = ("The two leagues do not show the contrast of one building the "
                          "convention while the other does not.")
    max55 = max(float(series(lg, "share_above_55").filter(
        pl.col("league_age").is_between(age_lo, age_hi))["value"].max()) for lg in ("nba", "wnba"))
    if max55 < 0.03:
        above55_lead = "Numbers above 55 were rare in both at every one of these ages"
        rare55 = f"; no single season above {max55:.1%}"
    else:
        above55_lead = "Numbers above 55, averaged over the same windows, were"
        rare55 = ""
    rule_hypothesis = (
        "Whether a college numbering rule fed the NBA's falling 6-9 share is a "
        "hypothesis this analysis does not test, since the old rule's start date is "
        "unverified." if direction(*n6, 0.02) == "fell" else "")
    head2 = ("2. The NCAA digit rule: no detectable effect yet, on small samples"
             if not w_effect and not n_effect else "2. The NCAA digit rule")

    return f"""
Does the WNBA show the NBA's collapse of the big-players-wear-high-numbers
convention? Did the NCAA's {fmt_season(exp_first - 1, "nba")} change to allow the digits 6-9 move the
numbers rookies choose? And how do the two leagues compare at the same league
age? Scripts: `python/08_wnba_analysis.py` and `R/08_wnba_analysis.R` (two
independent implementations), `python/09_reconcile_wnba.py` (the gate:
deterministic tables to 1e-9, bootstrap intervals by overlap and equal group
sizes, and the NBA seasons from {fmt_season(1980, "nba")} on against the main
study's own output), and `python/10_wnba_findings.py` (this section).

**Data.** WNBA rosters {span(w_first, w_last, "wnba")} ({wh.height} seasons,
{w_n:,} player-seasons after cleaning) from `CommonTeamRoster` with the WNBA
league ID, folded franchises included. For the league-age comparison, NBA
rosters {span(n_first, 1979, "nba")} (all franchises, defunct ones included)
are added to the main study's {span(1980, n_last, "nba")}, {n_n:,} NBA
player-seasons in all. Cleaning rules are the ones in the table above. One new
metric, `share_digit69`: the share of numbered players wearing a number with any
digit 6 through 9 ("6", "19", and "69" count; "0", "00", and "45" do not).

#### Judgment calls

- **Early-NBA coverage threshold.** Number-based metrics count for a season only
  when at least {W.COVERAGE_MIN:.0%} of its players have a parseable jersey number.
  This excludes the NBA's {excl_txt} ({n_excl.height} seasons; coverage
  {n_excl['value'].min():.0%} to {n_excl['value'].max():.0%}). The lowest included NBA
  season is {fmt_season(int(lowest_in['season_start']), "nba")} at {lowest_in['value']:.1%}.
  {"Every WNBA season passes" if w_all_in else "Not every WNBA season passes"}; the lowest is
  {fmt_season(int(w_low['season_start']), "wnba")} at {w_low['value']:.1%}. Height metrics do not
  depend on the threshold. {concentrated}
- **Rookies.** A rookie is a player whose `EXP` is "R" *and* who is in their
  first season in the data. The two signals mostly agree: across WNBA seasons after
  {fmt_season(W.LEAGUE_START["wnba"], "wnba")}, {aw['both']:,} rows satisfy both,
  {aw['exp_r_only']} have `EXP == "R"` on a later roster (most likely a player
  who sat out the season they were first rostered, so their last college season
  is earlier than the class suggests; not verified row by row), and {aw['first_only']} are first appearances
  with `EXP` of 1 or more (likely a player whose earlier stint ended before the
  end-of-season roster snapshot, also not verified row by row). Requiring both drops those ambiguous rows. The
  NBA figures are {an['both']:,}, {an['exp_r_only']}, and {an['first_only']}. The WNBA's
  inaugural {fmt_season(W.LEAGUE_START["wnba"], "wnba")} rosters ({w_inaug['n']} players, all
  first appearances) are never a rookie class. Veterans are rows with a numeric
  `EXP`.
- **NCAA background, from `SCHOOL`.** Non-NCAA means: blank, "None", "No College",
  or "Unknown" (on recent rookie rows these are all international players); a US high
  school or prep academy; a junior college; a pro or development pathway (G League
  Ignite, Overtime Elite, an NBA team); or one of the international clubs,
  countries, and cities listed in `data/school_non_ncaa.csv` (curated by reading
  every `SCHOOL` value on a rookie row in both leagues). Everything else counts as
  NCAA, including year-suffixed entries ("Virginia '96"). NAIA schools are not
  separated out, so a handful of NAIA alumni count as NCAA. WNBA rookies split
  {school_n("wnba", "rookie", "ncaa")} NCAA and {school_n("wnba", "rookie", "non_ncaa")} non-NCAA; NBA rookies
  {school_n("nba", "rookie", "ncaa"):,} and {school_n("nba", "rookie", "non_ncaa")}.
- **Exposure.** Source for the rule change: {NSGA}. The start date of the old
  rule is not verified here and is not used. A rookie whose last college season
  was {fmt_season(exp_first - 1, "nba")} or later is exposed: WNBA rookie seasons
  {span(exp_first, w_exp_hi, "wnba")}, NBA rookie seasons {span(nba_exp_first, n_last, "nba")}. The
  rookie season is the only proxy for the last college season, so a player who
  spent a year abroad between college and the pros is misdated.
- **Comparison window.** The primary comparison is the {W.PRE_WINDOW} rookie classes
  just before exposure. Every earlier class is a secondary comparison, and a weak
  one for this question: {decade_txt}, so the long window mixes eras with
  different number habits.

#### {head1}

Mean listed height went from **{h0:.2f} in** ({fmt_season(w_first, "wnba")}) to **{h1:.2f} in**
({fmt_season(w_last, "wnba")}). Numbers above 55 went from **{a0:.1%}** to **{a1:.1%}** (never above
{a_max:.1%} in any season), 0 or 00 from **{z0:.1%}** to **{z1:.1%}**, and numbers with a 6-9
digit from **{d0:.1%}** to **{d1:.1%}**.

The jersey/height correlation was **{era['cor_first5']:+.3f}** in the first five seasons
({span(era['first_lo'], era['first_hi'], "wnba")}) and **{era['cor_last5']:+.3f}** in the last five
({span(era['last_lo'], era['last_hi'], "wnba")}); single seasons ranged from {c_lo_row['value']:+.3f}
({fmt_season(int(c_lo_row['season_start']), "wnba")}) to {c_hi_row['value']:+.3f}
({fmt_season(int(c_hi_row['season_start']), "wnba")}). The bootstrap change is **{era['estimate']:+.3f}**
(95% CI [{era['ci_lo']:+.3f}, {era['ci_hi']:+.3f}], {int(era['reps']):,} resamples of
{era['n_first']} and {era['n_last']} player-seasons), and the interval {era_zero}. For the NBA
the same quantity is {nba_est:+.3f} [{nba_lo:+.3f}, {nba_hi:+.3f}]. {verdict} {start_txt}

#### {head2}

Share of numbered players wearing a number with any 6-9 digit, the {W.PRE_WINDOW}
rookie classes before exposure against the exposed classes:

**WNBA**

{table("wnba")}

**NBA (cross-check)**

{table("nba")}

{rule_verdict} Against veterans in the same seasons, the change for WNBA NCAA
rookies is {contrast_txt("wnba", "did_ncaa_rookie_vs_veteran")}; against non-NCAA
rookies, {contrast_txt("wnba", "did_ncaa_vs_non_ncaa_rookie")}. For the NBA the same
two contrasts are {contrast_txt("nba", "did_ncaa_rookie_vs_veteran")} and
{contrast_txt("nba", "did_ncaa_vs_non_ncaa_rookie")}.

The samples are small, and the intervals say so. The exposed groups are
{w_post['n']} WNBA NCAA rookies across {w_post['season_hi'] - w_post['season_lo'] + 1} classes and
{n_post['n']} NBA NCAA rookies across {n_post['season_hi'] - n_post['season_lo'] + 1}; the non-NCAA
controls are {w_nn_post['n']} and {n_nn_post['n']}. The NCAA-rookie intervals are
{width_w:.0f} (WNBA) and {width_n:.0f} (NBA) percentage points wide, so a real shift of
a few points would be invisible here. Against every earlier class instead of
the last {W.PRE_WINDOW}, the NCAA-rookie change is {contrast_txt("wnba", "ncaa_rookie_all_pre")} in
the WNBA (baseline {all_pre_w['share']:.1%} over {span(all_pre_w['season_lo'], all_pre_w['season_hi'], "wnba")})
and {contrast_txt("nba", "ncaa_rookie_all_pre")} in the NBA (baseline {all_pre_n['share']:.1%}
over {span(all_pre_n['season_lo'], all_pre_n['season_hi'], "nba")}); see the comparison-window note
above for why that window is weaker. Veteran player-seasons are resampled as if
independent, though one veteran appears in several seasons, so the veteran
intervals are somewhat too narrow. Each new rookie class adds to the exposed
sample; this is a question to rerun, not a settled answer.

#### {head3}

Aligned by league age (NBA seasons since {fmt_season(W.LEAGUE_START["nba"], "nba")}, WNBA seasons since {fmt_season(W.LEAGUE_START["wnba"], "wnba")}),
the ages where both leagues have covered data run from {age_lo} to {age_hi}.
Comparing ages {early[0]}-{early[1]} with ages {late[0]}-{late[1]}: the NBA's jersey/height
correlation {direction(*nc, 0.05)}, from {nc[0]:+.3f} to {nc[1]:+.3f}, while the WNBA's
{direction(*wc_, 0.05)} ({wc_[0]:+.3f} to {wc_[1]:+.3f}). The NBA's 6-9 share
{direction(*n6, 0.02)} from {n6[0]:.1%} to {n6[1]:.1%}; the WNBA's {direction(*w6, 0.02)}
({w6[0]:.1%} to {w6[1]:.1%}). {above55_lead}
(NBA {n55[0]:.1%} and {n55[1]:.1%}, WNBA {w55[0]:.1%} and {w55[1]:.1%}{rare55}). {age_conclusion}
{rule_hypothesis}

Figures (interactive, `figures/`): `fig7_wnba_number_conventions.html`,
`fig8_wnba_jersey_height_cor.html`, `fig9_league_age_cor.html`,
`fig10_league_age_above55.html`, `fig11_league_age_digit69.html`,
`fig12_wnba_rookie_digit69.html`, and `fig13_nba_rookie_digit69.html`.
"""


def regenerate(text: str) -> str:
    if not REGION.search(text):
        raise SystemExit("README.md is missing the gen:wnba markers")
    body = build()
    return REGION.sub(lambda _m: f"<!-- gen:wnba -->{body}<!-- /gen:wnba -->", text, count=1)


def main(argv: list[str]) -> int:
    current = README.read_text()
    if "--check" in argv:
        plain = strip_abbr(current)
        if plain != regenerate(plain):
            print("Committed README WNBA section differs from what output/wnba/ supports. "
                  "Fix: python python/10_wnba_findings.py, then glossary.py --sync.")
            print("WNBA FINDINGS CHECK FAILED")
            return 1
        print("WNBA FINDINGS CHECK PASSED (gen:wnba regenerates from output/wnba/)")
        return 0
    README.write_text(regenerate(current))
    print(f"Updated gen:wnba in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
