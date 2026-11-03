# Joint recovery of the three original trajectories

This is a research progress snapshot for `fast8-auto-20261016-161535-99008d35-1-lower`. The goal remains open. No production model has changed.

## Joint-model result

The new frequency term is now fitted jointly with position, receiver calibration, satellite timing, common clocks and detection probabilities. One temporal half of each original trajectory is available for fitting; the other half is excluded from the objective. The starting background calibration excludes all 129 target points, but still inherits the original full-scan candidate bank, high-band contrast and saved initialization. The cold-start controls below address that remaining conditioning.

| Fitted-`c` experiment | Early CH2 withheld RMS | CH4 withheld RMS | Late CH2 withheld RMS | Late CH2 assigned to proposed satellite |
| --- | ---: | ---: | ---: | ---: |
| Early → late, no band term | 133.81 Hz | 155.79 Hz | 2,892.99 Hz | 0/13 |
| Early → late, learned band term | 134.08 Hz | 157.33 Hz | 126.01 Hz | 13/13 |
| Late → early, no band term | 97.58 Hz | 119.93 Hz | 2,509.79 Hz | 0/14 |
| Late → early, learned band term | 97.97 Hz | 121.22 Hz | 179.52 Hz | 14/14 |

These are frequency residuals on all withheld target points, including any that remain unassociated. They are not geographical position errors. Across both disjoint test folds, the band-term models assign 29/29 early CH2, 72/73 CH4 and 27/27 late CH2 points to the proposed satellite. The remaining CH4 point is left as clutter; no assignment is forced. The earlier CH4 crossing at 70.396 s is assigned to the coherent candidate by the fitted model.

![Held-point frequency-residual distributions](01_joint_frequency_cdfs.png)

## How the rule is selected

The preceding generic search tests all 1,035 regional candidates using training measurements only. Its candidate identities are outputs, not code branches. For each accepted proposal:

1. If the candidate has at least ten background upper-band associations spanning at least ten seconds, preserve that timing evidence and introduce one lower-band frequency basis.
2. Otherwise use the coherent training trajectory to initialize the candidate's shared timing.

The background model gives three upper-band associations for each of the first two candidates and 58 for the late-CH2 candidate. The common rule therefore selects shared timing initialization for the first two and a lower-band frequency term for the third. The term applies to all CH1–4 observations of its candidate across both receivers and throughout the scan, rather than to a hand-selected time interval.

The frequency basis is the orbital Doppler time derivative evaluated at a fixed training reference. A jointly estimated coefficient multiplies this basis. Its prior standard deviation is 0.5 seconds, its bound is ±2 seconds, and its fitted values are −0.954 and −0.970 seconds in the two folds. These units do not establish a recording-clock error. Observation timestamps are unchanged; the frozen-basis convention is included in the derivatives.

## Surrounding-scan checks

The same candidate's upper-band associations increase from 58 without the term to 59 with it in both fitted-`c` folds. Background associations, excluding every original target point, increase from 2,493 to 2,512 and from 2,488 to 2,513. Applying the fitted models to the same 4,797 observations gives 2,594 → 2,639 and 2,590 → 2,642 associations. Those whole-scan totals mix training and withheld observations; the target table above is the held-out comparison.

![Association counts and calibration control](02_joint_coverage_and_controls.png)

This does not establish an improvement over the earlier hand-selected 2,666-association fit, which used different fitting information and initialization. It demonstrates a controlled contribution of the automatically chosen band term within this joint experiment.

## Numerical and calibration controls

All eight combinations of temporal fold, band-term availability, and zero versus fitted RF-dependent coefficient `c` pass the independent feasibility, strict stationarity and replay audit after at most two matched 60-second solver / 65-second total / 5,000-objective allowances. The extra allowance was applied to both arms. First-attempt nonconverged zero-`c` results remain in the evidence rather than being silently replaced.

The band term also recovers all 27 withheld late-CH2 points with `c = 0`; without it, neither zero-`c` fold recovers them. The fitted-`c` arm has better training NLL in these runs, but withheld NLL and point residuals do not uniformly favor it. This is not evidence of superior position accuracy for either arm.

Physical, clock, detectability and new band-coefficient gradients are checked against central differences. A common-timing finite-difference step sweep is retained: near one converged endpoint, the original 10-microsecond stencil gave a discrepancy; a 3-microsecond stencil agreed within 0.000012 in absolute gradient. The numerical tolerance was not relaxed. Arbitrarily perturbing every withheld measurement leaves the training objective and both gradient blocks exactly unchanged.

## Cold-start diagnostic: conditioning is material

A separate 329-second pipeline run removes the whole 129 target probe groups before discovery, candidate selection, calibration and initialization. The original public export is untouched; the derived input has a separately recorded hash. This is a deliberately strong background-only diagnostic: it also removes the target training halves.

That pipeline selects a different local position/calibration solution, with 61 selected background candidates. At that frozen solution, the same per-track search fails to recover the previous identities reliably: the early CH2 top candidate is 66154 with 1.88–2.17 kHz withheld RMS; CH4 selects 62052 with 418–503 Hz; late CH2 selects different candidates in the two directions and yields 3.12–4.64 kHz. The earlier candidate identities are not ground-truth labels, but these poor transfer errors show that the background-only result does not qualify as an independent recovery.

The cold calibration is transported to original observation metadata with an explicit frequency-closure check; the failure cannot be dismissed as a centering or receiver-offset transport error.

Two further cold pipelines have been launched with the appropriate train/test design: retain the declared training half from the outset and remove only the 63 or 66 withheld probe groups before every discovery stage. Each is bounded to 480 seconds. Their results and subsequent recovery tests are pending at this snapshot. This distinction matters because the long target arcs carry geometry information even when the original final model leaves their points unassociated.

## Remaining work and reproducibility limits

Finish the fresh training-fold pipeline controls and test the same learned mechanism using their own calibration, candidate bank and initialization. If source selection still fails, use training-only coherent-track evidence to compare alternative discovery basins rather than selecting a favorable basin with test measurements. Do not interpret the new frequency term as a physical clock measurement, or its fit gain as improved localization, without independent evidence.

The adjacent manifest binds result JSONs, source code and figures. The research adapter imports only analysis modules and changes no persisted runtime contract. Scripts currently require the recorded public export, pinned deployed analysis package, TLE archive and diagnostic checkpoint paths documented in their source. A self-contained checkpoint restoration/replay entrypoint is still required before declaring reproducibility complete.
