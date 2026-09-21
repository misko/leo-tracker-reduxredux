# Formal fixed-identity orbit model: sealed matched replay

This report records the Stage B/C fixed-identity model before any parameter was
selected using receiver truth. The numerical core was frozen at SHA-256
`72fc9e255473ccf81b8a09168391e9066861bfc434389c6ffe288f39432f8b38`.
After the benchmark completed, formatting, unused imports, and an outdated
descriptive approximation label were cleaned up. The numerical AST is unchanged;
[the transition receipt](artifacts/2026_09_21_formal_orbit_model/source-transition.json)
and [executed source](artifacts/2026_09_21_formal_orbit_model/executed-formal-orbit.py.gz)
preserve that intermediate version. A subsequent optimizer-only correction
restarts a bound-collapsed noise simplex using the fit's own position and the
midpoint of the declared log-noise bounds. The objective and physical model
are unchanged. The saved fit's old first-order label is stale:
the executed calculation used quadratic phase states as described below.
The earlier `/tmp/leo-formal-orbit-full.json` experiment is invalid and
superseded: it mistakenly treated receiver-clock sensitivity states as orbit
phase states and used the wrong identity population. It was rejected before
ground-truth scoring.

## Sealed inputs and configuration

The corrected prepared archive is
[`phase-states.npz`](artifacts/2026_09_21_formal_orbit_model/phase-states.npz), SHA-256
`96128825f740a7d4054f85c513f5aea41c450cfaf8524608f4f239a232f60069`,
schema `formal-orbit-phase-state-v1`. Its provenance is fail-closed against the
committed strict inference and strict-reranking digests. It contains 21,702
observations, 622 episodes, and 446 fixed strict-causal NORAD identities. All
causal TLE ages are positive (3.287 to 96.170 hours). Catalogue epoch and first
collection time must both precede capture. Targets without phase-history data
retain their measured positive TLE age and use nominal predicted phase zero.

Orbit states were propagated at predicted phase and predicted phase plus/minus
one second with receiver clock fixed at zero. The correction prior is
`Normal(0, 0.09176615913014215²) s/hour`, learned on the sealed pretarget
history. The normalized likelihood uses Student-t residuals with four degrees
of freedom and fixed AR(1) settings `rho=0.65`, `tau=1 s`. Each fit learns its
own measurement scale only from its fitting observations under the frozen
`LogNormal(log(250 Hz), 1.5)` prior and 5--2000 Hz bounds. Segment offsets and
bounded satellite rates are profiled by iteratively relinearized, exact
per-source Schur solves. No held-out frequency or receiver truth enters fitting.

## Frozen matched result

The sealed output is [`fit.json`](artifacts/2026_09_21_formal_orbit_model/fit.json), SHA-256
`11a0ca800f8cdcc7d74ddd6dd409cfef35c4c92459d0488d93a80c37d804b7a3`.
Both the outer fit and inner nuisance iterations converged in 280 objective
evaluations. One phase rate reached its declared bound.

| Metric | Result |
|---|---:|
| East, north in declared region | -1527.193 km, -62.215 km |
| Estimated latitude, longitude | 37.8464327°, -122.4874192° |
| Training RMS | 82.25 Hz |
| Randomized held-out RMS | 86.59 Hz |
| Learned measurement scale | 45.32 Hz |
| Local conditional 95% major axis | 0.045 km |

The local ellipse is a finite-difference Laplace approximation to the profiled
posterior. It is conditional on fixed identities, fixed clock, the declared
correlation model, and the local mode. It is not a calibrated probability
region; simulation and independent-session coverage results govern that claim.

## Exact propagation check

The machine-readable audit is
[`exact-sgp4-verification.json`](artifacts/2026_09_21_formal_orbit_model/exact-sgp4-verification.json),
SHA-256 `8c964413dd198332ad3670e9b87e1ed433fad911143a6571010ee17731e6d208`.
It repropagates every episode with SGP4 at the fitted phase and compares it with
the quadratic phase-state approximation. Across 21,702 observations, the
difference is 0.00716 Hz RMS, 0.03493 Hz at the 99th percentile, and 0.10433 Hz
maximum. This passes the frozen 0.2 Hz maximum tolerance and is negligible
relative to the inferred 45.32 Hz measurement scale.

The external-start fit also passes the same exact check across all observations:
[verification output](artifacts/2026_09_21_formal_orbit_model/external-start-exact-verification.json).
The reusable `tools/verify_formal_orbit.py` command checks input hashes, causal
availability, identities, TLE ages, and coverage of every observation before
comparing the cached quadratic approximation with exact SGP4. Its component test
also verifies that a deliberately corrupted interpolation fails.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools \
uv run --no-project --with scipy --with sgp4 --with pydantic --with pyyaml \
  python tools/verify_formal_orbit.py \
  --states reports/artifacts/2026_09_21_formal_orbit_model/phase-states.npz \
  --fit reports/artifacts/2026_09_21_formal_orbit_model/external-start-fit.json \
  --prior reports/artifacts/2026_09_21_formal_orbit_model/prior-analysis.json \
  --reranking reports/2026_09_20_strict_causal_vs_retrospective/strict-reranking.json \
  --region '{"latitude_deg":39.7392,"longitude_deg":-104.9903,"width_km":14484.096,"height_km":14484.096}' \
  --output /tmp/formal-exact-verification.json
```

The archived prior analysis includes separately labelled retrospective diagnostics.
This fitter and verifier read only its causal target phase predictions; future
TLE fields do not select parameters or contribute to predictions.

## Evaluator-only truth score

The corrected optimizer also recovered the same solution from the external
Denver-centered start `[0, 0]`, without a parent-fit initial position. Its
[sealed output](artifacts/2026_09_21_formal_orbit_model/external-start-fit.json)
has negative log posterior 67134.52201, noise scale 45.31757 Hz, randomized
held-out RMS 86.58587 Hz, and one noise-bound restart. A regression test first
reproduced the original false convergence at 2000 Hz and then passed after the
restart fix. The paired subset report retains that failed optimizer version.

After inference and the exact-propagation check were sealed, the evaluator used
the known coordinate 37.84903264307456°, -122.4856541910174°. The corrected
estimate has 328.0 m horizontal error. This is a matched local replay, not an
independent accuracy guarantee. For context on the same research cohort, the
published strict-causal baseline was approximately 4,859 m and the earlier
exploratory fixed-identity orbital result was approximately 275 m. Those values
are comparisons, not tuning targets; the formal model's slightly larger point
error and slightly higher held-out RMS than the exploratory model are retained.

| Model | Position error | Randomized held-out RMS |
|---|---:|---:|
| Strict causal baseline, fixed UTC | approximately 4,859 m | 157.09 Hz |
| Earlier exploratory orbit correction | approximately 275 m | 78.63 Hz |
| Formal fixed-identity model | 328.0 m | 86.59 Hz |

This sealed archived replay has sub-kilometre error; operational performance
has not been established. The 45 m nominal 95% major semiaxis misses the truth.
Claims about median, 95th-percentile error, or calibrated uncertainty remain
pending the prespecified simulations, subset matrix, and independent sessions.
