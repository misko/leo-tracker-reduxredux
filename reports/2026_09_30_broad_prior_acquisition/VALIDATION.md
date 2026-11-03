# Validation

The component and report suite passed: **31 tests**. Run from the repository
root using the existing virtual environment:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src \
TMPDIR=/home/mouse9911/.cache/leo/research/broad_prior_acquisition/tmp \
.venv/bin/python -m pytest -q \
  tests/analysis/test_gaussian_mixture_reduction.py \
  tests/analysis/test_adaptive_location_map.py \
  reports/2026_09_30_broad_prior_acquisition/test_common.py \
  reports/2026_09_30_broad_prior_acquisition/test_merging.py \
  reports/2026_09_30_broad_prior_acquisition/test_evaluate.py \
  reports/2026_09_30_broad_prior_acquisition/diagnostics/test_diagnostics.py \
  reports/2026_09_30_broad_prior_acquisition/diagnostics/test_synthetic.py
```

Checks cover mixture normalization, full joint moment preservation, projected
versus full-state scoring, bounded pair work, unchanged mixtures already under
the cap, duplicate-observation rejection, exact disk area, persistent shared
nuisance hypotheses, factor-history replay after refinement, refinement-order
invariance, independent synthetic signal/background behavior, source seals,
complete-panel publication, and failed-estimate exclusion from accepted errors.

An initial combined test run exposed report-module search-path contamination in
the import regression test. The test now exercises a fresh CLI interpreter,
matching actual per-scan execution; the scientific fitter was unchanged.

Regenerate the comparison only after all 64 sealed attempts are present:

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python \
  reports/2026_09_30_broad_prior_acquisition/evaluate.py
```

These tests establish numerical and bookkeeping properties. Real-data accuracy,
posterior calibration, and spatial-map convergence require their own evidence;
a passing software test is not a successful localization result.
