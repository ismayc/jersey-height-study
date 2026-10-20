# The players didn't shrink. The jersey numbers did.

Ask a basketball fan what happened to NBA height over the last twenty years
and you will hear a confident story: the game spread out, centers gave way
to wings, and the league got smaller. Forty-six seasons of roster data
(18,947 player-seasons, 1980-81 through 2025-26) say the confident story is
about three-quarters measurement artifact.

<div class="tiles">
<div class="tile"><div class="label">The 2019-20 height cliff</div>
<div class="value">&minus;0.61<small> in</small></div>
<div class="sub">Largest year-over-year move in the 45-season record</div></div>
<div class="tile"><div class="label">Number-height correlation</div>
<div class="value">.44 &rarr; .12</div>
<div class="sub">The jersey number used to tell you the height. It barely does now.</div></div>
<div class="tile"><div class="label">Median jersey number</div>
<div class="value">25 &rarr; 14</div>
<div class="sub">1980-81 to 2025-26. The low numbers won.</div></div>
<div class="tile"><div class="label">Sample</div>
<div class="value">18,947</div>
<div class="sub">Player-seasons across 46 years of rosters</div></div>
</div>

<div class="eyebrow beat">The height story</div>

## Not a slope. A cliff.

Mean listed height did rise for two decades, peaking at 79.4 inches in
2002-03, and it has drifted down since. The question is *how* it came down,
and that is exactly the kind of question a summary statistic hides and a
time series answers. The figure below is the study's centerpiece for one
reason. The decline is not a slope, it is a **cliff**: a single-season
drop of 0.61 inches between 2018-19 and 2019-20, the largest year-over-year
move in the entire 45-season record and 2.3 times the next-largest drop.
Trends produced by basketball evolution do not move like that. Rule changes
do.

{{fig:fig1_height_trend_py|Mean listed height by season. The reason this chart exists: the 2019-20 cliff is visible to the naked eye, and no smooth "the game got smaller" story survives contact with it. Hover any season for the exact value.}}

{{svg:dg1_height_steps|The decline from the 2002-03 peak, split into its three parts. The slow drift before 2018-19 is small, the single offseason of the rule change is most of it, and heights have risen since. The box fits that step with the regime model instead of reading it off two seasons.}}

2019-20 is precisely when the league began requiring measured heights
without shoes. Two checks pin the attribution down. A regime-aware model
(piecewise trends with an explicit level-shift term at 2019) estimates the
rule-change step at −0.62 inches (95% CI [−0.79, −0.46]), and fitting the
step explicitly keeps it from contaminating the trend slopes on either
side. And among the 388 players rostered in **both** 2018-19 and 2019-20,
the same drop appears within the same human beings. So roster turnover,
the one mundane alternative explanation, cannot account for it. Since the
rule change, the league has actually been getting slightly *taller*.

{{svg:dg2_same_players|The within-player check. Each dot is one player rostered in both seasons, colored by how his listed height changed across the rule change: more than half were listed shorter. The bars show the same share for every offseason. In the typical one almost no returning player is listed shorter, and the smaller bars after the rule change are consistent with later re-measurements. A change in who plays cannot produce a drop inside the same people.}}

<div class="eyebrow beat">Positions</div>

## Convergence is real. It just isn't the story.

Height by position tells the second half of the story. Positional
convergence is real. But it is gradual and modest next to the step, which
is why the two need to be separated before either can be read.

{{fig:fig2_height_by_position_py|Height by listed position over time. Necessary because "the league got smaller" and "positions converged" are different claims. This figure shows the second is real but gradual, which is what isolates the step in the first figure as a measurement event.}}

<div class="eyebrow beat">The cultural signal</div>

## Big men no longer wear big numbers

The study's original question, jersey numbers, turns out to carry the
cultural signal. Number choice used to encode position: big men wore big
numbers. That convention has dissolved.

{{fig:fig3_number_conventions_py|Jersey-number conventions by era. The cultural companion to the height story: which numbers players choose, and how the old big-man-big-number convention faded.}}

The correlation in the next chart is one number per season, and the
diagram below shows what it summarizes, for the first season and the
latest.

