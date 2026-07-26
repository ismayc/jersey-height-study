# One finding, three audiences: jersey numbers & heights

The same result told three ways, because analysis that other groups depend on
has to survive translation. Numbers below come from `output/` (see README
Findings for the generated originals).

---

## For the front office (one minute, no statistics background)

**Are NBA players really getting shorter?** You'll hear that they are: average
listed height peaked in 2002-03 and is down almost an inch since.

**Mostly, no.** In 2019 the league changed the rule for how heights are
reported: measured, without shoes. That one change accounts for about
**70% of the entire "decline."** We can prove it isn't about who's in the
league: we tracked the *same 388 players* across that one offseason, and
**55% of them "got shorter" on paper**. In a typical offseason about 2% of
continuing players' listed heights change at all, and no other offseason since
1980 comes close. Same players, new tape measure. (The two runner-up churn
years, 2021–2023, are the rule change's own aftershocks: corrections still
trickling in.)

**What's left after removing the rule change:** a slow drift down of about a
third of an inch across 16 seasons, then flat. Real, but small, and worth
knowing next time a "players are shrinking" chart makes the rounds.

**One more thing to trust the data on:** when the NBA retired #6 league-wide
for Bill Russell, our data shows exactly the expected pattern: a decline to
just 2 wearers by 2024-25 as grandfathered players aged out. The pipeline
reproduces league history it was never told about.

## For analytics peers (methods in one paragraph)

45 seasons of `CommonTeamRoster` (18,399 player-seasons), cleaned with
documented rules, implemented independently in R/tidyverse and Python/polars
with a reconciliation gate (1e-9 on metrics, 1e-6 on coefficients, non-zero
exit on mismatch). Height trend modeled two ways: the descriptive piecewise
fit, and a regime-aware model (knots 1990/2002 + level shift at 2019) that
estimates the measurement break directly at **−0.64 in [−0.80, −0.47]** with
R² 0.85 vs 0.30 for the single-knot version. Attribution confirmed
within-player (composition-free). Jersey/height correlation fell +0.44 → +0.12;
bootstrap on the first-five vs last-five season change: −0.28 [−0.34, −0.23].
Known limitations: listed ≠ measured heights pre-2019, current franchises
only, roster presence not minutes, association ≠ mechanism.

## For the executive summary (three bullets)

- The reported post-2002 height decline is ~70% a 2019 measurement-rule
  change, not basketball; the true drift is ~0.35 in over 16 seasons, then flat.
- The link between jersey numbers and player size has largely dissolved since
  the 1980s (correlation +0.44 → +0.12).
- Every number is machine-generated from the pipeline, verified by two
  independent implementations that must agree before publication.
