# Why scan-fw-ac11ac00c0676d1b failed

The controlled replay reduces position error from **55.685 to 1.031 km with
fitted-c**, and **53.945 to 1.927 km with c=0**. The ordinary baseline replay
reproduces the published errors. Both recovered final fits satisfy the unchanged
independent convergence test, and the restored region wins by the existing
model-score selection rule. Reference coordinates were used only afterward to
measure these errors.

The confirmed failure chain begins before final fitting: a useful ordinary
search region was discarded during calibration, and recovery eligibility omitted
its fine-grid location. The final joint fit then converged in another region.
Preserving and numerically qualifying that region removes most of this scan's
error. The remaining 1–2 km error is not explained by this investigation, and
this consumed single-scan diagnostic does not establish a general improvement.

| Arm | Published / replayed baseline | Restored-region B7 | Final stationarity |
|---|---:|---:|---:|
| Fitted-c | 55.685 km | 1.031 km | 0.000130 |
| c=0 | 53.945 km | 1.927 km | 0.000537 |

The final stationarity requirement remains 0.001. Production B7 and the scan's
published result have not been changed by these research replays.

![Controlled replay: position, support and frequency fit](../2026_10_09_position_error_iter98/comparison.png)

The recovered regional fitted-c estimate is initially still 40.6 km wrong.
The existing B7 sequence then reduces error to 15.6 km after timing pruning and
0.826 km after its relaxed clock-prior stage, finishing at 1.031 km. Thus the
repair restores a useful position/calibration hypothesis that the existing
downstream model can refine; it does not inject the true position. We retain
the normal final B7 result rather than choosing the earlier stage with the
smallest reference error.

## Evidence in the published pipeline

![Position error and evidence through the B7 stages](../2026_10_09_position_error_iter93/stage-audit.png)

1. The search sampled 400 points. Its lowest-score retained ordinary region,
   `point:-47.5:-62.5`, had score 40696.314623 and 5 km grid spacing. Selection of
   this diagnostic region uses the search score, not the known receiver position.
2. Calibration failed for that region in all three regional separation passes.
   The stored coarse state had stationarity 0.001535 against a 0.001 requirement.
3. The existing bounded recovery eligibility covers failed initial 40 km grid
   points. This failed retained 5 km point was ineligible. It never reached
   association and final region comparison.
4. Both published arms instead came from `point:-72.5:-137.5`. B3 was already
   59.468 km wrong fitted-c and 57.806 km wrong c=0. All subsequent B7 stages
   qualified near the wrong regional solution.
5. Timing pruning removed 25 of 41 satellites, but position error improved at
   that step. The evidence does not establish pruning as the cause of worse
   accuracy. Later frequency flexibility made only small position changes.

The final fitted-c stationarity is 0.0000119; c=0 is 0.000234. Extending those
final fits solely because the answer is geographically wrong is not supported
by their convergence diagnostics.

## Controlled calibration tests

| Test | Outcome | What it establishes |
|---|---|---|
| Replay ordinary prefit with legacy and bounded solvers | Both stop almost immediately above the unchanged stationarity gate | Larger budgets did not help these replay starts; solvers stopped before budget |
| Reset timing terms to zero | Qualified, but objective about 7,278 worse | A qualified alternative can be a much poorer model fit |
| Strict score-decreasing scalar polish | No accepted step | Objective comparisons limit this tiny correction |
| Curvature polish with a fixed numerical score allowance | Stationarity 0.001535 → 0.000845 in six evaluations | First prefit qualification recovered without relaxing the gate |
| Continue the corrected calibration | Optimizer reports success; independent stationarity 0.016401 | A second calibration state still blocks downstream testing |
| Apply the same scalar polish to that state | All Newton corrections violate a coupled timing constraint | Scalar coordinate correction is inadequate at this boundary |
| Move in the feasible tangent direction | Stationarity 0.016401 → 0.002408; still fails 0.001 | Coupled motion helps, but scalar curvature is insufficient in this test |
| Solve the reduced joint curvature system | Stationarity 0.002408 → 0.000000207 in 46 evaluations | Corrected calibration qualifies with unchanged constraints and gate |
| Continue association, both regional arms and B7 | Restored region wins; 1.031 / 1.927 km | Region loss explains the dominant position failure in this scan |

