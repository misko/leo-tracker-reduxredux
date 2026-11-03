# Alternating calibrated search does not qualify

The bounded alternating method accepts10/12development scans. DS10-F028 and
DS11-F018 reach the25-second internal refinement limit after7and5continuous
fits respectively. They remain failures, without accepted geographic scores;
no continuation or retry was used.

Among the same10accepted scans, results are:

| Method | Median error (m) | p90 error (m) |
|---|---:|---:|
| Original all-data baseline | 1,892 | 3,109 |
| Calibrated fixed assignments | 2,213 | 3,658 |
| Calibrated alternating assignments | 2,164 | 3,577 |

These are conditional quantiles, not a12-scan success claim. Counts against all
12planned scans are3/12within1km and7/12within3km. The acceptance loss and worse
paired accuracy than the original baseline rule out promotion to64scans.

Every round refits continuous state, then evaluates each track's best alternative
excluding its incumbent using the complete calibrated objective. It accepts the
greatest positive change, profiles unused epoch priors exactly, and repeats for
at most12rounds under one25-second deadline (30-second external process cap).
All runs start fresh from the sealed calibrated fixed-assignment parents. The
same uniform Sacramento support,100ftMSLheight, frozen excluded-dataset frequency
calibration and original shared nuisance priors are preserved.

All12controls and10successful candidates pass input/source checks, objective
reproduction, scalar finite-difference gradient and scaled-stationarity checks.
For each successful candidate, the evaluator independently reconstructs every
final-round best-training alternative and recomputes its full scalar objective.
It verifies complete membership of this proposal set and absence of a positive
tested change. This does not establish stability against every catalogue
assignment, coordinated changes or other geographic modes.

Median warm runtime across all12candidate attempts is11.82seconds, maximum25.17;
median CPU is11.76seconds. These exclude cold acquisition, preprocessing and the
parent calibrated fit. Neither a cold90-second result nor new geographic
uncertainty calibration is established. No RF or held-out recording evaluation.

## Measured next optimization

At the two sealed failed endpoints, a separate read-only profile tests92single
track alternatives without fitting or geographic scoring. Median construction
cost is13.33ms, vectorized scoring7.04ms, and independent scalar scoring24.78ms.
Construction accounts for56.4%of total construction-plus-vectorized-score cost.
Scalar/vectorized objectives agree within3.77e-12. The profile excludes catalogue
scoring and continuous optimization and is not a full runtime decomposition.

The current constructor rebuilds every prediction slot for each single-track
change. Next, evaluate an exact local replacement of the changed track's terms
while reusing unchanged predictions and candidate-group sums. Verify it against
the existing scalar objective, including clutter transitions, shared satellite
epochs and unused-prior profiling, before rerunning any fits. This targets a
measured cost; it promises no geographic gain. Preserve existing failures, do
not simply extend their deadlines, and retain the original64baseline.

Evidence: `calibrated-alternating-v1-evaluation.json`,
`calibrated-proposal-profile-v1.json`, their source freezes/receipts and SHA256
sidecars. Existing exposed development scans and unsurveyed operator reference;
no independent-recording or calibrated absolute-accuracy claim.
