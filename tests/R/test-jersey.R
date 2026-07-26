# Unit tests for jersey-height-study/R/functions.R

source(file.path(REPO, "jersey-height-study", "R", "functions.R"))

test_that("parse_height_in handles the feed's formats", {
  expect_equal(parse_height_in(c("6-9", "7-0", "5-11")), c(81, 84, 71))
  expect_true(all(is.na(parse_height_in(c("", "junk", NA)))))
})

test_that("within_player_changes matches by player and classifies deltas", {
  players <- tibble::tibble(
    PLAYER_ID = c("A", "B", "C", "A", "B"),
    season_start = c(2000, 2000, 2000, 2001, 2001),
    height_in = c(80, 75, 82, 79, 75)
  )
  wp <- within_player_changes(players)
  expect_equal(nrow(wp), 1)
  expect_equal(wp$n_matched, 2)          # C only in season 1: excluded
  expect_equal(wp$share_shrunk, 0.5)
  expect_equal(wp$share_same, 0.5)
  expect_equal(wp$share_grew, 0)
  expect_equal(wp$mean_delta, -0.5)
})
