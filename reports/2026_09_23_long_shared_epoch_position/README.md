# Conditional fixed-identity shared epoch fit

Shared per-scan epoch corrections improve the fixed-identity TRAIN objective and
complementary-row residuals, but the best reported position remains 5.1–5.8 km
from the reference. This does not establish sub-300 m positioning and should not
be promoted to validation.

| View | Prior | Scale | Train capped RMS | Reserved capped RMS | Error |
|---|---|---:|---:|---:|---:|
| 6 | Sacramento | 0.2 s | 279.08 Hz | 304.83 Hz | 9.435 km |
| 6 | Sacramento | 1.0 s | 276.78 Hz | 302.69 Hz | 6.400 km |
| 6 | Sacramento | 5.0 s | 276.60 Hz | 302.27 Hz | 5.091 km |
| 6 | Reno | 0.2 s | 279.09 Hz | 304.83 Hz | 9.439 km |
| 6 | Reno | 1.0 s | 276.78 Hz | 302.69 Hz | 6.400 km |
| 6 | Reno | 5.0 s | 276.60 Hz | 302.26 Hz | 5.090 km |
| 16 | Sacramento | 0.2 s | 300.29 Hz | 326.78 Hz | 9.301 km |
| 16 | Sacramento | 1.0 s | 296.72 Hz | 322.09 Hz | 6.678 km |
| 16 | Sacramento | 5.0 s | 296.66 Hz | 322.04 Hz | 5.782 km |
| 16 | Reno | 0.2 s | 300.35 Hz | 327.40 Hz | 9.296 km |
| 16 | Reno | 1.0 s | 296.81 Hz | 322.77 Hz | 6.654 km |
| 16 | Reno | 5.0 s | 296.75 Hz | 322.72 Hz | 5.754 km |

The scales are Gaussian-shaped regularization settings, not calibrated clock
uncertainties. Each scale excursion costs one 800 Hz one-second unmatched-track
penalty. All scales and both priors are reported; geographic error did not select
one. The tau-zero baselines are 283.56 Hz for six scans and 308.37 Hz for sixteen,
so timing flexibility lowers both training and reserved residuals.

No fitted candidate falls below the exact horizon and no tau reaches ±5 s.
Across arms, fitted taus range from −1.50 to +0.96 s. These shifts greatly exceed
the tight host brackets observed in the separately qualified six-recording older
sample, but equivalent timing-authority coverage was not established for every
scan used here. The fitted shifts can absorb orbit, association, track-shape, or
other model mismatch; they are not calibrated clock estimates.

The first bounded Powell pass exhausted its 300-call budget in ten of twelve
arms and is preserved in `results_superseded_powell300`. Before inspecting
reference outcomes, every arm was predeclared for an identical bounded L-BFGS-B
polish. Ten of twelve polish runs report convergence. The 6-scan Reno 0.2-second
arm's polish stopped on its line search, but its preceding Powell fit converged.
Thus eleven arms converged in at least one stage. The 6-scan Sacramento 5-second
arm reports no optimizer success flag, while its Reno counterpart converged to
the same objective and position basin. Results retain the best training
penalized point among the baseline, Powell, and polish candidates; an absent
success flag must not be interpreted as a converged model result.

This experiment is explicitly conditional on the identities chosen by the
sealed blind tau-zero baseline. It is not full blind reassociation. It also
depends on capped-loss/prior scaling, one-second state interpolation, altitude
zero, regional candidate filtering, and local optimization. Complementary rows
and the reference coordinate were evaluated only after inference was sealed.

![Shared epoch results](shared_epoch_results.png)

Inference took 155.1 seconds after materializing each compressed cache once.
No long validation/test or prospective evidence, deployment, or RF collection
was accessed.

Reproduce from the repository root with the already exported frozen TRAIN
caches:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python reports/2026_09_23_long_shared_epoch_position/fit.py \
  --manifest reports/2026_09_23_long_inventory_complete/manifest.json \
  --cache-root /tmp/leo-long-training-cache-first16 \
  --baseline reports/2026_09_23_long_training_search_multi/results/results.json \
  --single-tool reports/2026_09_23_long_training_search/search.py \
  --output /tmp/long-shared-epoch-reproduction
```

The accepted source SHA-256 is
`59ed44803e6785e8df1e1b2521127633f5fc60f750e58f6f97f31e9c658ae331`.
The sealed inference and post-seal results are respectively
`fe7787d92c9ec6bb241f67992085795dd28a440b3b988b7d5cb6aabb3cb354d0`
and `edbae6d7908f60222949f9613e53f861bd54ccbc2faf689aaf49e75f40123ab6`.
The inference's embedded source binding and `inference.sha256` both match these
files; `results.sha256` matches the post-seal result.
