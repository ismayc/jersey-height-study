"""Verify the R and Python analyses agree.

Two independent implementations of the same metric definitions will disagree
wherever a definition was ambiguous. That disagreement is the signal worth
catching: it usually means a cleaning rule was underspecified, not that one
language is wrong.

Exit code is non-zero when any metric exceeds tolerance, so this can gate a
commit or CI run.

Run:  python python/04_reconcile.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"

# Season-level shares and correlations should agree to floating-point noise.
# Model coefficients get a looser tolerance because the two stacks use different
# linear-algebra backends.
TOL_METRICS = 1e-9
TOL_MODELS = 1e-6
# The bootstrap uses different RNGs in each language, so it is compared as
# overlapping intervals rather than equal numbers.


def compare_metrics() -> tuple[bool, pl.DataFrame]:
    r = pl.read_csv(OUT / "results_r.csv")
    p = pl.read_csv(OUT / "results_python.csv")

    merged = r.join(p, on=["metric", "season_start"], how="full",
                    suffix="_py", coalesce=True)

    unmatched = merged.filter(pl.col("value").is_null() | pl.col("value_py").is_null())
    # A genuinely null metric (e.g. an undefined correlation) is null in both and
    # is not a mismatch; only one-sided nulls are.
    one_sided = unmatched.filter(
        pl.col("value").is_null() != pl.col("value_py").is_null()
    )
    if one_sided.height:
        print(f"  {one_sided.height} rows present in only one implementation:")
        print(one_sided.select("metric", "season_start", "value", "value_py").head(10))

    both = (merged
            .filter(pl.col("value").is_not_null() & pl.col("value_py").is_not_null())
            .with_columns(
                abs_diff=(pl.col("value") - pl.col("value_py")).abs(),
                n_diff=(pl.col("n") - pl.col("n_py")).abs(),
            ))

    summary = (both.group_by("metric")
               .agg(seasons=pl.len(),
                    max_abs_diff=pl.col("abs_diff").max(),
                    max_n_diff=pl.col("n_diff").max())
               .with_columns(
                   status=pl.when((pl.col("max_abs_diff") <= TOL_METRICS)
                                  & (pl.col("max_n_diff") == 0))
                   .then(pl.lit("PASS")).otherwise(pl.lit("FAIL")))
               .sort("metric"))

    ok = (summary["status"] == "PASS").all() and one_sided.height == 0
    return bool(ok), summary


def compare_models() -> tuple[bool, pl.DataFrame]:
    r = pl.read_csv(OUT / "models_r.csv")
    p = pl.read_csv(OUT / "models_python.csv")
    merged = (r.join(p, on=["model", "term"], how="inner", suffix="_py")
              .with_columns(
                  est_diff=(pl.col("estimate") - pl.col("estimate_py")).abs(),
                  se_diff=(pl.col("std.error") - pl.col("std.error_py")).abs(),
              )
              .with_columns(
                  status=pl.when((pl.col("est_diff") <= TOL_MODELS)
                                 & (pl.col("se_diff") <= TOL_MODELS))
                  .then(pl.lit("PASS")).otherwise(pl.lit("FAIL"))))
    ok = (merged["status"] == "PASS").all()
    return bool(ok), merged.select("model", "term", "estimate", "estimate_py",
                                   "est_diff", "se_diff", "status")


def compare_bootstrap() -> bool:
    fr, fp = OUT / "bootstrap_r.csv", OUT / "bootstrap_python.csv"
    if not (fr.exists() and fp.exists()):
        print("\nBootstrap: skipped (not enough seasons in this run)")
        return True
    r = pl.read_csv(fr).row(0, named=True)
    p = pl.read_csv(fp).row(0, named=True)
    overlap = (r["ci_lo"] <= p["ci_hi"]) and (p["ci_lo"] <= r["ci_hi"])
    print("\nBootstrap (different RNGs, so intervals are compared for overlap):")
    print(f"  R:      {r['estimate']:+.4f}  [{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}]")
    print(f"  Python: {p['estimate']:+.4f}  [{p['ci_lo']:+.4f}, {p['ci_hi']:+.4f}]")
    print(f"  Intervals overlap: {'PASS' if overlap else 'FAIL'}")
    return bool(overlap)


def main() -> int:
    print("Reconciling R and Python implementations\n")

    print(f"Season metrics (tolerance {TOL_METRICS:g}):")
    metrics_ok, metrics = compare_metrics()
    print(metrics)

    print(f"\nModel coefficients (tolerance {TOL_MODELS:g}):")
    models_ok, models = compare_models()
    print(models)

    boot_ok = compare_bootstrap()

    all_ok = metrics_ok and models_ok and boot_ok
    print("\n" + ("ALL CHECKS PASS" if all_ok else "MISMATCHES FOUND"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
