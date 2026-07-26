# The NBA didn't get shorter. The ruler changed.

Ask a basketball fan what happened to NBA height over the last twenty years
and you will hear a confident story: the game spread out, centers gave way
to wings, and the league got smaller. Forty-five seasons of roster data —
18,399 player-seasons, 1980-81 through 2024-25 — say the confident story is
about seventy percent measurement artifact.

Mean listed height did rise for two decades, peaking at 79.4 inches in
2002-03, and it has drifted down since. The question is *how* it came down,
and that is exactly the kind of question a summary statistic hides and a
time series answers. The figure below is the study's centerpiece for one
reason: the decline is not a slope, it is a **cliff** — a single-season
drop of 0.61 inches between 2018-19 and 2019-20, the largest year-over-year
move in the entire 45-season record and 2.3 times larger than the runner-up.
Trends produced by basketball evolution do not move like that. Rule changes
do.

{{fig:fig1_height_trend_py|Mean listed height by season. The reason this chart exists: the 2019-20 cliff is visible to the naked eye, and no smooth "the game got smaller" story survives contact with it. Hover any season for the exact value.}}

2019-20 is precisely when the league began requiring measured heights
without shoes. Two checks pin the attribution down. A regime-aware model —
piecewise trends with an explicit level-shift term at 2019 — estimates the
rule-change step at −0.64 inches (95% CI [−0.80, −0.47]), and fitting the
step explicitly keeps it from contaminating the trend slopes on either
side. And among the 388 players rostered in **both** 2018-19 and 2019-20,
the same drop appears within the same human beings — so roster turnover,
the one mundane alternative explanation, cannot account for it. Since the
rule change, the league has actually been getting slightly *taller*.

Height by position tells the second half of the story. Positional
convergence is real — but it is gradual and modest next to the step, which
is why the two need to be separated before either can be read.

{{fig:fig2_height_by_position_py|Height by listed position over time. Necessary because "the league got smaller" and "positions converged" are different claims — this figure shows the second is real but gradual, which is what isolates the step in the first figure as a measurement event.}}

The study's original question — jersey numbers — turns out to carry the
cultural signal. Number choice used to encode position: big men wore big
numbers. That convention has dissolved.

{{fig:fig3_number_conventions_py|Jersey-number conventions by era. The cultural companion to the height story: which numbers players choose, and how the old big-man-big-number convention faded.}}

{{fig:fig4_jersey_height_cor_py|The correlation between jersey number and height, by season — from +0.44 to +0.12. This is the single chart that summarizes the study's answer: the number on the jersey used to tell you how tall its wearer was, and now it barely does.}}

The correlation between a player's number and his height fell from **+0.44
to +0.12** across the sample — a quiet, steady cultural change that, unlike
the height "decline," is exactly what it appears to be.

Why does any of this matter beyond trivia? Because it is a clean, low-stakes
rehearsal of a high-stakes failure mode: a headline metric moved, the
obvious narrative was ready, and the obvious narrative was wrong in a way
that only shows up when you decompose the change, model the break
explicitly, and check it within-player. Every study in this family runs on
that discipline; this one just happens to make the lesson visible in a
single picture.
