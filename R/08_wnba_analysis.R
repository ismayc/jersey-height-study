# WNBA extension --- R / tidyverse implementation.
#
# Independent of python/08_wnba_analysis.py: written from the definitions in
# the README's WNBA section, so python/09_reconcile_wnba.py is a real check.
# Cleaning follows R/03_analysis.R: HEIGHT parsed to inches and rows without a
# height dropped; NUM kept as text and converted to a number (blank or
# non-numeric entries drop out of number-based metrics only); first row kept
# per (PLAYER_ID, season_start).
#
# Writes output/wnba/*_r.csv (no figures; the plotly figures come from the
# Python run). Every table is sorted on its keys before it is written or
# bootstrapped.
#
# Run:  Rscript R/08_wnba_analysis.R

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(purrr)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")
DATA <- file.path(ROOT, "data")
OUT_DIR <- file.path(ROOT, "output", "wnba")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

source(file.path(ROOT, "R", "functions.R"))       # parse_height_in
source(file.path(ROOT, "R", "wnba_functions.R"))  # has_digit_69, league_age, ...

COVERAGE_MIN <- 0.90   # minimum share of a season's players with a parseable NUM
EXPOSED_FIRST <- c(nba = 2024L, wnba = 2024L)
PRE_WINDOW <- 10L
REPS <- 2000L
SEED <- 2026L

non_ncaa <- read_csv(file.path(DATA, "school_non_ncaa.csv"),
                     col_types = cols(.default = col_character()), na = character())$SCHOOL

read_text <- function(f) {
  read_csv(file.path(DATA, f), col_types = cols(.default = col_character()),
           na = "", progress = FALSE) %>%
    select(PLAYER_ID, PLAYER, NUM, HEIGHT, EXP, SCHOOL, season_start)
}

load_players <- function(league) {
  files <- if (league == "nba") c("nba_early_rosters.csv", "nba_rosters.csv") else "wnba_rosters.csv"
  bind_rows(lapply(files, read_text)) %>%
    mutate(
      season_start = as.integer(season_start),
      height_in = parse_height_in(HEIGHT),
      jersey_raw = str_trim(coalesce(NUM, "")),
      jersey_num = suppressWarnings(as.numeric(jersey_raw))
    ) %>%
    filter(!is.na(height_in)) %>%
    distinct(PLAYER_ID, season_start, .keep_all = TRUE) %>%
    mutate(digit69 = has_digit_69(jersey_raw),
           school_class = classify_school(SCHOOL, non_ncaa),
           league = league) %>%
    arrange(season_start, PLAYER_ID)
}

# ---- Season metrics (parts 1 and 3) ------------------------------------------
season_metrics <- function(players, league) {
  per_season <- players %>%
    group_by(season_start) %>%
    summarise(n_all = n(),
              num_coverage = mean(!is.na(jersey_num)),
              mean_height_in = mean(height_in), .groups = "drop")
  nums <- players %>%
    filter(!is.na(jersey_num)) %>%
    group_by(season_start) %>%
    summarise(n = n(),
              share_above_55 = mean(jersey_num > 55),
              share_zero = mean(jersey_raw %in% c("0", "00")),
              share_digit69 = mean(digit69),
              jersey_height_cor = cor(jersey_num, height_in),
              .groups = "drop") %>%
    pivot_longer(-c(season_start, n), names_to = "metric", values_to = "value")
  base <- per_season %>%
    pivot_longer(c(num_coverage, mean_height_in), names_to = "metric", values_to = "value") %>%
    rename(n = n_all)
  bind_rows(base, nums) %>%
    left_join(per_season %>% transmute(season_start,
                                       included = as.integer(num_coverage >= COVERAGE_MIN)),
              by = "season_start") %>%
    mutate(league = league, league_age = league_age(season_start, league),
           n = as.integer(n)) %>%
    select(league, metric, season_start, league_age, value, n, included) %>%
    arrange(league, metric, season_start)
}