{{svg:dg3_number_height|What the correlation measures. In the first season the centers (blue) mostly wear high numbers and the cloud climbs from left to right; in the latest season most centers wear low numbers too, and the best-fit line is nearly flat. Each point on the next chart is one season's version of this cloud.}}

{{fig:fig4_jersey_height_cor_py|The correlation between jersey number and height, by season: from +0.44 to +0.12. This is the single chart that summarizes the study's answer: the number on the jersey used to tell you how tall its wearer was, and now it barely does.}}

The correlation between a player's number and his height fell from **+0.44
to +0.17** across the sample (its 2024-25 floor was +0.12): a quiet, steady cultural change that, unlike
the height "decline," is exactly what it appears to be.

<div class="eyebrow beat">46 seasons of number choices</div>

## The low numbers won

The numbers themselves deserve a season-by-season look, not just a
correlation. Two explorable views below (0 and 00 are pooled into a
single bucket throughout: distinct uniforms, same cultural choice; the
pooling is noted on each figure). The median tells the story in one line:
**the typical jersey number nearly halved, from 25 in 1980-81 to 14 in
2025-26 (13 the season before).** The low numbers won.

{{fig:fig5_median_number|The median jersey number by season, with the middle-50% band. Necessary because the correlation chart above says the number-height link dissolved but not what players chose instead: the entire distribution slid steadily toward low numbers, with the median nearly halving over 46 seasons. Hover any season for the 0/00 and 50+ shares.}}

{{fig:fig6_number_histogram|The full jersey-number distribution, one season at a time: drag the slider or press play to walk 46 seasons, and switch the bin size (1, 5, or 10 numbers per bar) to trade detail for shape. This is the exploratory view the medians compress away: any bar with ten or fewer wearers lists them on hover (a player traded mid-season shows once, with his final team, because the roster archive is end-of-season). Watch the high-number right tail thin out and the 0/00 bar (first bar, pooled) grow from 1.1% of the league in 1980-81 to its 6.8% all-time peak in 2024-25 (5.6% in 2025-26). Numbers 50 and up went from 7.7% of players to 4.8%.}}

<div class="eyebrow beat">The WNBA</div>

## The WNBA never had the convention to lose

The WNBA started in 1997, when the NBA's big-man-big-number habit was
already fading, and its rosters show it. The jersey/height correlation was
+0.20 across the WNBA's first five seasons and +0.19 across its last five:
a change of about zero (95% CI [-0.10, +0.09]), and an interval that rules
out a drop anywhere near the NBA's. Numbers above 55 were never common
there at all.

{{fig:fig7_wnba_number_conventions|WNBA number conventions by season: the share of players in numbers above 55, in 0 or 00, and in numbers containing a digit from six through nine. Necessary because it shows the high-number habit the NBA abandoned was never present in the WNBA to begin with.}}

{{fig:fig8_wnba_jersey_height_cor|The WNBA's jersey/height correlation by season. The flat line is the finding: the WNBA began about where the NBA has fallen to and stayed there.}}

Lining the two leagues up by league age rather than calendar year sharpens
the contrast. At the same ages, the NBA's correlation was building, from
+0.07 at league ages 8 to 12 to +0.33 at ages 25 to 29, while the WNBA's held
at +0.21 and +0.19. The NBA grew the convention as it aged and has since let
it go; the WNBA, born later, never built it.

{{fig:fig9_league_age_cor|Jersey/height correlation by league age, NBA and WNBA. Necessary because calendar years compare a league in its fourth decade with one in its ninth; league age compares like with like.}}

{{fig:fig10_league_age_above55|Share of players in numbers above 55 by league age. Rare in both leagues at every league age the two share.}}

{{fig:fig11_league_age_digit69|Share of players wearing a number with a digit from six through nine, by league age. The NBA's share fell as it aged; the WNBA's did not.}}

<div class="eyebrow beat">A natural experiment</div>

## College rules and the numbers rookies pick

For decades the NCAA barred the digits six through nine on basketball uniforms,
so almost every WNBA rookie arrived having never been allowed to wear one.
The NCAA dropped the restriction for the 2023-24 season, which makes the
2024 to 2026 rookie classes the first exposed to the new rule. Among NCAA
rookies, the share wearing a digit from six to nine went from 8.5% in the ten classes
before to 13.0% in the exposed classes, a change of +4.5 points with a 95%
interval of [-2.8, +12.8]. In the NBA, which drafts from the same college
system, it went from 22.9% to 21.3%. Neither change clears zero, and with
92 exposed WNBA rookies the interval is wide enough to hide a real shift of
a few points. This is a question to rerun as each new class arrives.

{{fig:fig12_wnba_rookie_digit69|WNBA rookies wearing a number with a digit from six to nine, by class, NCAA alumni against everyone else. The first three classes after the rule change sit inside the earlier range.}}

{{fig:fig13_nba_rookie_digit69|The same rookie measure for the NBA, as a cross-check: men's college basketball had the same rule and the same change.}}

<div class="eyebrow beat">The lesson</div>

## A rehearsal for every "the metric moved" argument

Why does any of this matter beyond trivia? Because it is a low-stakes
rehearsal of a high-stakes failure mode. A headline metric moved, and the
obvious narrative was ready. The narrative was wrong. And the error only
shows up when you decompose the change, model the break explicitly, and
check it within the same players. Every study in this family runs on that
discipline; this one just happens to make the lesson visible in a single
picture.
