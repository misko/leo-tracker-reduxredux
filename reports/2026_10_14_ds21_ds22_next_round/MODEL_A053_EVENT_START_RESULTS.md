# A053 two-sided visibility-event starts

Three of six prespecified starts escaped the stalled hard-visibility event and reached a strictly accepted CH1–4 basin. The training-selected low error is now **1.659857 km**, replacing the previously accepted 0.190263 km incumbent because its objective is better by 215.489449. The current full/low/high comparison is therefore **1.343357 / 1.659857 / 1.444907 km**: full is better than both current conditional half selectors, but its own error has not improved and remains above 1 km. This corrects an optimistic half-view comparison; it is not an accuracy improvement or a solved model.

The experiment preserves the original hard-visibility propensity likelihood, fitted c, learned shifts, priors, 59-satellite bank and original 50 km disk. Starting from the same failed low complete state, it displaces X and Y by exactly plus/minus 0.001 km and common timing by exactly plus/minus 0.001 s. All other parameters remain unchanged. Every seed is qualified for exact initializer/domain feasibility; six objective and six extra orbit evaluations record its score and visibility digest before any fit. The six offsets are fixed by the measured event, not reference geography.

| Start | Acceptance | Objective | KKT | Actual evaluations | Complete fitting seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| X minus 1 m | Accepted | 12871.464237255 | 0.000588524 | 269 | 1.358 |
| X plus 1 m | Rejected, evaluation cap | — | — | 600 | 2.911 |
| Y minus 1 m | Accepted | 12871.464237256 | 0.000286560 | 275 | 1.790 |
| Y plus 1 m | Rejected, evaluation cap | — | — | 600 | 2.889 |
| Common time minus 1 ms | Rejected, nonstationary | 12871.455761849 | 1.471987 | 395 | 1.902 |
| Common time plus 1 ms | Accepted, training selected | 12871.464237255 | 0.000009012 | 280 | 1.394 |

The three accepted position errors are 1.659857, 1.659868 and 1.659857 km respectively. Their tiny objective differences should not be interpreted as meaningful accuracy differences. The previous strict low incumbent (objective 13086.953686, error 0.190263 km) remained eligible and loses the training selector. The slightly lower objective of the failed time-minus endpoint does not confer eligibility. No failed call was retried or accepted under a relaxed threshold.

Each numerical call has a 20-second, 600-actual-evaluation cap and the original independent strict KKT/domain replay. All six outcomes and the retained incumbent were sealed before reading the reference. The four earlier numerical controls remain unchanged in their own namespace. This finite event-side multistart is not a general event-aware optimizer or a global optimality proof. It does demonstrate that small, prespecified moves across the measured visibility event can recover a valid basin that an unchanged initialization repeatedly failed to reach.

The remaining model issue is stronger than the old comparison suggested: the same low-band model prefers this less accurate basin over its 0.190 km incumbent. Better fitting alone cannot select a model or validate its accuracy. The independently developed continuous-visibility model will be qualified against the observed discontinuity, with explicit width and derivative checks, before any new fits.

Source `d51a437da`; two tests and Ruff pass. Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a053-event-starts-v1`. No held observations, new RF collection, reference-chosen seeds or altered golden fixtures were used. Channel halves remain conditional views with full-derived discovery/calibration, not independently discovered pipelines.