The successful prefit correction changed a relative timing **basis coefficient**
by approximately 16 ns. Its objective changed by six floating-point increments
at a score near 40,696, within the predeclared fixed 128-increment allowance.
This is numerical cleanup at a fixed hypothesis position. It is not evidence
of a physical receiver-clock correction or position improvement.

![Prefit qualification recovery](../2026_10_09_position_error_iter96/qualification.png)

The corrected postfit is a different objective because receiver calibration
has been applied. Its score must not be compared directly with the prefit score
as a same-model improvement. The latest failed scalar polish changed neither
its parameters nor its score. A subsequent constraint-preserving tangent
correction accepted four steps and slightly lowered the objective, but did not
qualify. Its remaining trial steps lower the objective while increasing the
largest stationarity residual. The subsequent joint curvature correction solved
the coupled residual in one accepted Newton round. Its reduced Hessian was
positive definite; no ridge or acceptance-threshold relaxation was introduced.

## Interpretation and limits

There are two confirmed implementation weaknesses: recovery eligibility omits
failed fine-grid retained regions, and numerical optimizer success can still
leave calibration outside the independent acceptance gate. The latter correctly
prevents unqualified fits from being treated as converged, but currently causes
the entire region to be lost. The final optimizer's local convergence does not
establish global regional correctness.

The causal replay qualified the ordinary calibration, ran association and
matched c=0/fitted-c finals, retained the original operational candidates, and
selected by the unchanged score rule. Both arms selected the recovered region.
It then passed through unchanged B7 stages to the results above. No repaired
research result has been substituted into production.

This motivates a general, bounded recovery for **failed retained regions at
every grid level**, with constraint-aware numerical qualification and original
candidate preservation. It does not justify dropping the convergence check,
selecting by known position error, changing the satellite bank using ground
truth, or adding more final-fit time to already-converged wrong-region fits.
The generalized recovery still needs matched dataset evaluation and independent
validation before any deployment recommendation.

This scan is newer-cohort member 051 and is now consumed development data.
Reference receiver coordinates remain evaluation-only. No truth-guided seeds,
satellite bank, region selection, new RF collection or production changes were
used. Reserved recordings remain closed.

## Reproducible evidence

- [Original checkpoint/calibration path](../2026_10_09_position_error_iter93/CALIBRATION_PATH.md)
- [Per-stage position and support audit](../2026_10_09_position_error_iter93/STAGE_AUDIT.md)
- [Four prefit replays](../2026_10_09_position_error_iter93/PREFIT_RESULTS.md)
- [Precision and curvature diagnostic](../2026_10_09_position_error_iter94/CURVATURE.md)
- [Qualified prefit correction](../2026_10_09_position_error_iter96/RESULTS.md)
- [Downstream calibration failure](../2026_10_09_position_error_iter95/RESULTS.md)
- [Unchanged scalar polish results](../2026_10_09_position_error_iter97/RESULTS.md)
  and [raw receipt](../2026_10_09_position_error_iter97/result.json)
- [Exact timing constraint and valid KKT projection](../2026_10_09_position_error_iter97/CONSTRAINT_AUDIT.md)
- [Tangent correction protocol](../2026_10_09_position_error_iter99/README.md)
  and [raw receipt](../2026_10_09_position_error_iter99/result.json)
- [Successful joint curvature correction](../2026_10_09_position_error_iter100/RESULTS.md)
- [Matched downstream results and plots](../2026_10_09_position_error_iter98/RESULTS.md)
  and [complete result](../2026_10_09_position_error_iter98/result.json)

Research protocols and receipts are append-only. Each negative attempt remains
visible. Iteration 96 was frozen in a local commit before execution; a concurrent
remote update delayed its remote publication until after the run. Iterations 95
and 97 were published before execution.
