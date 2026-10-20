#!/bin/bash
# Every check in this repo: unit tests, then the study's reconciliation /
# validation gate. Non-zero exit on any failure. PY overrides the
# interpreter (the family orchestrator sets it to a shared venv).
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}

echo "=== unit tests: Python (pytest) ==="
$PY -m pytest tests/python -q

echo
echo "=== unit tests: R (testthat) ==="
Rscript tests/R/run_tests.R

echo
echo "=== reconciliation / validation ==="
$PY python/04_reconcile.py | tail -1

echo
echo "=== number explorer: offline gate replay ==="
$PY python/06_number_explorer.py --check | tail -1

echo
echo "=== findings: README numbers regenerate from outputs ==="
$PY python/05_findings.py --check | tail -1

echo
echo "=== WNBA extension: R vs Python reconciliation ==="
$PY python/09_reconcile_wnba.py | tail -1

echo
echo "=== WNBA extension: README section regenerates from outputs ==="
$PY python/10_wnba_findings.py --check | tail -1

echo
echo "=== diagrams: every explainer SVG rebuilds identically from committed tables ==="
$PY python/14_diagrams.py --check | tail -1

echo
echo "=== roster completeness: participation check (informational, not a gate) ==="
# Compares roster players with LeagueDashPlayerStats per season. Only NBA 2024-25 is
# cached so far; every other league-season prints NOT RUN and the summary says so.
# Exit is 0 here on purpose. Once every season is cached (python/11_participation_check.py
# --fetch), switch this line to add --require-all --fail-on-flags and make it a gate.
$PY python/11_participation_check.py | tail -3
