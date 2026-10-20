# NBA jersey numbers and player heights, 1980–2024

How have NBA jersey numbers and player heights changed over four decades, and has
the relationship between the two changed?

Part of the [basketball-data-science](https://github.com/ismayc/basketball-data-science)
family of studies. The
analysis is implemented **twice: once in R with the tidyverse, once in Python
with polars and plotly**, and a reconciliation step checks that the two agree
before any result is reported.

<!-- gen:headline -->
**Headline:** across 46 seasons and 18,947 player-seasons, the correlation
between jersey number and listed height collapsed from **+0.44** to a low
of **+0.12** in 2024-25 (**+0.17** in 2025-26). Big men no longer
monopolize the high numbers. Heights look like they peaked in 2002-03 and
fell sharply, but **75% of that decline is a single 2019-20 rule change**
requiring measured heights without shoes, not a change in who plays.
Separating those two is the main analytical result. Full numbers in
*Findings* below.
<!-- /gen:headline -->

<!-- terms -->
> **Terms used in this analysis.** Dotted-underlined terms anywhere below repeat these definitions on hover ([full glossary](https://github.com/ismayc/basketball-data-science/blob/main/docs/glossary.md)).
>
> - **stint**: A stretch of game time with no substitution at either end - the unit of observation for the stint-level RAPM model.
> - **CI**: Confidence interval.
<!-- /terms -->

## Why two implementations

Not to show off two languages. Two independent implementations of the same metric
definitions disagree exactly where a definition was ambiguous, and an ambiguous
definition is the most common way an analysis is quietly wrong. `04_reconcile.py`
compares every season-level metric to a `1e-9` tolerance and every model
coefficient to `1e-6`, and exits non-zero on any mismatch, so it can gate a
commit.

It has already caught one real issue: on a partial harvest the piecewise knot term
was constant zero, which R aliases to `NA` while `statsmodels` silently returns
`0.0` on the singular design. Same input, different silent behavior: the kind of
thing that survives a single-implementation review.

## Pipeline

```
python/01_harvest_rosters.py   stats.nba.com -> data/raw_rosters/*.csv   (resumable, cached)
python/02_combine.py           raw cache     -> data/nba_rosters.csv
R/03_analysis.R                             -> output/results_r.csv,      figures/*_r.png
python/03_analysis.py                       -> output/results_python.csv, figures/*_py.{png,html}
python/04_reconcile.py         compares the two, non-zero exit on mismatch
python/05_findings.py          writes the Findings section of this README

WNBA extension (see "Extension" below):
python/07_harvest_more_rosters.py wnba | nba-early   -> data/wnba_rosters.csv, data/nba_early_rosters.csv
R/08_wnba_analysis.R                        -> output/wnba/*_r.csv
python/08_wnba_analysis.py                  -> output/wnba/*_python.csv, figures/fig7..fig13 (HTML)
python/09_reconcile_wnba.py    compares the two, non-zero exit on mismatch
python/10_wnba_findings.py     writes the Extension section of this README

Roster-completeness checks (added October 19, 2026):
python/roster_guard.py         an empty CommonTeamRoster is accepted only for a team that did not play
python/12_build_active_seasons.py   rebuilds data/franchise_active_seasons.csv (the guard's source)
python/11_participation_check.py    roster players vs LeagueDashPlayerStats, per league and season
python/13_participation_impact.py   the missing players added back, per cached season -> output/participation_impact.csv

Story page diagrams (added October 20, 2026):
python/14_diagrams.py          explainer SVGs for docs/story.md, drawn from output/ and the committed rosters (--check rebuilds and compares)
```

Each stage is independently re-runnable. The harvest caches one CSV per
team-season, so an interrupted run resumes and the analysis never re-hits the
network.

### Reproducing

```bash
pip install nba_api polars plotly kaleido statsmodels scipy numpy pandas
Rscript -e 'install.packages(c("tidyverse","broom"))'

python python/01_harvest_rosters.py --start 1980 --end 2024   # ~90 min, rate-limited
python python/02_combine.py
Rscript R/03_analysis.R
python python/03_analysis.py
python python/04_reconcile.py    # exits non-zero if the two disagree
python python/05_findings.py     # rewrites the Findings section below

python python/07_harvest_more_rosters.py wnba        # resumable, cached
python python/07_harvest_more_rosters.py nba-early
Rscript R/08_wnba_analysis.R
python python/08_wnba_analysis.py
python python/09_reconcile_wnba.py    # exits non-zero if the two disagree
python python/10_wnba_findings.py     # rewrites the Extension section
```

## Data

**Source:** `stats.nba.com` `CommonTeamRoster`, via the `nba_api` package. One
request returns a full team-season roster with jersey number, listed height,
position, weight, age, and experience.

Choosing this endpoint was the main efficiency decision: assembling the same table
from per-player endpoints would need thousands of calls instead of ~1,380.

**Scope:** the 30 current franchises, 1980-81 through 2025-26.

### Cleaning rules

| Field | Rule |
|---|---|
| `HEIGHT` | Arrives as `"6-9"`; parsed to inches. Rows without a parseable height are dropped |
| `NUM` | Read as text so `"00"` stays distinct from `"0"`. Blanks and nulls are dropped from number-based metrics but **retained for height metrics** |
| `POSITION` | `"G"`/`"F"`/`"C"` in early seasons, `"G-F"` later; the leading letter is used so the grouping is comparable across the whole span |
| Duplicates | A player traded mid-season appears on two rosters; the first row per `(PLAYER_ID, season)` is kept |

### Metric definitions

| Metric | Definition |
|---|---|
| `mean_height_in` | Mean listed height, inches |
| `share_above_55` | Share of numbered players wearing a number above 55 |
| `share_zero` | Share wearing `"0"` or `"00"` |
| `jersey_height_cor` | Pearson correlation between jersey number and listed height |
| `num6_count` | Players wearing number 6 |

`share_above_55` uses 55 as the boundary because the NBA's referee hand-signal
convention is built on digits 0–5, which is why numbers above 55 were historically
unusual and required special accommodation.

`num6_count` is a **validation check, not a finding**: the NBA retired number 6
league-wide for Bill Russell ahead of 2022-23, with existing wearers
grandfathered. A correct pipeline should show a sharp drop after 2022 and a small
grandfathered tail. If it doesn't, something upstream is wrong.

## Models

1. **Height trend**: piecewise-linear with a knot at 1990, weighted by roster
   size. A single straight line across four decades would be the wrong model:
   heights rose and then *reversed* (exact slopes in the Findings below),
   and one slope would average those into a claim matching neither era.
2. **Regime-aware height model**: the same idea taken seriously, with knots at
   1990 and the 2002 peak, plus a **level-shift term at the 2019-20 measurement rule
   change**. The shift term estimates the rule-change step directly (with a <abbr title="Confidence interval.">CI</abbr>)
   instead of reading it off consecutive seasons, and keeps the break from
   contaminating the trend slopes. It fits far better than the single-knot model
   by a wide margin, which is itself evidence that the break is structural.
3. **Within-player check**: year-over-year listed-height change for players
   rostered in consecutive seasons. The aggregate mean moves when *who plays*
   changes; a continuing player's listed height only moves when the measurement
   does. This isolates the 2019 step from roster composition entirely.
4. **Association trend**: per-season jersey/height correlation regressed on
   season, weighted by roster size.
5. **Bootstrap**: 2,000 resamples of the change in jersey/height correlation
   between the first and last five seasons, reported as a 95% percentile
   interval. Seeded for reproducibility. The R and Python runs use different RNGs,
   so reconciliation checks that their intervals *overlap* rather than match.

## Figures

Static PNG from both languages, plus interactive HTML with hover tooltips from
the plotly implementation. The three-color categorical palette
(`#2a78d6`, `#eb6834`, `#1baf7a`) was checked for color-vision separation across
all pairs before use; series are direct-labeled rather than relying on a legend
box, since one of the three sits below 3:1 contrast against the chart surface.

## Limitations

Stated plainly, because an analysis that hides its weaknesses isn't a good
analysis.

1. **Listed heights are not measured heights.** Teams historically listed players
   generously or in shoes; the NBA began requiring measured heights without shoes
   in 2019-20. This is not a hypothetical concern. <!-- gen:limitations -->It is **visible in the data as
   a -0.61 in single-season step**, the largest year-over-year move in
   the entire 46-season series and 2.3× the next-largest drop. It
   accounts for 75% of the apparent post-2002 decline.<!-- /gen:limitations --> The series is best read as **two regimes spliced together**,
   and the study does not attempt to correct or bridge them; it quantifies the
   break and restricts the claims accordingly (see Finding 1). Any comparison
   spanning 2019 is comparing two different measuring conventions.
2. **Current franchises only.** Teams that folded or relocated under a different
   franchise ID are missing, so the earliest seasons are slightly under-covered.
3. **Roster presence, not playing time.** Every rostered player counts equally; a
   12th man weighs the same as a starter. A minutes-weighted version would answer
   a different and arguably more useful question.
4. **Position labels are coarse and drifting.** "Center" in 1985 and "Center" in
   2024 describe different jobs, so the position comparison partly measures
   relabeling rather than change in personnel.
5. **Association is not mechanism.** A falling jersey/height correlation is
   consistent with loosening number conventions, positional convergence, or both.
   This analysis does not separate them.
6. **The roster snapshot omits some players who appeared.** `CommonTeamRoster`
   lists who is on a team when the roster is read, so a player who played for a
   team and left before that moment is absent. An October 19, 2026 audit found
   this in NBA 2024-25 (41 of 569 players in `LeagueDashPlayerStats` are missing,
   1.8% of games played) and WNBA 2025 (21 of 182). Adding the 41 back, with
   height and number from `PlayerIndex`, moves that season's jersey/height
   correlation by +0.005, its mean height by +0.003 inches, and its share of numbers
   above 55 by +0.002. The published numbers are unchanged, and no finding turns
   on a gap that size. Other seasons are unmeasured until `python/11_participation_check.py
   --fetch` has been run when `stats.nba.com` is reachable.

   **Empty rosters (October 19, 2026).** The harvest used to cache an empty
   response as "franchise did not exist" and the combine step skipped it, which
   would have hidden a failed call. All 88 cached empty NBA rosters (1980-81
   through 2025-26) were checked against `data/franchise_active_seasons.csv`
   (regular-season team-seasons from the sibling `playoff-series-study`): each is a
   team-season in which the franchise did not play, and none was a lost roster.
   The harvest now refuses to cache any other empty response and the combine step
   fails with the list.

## What this is and isn't

It is a demonstration of how a question gets turned into defined metrics,
quantified uncertainty, an independent validation step, and documented
limitations.

It is **not** tracking or play-by-play work, and it does not model player or
lineup value. The sibling studies in the family cover those.

---

## Exploratory: the numbers season by season

<!-- gen:explorer -->
`python/06_number_explorer.py` adds two explorable views (gated, wired
into `run_checks.sh`): the median jersey number by season with quartile
band (`figures/fig5_median_number.html`) and a slider/play histogram
with adjustable bin size (1, 5, or 10 numbers per bar) of
the full number distribution per season
(`figures/fig6_number_histogram.html`). Parsing rules, gated: **0 and 00
are pooled** (noted on every surface that shows it), multi-number season
entries use the first listed number, and blank entries are dropped and
counted. Data note: `CommonTeamRoster` archives END-OF-SEASON rosters,
so a traded player appears once, on his final team (Dončić is LAL-only
in 2024-25); the one exception in 46 seasons is Spencer Dinwiddie's
2015-16 double listing (CHI and DET), which the wearer list logic
aggregates into a single entry (that bar has too many wearers to display
a list, so the case is moot on screen, and gated in the code). Headline:
the median number nearly halved from 25 (1980-81) to
14 (2025-26); the 0/00 share peaked at
6.8% in 2024-25.
<!-- /gen:explorer -->

## Extension: the WNBA, the NCAA digit rule, and league age

<!-- gen:wnba -->
Does the WNBA show the NBA's collapse of the big-players-wear-high-numbers
convention? Did the NCAA's 2023-24 change to allow the digits 6-9 move the
numbers rookies choose? And how do the two leagues compare at the same league
age? Scripts: `python/08_wnba_analysis.py` and `R/08_wnba_analysis.R` (two
independent implementations), `python/09_reconcile_wnba.py` (the gate:
deterministic tables to 1e-9, bootstrap intervals by overlap and equal group
sizes, and the NBA seasons from 1980-81 on against the main
study's own output), and `python/10_wnba_findings.py` (this section).

**Data.** WNBA rosters 1997 to 2026 (30 seasons,
4,590 player-seasons after cleaning) from `CommonTeamRoster` with the WNBA
league ID, folded franchises included. For the league-age comparison, NBA
rosters 1946-47 to 1979-80 (all franchises, defunct ones included)
are added to the main study's 1980-81 to 2025-26, 24,383 NBA
player-seasons in all. Cleaning rules are the ones in the table above. One new
metric, `share_digit69`: the share of numbered players wearing a number with any
digit 6 through 9 ("6", "19", and "69" count; "0", "00", and "45" do not).

#### Judgment calls

- **Early-NBA coverage threshold.** Number-based metrics count for a season only
  when at least 90% of its players have a parseable jersey number.
  This excludes the NBA's 1946-47 to 1953-54 (8 seasons; coverage
  23% to 77%). The lowest included NBA
  season is 1980-81 at 91.1%.
  Every WNBA season passes; the lowest is
  2008 at 90.8%. Height metrics do not
  depend on the threshold. Every excluded season comes before the first included one, so missing numbers are concentrated in the earliest rosters, and a season missing a large share of its numbers is measuring a different set of players, not a sample of the same one.
- **Rookies.** A rookie is a player whose `EXP` is "R" *and* who is in their
  first season in the data. The two signals mostly agree: across WNBA seasons after
  1997, 894 rows satisfy both,
  54 have `EXP == "R"` on a later roster (most likely a player
  who sat out the season they were first rostered, so their last college season
  is earlier than the class suggests; not verified row by row), and 82 are first appearances
  with `EXP` of 1 or more (likely a player whose earlier <abbr title="A stretch of game time with no substitution at either end - the unit of observation for the stint-level RAPM model.">stint</abbr> ended before the
  end-of-season roster snapshot, also not verified row by row). Requiring both drops those ambiguous rows. The
  NBA figures are 4,597, 50, and 130. The WNBA's
  inaugural 1997 rosters (86 players, all
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
  754 NCAA and 140 non-NCAA; NBA rookies
  4,215 and 382.
- **Exposure.** Source for the rule change: NSGA release, June 9, 2023 (<https://nsga.org/?p=6571>): "numbers 0 or 00 through 99 will be permitted in NCAA men's and women's basketball". The start date of the old
  rule is not verified here and is not used. A rookie whose last college season
  was 2023-24 or later is exposed: WNBA rookie seasons
  2024 to 2026, NBA rookie seasons 2024-25 to 2025-26. The
  rookie season is the only proxy for the last college season, so a player who
  spent a year abroad between college and the pros is misdated.
- **Comparison window.** The primary comparison is the 10 rookie classes
  just before exposure. Every earlier class is a secondary comparison, and a weak
  one for this question: the NBA's 6-9 share averaged 39.4% across its covered 1950s seasons and 13.5% across the 1970s, so the long window mixes eras with
  different number habits.

#### 1. The WNBA shows no collapse of the convention

Mean listed height went from **71.59 in** (1997) to **72.82 in**
(2026). Numbers above 55 went from **0.0%** to **0.9%** (never above
1.4% in any season), 0 or 00 from **1.2%** to **5.0%**, and numbers with a 6-9
digit from **14.0%** to **16.3%**.

The jersey/height correlation was **+0.197** in the first five seasons
(1997 to 2001) and **+0.193** in the last five
(2022 to 2026); single seasons ranged from +0.150
(2025) to +0.334
(2014). The bootstrap change is **-0.005**
(95% <abbr title="Confidence interval.">CI</abbr> [-0.103, +0.088], 2,000 resamples of
701 and 812 player-seasons), and the interval includes zero. For the NBA
the same quantity is -0.300 [-0.350, -0.245]. **The WNBA shows none of the NBA's collapse.** Its interval also rules out a drop as large as the NBA's (-0.300), so this is not just a small sample failing to detect the same change. The WNBA started (+0.197) near the level the NBA has fallen to (its last five seasons average +0.194) and stayed there.

#### 2. The NCAA digit rule: no detectable effect yet, on small samples

Share of numbered players wearing a number with any 6-9 digit, the 10
rookie classes before exposure against the exposed classes:

**WNBA**

| Group | Earlier seasons | Exposed seasons | Change (95% <abbr title="Confidence interval.">CI</abbr>) | Interval |
|---|---|---|---|---|
| NCAA rookies | 8.5% (18 of 211, 2014 to 2023) | 13.0% (12 of 92, 2024 to 2026) | +4.5 points [-2.8, +12.8] | includes zero |
| Non-NCAA rookies | 39.4% (13 of 33, 2014 to 2023) | 32.4% (11 of 34, 2024 to 2026) | -7.0 points [-28.2, +16.8] | includes zero |
| Veterans | 11.7% (142 of 1,212, 2014 to 2023) | 15.5% (62 of 399, 2024 to 2026) | +3.8 points [+0.1, +7.7] | borderline (R and Python disagree on zero) |

**NBA (cross-check)**

| Group | Earlier seasons | Exposed seasons | Change (95% <abbr title="Confidence interval.">CI</abbr>) | Interval |
|---|---|---|---|---|
| NCAA rookies | 22.9% (169 of 737, 2014-15 to 2023-24) | 21.3% (30 of 141, 2024-25 to 2025-26) | -1.7 points [-9.0, +6.0] | includes zero |
| Non-NCAA rookies | 41.9% (52 of 124, 2014-15 to 2023-24) | 39.3% (11 of 28, 2024-25 to 2025-26) | -2.6 points [-22.5, +17.3] | includes zero |
| Veterans | 23.7% (952 of 4,011, 2014-15 to 2023-24) | 24.5% (214 of 875, 2024-25 to 2025-26) | +0.7 points [-2.3, +3.7] | includes zero |

**Neither league shows a detectable rise in 6-9 numbers among the first exposed NCAA classes.** No NCAA-rookie change, and no difference against either control, clears zero in either league. Against veterans in the same seasons, the change for WNBA NCAA
rookies is +0.7 points (95% <abbr title="Confidence interval.">CI</abbr> [-8.1, +9.6], which includes zero); against non-NCAA
rookies, +11.6 points (95% <abbr title="Confidence interval.">CI</abbr> [-13.6, +36.9], which includes zero). For the NBA the same
two contrasts are -2.4 points (95% <abbr title="Confidence interval.">CI</abbr> [-10.3, +5.9], which includes zero) and
+1.0 points (95% <abbr title="Confidence interval.">CI</abbr> [-20.9, +21.3], which includes zero).

The samples are small, and the intervals say so. The exposed groups are
92 WNBA NCAA rookies across 3 classes and
141 NBA NCAA rookies across 2; the non-NCAA
controls are 34 and 28. The NCAA-rookie intervals are
16 (WNBA) and 15 (NBA) percentage points wide, so a real shift of
a few points would be invisible here. Against every earlier class instead of
the last 10, the NCAA-rookie change is +5.6 points (95% <abbr title="Confidence interval.">CI</abbr> [-1.5, +13.2], which includes zero) in
the WNBA (baseline 7.4% over 1998 to 2023)
and +6.7 points (95% <abbr title="Confidence interval.">CI</abbr> [+0.0, +14.2], which is borderline (one implementation's interval excludes zero and the other's does not)) in the NBA (baseline 14.5%
over 1954-55 to 2023-24); see the comparison-window note
above for why that window is weaker. Veteran player-seasons are resampled as if
independent, though one veteran appears in several seasons, so the veteran
intervals are somewhat too narrow. Each new rookie class adds to the exposed
sample; this is a question to rerun, not a settled answer.

#### 3. League age: the NBA's convention strengthened as the league aged; the WNBA's did not

Aligned by league age (NBA seasons since 1946-47, WNBA seasons since 1997),
the ages where both leagues have covered data run from 8 to 29.
Comparing ages 8-12 with ages 25-29: the NBA's jersey/height
correlation rose, from +0.073 to +0.331, while the WNBA's
held roughly level (+0.210 to +0.190). The NBA's 6-9 share
fell from 40.9% to 14.3%; the WNBA's rose
(11.7% to 14.9%). Numbers above 55 were rare in both at every one of these ages
(NBA 0.4% and 0.0%, WNBA 0.4% and 0.6%; no single season above 1.9%). So the NBA's big-men-in-the-50s convention was weak at the earliest well-covered league ages and strengthened through league age 29 (it has since faded), while the WNBA, at the same league ages, did not build one. The NBA's seasons before league age 8 fail the coverage threshold, so what the convention looked like in its very first seasons is not measured here.
Whether a college numbering rule fed the NBA's falling 6-9 share is a hypothesis this analysis does not test, since the old rule's start date is unverified.

Figures (interactive, `figures/`): `fig7_wnba_number_conventions.html`,
`fig8_wnba_jersey_height_cor.html`, `fig9_league_age_cor.html`,
`fig10_league_age_above55.html`, `fig11_league_age_digit69.html`,
`fig12_wnba_rookie_digit69.html`, and `fig13_nba_rookie_digit69.html`.
<!-- /gen:wnba -->

## Findings

Covering 1980-81 through 2025-26. Every number
below is generated by `python/05_findings.py` from `output/`, not typed by hand.

### 1. Height rose, peaked, and then mostly changed measuring tape

Mean listed height went from **78.45 in** in 1980-81 to
**78.57 in** in 2025-26, peaking at **79.37 in** in
2002-03. The piecewise fit puts the pre-1990 trend at
**+0.0679 in/season** and the post-1990 trend at **-0.0159 in/season**.

**The obvious read of that is wrong, and this is the most important result here.**
Decomposing the 0.805 in decline from 2002-03 to
2025-26:

| Period | Change | Note |
|---|---|---|
| 2002-03 → 2018-19 | **-0.353 in** | gradual, over 16 seasons |
| 2018-19 → 2019-20 | **-0.606 in** | **one season** |
| 2019-20 → 2025-26 | **+0.154 in** | flat to slightly rising |

That single 2019-20 step is **75% of the
entire decline**, and it is the largest year-over-year move in all
46 seasons: 2.3× the next-largest drop
(-0.258 in, 2017-18).

2019-20 is exactly when the NBA began requiring measured heights without
shoes. The league did not get shorter that summer; the ruler changed. Players have
been *slightly taller* since.

Two further checks pin that attribution down:

- **Modelled, not eyeballed.** A regime-aware model (piecewise trend, knots at
  1990 and 2002, plus a level-shift term at 2019) estimates the rule-change step
  at **-0.623 in** (95% <abbr title="Confidence interval.">CI</abbr> [-0.790, -0.456]).
  Fitting the shift explicitly also stops the break from contaminating the trend
  slopes on either side of it.
- **Within-player, so roster turnover cannot explain it.** Among the
  **388** players rostered in both 2018-19 and 2019-20,
  **55%** got shorter on paper, with a mean change of
  **-0.57 in**, against a typical offseason, where the median
  share of continuing players whose listed height changes downward is
  **0%**. The same players, measured two ways, account for
  essentially the whole aggregate step.
- **The 2019 break has echoes.** The next-largest within-player churn years are
  both immediately after the rule change (2021-22 → 2022-23: 26% changed (net +0.08 in); 2024-25 → 2025-26: 32% changed (net -0.03 in)), consistent with
  follow-on re-measurements and corrections trickling in, the 2021-22 wave
  skewing *upward*. No other offseason since 1980 exceeds 18%. Any
  within-player analysis spanning 2019-2023 is looking at a settling process,
  not a stable series.

The defensible claim is narrow: heights rose into the early 2000s, drifted down
modestly through the 2010s (-0.353 in over 16 seasons), and have been
stable since. Anyone quoting the raw peak-to-today number as a basketball trend is
quoting a measurement change.

### 2. Number conventions loosened

Numbers above 55 went from **0.0%** of numbered players to **2.1%**.
Players wearing 0 or 00 went from **0.7%** to **5.6%**.

### 3. The jersey/height link has weakened

The per-season correlation between jersey number and listed height moved from
**+0.442** to **+0.169**, trending **-0.00875 per season**
(p < 0.0001). A bootstrap of the change between the first and last five seasons puts it at **-0.300** (95% <abbr title="Confidence interval.">CI</abbr> [-0.350, -0.245], 2,000 resamples). The interval excludes zero, so the weakening is not an artifact of sampling.

Interpretation, with the caveat from limitation 5: the old convention of big men in
the 50s and guards in single digits has decayed. Whether that is looser number
rules, positional convergence, or both, this analysis cannot separate.

### 4. Validation: the Bill Russell check

Players wearing number 6, by season: **15** (2018-19) → **14** (2019-20) → **13** (2020-21) → **17** (2021-22) → **12** (2022-23) → **4** (2023-24) → **2** (2024-25) → **1** (2025-26).

The count averaged **14.8** per season across the four seasons before the rule (2018-19 to 2021-22) and **2.3** in the two seasons after it took full effect. That is the expected signature: the NBA retired number 6 league-wide for Bill Russell ahead of 2022-23 but grandfathered existing wearers, so the decline is an attrition curve rather than a cliff.

The pipeline was never told about this rule. Reproducing a known external fact from the data is the cheapest evidence available that the harvest, de-duplication, and number parsing are behaving.