# ---- Era bootstrap (part 1) ----------------------------------------------------
era_bootstrap <- function(players, league) {
  numbered <- players %>% filter(!is.na(jersey_num)) %>% arrange(season_start, PLAYER_ID)
  seasons <- sort(unique(numbered$season_start))
  if (length(seasons) < 12) return(NULL)
  first5 <- head(seasons, 5); last5 <- tail(seasons, 5)
  a <- numbered %>% filter(season_start %in% first5)
  b <- numbered %>% filter(season_start %in% last5)
  set.seed(SEED)
  diffs <- map_dbl(seq_len(REPS), function(i) {
    ia <- sample.int(nrow(a), replace = TRUE)
    ib <- sample.int(nrow(b), replace = TRUE)
    cor(b$jersey_num[ib], b$height_in[ib]) - cor(a$jersey_num[ia], a$height_in[ia])
  })
  ci <- quantile(diffs, c(0.025, 0.975), names = FALSE)
  cor_a <- cor(a$jersey_num, a$height_in); cor_b <- cor(b$jersey_num, b$height_in)
  tibble(league = league, quantity = "cor_diff_last5_minus_first5",
         first_lo = first5[1], first_hi = first5[5], last_lo = last5[1], last_hi = last5[5],
         cor_first5 = cor_a, cor_last5 = cor_b, observed = cor_b - cor_a,
         estimate = mean(diffs), ci_lo = ci[1], ci_hi = ci[2], reps = REPS,
         n_first = nrow(a), n_last = nrow(b))
}

# ---- NCAA digit rule (part 2) ----------------------------------------------------
rookie_frame <- function(players, league) {
  exp_first <- EXPOSED_FIRST[[league]]
  covered <- players %>% group_by(season_start) %>%
    summarise(cov = mean(!is.na(jersey_num)), .groups = "drop") %>%
    filter(cov >= COVERAGE_MIN) %>% pull(season_start)
  tagged <- identify_rookies(players, LEAGUE_START[[league]]) %>%
    filter(season_start %in% covered, !is.na(jersey_num), rookie_status != "excluded") %>%
    mutate(group = if_else(rookie_status == "veteran", "veteran",
                           paste0(school_class, "_rookie")))
  bind_rows(
    tagged %>% filter(season_start >= exp_first) %>% mutate(window = "exposed"),
    tagged %>% filter(season_start >= exp_first - PRE_WINDOW, season_start < exp_first) %>%
      mutate(window = "recent"),
    tagged %>% filter(season_start < exp_first) %>% mutate(window = "all_pre")
  ) %>%
    mutate(league = league) %>%
    arrange(league, group, window, season_start, PLAYER_ID)
}

rookie_status_audit <- function(players, league) {
  identify_rookies(players, LEAGUE_START[[league]]) %>%
    mutate(exp_r = coalesce(str_trim(EXP), "") == "R",
           first = season_start == first_season) %>%
    group_by(season_start) %>%
    summarise(n = n(), exp_r_n = sum(exp_r), first_app = sum(first),
              both = sum(exp_r & first), exp_r_only = sum(exp_r & !first),
              first_only = sum(!exp_r & first),
              rookies = sum(rookie_status == "rookie"),
              veterans = sum(rookie_status == "veteran"),
              excluded = sum(rookie_status == "excluded"), .groups = "drop") %>%
    rename(exp_r = exp_r_n) %>%
    mutate(league = league) %>%
    select(league, season_start, n, exp_r, first_app, both, exp_r_only, first_only,
           rookies, veterans, excluded) %>%
    arrange(league, season_start)
}

school_class_counts <- function(players, league) {
  identify_rookies(players, LEAGUE_START[[league]]) %>%
    count(rookie_status, school_class, name = "n") %>%
    mutate(league = league) %>%
    select(league, rookie_status, school_class, n) %>%
    arrange(league, rookie_status, school_class)
}

rookie_shares <- function(frame) {
  frame %>%
    group_by(league, group, window) %>%
    summarise(n = n(), n_digit69 = sum(digit69), share = mean(digit69),
              season_lo = min(season_start), season_hi = max(season_start),
              .groups = "drop") %>%
    arrange(league, group, window)
}

rookie_classes <- function(frame) {
  frame %>%
    filter(window %in% c("all_pre", "exposed")) %>%
    group_by(league, group, season_start) %>%
    summarise(n = n(), n_digit69 = sum(digit69), share = mean(digit69), .groups = "drop") %>%
    arrange(league, group, season_start)
}

