# Pure functions for the WNBA extension (R/08_wnba_analysis.R), kept apart
# from the pipeline so tests/R/test-wnba.R can source them without side
# effects. Definitions are documented in the README's WNBA section.

# First season of each league. League age = season_start - this. It is also
# the inaugural season, which is never a rookie class.
LEAGUE_START <- c(nba = 1946L, wnba = 1997L)

#' TRUE when a jersey number contains any digit 6-9; NA when missing or blank.
has_digit_69 <- function(x) {
  s <- stringr::str_trim(x)
  out <- stringr::str_detect(s, "[6-9]")
  out[is.na(s) | s == ""] <- NA
  out
}

#' Seasons since the league's first season (NBA 1946 -> 0, WNBA 1997 -> 0).
league_age <- function(season_start, league) {
  if (!all(league %in% names(LEAGUE_START))) stop("unknown league: ", league)
  as.integer(season_start - unname(LEAGUE_START[league]))
}

# SCHOOL values that are not an NCAA school: blank, "none", "no college", or
# "unknown"; high schools and prep academies; junior colleges; pro and
# development pathways; plus the exact-match list in data/school_non_ncaa.csv.
NON_NCAA_BLANK <- c("", "none", "no college", "unknown")
NON_NCAA_REGEX <- paste0(
  "\\bHS\\b|High School|\\bPrep\\b|Preparatory|Academy \\([A-Z]{2}\\)",
  "|G League|Ignite|Overtime Elite",
  "|\\bC\\.C\\.|\\bJ\\.C\\.|\\bCC\\b|Community College|Junior College")

#' "ncaa" or "non_ncaa" for each SCHOOL value.
classify_school <- function(school, non_ncaa) {
  s <- stringr::str_trim(dplyr::coalesce(school, ""))
  non <- tolower(s) %in% NON_NCAA_BLANK |
    stringr::str_detect(s, NON_NCAA_REGEX) |
    s %in% non_ncaa
  ifelse(non, "non_ncaa", "ncaa")
}

#' Add first_season and rookie_status ("rookie", "veteran", "excluded").
#'   rookie:   EXP == "R" and the player's first season in the data
#'   veteran:  EXP is a whole number
#'   excluded: the league's inaugural season, EXP == "R" on a later roster,
#'             or EXP missing
identify_rookies <- function(players, league_first_season) {
  firsts <- players |>
    dplyr::group_by(PLAYER_ID) |>
    dplyr::summarise(first_season = min(season_start), .groups = "drop")
  players |>
    dplyr::left_join(firsts, by = "PLAYER_ID") |>
    dplyr::mutate(
      exp_clean = stringr::str_trim(dplyr::coalesce(EXP, "")),
      rookie_status = dplyr::case_when(
        season_start == league_first_season ~ "excluded",
        exp_clean == "R" & season_start == first_season ~ "rookie",
        stringr::str_detect(exp_clean, "^[0-9]+$") ~ "veteran",
        TRUE ~ "excluded"
      )
    ) |>
    dplyr::select(-exp_clean) |>
    dplyr::arrange(season_start, PLAYER_ID)
}
