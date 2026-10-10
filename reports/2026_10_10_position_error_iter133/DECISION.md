# Decision: sub-bin refinement is not a broad localization improvement

Do not deploy either refiner or expand this unchanged final-model sensitivity
experiment to the full cohort on the strength of these results. All twelve
consumed development members completed all six matched fits; all 72 fits passed
the unchanged independent convergence gate. This is a negative general-improvement
result, not an optimizer or missing-input failure.

![Matched position errors](comparison.png)

| Arm / measurement | Mean km | Median km | p95 km | Worst km |
|---|---:|---:|---:|---:|
| Fitted-c original | 1.117359 | 0.905836 | 2.501273 | 3.389263 |
| Fitted-c log-parabola | 1.104340 | 1.097311 | 2.151639 | 2.628350 |
| Fitted-c Newton | 1.104707 | 1.096246 | 2.153156 | 2.630162 |
| c=0 original, matched start | 1.280581 | 0.826722 | 2.915394 | 4.193248 |
| c=0 log-parabola | 1.240088 | 0.787617 | 2.736961 | 3.189004 |
| c=0 Newton | 1.247961 | 0.786027 | 2.737934 | 3.190709 |

The fitted-c log-parabola mean improves by only 13 metres (1.17%), while the
median worsens by 191 metres (21.14%). Both refiners improve six recordings and
regress six. Maximum fitted-c regression is 309 metres. DS17 fitted-c mean
worsens from 0.868 to 0.967 km; DS16 changes 1.027 to 1.012 km and DS18 changes
1.458 to 1.334 km. Each dataset has four pilot members, not its full membership.
The largest fitted-c improvement is DS18-023, from 3.389 to 2.628 km. It does not
justify selecting a different estimator for that particular scan.

The zero-c comparison has the same fitted-derived physical and clock start as
fitted-c, with the existing RF locks applied. Its fresh original-frequency mean
is 1.280581 km, whereas the historical own-start zero-c archive mean is 1.255968
km. Use the fresh matched-start control for causal refiner comparisons; do not
silently substitute the historical comparator. Both zero-c refiners also have
six improvements and six regressions, with maximum regression about 498 metres.

Frequency effects do not rescue the localization claim. Across scans, median
posterior frequency RMS increases from 59.940 to 79.472 Hz for fitted-c
log-parabola, and from 107.641 to 115.144 Hz for c=0. Newton is very similar.
These compare different measured-frequency arrays under fixed calibration and
support; they are not direct frequency-truth errors or proof that the sub-bin
estimates are physically less accurate. Score components, assignment changes,
responsibility changes and effective support are retained separately in the
[full report](RESULTS.md) and [evaluation](evaluation.json).

This isolates frequency substitution at the final model. It does not rerun
calibration, association, satellite-bank selection or regional search. A future
end-to-end measurement experiment would require a separate protocol and a
specific causal reason to expect the earlier stages to change this result. No
per-scan estimator selection, geographic correction or reference-guided start
was used. The ordinary fitted-c control reproduces the archive to numerical
precision; all reference-coordinate reads occurred after all twelve members
were terminal.

All 35,206 original observations are represented. Eleven members use the
immutable128 receipts; DS18-029 uses the explicit134 full-member replay. The
original128 1,782 guarded read failures, its 74.881-second cost, and the
92.293-second successor cost remain visible. This addresses sparse event-ID
translation only and does not alter RF admission or scientific tolerances.
Position-comparison member runtimes sum to 235.931 seconds, including clean
reconstruction, not only optimizer time. No fallback or retry was used in133.

The broader full193 fitted-c mean remains **1.254810 km** from iteration107;
these pilot results are not substituted into that census. The **0.4 km mean
goal remains unmet**. Production B7 is unchanged. The independent fresh
native-versus-common-bank search comparison continues in129; physical phase
timing and residual-correlation models remain research hypotheses, not deployed
fixes or independently validated improvements.
