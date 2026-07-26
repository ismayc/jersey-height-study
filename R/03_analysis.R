# NBA jersey numbers and player heights over time --- R / tidyverse analysis
#
# Reads the harvested roster table and produces:
#   - output/results_r.csv   season-level metrics (reconciled against the Python run)
#   - output/models_r.csv    fitted model coefficients
#   - figures/*.png          publication figures
#
# The Python script python/03_analysis.py computes the same quantities
# independently; python/04_reconcile.py checks that the two agree. That
# cross-implementation check is the point: it catches cleaning mistakes that a
# single implementation would silently carry through.
#
# Run:  Rscript R/03_analysis.R

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(purrr)
  library(ggplot2)
  library(broom)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")

DATA_CSV <- file.path(ROOT, "data", "nba_rosters.csv")
OUT_DIR <- file.path(ROOT, "output")
FIG_DIR <- file.path(ROOT, "figures")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)
dir.create(FIG_DIR, showWarnings = FALSE, recursive = TRUE)

# ---- Palette (validated for CVD separation; see README) ---------------------
PAL <- c(blue = "#2a78d6", orange = "#eb6834", aqua = "#1baf7a")
INK <- "#0b0b0b"; INK2 <- "#52514e"; MUTED <- "#898781"
GRID <- "#e1e0d9"; AXIS <- "#c3c2b7"; SURFACE <- "#fcfcfb"

theme_study <- function() {
  theme_minimal(base_size = 11) +
    theme(
      plot.background = element_rect(fill = SURFACE, colour = NA),
      panel.background = element_rect(fill = SURFACE, colour = NA),
      panel.grid.major = element_line(colour = GRID, linewidth = 0.3),
      panel.grid.minor = element_blank(),
      axis.line = element_line(colour = AXIS, linewidth = 0.3),
      axis.text = element_text(colour = MUTED, size = 8.5),
      axis.title = element_text(colour = INK2, size = 9),
      plot.title = element_text(colour = INK, face = "bold", size = 12),
      plot.subtitle = element_text(colour = INK2, size = 9),
      plot.caption = element_text(colour = MUTED, size = 7.5, hjust = 0),
      legend.position = "none"   # series are direct-labelled instead
    )
}

# ---- Load and clean ---------------------------------------------------------
# Documented cleaning decisions:
#   * HEIGHT arrives as "6-9"; parsed to inches. Rows without height are dropped.
#   * NUM is character so "00" stays distinct from "0"; blanks/NA are dropped
#     for number-based metrics but retained for height metrics.
#   * POSITION is "G"/"F"/"C" in early seasons and "G-F" etc. later; the leading
#     letter is used so the grouping is comparable across the whole span.
#   * A player traded mid-season appears on two rosters; the first row per
#     (PLAYER_ID, season) is kept so players are not double counted.

# Pure functions live in functions.R so the test suite (tests/R) can source
# them without running this pipeline.
source(file.path(ROOT, "R", "functions.R"))

raw <- read_csv(DATA_CSV, col_types = cols(.default = col_character()), progress = FALSE)

players <- raw %>%
  mutate(
    season_start = as.integer(season_start),
    height_in = parse_height_in(HEIGHT),
    jersey_raw = str_trim(NUM),
    jersey_num = suppressWarnings(as.numeric(jersey_raw)),
    position_group = str_sub(POSITION, 1, 1),
    weight_lb = suppressWarnings(as.numeric(WEIGHT))
  ) %>%
  filter(!is.na(height_in)) %>%
  distinct(PLAYER_ID, season_start, .keep_all = TRUE)

message(sprintf("Loaded %s player-seasons across %d seasons (%d-%d)",
                format(nrow(players), big.mark = ","),
                dplyr::n_distinct(players$season_start),
                min(players$season_start), max(players$season_start)))

# ---- Season-level metrics ---------------------------------------------------
# Metric definitions:
#   mean_height_in    mean listed height, inches
#   share_above_55    share of numbered players wearing a number above 55.
#                     Numbers above 55 were historically unusual; the league's
#                     referee hand-signal convention is built on digits 0-5.
#   share_zero        share wearing "0" or "00"
#   jersey_height_cor Pearson correlation between jersey number and height
#   num6_count        players wearing 6 (retired league-wide for Bill Russell
#                     ahead of 2022-23, with existing wearers grandfathered)

numbered <- players %>% filter(!is.na(jersey_num))

height_by_season <- players %>%
  group_by(season_start) %>%
  summarise(
    n = n(),
    value = mean(height_in),
    sd = sd(height_in),
    .groups = "drop"
  ) %>%
  mutate(
    se = sd / sqrt(n),
    ci_lo = value - qt(0.975, n - 1) * se,
    ci_hi = value + qt(0.975, n - 1) * se,
    metric = "mean_height_in"
  )

