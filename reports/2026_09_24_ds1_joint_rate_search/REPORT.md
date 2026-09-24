# DS1 joint cache-rate geographic screening prototype

## Result

The rate-aware surrogate can change geographic selection before exact SGP4
refinement.  In the sealed `20260921_16` singleton basin, nominal cached
screening selected the `(east, north) = (+2, -2)` km point while the joint
rate score selected `(+2, +2)` km.  Both results use the same 3x3, 2-km-spaced
RF-only basin around an already sealed finalist.  This is evidence that the
per-NORAD causal phase rate is no longer only a finalist nuisance.

The prototype is deliberately not a DS1-wide replacement: it validates the
objective and its cache/exact agreement on two representative sealed singleton
finalists.  It does not make a claim about a global prior search or post-seal
position error.

## Objective, fixed before the run

At every location and global `tau`, the cache is read through the existing
full-observation engine.  Every qualified track reacquires a hard candidate
from the full causal STARLINK catalogue.  For a selected candidate and
observation `i`, its local rate feature is

```text
d_i = [D_cache(tau + 1 s) - D_cache(tau - 1 s)] / 2 s
phase_i = causal_TLE_age_h(source_i) * rate_source_i
y_i ~= D_cache(tau)_i + d_i * phase_i + CFO_track_i
```

`CFO_track` is profiled analytically.  Each NORAD has one rate, bounded to
`[-0.25, +0.25] s/h`, with the historical Normal(0, 0.0917661591 s/h) prior.
The profile optimizer uses a smooth robust residual objective plus the prior;
the geographic selection score is the full-observation capped loss plus
`0.001 * 0.5 * sum((rate / sigma)^2)`.  If that score exceeds the zero-rate
score, the prototype retains zero rates.

The script can reacquire once after a fit with `--reassign-once`.  This run
used the more conservative single hard association, so the location comparison
does not depend on a rate-driven identity loop.

The cache-time derivative advances Earth rotation together with the orbital
state.  It is therefore only a screening approximation.  Exact auditing uses
the existing receipt-bound SGP4 phase nodes, which hold Earth rotation fixed at
receive time plus `tau`.

## Sealed finalist audit

| Causal cache / singleton finalist | nominal selected offset km | joint selected offset km | joint score | surrogate capped loss | exact capped loss | absolute loss error | cache screen s/point | exact s | exact/cache ratio | exact max Doppler discrepancy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `20260921_00` / Sacramento | (-2, -2) | (-2, -2) | 0.096820 | 0.082453 | 0.082395 | 0.000058 | 1.483 | 13.401 | 9.04x | 0.0000224 Hz |
| `20260921_16` / Sacramento | (+2, -2) | (+2, +2) | 0.085977 | 0.081242 | 0.081004 | 0.000238 | 1.344 | 9.410 | 7.00x | 0.0000194 Hz |

Both exact winner gates passed the established 0.2-Hz maximum-Doppler
tolerance.  The bounded cache screen therefore costs about one seventh to one
ninth of an exact rate fit per geographic point while keeping the capped-loss
error below 2.4e-4 on these supports.

## Causality and scope

`results.json` binds the two source inference artifacts, the shared runner,
the exact orbit helper, and receipt-bound causal caches.  It contains no
reference coordinate or observation mask; each input artifact declares
`reference_used_for_fit: false`, and all qualified observations are used.  No
reference truth enters candidate association, rate fitting, score selection,
or exact replay.

## Reproduction

```bash
.venv/bin/python -m pytest -q reports/2026_09_24_ds1_joint_rate_search/test_joint_rate_search.py
.venv/bin/python reports/2026_09_24_ds1_joint_rate_search/joint_rate_search.py \
  --sealed-finalist reports/2026_09_24_ds1_train_full/artifacts/one-hour/causal_per_norad_orbit_rate/one-hour--train-20260921_00--first-singleton--sacramento--causal_per_norad_orbit_rate.json \
  --sealed-finalist reports/2026_09_24_ds1_train_full/artifacts/one-hour/causal_per_norad_orbit_rate/one-hour--train-20260921_16--first-singleton--sacramento--causal_per_norad_orbit_rate.json \
  --spacing-km 2 \
  --output reports/2026_09_24_ds1_joint_rate_search/results.json
```
