# Unit tests for jersey-height-study/R/wnba_functions.R

source(file.path(REPO, "R", "wnba_functions.R"))
non_ncaa <- readr::read_csv(file.path(REPO, "data", "school_non_ncaa.csv"),
                            col_types = readr::cols(.default = "c"), na = character())$SCHOOL

test_that("has_digit_69 finds any digit 6-9", {
  expect_equal(has_digit_69(c("00", "0", "69", "6", "19", "45", "55", " 7 ")),
               c(FALSE, FALSE, TRUE, TRUE, TRUE, FALSE, FALSE, TRUE))
})

test_that("has_digit_69 treats a missing NUM as unknown", {
  expect_equal(has_digit_69(c(NA, "", "   ")), c(NA, NA, NA))
})

test_that("league_age counts seasons since the first", {
  expect_equal(league_age(c(1946, 1975), "nba"), c(0L, 29L))
  expect_equal(league_age(c(1997, 2026), "wnba"), c(0L, 29L))
  expect_equal(league_age(c(1946, 1997), c("nba", "wnba")), c(0L, 0L))
  expect_error(league_age(2000, "g-league"), "unknown league")
})

test_that("classify_school applies the documented rules", {
  non <- c(NA, "", "   ", "None", "No College", "Unknown", "Lower Merion HS (PA)",
           "IMG Academy (FL)", "Athlete Institute Prep", "Blinn J.C.", "Seward County CC",
           "G League Ignite", "Overtime Elite", "Real Madrid", "Serbia-Montenegro",
           " Serbia-Montenegro")
  yes <- c("Connecticut", "Virginia '96", "Old Dominion '98/Portugal", "St. John's (NY)",
           "Air Force Academy", "Arizona State")
  expect_true(all(classify_school(non, non_ncaa) == "non_ncaa"))
  expect_true(all(classify_school(yes, non_ncaa) == "ncaa"))
})

test_that("identify_rookies requires EXP R and a first appearance", {
  players <- tibble::tibble(
    PLAYER_ID = c("a", "a", "b", "b", "c", "d", "e", "f"),
    season_start = c(1997L, 1998L, 1998L, 1999L, 1999L, 1999L, 2000L, 2000L),
    EXP = c("R", "1", "R", "R", "1", NA, "R", "R"),
    NUM = c("00", "0", "69", "69", NA, "5", "", "7")
  )
  out <- identify_rookies(players, 1997L)
  st <- setNames(out$rookie_status, paste(out$PLAYER_ID, out$season_start))
  expect_equal(unname(st["a 1997"]), "excluded")   # inaugural season
  expect_equal(unname(st["a 1998"]), "veteran")
  expect_equal(unname(st["b 1998"]), "rookie")
  expect_equal(unname(st["b 1999"]), "excluded")   # R again on a later roster
  expect_equal(unname(st["c 1999"]), "veteran")
  expect_equal(unname(st["d 1999"]), "excluded")   # EXP missing
  expect_equal(unname(st["e 2000"]), "rookie")     # missing NUM does not matter
  expect_false(is.unsorted(out$season_start))
})
