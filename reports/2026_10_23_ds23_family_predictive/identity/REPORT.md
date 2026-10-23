# DS23-0259 symmetric withheld-family native prediction

All eight bounded jobs completed, with converged fixed-position calibration phase refreshes. The calibration mask removes every retained curved point assigned any identity in the frozen target-specific union shortlist. Every candidate—including the original—then uses a fresh causal phase prior and three physical orbit modes with zero mean and unit variance. No fitted original phase or mode coefficient enters its predictive prior. Radio uncertainty is shared within each comparison. This is a new common physical prior policy, including candidates that previously received phase-only uncertainty.

The original identity has the lowest score in every context under this symmetric common model, and passes physical plus fixed-radio residual gates. No alternative passes both sets of gates. For65340, the nearest alternative62890 is worse by36.98–39.22 score units and exceeds the phase bound; the best physically qualified62754 is worse by85.32–86.09 and fails residual gates. For67618, nearest58744 is worse by624.61–658.00 and exceeds the phase bound; best physically qualified57079 is worse by743.88–802.34 and fails residual gates.

| Family | Arm | Fixed RF position | Calibration retained/withheld | Native paths/points | Original score | Best alternative (delta) | Physically qualified? |
|---|---|---|---|---|---|---|---|
| 65340 | c0 | graph_parent | 445/111 | 4/54 | 753.391 | 62890 (+37.350) | False |
| 65340 | c0 | native_RF_endpoint | 445/111 | 4/54 | 751.693 | 62890 (+39.220) | False |
| 65340 | fitted_c | graph_parent | 445/111 | 4/54 | 753.468 | 62890 (+36.980) | False |
| 65340 | fitted_c | native_RF_endpoint | 445/111 | 4/54 | 751.832 | 62890 (+38.895) | False |
| 67618 | c0 | graph_parent | 533/23 | 1/23 | 324.603 | 58744 (+645.830) | False |
| 67618 | c0 | native_RF_endpoint | 533/23 | 1/23 | 323.579 | 58744 (+657.996) | False |
| 67618 | fitted_c | graph_parent | 533/23 | 1/23 | 324.315 | 58744 (+624.613) | False |
| 67618 | fitted_c | native_RF_endpoint | 533/23 | 1/23 | 323.433 | 58744 (+637.304) | False |

Score deltas only within the new common holdout + fresh physical prior model. No score deltas against previous asymmetric screens.

Withheld-family curved points excluded rather than tested; evidence comprises target native paths. Fixed RF positions were fitted using original evidence; this is position-conditioned sensitivity, not crossvalidation. Original and replacements have no calibrated phase/mode advantage, but remaining radio posterior is conditional on other retained graph identities. Finite frozen shortlist, Gaussian phase-moment approximation, independently proposed path aliases, causal physical-mode approximation.1338 coarse phase-only output is diagnostic, not exhaustive physical fit.

Physical qualification applies the same ±15s phase, nonnegative elevation and ≤0.01s phase-convergence rules to all identities. Fixed-radio per-path residual/noise gates are reported separately; no predictive observation calibrates the radio posterior. The all1338 causal entries receive a phase-only coarse diagnostic screen, while exact phase + physical-mode refinement uses only the pre-frozen union shortlist. Newly nominated coarse objects are visible in compact.json but are not silently added without the matching calibration holdout.

No localization accuracy or external satellite-identity confirmation is claimed. Inputs, prior matrices, held/calibration ID vectors, candidate scores and diagnostic gates are retained in per-job JSON. No new RF, future TLE, position optimization or publication occurred.

![Symmetric predictive score margins](symmetric_margins.png)
