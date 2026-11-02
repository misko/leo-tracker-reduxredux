# Family physical covariance sensitivity (prototype B)

Widening the existing family orbital covariance improves the RF objective on both scans. DS26-0309 remains qualified and its post-fit position error decreases moderately. DS26-0070 still fails the original 0.01 s phase-closure requirement in every grid cell. Its lowest-error cell differs from its best RF-objective cell, so the position result does not justify selecting that cell. This experiment does not establish unique satellite identity or independently validated localization.

This is a report-local sensitivity prototype on frozen ALGO07 revision `d8d7033f9f654279463fa054cd2020be0bfd273e`. It changes no production implementation, ownership artifact, or fixture. The generic existing RF influence trigger selects 60148 in DS26-0309 and 62320 in DS26-0070. There are no case IDs in the model or family-selection code. Frozen association identities remain unchanged; in particular the 62320/67047/63571 alternatives are not compared here. The parent experiment supplies predictive comparison and combined models.

The model already contains three marginalized physical Gaussian orbital directions for supported families: mean motion, inclination, and RAAN. This experiment scales their existing prior standard deviations together by **1, 2, or 4**, multiplying their family covariance by **1, 4, or 16**. It adds zero nuisance columns and no free offset or slope. The existing phase prior and receiver/band prior remain unchanged. The unmodified hierarchical Gaussian/Gamma ELBO retains its low-rank log determinant, prior penalty, Gamma terms, and predictive normalization. Existing fractional powers, where present, make this a generalized evidence comparison rather than a normalized sampling probability.

The protocol was saved before any fit. Both c arms use the same published fitted-c RF position and phase reference as their starting point; every cell gets the same 15 refresh rounds and 40 feasible-fit iterations per round in the existing regional bounds. The observations, masks, aliases, candidates, priors other than the declared physical SD scaling, and budgets are matched. Evaluation truth is first used after fitting and original qualification. No scale is selected here.

| Scan | Physical SD | c=0 error km | fitted-c error km | fitted-c RF objective | Fully qualified both arms |
|---|---:|---:|---:|---:|---|
| DS26-0309 | 1 | 3.162 | 3.127 | 31495.29 | yes |
| DS26-0309 | 2 | 2.739 | 2.709 | 31459.65 | yes |
| DS26-0309 | 4 | 1.880 | 1.860 | 31386.54 | yes |
| DS26-0070 | 1 | 7.597 | 6.158 | 22292.05 | no: phase closure |
| DS26-0070 | 2 | 0.948 | 1.121 | 22171.79 | no: phase closure |
| DS26-0070 | 4 | 3.257 | 3.391 | 22132.91 | no: phase closure |

Smaller RF objective is better under the declared prior cell. These numbers separate in-sample frequency-fit gains from post-fit position error. For DS26-0070, the final phase change is 0.043–0.447 s at 1×, 0.081–0.091 s at 2×, and 0.308–0.326 s at 4×, all above 0.01 s. Every endpoint passes the original approximate/exact residual gates, mixture phase-interior test, and optimizer success; those passes do not override nonclosure.

All 2,659 active curved native IDs in DS26-0309 and all 2,023 in DS26-0070 are retained in every cell, with identical hashes across cells and arms. No published owner is lost or reassigned. The inherited full-graph membership routine proposes incidental previously unowned extensions (0309: zero at 1×/2×, 28 at 4×; 0070: 485 at 1×, 523 at 2×/4×). These proposed extensions never enter any fit, are not adopted, and do not count as new recovery evidence. `fully_qualified` here means the original RF/phase/solver/mixture checks plus preservation of all input IDs and incumbent owners; it does not mean a new production acceptance or identity validation.

The first experiment finished in 67 s and 75 s for the two case workers, each with BLAS=1; both ran concurrently. Five numerical tests check covariance scaling, cached-bank immutability, exact low-rank versus dense normalized Gaussian costs across all three scales, and the nonzero volume penalty for greater covariance even at zero residual. The separate actual-model invariant receipt verifies exact 1× replay, unchanged non-family features and receiver prior, and exact 4× scaling of only the selected three physical columns. The physical metadata describe original 1× scales; multiply SD values by the grid multiplier to recover each prior cell.

Artifacts: [comparison](comparison.png), [native family residuals](family-residuals.png), [CSV](candidate_fits.csv), [summary](summary.json), [protocol](protocol.json), and [actual-model invariant checks](model-invariant-checks.json). The dense `run_manifest.json` remains local and its hash is recorded in the publication manifest. Each scan directory contains the frozen start/ranking/native-ID inventory, all twelve cell JSONs across scans, all native predictions and feature matrices in compressed NPZ files, and completion timing. Native points retain original identity through each row's `tracks` inventory and its `plan.json`; NPZ arrays include masked-out native points with the explicit keep mask. The existing outlier investigation contains the broader polynomial/TLE/native context; this narrow sensitivity does not rerun catalogue or retrospective searches.

Reusable API in `prototype.py`: `configure(...)`; `select_family(d,z)` returns `(norad, ranked)`; `candidate_context(d,z,scale,family=None)` returns an ordinary engine context usable with `e.build` and `previous.fit`; `build_candidate(d,z,arm,reference,scale,family=None)` returns `(problem, context)`. The copied bank leaves cached physical mode arrays unmodified, so separate candidates are independent.

Reproduce from the worktree root:

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONPATH=src:tools:reports/2026_11_02_family_reliability/family
PY=/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python
$PY -m pytest reports/2026_11_02_family_reliability/family/test_prototype.py -q
$PY reports/2026_11_02_family_reliability/family/run.py DS26-0309
$PY reports/2026_11_02_family_reliability/family/run.py DS26-0070
$PY reports/2026_11_02_family_reliability/family/verify.py
$PY reports/2026_11_02_family_reliability/family/summarize.py
```

Existing completed fit cells are reused. Regeneration of figures uses saved numerical outputs. No results are promoted to production; publication of research artifacts is handled by the parent report.
