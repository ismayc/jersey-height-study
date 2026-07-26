# NBA jersey numbers and player heights, 1980–2024

How have NBA jersey numbers and player heights changed over four decades, and has
the relationship between the two changed?

Part of the [basketball-data-science](https://github.com/ismayc/basketball-data-science)
family of studies. The
analysis is implemented **twice: once in R with the tidyverse, once in Python
with polars and plotly**, and a reconciliation step checks that the two agree
before any result is reported.

**Headline:** across 45 seasons and 18,399 player-seasons, the correlation between
jersey number and listed height collapsed from **+0.44 to +0.12**. Big men no
longer monopolise the high numbers. Heights look like they peaked in 2002-03 and
fell sharply, but **71% of that decline is a single 2019-20 rule change** requiring
measured heights without shoes, not a change in who plays. Separating those two is
the main analytical result. Full numbers in *Findings* below.

<!-- terms -->
> **Terms used in this analysis.** Dotted-underlined terms anywhere below repeat these definitions on hover ([full glossary](https://github.com/ismayc/basketball-data-science/blob/main/docs/glossary.md)).
>
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
`0.0` on the singular design. Same input, different silent behaviour: the kind of
thing that survives a single-implementation review.

## Pipeline

```
python/01_harvest_rosters.py   stats.nba.com -> data/raw_rosters/*.csv   (resumable, cached)
python/02_combine.py           raw cache     -> data/nba_rosters.csv
R/03_analysis.R                             -> output/results_r.csv,      figures/*_r.png
python/03_analysis.py                       -> output/results_python.csv, figures/*_py.{png,html}
python/04_reconcile.py         compares the two, non-zero exit on mismatch
python/05_findings.py          writes the Findings section of this README
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
```

## Data

**Source:** `stats.nba.com` `CommonTeamRoster`, via the `nba_api` package. One
request returns a full team-season roster with jersey number, listed height,
position, weight, age, and experience.

Choosing this endpoint was the main efficiency decision: assembling the same table
from per-player endpoints would need thousands of calls instead of ~1,350.

**Scope:** the 30 current franchises, 1980-81 through 2024-25.

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
   heights rose and then *reversed* (+0.067 in/season before 1990, −0.015 after),
   and one slope would average those into a claim matching neither era.
2. **Regime-aware height model**: the same idea taken seriously, with knots at
   1990 and the 2002 peak, plus a **level-shift term at the 2019-20 measurement rule
   change**. The shift term estimates the rule-change step directly (with a <abbr title="Confidence interval.">CI</abbr>)
   instead of reading it off consecutive seasons, and keeps the break from
   contaminating the trend slopes. It fits far better than the single-knot model
   (R² 0.85 vs 0.30), which is itself evidence that the break is structural.
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
the plotly implementation. The three-colour categorical palette
(`#2a78d6`, `#eb6834`, `#1baf7a`) was checked for colour-vision separation across
all pairs before use; series are direct-labelled rather than relying on a legend
box, since one of the three sits below 3:1 contrast against the chart surface.

## Limitations

Stated plainly, because an analysis that hides its weaknesses isn't a good
analysis.

1. **Listed heights are not measured heights.** Teams historically listed players
   generously or in shoes; the NBA began requiring measured heights without shoes
   in 2019-20. This is not a hypothetical concern. It is **visible in the data as
   a −0.61 in single-season step**, the largest year-over-year move in the entire
   45-season series and 2.3× the next largest. It accounts for 71% of the apparent
   post-2002 decline. The series is best read as **two regimes spliced together**,
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

## What this is and isn't

It is a demonstration of how a question gets turned into defined metrics,
quantified uncertainty, an independent validation step, and documented
limitations.

It is **not** tracking or play-by-play work, and it does not model player or
lineup value. The sibling studies in the family cover those.

---

## Findings

Covering 1980-81 through 2024-25. Every number
below is generated by `python/05_findings.py` from `output/`, not typed by hand.

### 1. Height rose, peaked, and then mostly changed measuring tape

Mean listed height went from **78.45 in** in 1980-81 to
**78.52 in** in 2024-25, peaking at **79.37 in** in
2002-03. The piecewise fit puts the pre-1990 trend at
**+0.0669 in/season** and the post-1990 trend at **-0.0152 in/season**.

**The obvious read of that is wrong, and this is the most important result here.**
Decomposing the 0.856 in decline from 2002-03 to
2024-25:

| Period | Change | Note |
|---|---|---|
| 2002-03 → 2018-19 | **-0.353 in** | gradual, over 16 seasons |
| 2018-19 → 2019-20 | **-0.606 in** | **one season** |
| 2019-20 → 2024-25 | **+0.103 in** | flat to slightly rising |

That single 2019-20 step is **71% of the
entire decline**, and it is the largest year-over-year move in all
45 seasons: 2.3× the next largest
(-0.258 in, 2017-18).

2019-20 is exactly when the NBA began requiring measured heights without
shoes. The league did not get shorter that summer; the ruler changed. Players have
been *slightly taller* since.

Two further checks pin that attribution down:

- **Modelled, not eyeballed.** A regime-aware model (piecewise trend, knots at
  1990 and 2002, plus a level-shift term at 2019) estimates the rule-change step
  at **-0.636 in** (95% <abbr title="Confidence interval.">CI</abbr> [-0.801, -0.472]).
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
  both immediately after the rule change (2021-22 → 2022-23: 26% changed (net +0.08 in); 2022-23 → 2023-24: 18% changed (net -0.06 in)), consistent with
  follow-on re-measurements and corrections trickling in, the 2021-22 wave
  skewing *upward*. No other offseason since 1980 exceeds 12%. Any
  within-player analysis spanning 2019-2023 is looking at a settling process,
  not a stable series.

The defensible claim is narrow: heights rose into the early 2000s, drifted down
modestly through the 2010s (-0.353 in over 16 seasons), and have been
stable since. Anyone quoting the raw peak-to-today number as a basketball trend is
quoting a measurement change.

### 2. Number conventions loosened

Numbers above 55 went from **0.0%** of numbered players to **2.5%**.
Players wearing 0 or 00 went from **0.7%** to **6.8%**.

### 3. The jersey/height link has weakened

The per-season correlation between jersey number and listed height moved from
**+0.442** to **+0.119**, trending **-0.00878 per season**
(p < 0.0001). A bootstrap of the change between the first and last five seasons puts it at **-0.283** (95% <abbr title="Confidence interval.">CI</abbr> [-0.337, -0.228], 2,000 resamples). The interval excludes zero, so the weakening is not an artifact of sampling.

Interpretation, with the caveat from limitation 5: the old convention of big men in
the 50s and guards in single digits has decayed. Whether that is looser number
rules, positional convergence, or both, this analysis cannot separate.

### 4. Validation: the Bill Russell check

Players wearing number 6, by season: **15** (2018-19) → **14** (2019-20) → **13** (2020-21) → **17** (2021-22) → **12** (2022-23) → **4** (2023-24) → **2** (2024-25).

The count averaged **14.8** per season across the four seasons before the rule (2018-19 to 2021-22) and **3.0** in the two seasons after it took full effect. That is the expected signature: the NBA retired number 6 league-wide for Bill Russell ahead of 2022-23 but grandfathered existing wearers, so the decline is an attrition curve rather than a cliff.

The pipeline was never told about this rule. Reproducing a known external fact from the data is the cheapest evidence available that the harvest, de-duplication, and number parsing are behaving.
