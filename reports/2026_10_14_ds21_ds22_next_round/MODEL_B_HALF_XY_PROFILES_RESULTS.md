# B059 half XY with current full calibration: selected error regresses

The declared full-training selector chooses the accepted low-anchor release at **1.210448km**, versus the incumbent1.129758km. Its objective improves8.482320, while localization regresses. The high fixed-position profile reaches a lower objective than either eligible free state but fails the unchanged stationarity gate; it receives no release. This experiment does not establish an unavoidable full-likelihood preference against the high geography.

Source/protocol `09d99ae5e` passed four owned tests and Ruff before source freeze. Qualification made three objectives and zero optimizer calls in19.340s, including guards/preparation: the incumbent replays exactly with FREE KKT.000136635; both starts retain its complete non-geographic vector/nuisance/q and original priors. Only XY comes from the two accepted matched-half fits. The original donor25km disk, full bank/frame/clock nodes, fitted c, normalized propensity likelihood, sigma125Hz, detection budget1.6 and all q priors/bounds remain unchanged. No calibration-projection coefficients or complete half calibration states initialize a fit. Initial low/high objectives are28215.884547/31958.578907, with the same339.226699 prior.

Both profile workers sealed before either release worker. Exactly three new20s/600 calls ran: two fixed-XY profiles and the single release of the accepted low profile. The rejected high profile has a sealed zero-call release unit. Each independent worker has internal120/TERM135/KILL140 including source guards/preparation/audit and at least30s admission. Up to two workers ran concurrently; repeated preparation is additional cost. There are no retries, tolerance changes or unused-budget reallocations.

| Full-target state | Accepted | Objective | NLL | Prior | KKT | Fit time | Development error km |
|---|---|---:|---:|---:|---:|---:|---:|
| historical current full |true |28054.858757 |27715.632058 |339.226699 |.000136635 |historical |1.129758 |
| low fixed XY profile |true |28046.655844 |27707.803936 |338.851908 |.000148104 |6.736s |1.035045 |
| high fixed XY profile |false |27757.972556 |27451.120165 |306.852391 |.008014186 |5.849s |.468524 |
| low FREE release **selected** |true |28046.376437 |27707.170952 |339.205485 |.000052840 |5.779s |1.210448 |

Fixed profiles are ineligible free endpoints. The high profile reports solver success after595 evaluations but fails strict fixed-XY physical/nuisance KKT≤.001. It stops well before20s. Its296.886201 objective advantage over the incumbent decomposes into264.511893 lower NLL and32.374308 lower prior, so it remains a numerical-stopping/optimization lead rather than an accepted result. A separate bounded zero-fit finite-difference/curvature/ULP postmortem follows; no high retry or promotion is included here.

Group-offset priors stay near.4049 in both profiles and the release, avoiding the near-zero group-offset collapse of the previous complete-half continuation experiment. The low release improves incumbent NLL8.461106 and prior.021214, but its small additional geographic movement worsens development accuracy. This isolates the declared common-start pathway; it does not prove the calibration basis is physically adequate or rule out better coupled timing/q states. The separate matched-view result remains all1.129758/low1.035045/high.468524km, with all worse than both own-model halves. Neither that result nor this control meets the target.

Whole worker times: low/high profiles27.687/24.463s, low release28.020s and high zero-call unit20.585s. All outcomes and the training-only selector were sealed before reference joins; evaluation took16.913s, zero fits. Original held/locked observations were never read. The three calls add to32 prior observation-model/control calls plus upstream work; this is not an equal end-to-end-budget comparison.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-half-xy-profiles-059-v1`. Qualification SHA256 `25944ac349dae0c8e8e80f31ad58b4c53c879c9117e5ed63fa2d5cf58fbbde49`; scientific seal `d61c2448eb77ca43ad70b665247efc446e10952b1ed1a4939fff2315dce0cc25`; postseal evaluation `3b2655592430d5c9aa0c6b1c4a1d960e1f261e3aa376eb256c4904d21a421359`.