CONTRASTS <- tribble(
  ~contrast,                     ~group,             ~pre_window, ~control,
  "ncaa_rookie_recent",          "ncaa_rookie",      "recent",    "",
  "non_ncaa_rookie_recent",      "non_ncaa_rookie",  "recent",    "",
  "veteran_recent",              "veteran",          "recent",    "",
  "ncaa_rookie_all_pre",         "ncaa_rookie",      "all_pre",   "",
  "non_ncaa_rookie_all_pre",     "non_ncaa_rookie",  "all_pre",   "",
  "veteran_all_pre",             "veteran",          "all_pre",   "",
  "did_ncaa_rookie_vs_veteran",  "ncaa_rookie",      "recent",    "veteran",
  "did_ncaa_vs_non_ncaa_rookie", "ncaa_rookie",      "recent",    "non_ncaa_rookie"
)

rookie_bootstrap <- function(frame, league) {
  cell <- function(g, w) {
    frame %>% filter(group == g, window == w) %>%
      arrange(season_start, PLAYER_ID) %>% pull(digit69) %>% as.numeric()
  }
  pmap_dfr(CONTRASTS, function(contrast, group, pre_window, control) {
    cells <- list(cell(group, pre_window), cell(group, "exposed"))
    if (control != "") cells <- c(cells, list(cell(control, pre_window), cell(control, "exposed")))
    stat <- function(cs) {
      d <- mean(cs[[2]]) - mean(cs[[1]])
      if (length(cs) == 4) d - (mean(cs[[4]]) - mean(cs[[3]])) else d
    }
    observed <- NA_real_; lo <- NA_real_; hi <- NA_real_
    if (all(lengths(cells) > 0)) {
      set.seed(SEED)
      draws <- vapply(seq_len(REPS), function(i) {
        stat(lapply(cells, function(x) x[sample.int(length(x), replace = TRUE)]))
      }, numeric(1))
      q <- quantile(draws, c(0.025, 0.975), names = FALSE)
      observed <- stat(cells); lo <- q[1]; hi <- q[2]
    }
    tibble(league = league, contrast = contrast, group = group, pre_window = pre_window,
           control = control,
           n_pre = length(cells[[1]]), n_exposed = length(cells[[2]]),
           n_ctrl_pre = if (control != "") length(cells[[3]]) else 0L,
           n_ctrl_exposed = if (control != "") length(cells[[4]]) else 0L,
           observed = observed, ci_lo = lo, ci_hi = hi, reps = REPS)
  }) %>% arrange(league, contrast)
}

# ---- Main ----------------------------------------------------------------------------
leagues <- c("nba", "wnba")
players <- setNames(lapply(leagues, load_players), leagues)
for (lg in leagues) {
  message(sprintf("%s: %s player-seasons, %d-%d", toupper(lg),
                  format(nrow(players[[lg]]), big.mark = ","),
                  min(players[[lg]]$season_start), max(players[[lg]]$season_start)))
}

bind_rows(lapply(leagues, function(lg) season_metrics(players[[lg]], lg))) %>%
  arrange(league, metric, season_start) %>%
  write_csv(file.path(OUT_DIR, "season_metrics_r.csv"))

boot <- era_bootstrap(players[["wnba"]], "wnba")
write_csv(boot, file.path(OUT_DIR, "era_bootstrap_r.csv"))
message(sprintf("WNBA era bootstrap: %+.3f [%+.3f, %+.3f]", boot$estimate, boot$ci_lo, boot$ci_hi))

bind_rows(lapply(leagues, function(lg) rookie_status_audit(players[[lg]], lg))) %>%
  write_csv(file.path(OUT_DIR, "rookie_status_r.csv"))
bind_rows(lapply(leagues, function(lg) school_class_counts(players[[lg]], lg))) %>%
  write_csv(file.path(OUT_DIR, "school_class_r.csv"))

frames <- setNames(lapply(leagues, function(lg) rookie_frame(players[[lg]], lg)), leagues)
bind_rows(lapply(frames, rookie_shares)) %>% arrange(league, group, window) %>%
  write_csv(file.path(OUT_DIR, "rookie_shares_r.csv"))
bind_rows(lapply(frames, rookie_classes)) %>% arrange(league, group, season_start) %>%
  write_csv(file.path(OUT_DIR, "rookie_classes_r.csv"))
bind_rows(lapply(leagues, function(lg) rookie_bootstrap(frames[[lg]], lg))) %>%
  arrange(league, contrast) %>%
  write_csv(file.path(OUT_DIR, "rookie_bootstrap_r.csv"))

message("WNBA extension (R) complete: wrote output/wnba/*_r.csv.")
