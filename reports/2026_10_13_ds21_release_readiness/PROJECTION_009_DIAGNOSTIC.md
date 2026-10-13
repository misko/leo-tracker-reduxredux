# DS21-009 calibration-seed projection failure

The first generic A/B/C initialization failed before any position fits. A bounded
replay identifies the failing seed as **Model B, CH1–8, `cold-0`**. The required
calibration projection reaches the solver's 200-iteration limit despite matching
the source correction to `5.1875e-12 Hz` RMS. This is a seed-projection numerical
failure, not an observed position-fit or accuracy failure.

The original failed `models-v1/DS21-009` attempt and its source archive remain
unchanged. Diagnostic implementation `97b1f8428` replays original A/B projections
in their original order, stopping at the first failure. It uses the same inputs,
matrix, scaling, bounds, exact least-squares solver, `tol=1e-11` and 200-iteration
limit. One additional identical solve exposes the termination certificate.

| Measurement | Result |
| --- | ---: |
| Original projections attempted | 19 |
| Original projections successful | 18; all Model A |
| Certificate solves | 1 |
| Total calibration projection calls | 20 |
| Position optimizer calls | 0 |
| Failing projection residual RMS | 5.187475690345124e-12 Hz |
| Maximum absolute residual | 1.8189894035458565e-11 Hz |
| Least-squares cost | 3.652433428553899e-20 |
| Reported scaled optimality | 0.00027053899214113446 |
| Iterations / status | 200 / 0, maximum iterations exceeded |
| Design dimensions | 2,780 windows × 25 columns |
| Reported active-bound coefficient indices | 21, 22 |

No reference or held observations were accessed. The diagnostic was bounded to
90 seconds internally, with external TERM/KILL limits of 105/110 seconds. It
completed normally and validated its source, original failure, parent inputs and
ordered call inventory. Eight owned tests cover ordering, stopping, exact solver
reconstruction, bounded failure, source binding and tamper rejection; Ruff passed.
Immutable hashes and the compact certificate are in
[PROJECTION_009_DIAGNOSTIC.json](PROJECTION_009_DIAGNOSTIC.json).

Model A's initial all-view calibration is overwritten before fitting, and its
initial high-view vector contributes only timing. Although those projections
are unnecessary, all 18 A projections succeeded here. Removing them alone would
not fix the observed failure.

The next implementation must verify a feasible physical seed directly or use a
numerically justified projection, while preserving calibration bounds and
physical correction closure. A new adapter and namespace will preserve v1;
failed solver status will not silently become a converged position fit. The
source of the solver's misleadingly large scaled optimality still needs analysis.
No revised initialization, final A/B/C fits or accuracy improvement is claimed
by this diagnostic. The full-DS21 0.5 km target remains unmet.
