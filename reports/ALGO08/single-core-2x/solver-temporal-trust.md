# Local time interpolation for regional trust steps

On DS30-0374, the temporal trust proposal saved **26 ms** inside the affected optimizers. It attempted 120 short derivative probes but replayed the stock optimizer on **32 of 60** fits. Full likelihood evaluations rose from 463 to 484. The northern wrong-region simulation saved 339 ms inside the affected optimizers. Both inputs reproduced the selected positions, all published owners and every grid value. The small physical saving leaves this variant out of the integrated candidate.

## Optimizer boundary

The instrumented stock DS30-0374 replay spent 8.76 seconds inside 90 bounded secant invocations. The full phase-geometry function used 1.78 profiled seconds across all of its callers. A faster orbital projection by itself can save only part of the repeated optimizer cost. The earlier affine geometry experiment held weights fixed across a diagnostic grid. It measured neither robust move acceptance nor changes in the selected fit. [Earlier cost breakdown](cost-checks.md) · [Affine diagnostic](solver-affine.md)

The first secant direction in a qualifying fit uses two trial derivatives of the conditional Doppler model. The computation evaluates the current orbit bank and phase tangent at up to three observation times per 20-second bin, using the existing quadratic time interpolation from broad association. It interpolates the geographic differences back to every observed row. Using the original full-data design, fixed posterior noise and coefficient precisions, and the interpolated frequency derivatives, it factors a Gaussian normal matrix to profile the receiver and orbital nuisance response. The surrogate holds the covariance volume and Gamma penalties fixed. It includes elevation derivatives for observations already below the horizon. [Timing kernel](../../../tools/pipeline_eval/variants/algo08_temporal_trust.py) · [Time-moment association](solver-track-moments.md)

Only the first two derivative probes of the stock optimizer receive the resulting tangent. Every proposed move must improve the exact robust objective. Subsequent finite-difference refreshes use the full likelihood, and an initial tangent that yields no accepted move replays the stock optimizer at the same point. The same rule applies in both calibration arms. Eligible fits have the original normal likelihood, at least 256 active rows and a geometry layout that needs no more than 60% of the original timestamps. The history, predictive and event likelihoods use the original optimizer. The released masks, phase refresh budget, station-independent gates and exact selected evidence/grid remain in use. [Component tests](../../../tests/pipeline_eval/test_algo08_temporal_trust.py)

## Matched saved-input trials

Each pair used identical verified saved detector bytes, TLE archive and offered region with existing causal reuse and coarse salvage statistics. One low-priority CPU and one numerical thread ran each process under the shared Gauss lock. North far ran the temporal method first and DS30-0374 ran the control first. The run boundary includes selected packet and grid construction. [Trial runner](solver_temporal_trust_trial.py)

| Saved input | Eligible fits, control / temporal | Full objective evaluations, control → temporal | Surrogate probes / stock replays | Eligible optimizer CPU s | Complete solve and grid CPU s | Complete solve and grid elapsed s |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0374 | 60 / 60 | 463 → 484 | 120 / 32 | 4.167 → 4.141 | 29.685 → 29.210 | 31.444 → 30.684 |
| North far | 25 / 25 | 314 → 285 | 50 / 5 | 1.206 → 0.867 | 11.437 → 11.084 | 11.619 → 11.309 |

The surrogate built 60 physical tangents from 28,980 geometry nodes representing 175,080 original row positions across the fixed layouts. Tangent assembly including the Gaussian factorization took 0.201 CPU seconds. The count of exact evaluations increased by 21 across the targeted fits. The 0.475-second complete physical difference substantially exceeds the 0.026-second difference in the changed stage. Each value is from one run per mode.

DS30-0374 retained the same seven selected salvage supports, aliases, satellites and coarse phase choices. The preliminary salvage scores shifted by up to 0.070 score units. Each final owner map matched. The selected packet reported zero endpoint objective replay discrepancy in both arms. The exact optimizer path and 179-point grid matched after excluding grid elapsed time. North far likewise reproduced the final owner maps, the cavity offer, optimizer path and 137-point grid. Both positions were false fixes at the offer boundary.

| Saved input and calibration arm | Position in both runs | Horizontal error (km) | Solver RF RMS (Hz) | Owners |
|---|---|---:|---:|---:|
| DS30-0374, `c = 0` | 37.849625, −122.464635 | 1.855 | 101.536 | 2,905 |
| DS30-0374, fitted `c` | 37.850682, −122.463809 | 1.935 | 101.520 | 2,905 |
| North far, `c = 0` | 47.785644, 16.798538 | 52.455 | 37.951 | 228 |
| North far, fitted `c` | 47.753706, 16.798538 | 52.491 | 37.533 | 228 |

The physical and simulated scoring references are supplied after inference. [Physical reference](../location-audit/README.md) · [Simulated errors](../regional-release/blind-scores.csv)

## Reproduce

Use the release runtime and saved detections identified by the earlier track-moment comparison. Supply the same detection SHA-256, archive and offer in each mode. The runner records full owner maps and grid data. [Saved detection digests](solver-track-moments.md#reproduce)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
for mode in control temporal; do
  flock /tmp/leo-algo08v2-2x-bench/gauss.lock \
    nice -n 15 ionice -c 2 -n 7 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -B \
    reports/ALGO08/single-core-2x/solver_temporal_trust_trial.py \
    "$mode" "$saved_detections" "$tle_archive" "$release/assets" "$offer" "$detector_digest"
done
```
