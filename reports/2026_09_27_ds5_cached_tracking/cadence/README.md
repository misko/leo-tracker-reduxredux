# Adaptive blind-search cadence experiment

This development-only replay asks whether reducing blind acquisition frequency
can approach the 10x compute objective when full per-visit coverage is relaxed.
It compares only 1 second and 5 second minimum per-key blind-search intervals
on recorded visits. These intervals do not guarantee maximum discovery latency.

Every key begins with a blind search. Between deadlines, the unchanged causal
tracker may run a fresh V3 two-frame known-state check. A missing, expired, or
rejected prediction produces an explicit unknown visit. It never copies a prior
detection forward and never treats skipped computation as absence evidence.

Run from the repository root with:

```bash
PYTHONPATH=reports/2026_09_27_ds5_cached_tracking/cadence:reports/2026_09_27_ds5_cached_tracking:reports/2026_09_27_ds5_cached_tracking/native \
  .venv/bin/python reports/2026_09_27_ds5_cached_tracking/cadence/run_cadence.py
```

`REPORT.md` records the measured compute, coverage, and discovery-latency
tradeoff. This experiment does not change the full-coverage objective.
