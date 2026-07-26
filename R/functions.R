# Pure functions for the jersey/height analysis, extracted so both the
# pipeline script (03_analysis.R) and the test suite (../../tests/R) can
# source them without side effects. Package-style separation of logic from
# script.

#' "6-9" -> 81 inches; anything unparseable -> NA.
parse_height_in <- function(x) {
  parts <- stringr::str_split_fixed(x, "-", 2)
  feet <- suppressWarnings(as.numeric(parts[, 1]))
  inches <- suppressWarnings(as.numeric(parts[, 2]))
  ifelse(is.na(feet) | is.na(inches), NA_real_, feet * 12 + inches)
}

#' Year-over-year listed-height change for players present in both seasons.
#' The composition-free check on the 2019-20 measurement step. Median
#' offseason churn is ~2% of continuing players; the 2019 break is 61%.
within_player_changes <- function(players) {
  seasons_sorted <- sort(unique(players$season_start))
  purrr::map_dfr(
    seq_len(length(seasons_sorted) - 1),
    function(i) {
      s0 <- seasons_sorted[i]; s1 <- seasons_sorted[i + 1]
      a <- players[players$season_start == s0, c("PLAYER_ID", "height_in")]
      b <- players[players$season_start == s1, c("PLAYER_ID", "height_in")]
      names(a)[2] <- "h0"; names(b)[2] <- "h1"
      j <- dplyr::inner_join(a, b, by = "PLAYER_ID")
      if (nrow(j) == 0) return(NULL)
      delta <- j$h1 - j$h0
      tibble::tibble(
        pair_start = s0,
        n_matched = nrow(j),
        mean_delta = mean(delta),
        share_shrunk = mean(delta < 0),
        share_same = mean(delta == 0),
        share_grew = mean(delta > 0)
      )
    }
  )
}
