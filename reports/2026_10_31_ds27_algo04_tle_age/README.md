# DS27 / ALGO04: TLE age versus fitted nuisance variables

Older causal TLEs are associated with larger fitted satellite time shifts in DS27. The relationship is strong for absolute phase correction (Spearman rho 0.61), weaker for departure from the prior in prior-scale units (0.23), and nearly absent for the norm of the three standardized orbital corrections (0.05) and final calibration residual RMS (0.07).

This is a numerical re-evaluation of the **existing sealed ALGO04 runs**, including their selected recoveries and fallback decisions. It is **not a new acquisition, GLRT extraction, or association search**. The selected calibration objectives, positions, and nuisance states were replayed in fresh scan-isolated processes. Both c = 0 and fitted-c arms are retained. No new algorithm, deployment, satellite selection, GPS-assisted inference, or later TLE was introduced.

## Cohort and verification

| Item | Count / result |
| --- | --- |
| DS27 fast scans in the sealed cohort | 15 |
| Complete ALGO04 results, successfully replayed | 13 |
| No usable result | 2 |
| Satellite–scan pairs with fitted corrections, per c arm | 328 |
| Calibration families / added predictive families | 323 / 5 |
| Unique satellites / unique TLE versions | 325 / 326 |
| Satellites appearing in more than one scan | 3 |
| Families with three fitted orbital modes, per arm | 207 |
| TLE epoch age range | 6.08–42.93 hours |
| Largest calibration-objective replay difference | 0.0 |
| Largest exported nuisance-state replay difference | 0.0 |

Complete recordings span October 30, 2026 at 15:34 UTC through October 31 at 13:53 UTC. Adaptive scans are excluded. DS27-0001 has no exported public GLRT input. DS27-0006 failed the family-excluded phase-convergence gate; it has no qualified result and is not counted as a zero-correction observation. Their original failure receipts remain in [run.json](run.json).

ALGO04 selected new evidence for 0016, 0024, 0026, and 0028; the other nine retained its ALGO03 fallback. Recovered families are included using the selected new-family or joint-family posterior, rather than their previous unestimated phase values. The historical 0018 recovery lacks a verified recovery read audit; it remains a fallback, and its baseline objective and state replay exactly. This analysis does not retroactively qualify a recovery.

Terminal and inventory hashes are checked against the sealed analysis index. Selected-source receipts are also hash-checked. For recovered cases, incumbent objective/state and all published point owners are replayed; added predictive-family posterior summaries are read from their hash-verified result/audit artifacts. We do not claim to have rerun their full phase quadrature or original optimizer. [replay_checks.csv](replay_checks.csv) gives the per-arm checks.

## Correlations

One row is one satellite in one scan, not one GLRT point or polynomial fragment. More points on a satellite therefore do not artificially increase its statistical weight. The two c arms use the same family identities and observations; they are analyzed separately, not pooled as independent samples.

| Magnitude or diagnostic versus TLE age | Families | rho, c = 0 | rho, fitted c | Fitted-c 95% scan-bootstrap interval | Fitted-c within-scan rank correlation |
| --- | ---: | ---: | ---: | --- | ---: |
| Absolute satellite phase correction | 328 | 0.607 | **0.605** | [0.456, 0.742] | 0.542 |
| Absolute phase departure from prior mean | 328 | 0.564 | 0.563 | [0.391, 0.716] | 0.504 |
| Phase prior width | 328 | 0.649 | 0.649 | [0.541, 0.751] | 0.617 |
| Absolute phase departure / prior width | 328 | 0.236 | **0.234** | [0.060, 0.385] | 0.199 |
| Orbital correction norm, in prior units | 207 | 0.038 | **0.051** | [−0.076, 0.213] | 0.048 |
| Absolute mean-motion correction | 207 | 0.148 | 0.155 | [0.025, 0.324] | 0.151 |
| Absolute inclination correction | 207 | 0.158 | 0.171 | [0.030, 0.329] | 0.194 |
| Absolute RAAN correction | 207 | 0.124 | 0.128 | [−0.012, 0.305] | 0.166 |
| Orbital CFO correction RMS | 202 | 0.185 | 0.194 | [0.072, 0.360] | 0.196 |
| Mean absolute fitted track offset | 323 | −0.034 | −0.048 | [−0.135, 0.033] | −0.112 |
| Final calibration residual RMS | 323 | 0.071 | **0.072** | [−0.019, 0.157] | 0.076 |

