# Common clock versus independent scan clocks

Status: implementation and layout tests prepared; no common-clock fits yet. Complete the unchanged independent-nuisance pilots on DS10-B01 and DS11-B01 before judging this ablation.

Hypothesis: the same receiver system over a roughly 26-minute quad may share a UTC timing offset. Independent scan clocks can absorb inconsistent model errors and distort the shared position. A common clock may improve identification, but will fail if real timing offsets vary between captures or if its extra coupling amplifies model mismatch.

The original window model gives each scan c_j ~ N(0,1 s²) independently. The new model uses c_j=c for all scans with c ~ N(0,1 s²), counting this prior once. Every individual scan retains the same marginal clock prior; the changed assumption is cross-scan dependence. Satellite epochs remain independent per scan at sigma=0.5 s; RX drift remains independent per scan and receiver at sigma=0.5 Hz/s. Position, observations, acquisition, association policy, Student-t4 residuals, height and budgets stay the same. Actual scan-local UTC origins remain inside the original physics ports.

For n scans, state dimension decreases by n−1. A one-scan window is exactly the original model: the parameter map and precision match elementwise in tests. Run the two adjacent pairs and quad for each pilot block, comparing to its already audited independent-clock runs. Reuse the single-scan baseline as the same mathematical model; do not count it as a new fit. New joint fits start from fresh regional acquisition with zero nuisance coordinates, not from a GPS-selected or baseline-selected seed.

The next alternative, if warranted by these data, is c_j=c+epsilon_j with a fixed scatter prior, explicitly separating persistent common error from per-capture error. That hierarchical model is not implemented or tuned here. Avoid searching scatter values against these first blocks' geographic results.

Why prioritize this before shared satellite epochs: the accepted DS9-B01 quad has 83 distinct active satellite/snapshot groups, none occurring in more than one scan. With these fixed signal identities, sharing epoch coordinates across scans adds no active likelihood coupling. Alternative labels or background visibility could still change under a fresh shared-epoch search, so this is a local diagnostic, not a universal equivalence claim. Verify overlap on DS10/DS11 before extending that conclusion.

Commands after baseline pilots:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python reports/2026_10_01_quad_development/common_clock_batch.py DS9-B01
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python reports/2026_10_01_quad_development/evaluate_common_clock.py DS9-B01
```

The batch uses at most two fits and external 180/360 s limits for pairs/quads. All outcomes must pass unchanged numerical acceptance checks before geography is read. No extension, replacement scan, altered gradient tolerance, or failed-window deletion is allowed. Report all planned denominators, paired error changes, clock estimates, acceptance and runtime; this development ablation does not establish calibrated posterior uncertainty.