number_metrics <- numbered %>%
  group_by(season_start) %>%
  summarise(
    n = n(),
    share_above_55 = mean(jersey_num > 55),
    share_zero = mean(jersey_raw %in% c("0", "00")),
    num6_count = sum(jersey_num == 6),
    jersey_height_cor = cor(jersey_num, height_in),
    .groups = "drop"
  ) %>%
  pivot_longer(
    c(share_above_55, share_zero, num6_count, jersey_height_cor),
    names_to = "metric", values_to = "value"
  )

results <- bind_rows(
  height_by_season %>% select(metric, season_start, value, n),
  number_metrics %>% select(metric, season_start, value, n)
) %>%
  arrange(metric, season_start)

write_csv(results, file.path(OUT_DIR, "results_r.csv"))

# ---- Models -----------------------------------------------------------------
# 1) Height trend. A single straight line across four decades would be the wrong
#    model: heights rose then flattened. Fit a piecewise-linear trend with a knot
#    at 1990 so the two eras get their own slope, and report both.
h <- height_by_season %>% mutate(post = pmax(season_start - 1990, 0))
m_height <- lm(value ~ season_start + post, data = h, weights = n)

# 1b) Regime-aware model: piecewise trend with knots at 1990 and the 2002 peak,
#     plus a LEVEL SHIFT at the 2019-20 measurement rule change. The shift term
#     turns the eyeballed "-0.61 in step" into a modelled estimate with a CI,
#     and keeps the trend slopes from being contaminated by the break.
#     (Fit comparison on this data: R^2 0.85 vs 0.30 for the single-knot model.)
hr <- height_by_season %>% mutate(
  k1990 = pmax(season_start - 1990, 0),
  k2002 = pmax(season_start - 2002, 0),
  shift2019 = as.numeric(season_start >= 2019)
)
m_regime <- lm(value ~ season_start + k1990 + k2002 + shift2019, data = hr, weights = n)

# 2) Has the jersey-number/height association weakened? Regress the per-season
#    correlation on season.
cors <- number_metrics %>% filter(metric == "jersey_height_cor")
m_cor <- lm(value ~ season_start, data = cors, weights = n)

models <- bind_rows(
  tidy(m_height, conf.int = TRUE) %>% mutate(model = "height_piecewise"),
  tidy(m_regime, conf.int = TRUE) %>% mutate(model = "height_regime"),
  tidy(m_cor, conf.int = TRUE) %>% mutate(model = "jersey_height_cor_trend")
) %>%
  select(model, term, estimate, std.error, statistic, p.value, conf.low, conf.high)

write_csv(models, file.path(OUT_DIR, "models_r.csv"))

# 2b) Within-player year-over-year height change: the composition-free check on
#     the 2019-20 measurement step. The aggregate mean can move because WHO
#     plays changed; a continuing player's listed height only moves when the
#     measurement itself does. Median offseason churn ~2%; the 2019 break 61%.
#     (Implementation in R/functions.R, unit-tested.)
write_csv(within_player_changes(players), file.path(OUT_DIR, "within_player_r.csv"))

# 3) Uncertainty without a distributional assumption: bootstrap the difference in
#    the jersey/height correlation between the first and last five seasons.
set.seed(2026)
era_boot_diff <- function(reps = 2000) {
  seasons <- sort(unique(numbered$season_start))
  # Windows must not overlap or the "change" is partly a season compared to itself.
  if (length(seasons) < 12) {
    message("Fewer than 12 seasons available; skipping era bootstrap.")
    return(NULL)
  }
  first5 <- head(seasons, 5)
  last5 <- tail(seasons, 5)
  a <- numbered %>% filter(season_start %in% first5) %>% select(jersey_num, height_in)
  b <- numbered %>% filter(season_start %in% last5) %>% select(jersey_num, height_in)
  if (nrow(a) < 30 || nrow(b) < 30) return(NULL)
  map_dbl(seq_len(reps), function(i) {
    ia <- sample.int(nrow(a), replace = TRUE)
    ib <- sample.int(nrow(b), replace = TRUE)
    cor(b$jersey_num[ib], b$height_in[ib]) - cor(a$jersey_num[ia], a$height_in[ia])
  })
}
boot <- era_boot_diff()
if (!is.null(boot)) {
  ci <- quantile(boot, c(0.025, 0.975))
  write_csv(
    tibble(quantity = "cor_diff_last5_minus_first5",
           estimate = mean(boot), ci_lo = ci[[1]], ci_hi = ci[[2]], reps = length(boot)),
    file.path(OUT_DIR, "bootstrap_r.csv")
  )
  message(sprintf("Bootstrap correlation change: %.3f [%.3f, %.3f]",
                  mean(boot), ci[[1]], ci[[2]]))
}

# ---- Figures ----------------------------------------------------------------
n_seasons <- dplyr::n_distinct(players$season_start)