The intervals resample whole scans, 1,500 draws with a fixed seed. They describe this selected cohort; there are only 13 scan clusters. These are exploratory comparisons, not multiplicity-adjusted significance claims. Within-scan correlation removes scan-specific means from globally ranked ages and corrections. It is a partial rank correlation, not the average of 13 separate Spearman coefficients.

![Age versus phase, priors, orbital corrections and residuals](age_vs_nuisance.png)

The fitted-c phase correlation remains 0.539–0.633 when any one scan is removed. Using one median observation per satellite gives 0.600. Restricting to the 323 calibration families gives 0.602, so the five recovered families do not create the result.

There is **insufficient repetition to estimate a credible within-satellite aging effect while also controlling scan**. With only three repeated satellites, the two-way fixed-effect design is nearly saturated. The code reports this as unavailable rather than displaying a misleading correlation of ±1 from one remaining residual direction. The same-satellite experiment remains outstanding.

![Sensitivity to scan and satellite controls](correlation_controls.png)

## What the sizes mean

Fitted-c median values, grouped by TLE epoch age:

| TLE age | Families | Absolute phase | Phase prior width | Absolute departure / prior width |
| --- | ---: | ---: | ---: | ---: |
| Up to 12 h, observed minimum 6.08 h | 94 | 0.166 s | 0.637 s | 0.261 |
| 12–24 h | 169 | 0.367 s | 1.072 s | 0.267 |
| 24–36 h | 53 | 1.391 s | 2.178 s | 0.536 |
| 36–48 h, observed maximum 42.93 h | 12 | 4.805 s | 7.112 s | 0.731 |

The oldest bin is small. Median residuals remain roughly 60–65 Hz across these age bins; that is an in-sample frequency-fit observation, not a claim about localization accuracy.

Here “phase” is the satellite trajectory time shift used in Doppler prediction, in seconds. It is not RF carrier phase or receiver clock drift. Orbital corrections are the mean-motion, inclination, and RAAN perturbations. Raw physical perturbations and their prior scales are provided in [families.csv](families.csv).

The three-dimensional orbital norm is the Euclidean norm of the fitted perturbations divided by their model scales. It is not a posterior probability or an independently calibrated chi-square statistic. Unsupported/unestimated orbital parameters are missing, rather than filled with zero. The CFO correction RMS is evaluated on active calibration points only, so it excludes the five added predictive families. Residual RMS and track-offset comparisons likewise use calibration families only; predictive-family profiled RMS is a different quantity and is not mixed into those correlations.

## Why part of this trend is already built into ALGO04

The phase prior uses disagreement between two causal TLEs. Before its learned distribution multiplier, the implemented scale is:

```text
scale_seconds = clip(sqrt(1 + (old_new_alignment_seconds * TLE_age / epoch_gap)^2), 1, 15)
```

If there is no alignment history, the base fallback scale is 1 second. The forecast prior mean can also depend on age and signed TLE disagreement. The model then applies its causal-history distribution parameters. For Student-t priors, the stored “sigma” is a scale parameter; a departure of eight scale units is not an eight-sigma Gaussian event.

Consequently, age and the allowed correction width are intentionally related. The correlation of age with raw fitted phase is not independent proof of orbit-error growth. Nevertheless, the phase departure from its prior mean also rises with age, and a weaker relationship remains after scale normalization. The broad pattern is consistent with larger timing uncertainty for older elements; this analysis cannot separate that from shrinkage, satellite mix, and accepted-track selection.

Orbital physical scales are also derived from causal TLE differences. Mean-motion/inclination correction magnitudes show weak positive age relationships, while the standardized orbital norm shows little relationship. This is compatible with the existing scaling doing useful work, but is not proof that its uncertainty coverage is calibrated.

## Receiver and band terms

Receiver nuisance coefficients are shared across many satellite families. They are analyzed **once per scan**, against the median fitted-family TLE age in that scan. Repeating one receiver drift for every satellite would manufacture a much larger sample size.

| Scan-level absolute term | rho, c = 0 | rho, fitted c |
| --- | ---: | ---: |
| RX1 low-band linear drift | 0.302 | 0.335 |
| RX1 high-band linear drift | 0.330 | 0.330 |
| RX2 low-band linear drift | 0.379 | 0.396 |
| RX2 high-band linear drift | 0.319 | 0.313 |
| Smooth receiver-frequency correction RMS | −0.154 | −0.115 |
| RF-dependent c coefficient | Not estimable: fixed at zero | −0.055 |

