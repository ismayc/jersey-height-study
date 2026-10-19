"""Verify the R and Python WNBA-extension implementations agree.

Deterministic tables (season metrics, rookie audit, school classes, 6-9
shares by window and by class) are compared row by row on their keys: every
key must exist in both, every count must match exactly, and every value must
agree to 1e-9. Bootstrap tables use different RNGs in each language, so they
are compared by equal group sizes, an equal observed statistic (1e-9), and
overlapping 95% intervals. Exit code is non-zero on any mismatch.

Run:  python python/09_reconcile_wnba.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "wnba"
TOL = 1e-9

# table stem -> (key columns, exact-match columns, tolerance columns)
TABLES = {
    "season_metrics": (["league", "metric", "season_start"], ["league_age", "n", "included"],
                       ["value"]),
    "rookie_status": (["league", "season_start"],
                      ["n", "exp_r", "first_app", "both", "exp_r_only", "first_only",
                       "rookies", "veterans", "excluded"], []),
    "school_class": (["league", "rookie_status", "school_class"], ["n"], []),
    "rookie_shares": (["league", "group", "window"],
                      ["n", "n_digit69", "season_lo", "season_hi"], ["share"]),
    "rookie_classes": (["league", "group", "season_start"], ["n", "n_digit69"], ["share"]),
}
# bootstrap stem -> (key columns, exact-match columns, tolerance columns)
BOOTS = {
    "era_bootstrap": (["league", "quantity"],
                      ["first_lo", "first_hi", "last_lo", "last_hi", "reps", "n_first", "n_last"],
                      ["cor_first5", "cor_last5", "observed"]),
    "rookie_bootstrap": (["league", "contrast"],
                         ["group", "pre_window", "control", "n_pre", "n_exposed",
                          "n_ctrl_pre", "n_ctrl_exposed", "reps"], ["observed"]),
}


def read(stem: str, impl: str) -> pl.DataFrame:
    # Text-typed "control" is empty for single-group contrasts; read it as "".
    df = pl.read_csv(OUT / f"{stem}_{impl}.csv")
    if "control" in df.columns:
        df = df.with_columns(pl.col("control").cast(pl.Utf8).fill_null(""))
    return df


def compare(stem: str, keys: list[str], exact: list[str], tol: list[str]) -> tuple[bool, dict]:
    r, p = read(stem, "r"), read(stem, "python")
    problems: list[str] = []
    if set(r.columns) != set(p.columns):
        problems.append(f"columns differ: {sorted(set(r.columns) ^ set(p.columns))}")
        return False, {"table": stem, "rows": 0, "max_abs_diff": None, "status": "FAIL"}
    for df, name in ((r, "R"), (p, "Python")):
        dup = df.height - df.select(keys).unique().height
        if dup:
            problems.append(f"{name} has {dup} duplicate keys")
        if df.sort(keys).select(keys).to_dicts() != df.select(keys).to_dicts():
            problems.append(f"{name} rows are not sorted on {keys}")
    m = r.join(p, on=keys, how="full", suffix="_py", coalesce=True)
    missing = m.filter(pl.any_horizontal(
        [pl.col(exact[0]).is_null() != pl.col(f"{exact[0]}_py").is_null()]))
    if missing.height:
        problems.append(f"{missing.height} keys in only one implementation, e.g. "
                        f"{missing.select(keys).head(3).to_dicts()}")
    for c in exact:
        bad = m.filter(pl.col(c).cast(pl.Utf8).fill_null("<null>")
                       != pl.col(f"{c}_py").cast(pl.Utf8).fill_null("<null>"))
        if bad.height:
            problems.append(f"{c}: {bad.height} rows differ, e.g. "
                            f"{bad.select(*keys, c, f'{c}_py').head(3).to_dicts()}")
    worst = 0.0
    for c in tol:
        one_sided = m.filter(pl.col(c).is_null() != pl.col(f"{c}_py").is_null())
        if one_sided.height:
            problems.append(f"{c}: {one_sided.height} rows null on one side only")
        d = m.select((pl.col(c) - pl.col(f"{c}_py")).abs().max()).item()
        worst = max(worst, d or 0.0)
    if worst > TOL:
        problems.append(f"max |diff| {worst:.3g} exceeds {TOL:g}")
    for msg in problems:
        print(f"  {stem}: {msg}")
    ok = not problems
    return ok, {"table": stem, "rows": m.height, "max_abs_diff": worst,
                "status": "PASS" if ok else "FAIL"}


def compare_boot(stem: str, keys: list[str], exact: list[str], tol: list[str]) -> bool:
    ok, _ = compare(stem, keys, exact, tol)
    r, p = read(stem, "r"), read(stem, "python")
    m = r.join(p, on=keys, how="inner", suffix="_py")
    print(f"\n{stem} (different RNGs: intervals compared for overlap):")
    for row in m.iter_rows(named=True):
        label = " ".join(str(row[k]) for k in keys)
        if row["ci_lo"] is None and row["ci_lo_py"] is None:
            print(f"  {label}: no interval in either (an empty cell); PASS")
            continue
        if (row["ci_lo"] is None) != (row["ci_lo_py"] is None):
            print(f"  {label}: interval in only one implementation; FAIL")
            ok = False
            continue
        overlap = row["ci_lo"] <= row["ci_hi_py"] and row["ci_lo_py"] <= row["ci_hi"]
        ok = ok and overlap
        print(f"  {label}: R [{row['ci_lo']:+.4f}, {row['ci_hi']:+.4f}]  "
              f"Python [{row['ci_lo_py']:+.4f}, {row['ci_hi_py']:+.4f}]  "
              f"{'PASS' if overlap else 'FAIL'}")
    return ok


def compare_main_study() -> bool:
    """The extension's NBA seasons from 1980 on must equal the main study's.

    Same data file, same cleaning rules, written again for this extension, so
    any difference means the extension's cleaning drifted from 03_analysis.py.
    """
    main = pl.read_csv(ROOT / "output" / "results_python.csv")
    ext = (read("season_metrics", "python").filter(pl.col("league") == "nba")
           .select("metric", "season_start", value_ext="value", n_ext="n"))
    shared = ["mean_height_in", "share_above_55", "share_zero", "jersey_height_cor"]
    m = (main.filter(pl.col("metric").is_in(shared))
         .join(ext, on=["metric", "season_start"], how="left"))
    missing = m.filter(pl.col("value_ext").is_null()).height
    worst = m.select((pl.col("value") - pl.col("value_ext")).abs().max()).item() or 0.0
    n_bad = m.filter(pl.col("n") != pl.col("n_ext")).height
    ok = m.height > 0 and missing == 0 and n_bad == 0 and worst <= TOL
    print(f"\nNBA seasons vs the main study (output/results_python.csv): {m.height} rows, "
          f"{missing} missing, {n_bad} with a different n, max |diff| {worst:.3g}: "
          f"{'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    print(f"Reconciling the WNBA extension, R vs Python (tolerance {TOL:g})\n")
    rows, all_ok = [], True
    for stem, spec in TABLES.items():
        ok, row = compare(stem, *spec)
        rows.append(row)
        all_ok = all_ok and ok
    print(pl.DataFrame(rows))
    for stem, spec in BOOTS.items():
        all_ok = compare_boot(stem, *spec) and all_ok
    all_ok = compare_main_study() and all_ok
    print("\n" + ("WNBA RECONCILE: ALL CHECKS PASS" if all_ok else "WNBA RECONCILE: MISMATCHES FOUND"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