# Figure 1: mean height with confidence band. One series, so no legend.
p1 <- ggplot(height_by_season, aes(season_start, value)) +
  geom_ribbon(aes(ymin = ci_lo, ymax = ci_hi), fill = PAL[["blue"]], alpha = 0.18) +
  geom_line(colour = PAL[["blue"]], linewidth = 0.7) +
  # The single largest year-over-year move in the series is a rule change, not a
  # basketball trend. Marking it keeps the chart from telling a false story.
  geom_vline(xintercept = 2019, colour = PAL[["orange"]], linewidth = 0.5, linetype = "dotted") +
  annotate("text", x = 2018.4, y = max(height_by_season$ci_hi), hjust = 1, vjust = 1,
           label = "2019-20: measured heights,\nno shoes, required",
           colour = PAL[["orange"]], size = 2.9) +
  labs(
    title = "Most of the height “decline” is a 2019 measurement change",
    subtitle = "Mean listed height per season, with 95% confidence band",
    x = NULL, y = "Height (inches)",
    caption = "Source: stats.nba.com CommonTeamRoster. One row per player-season; mid-season trades de-duplicated."
  ) +
  theme_study()
ggsave(file.path(FIG_DIR, "fig1_height_trend_r.png"), p1, width = 7.5, height = 4.2, dpi = 200)

# Figure 2: height by position group, direct-labelled (no legend box).
pos <- players %>%
  filter(position_group %in% c("G", "F", "C")) %>%
  group_by(season_start, position_group) %>%
  summarise(value = mean(height_in), n = n(), .groups = "drop")

pos_cols <- c(G = PAL[["blue"]], F = PAL[["orange"]], C = PAL[["aqua"]])
pos_labels <- pos %>% group_by(position_group) %>% filter(season_start == max(season_start)) %>% ungroup()

p2 <- ggplot(pos, aes(season_start, value, colour = position_group)) +
  geom_line(linewidth = 0.7) +
  geom_text(
    data = pos_labels,
    aes(label = c(G = "Guards", F = "Forwards", C = "Centers")[position_group]),
    hjust = -0.1, size = 3, fontface = "bold", show.legend = FALSE
  ) +
  scale_colour_manual(values = pos_cols) +
  scale_x_continuous(expand = expansion(mult = c(0.02, 0.14))) +
  labs(
    title = "Guards grew taller as the center–guard gap narrowed",
    subtitle = "Mean listed height per season by position group",
    x = NULL, y = "Height (inches)",
    caption = "Position taken from the leading letter so early 'G'/'F'/'C' and later 'G-F' codes are comparable."
  ) +
  theme_study()
ggsave(file.path(FIG_DIR, "fig2_height_by_position_r.png"), p2, width = 7.5, height = 4.2, dpi = 200)

# Figure 3: jersey number conventions over time.
num_share <- number_metrics %>%
  filter(metric %in% c("share_above_55", "share_zero")) %>%
  mutate(label = if_else(metric == "share_above_55", "Number above 55", "Wearing 0 or 00"))

lab3 <- num_share %>% group_by(metric) %>% filter(season_start == max(season_start)) %>% ungroup()

p3 <- ggplot(num_share, aes(season_start, value, colour = metric)) +
  geom_line(linewidth = 0.7) +
  geom_text(data = lab3, aes(label = label), hjust = -0.05, size = 3, fontface = "bold") +
  scale_colour_manual(values = c(share_above_55 = PAL[["blue"]], share_zero = PAL[["orange"]])) +
  scale_y_continuous(labels = scales::percent_format(accuracy = 1)) +
  scale_x_continuous(expand = expansion(mult = c(0.02, 0.20))) +
  labs(
    title = "Jersey number conventions have loosened",
    subtitle = "Share of numbered players per season",
    x = NULL, y = NULL,
    caption = "Numbers above 55 sit outside the digit range the NBA's referee hand-signal convention is built on."
  ) +
  theme_study()
ggsave(file.path(FIG_DIR, "fig3_number_conventions_r.png"), p3, width = 7.5, height = 4.2, dpi = 200)

# Figure 4: jersey/height association per season.
p4 <- ggplot(cors, aes(season_start, value)) +
  geom_hline(yintercept = 0, colour = AXIS, linewidth = 0.3) +
  geom_line(colour = PAL[["blue"]], linewidth = 0.7) +
  labs(
    title = "The link between jersey number and height has faded",
    subtitle = "Per-season correlation between jersey number and listed height",
    x = NULL, y = "Pearson correlation",
    caption = "Positive values mean taller players tend to wear higher numbers."
  ) +
  theme_study()
ggsave(file.path(FIG_DIR, "fig4_jersey_height_cor_r.png"), p4, width = 7.5, height = 4.2, dpi = 200)

message("R analysis complete: ", n_seasons, " seasons; wrote results, models, and 4 figures.")