These 13-point relationships are exploratory and potentially confounded by scan time, temperature, receiver state, and satellite geometry. They do not establish that the receiver is absorbing an age-dependent orbital error. All four RX/band offsets, their contrasts, drift rates in Hz/s, smooth RMS, and c in Hz/GHz are exported in [receiver_calibration.csv](receiver_calibration.csv). Offset-contrast correlations are in [receiver_correlations.csv](receiver_correlations.csv); these coefficients are conditional on the model's alias and offset conventions.

![Receiver terms versus scan median TLE age](receiver_terms.png)

## Individual cases worth inspecting

| Scan / satellite | TLE age | Fitted phase | Prior mean / width | Departure in scale units | Calibration RMS |
| --- | ---: | ---: | --- | ---: | ---: |
| DS27-0012 / 64331 | 42.58 h | −4.743 s | 0 / 0.602 s | 7.87 | 91.9 Hz |
| DS27-0028 / 68563 | 17.74 h | −3.047 s | −0.167 / 0.547 s | 5.27 | 23.9 Hz |
| DS27-0026 / 54101 | 27.16 h | +13.662 s | −0.804 / 4.867 s | 2.97 | 45.0 Hz |

The first case has causal TLE history; it is not a missing-history fallback. Its old/new alignment is only 0.05024 s across a 9.416-hour epoch gap. This produces a 1.02549 s base scale, reduced to 0.60245 s by the fitted causal-history multiplier 0.58747. Its prior is Student-t with nu = 3 and zero mean shrinkage. Thus a small recent TLE disagreement can still underpredict the RF-fitted phase departure of an older element. A wrong association or other model discrepancy remains possible; the correction alone does not decide which explanation is correct.

The second case shows that a relatively young TLE can also be an outlier. The third has a large absolute phase with a substantially wider prior. These are useful distinctions when prioritizing diagnostics: inspect both physical correction size and prior-normalized departure, not age alone. The top ten departures are exported in [largest_phase_departures.csv](largest_phase_departures.csv).

## Recommended next experiment

Keep the age/history-aware satellite priors. This result does not justify globally loosening receiver drift, adding arbitrary per-track curvature, or rejecting old elements solely by age.

The clean next test is a **matched causal TLE-vintage ablation**. For the same scan, same satellite identities, same GLRT observations, and both c arms, use the latest eligible causal TLE and earlier eligible causal versions. Compare (1) a fixed common prior policy to isolate propagation changes and (2) the operational age/history-aware policy to measure the complete method. Record phase/orbit departures, residual structure, evidence, and position error separately. This supplies within-satellite, within-scan contrasts that DS27's natural age variation lacks. The experiment should include association failures and use evaluation GPS only after inference.

Until that test, the supported conclusion is: **older accepted TLEs need larger timing adjustments, but this does not yet show that TLE age is the dominant cause of position error.** This cohort excludes missing/rejected families and is restricted by the original causal catalogue policy. No inference is made for ages above the observed 42.93 h, for the two failed/unavailable scans, or for unseen satellite populations.

## Reproduction and artifacts

Sources are the sealed study `/srv/bulk/leo/research/ds27-algo04-20261031`. Numerical replay uses `/srv/bulk/leo-dev/fast-algo02-production-v1`, Git revision `a9a340309a004d31f133e59662c24414a6a71b22`. This is distinct from the frozen ALGO04 release recorded in the source protocol; exact objective/state equality checks guard against changed numerical behavior. The selected ALGO04 version is `algo04-causal-numerical-v1`.

From the numerical worktree:

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=src:tools .venv/bin/python \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_31_ds27_algo04_tle_age/analyze.py --workers 4
```

From the user repository:

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with pandas --with numpy --with scipy --with matplotlib \
  python reports/2026_10_31_ds27_algo04_tle_age/summarize.py
OPENBLAS_NUM_THREADS=1 uv run --no-project --with pandas --with numpy --with scipy --with matplotlib \
  python reports/2026_10_31_ds27_algo04_tle_age/test_analysis.py
```

The six checks cover epoch-versus-collection age, rejection of noncausal sources, prior-centered phase scaling, orbital units, scan-confounding removal, nearly saturated fixed effects, paired unique family rows, and numerical replay agreement. No production component or scientific golden fixture changed.

Files: [family rows](families.csv), [all correlations](correlations.csv), [per-scan summary](per_scan.csv), [age-bin summary](age_bins.csv), [receiver terms](receiver_calibration.csv), [associated family inventory](associated_family_inventory.csv), [cohort status](run.json), [artifact hashes](artifact-manifest.json). [analyze.py](analyze.py) and [summarize.py](summarize.py) contain the complete extraction and analysis logic.
