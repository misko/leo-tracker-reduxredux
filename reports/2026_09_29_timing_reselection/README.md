# One timing re-selection round recovers the known N24 solutions

Training-only timing re-selection followed by the unchanged joint optimizer
recovers the existing N24 solution from the best qualified distant-start
endpoint in all three datasets. The recovered positions agree within 3 mm
numerically and training scores within 1.27e−8 log units. The original N24
endpoints require no timing changes.

This is an optimization improvement inside the existing candidate banks,
not a new geographic accuracy result or millimetre positioning precision.

| Dataset | Initial distant-fit score deficit | Timings changed / 24 | Gain from timing reset before refit | Final score difference | Position difference from N24 |
|---|---:|---:|---:|---:|---:|
| DS7 | 67.658 | 1 | +53.836 | −1.27e−8 | 0.00180 m |
| DS8 | 199.363 | 1 | +195.866 | −7.28e−10 | 0.00189 m |
| DS9 | 96.815 | 2 | +81.459 | +9.90e−9 | 0.00295 m |

The initial point per dataset is the highest-training-score qualified endpoint
among the four ±8-km corner starts from the
[wide-start audit](../2026_09_29_wide_start_audit/README.md). It is selected by
training likelihood, not reference error or target prediction. This test covers
that four-start-and-select procedure; it does not show that every inferior
corner endpoint can be recovered with one round.

## Fixed monotonic initialization step

The [protocol](PROTOCOL.md) precedes execution. At each converged geographic
point, recompute every scan's 41-node training timing curve. Compare its best
grid score to the score at the existing continuous timing value. Replace timing
only when training score increases by more than 1e−7. Including the current
value prevents loss from snapping a continuous optimum onto the grid.

After this one fixed round, jointly refit geography and all recording times
with the original optimizer and qualification gates. No repeated rounds,
reference tuning or failed-run retries occur. The geographic position is fixed
during timing selection and becomes free again only for the joint refit.

| Dataset / changed scan | Old timing | Selected grid timing |
|---|---:|---:|
| DS7 / scan-fw-4b7be407428889a5 | −0.644293 s | −1.50 s |
| DS8 / scan-fw-4cde9b2367652c52 | +0.798844 s | −0.50 s |
| DS9 / scan-fw-7b332587ba122e45 | +0.582590 s | −0.75 s |
| DS9 / scan-fw-abcaab3178200871 | −2.848977 s | −1.75 s |

These are phenomenological model timing offsets, not measured hardware latency
or physical UTC corrections. Following joint refitting, every timing parameter
matches the original N24 endpoint within 4.74 microseconds numerically. This
numerical agreement does not establish microsecond clock accuracy.

## Verification and claim boundary

All three refits qualify. Maximum gradient-audit discrepancy is 8.21e−6.
Training-grid/scalar scores and the sum of individual timing gains replay the
joint source score within 1e−7. Two tests verify preservation of the current
continuous optimum on ties and switching only on a training-score increase.
Source bindings and Ruff pass. All workers exit zero in 37–43 seconds, under
300-second caps.

The original N24 arm has zero changed timings in all datasets. No endpoint
improves the original N24 score by the frozen 1e−6 threshold, so the known
baseline is retained and its excluded-scan computation is not repeated. Tiny
floating-point differences may change the recorded numerical maximum label;
they do not trigger model promotion or a new predictive claim.

## Consequence for the method

The earlier distant-start failure was recoverable by rechecking timing after
geography moved. Initial timing choices at a remote geographic start can leave
the joint optimizer in a lower local mode even after geography moves close to
the known solution. Local gradient qualification alone does not detect this.

Retain this single timing re-selection pass as a useful research optimizer
step. A broader assessment should test the same frozen procedure on other
scan sets before production integration. It does not remove the site-conditioned
candidate bank, prove global optimization, or fix model discrepancy across time.
No new absolute sub-km validation follows from reproducing the existing fit.

See [summary](summary.json), [runner](run.py), source checkpoints and process
receipts. No RF collection, production changes or publication occurred.
Artifacts are local. Reproduce with `batch.py prepare`, `batch.py run` and
the recorded summary calculation in a fresh output context under NumPy/SciPy.
