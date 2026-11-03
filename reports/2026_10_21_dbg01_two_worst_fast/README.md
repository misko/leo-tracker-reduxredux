# DBG01: the two worst fast ALGO02 scans

DS23-0268 and DS23-0405 rank first and second among available fast ALGO02 endpoints, using fitted-c error. This is retrospective diagnosis. The original estimator and its benchmark are unchanged.

![Position comparison](method_comparison.png)

![All satellite-family ablations and remaining association](family_ablation_comparison.png)

| Scan | Method | Error km | Original GLRT % | Status |
| --- | --- | --- | --- | --- |
| DS23-0268 | original_ALGO02 | 5.319 | 57.883 | complete |
| DS23-0268 | signed_prior | 5.461 | 57.883 | complete |
| DS23-0268 | combined_recovery | 5.506 | 60.063 | budget_exhausted |
| DS23-0268 | skew_phase | 6.079 | None | accepted |
| DS23-0268 | multi_family_position | 5.461 | None | incumbent fallback |
| DS23-0405 | original_ALGO02 | 4.544 | 68.737 | complete |
| DS23-0405 | signed_prior | 4.544 | 68.737 | complete |
| DS23-0405 | combined_recovery | 3.453 | 70.088 | complete |
| DS23-0405 | skew_phase | 4.544 | None | incumbent fallback |
| DS23-0405 | multi_family_position | 3.592 | None | accepted |
| DS23-0268 | targeted_split | 0.943 | 71.216 | original paired gates pass |
| DS23-0268 | targeted_split_CH2 | 1.343 | 73.175 | original paired gates pass |

0268 combined recovery exhausted its 900 s search budget; its retained endpoint passes but the search is incomplete. 0405 combined recovery completed. Targeted 0268 repairs are single-scan development, not an automatically generalized method. The lowest-error 0268 split uses fewer points than the split plus CH2. Geographic error does not select identities. The multi-family position proposal is a family-subset-generated position proposal scored against original curved evidence; it is not an independently established new satellite-label assignment. Skew and multi-family coverage was not remeasured here.

The most recent opposite-receiver curve, reception-identity and RF/clock prototypes have not yielded a qualified position comparison on these two scans. Results from other development/confirmation cohorts are not substituted into this per-scan comparison.


## DS23-0268

| c arm | All original GLRT | Associated | Associated % | Tracks | Unassociated | In graph | Outside graph |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c0 | 3165 | 1832 | 57.883 | 51 | 1333 | 954 | 379 |
| fitted_c | 3165 | 1832 | 57.883 | 51 | 1333 | 954 | 379 |

All native lanes, exact partial masks and original point identities are retained. Gray is context; red is unassociated.


![Associated GLRT and polynomial tracks](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/associated_GLRT_fitted_c.png)


![Unassociated GLRT and polynomial tracks](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/unassociated_GLRT_fitted_c.png)


![Retained track residuals](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/track_residuals.png)


![Conditional loss and gradient](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/loss_gradient_10km.png)


![Regional starts and solver paths](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/convergence_10km.png)


![All family and individual-track ablations; generic controls](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/influence_and_controls.png)


![Reference versus endpoint loss decomposition](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0268/loss_decomposition.png)

The upper loss views sample 317 locations at 1 km spacing in a 10 km regional disk; lower views sample 289 points at 0.25 km spacing over ±2 km around evaluation truth. Pixels refit nuisance means, robust precision and five phase refreshes with fixed observations/labels/aliases. They do not rerun acquisition or association. The 81 restart paths can switch curved nominations/aliases among a finite cold-discovered pool after accepted c0 steps; predictive labels remain fixed. Fitted c follows the same branch schedule.

Restart summary: `{'c0': {'error_range_km': [5.145635931868288, 5.14563606236981], 'endpoint_max_pairwise_distance_km': 1.7773674286279903e-07, 'final_modes': [0], 'switches': 0, 'paired_valid_starts': 81, 'maximum_final_phase_change_s': 0.0005230885453902934}, 'fitted_c': {'error_range_km': [5.317840317027972, 5.317840599664762], 'endpoint_max_pairwise_distance_km': 3.6699647018891995e-07, 'final_modes': [0], 'switches': 0, 'paired_valid_starts': 81, 'maximum_final_phase_change_s': 0.00047592138958885144}}`.

The fixed reference site has a worse normalized loss by 34.114 / 35.003 in c0 / fitted-c after refreshing phases and nuisances. This is evidence of a conditional model preference; it does not prove the transmitter identities or isolate a hardware defect.

Among gate-passing, phase-converged deletion diagnostics, the smallest fitted-c error is 3.880 km after removing 63901. No satellite is removed automatically based on this reference-error ranking.


### Satellite-family ablation

| Removed family | Error km | RMS Hz | Remaining GLRT % | Curved removed | Predictive removed | Both gates pass |
| --- | --- | --- | --- | --- | --- | --- |
| 53923 | 2.124 | 144.058 | 43.381 | 309 | 59 | False |
| 54873 | 5.366 | 140.187 | 56.556 | 42 | 0 | True |
| 59328 | 5.446 | 139.187 | 56.556 | 42 | 0 | True |
| 60415 | 5.027 | 135.917 | 52.291 | 169 | 8 | True |
| 61977 | 6.336 | 138.725 | 53.934 | 84 | 41 | True |
| 63901 | 3.880 | 138.170 | 55.008 | 73 | 18 | True |
| 63913 | 6.498 | 138.989 | 55.197 | 41 | 44 | True |
| 64908 | 5.895 | 121.663 | 46.761 | 267 | 0 | False |
| 64923 | 5.224 | 141.827 | 53.175 | 116 | 33 | True |
| 64925 | 5.458 | 139.305 | 51.374 | 206 | 0 | True |
| 66812 | 5.444 | 138.851 | 56.904 | 31 | 0 | True |
| 68343 | 5.547 | 140.447 | 49.984 | 159 | 0 | False |
| 69445 | 4.951 | 139.108 | 55.039 | 82 | 8 | True |

Each deletion removes that family from curved calibration and predictive evidence; the original nuisance design stays fixed. Remaining association is reconstructed at the ablated endpoint and the deleted family cannot reenter. Raw objectives with different masks are not ranked. A lower geographic error is an influence diagnostic, not a deletion rule.


### Unassociated evidence and following-TLE diagnostics

The exact inventory has 954 graph-owned and 379 outside-graph unresolved points. Both catalogue screens test 1402 candidate identities over ±15 s in 0.25 s steps. Following elements are unavailable for 0 candidates; those causal fallbacks are labeled.

The RF-estimated position, receiver/band drift, offsets and smooth coefficients are frozen. Only phase, integer pilot alias and a constant with 300 Hz prior are fitted per evidence group, using a matched 150 Hz diagnostic white-noise scale. RMS ≤450 Hz, |constant|≤3000 Hz, horizon and unchanged mean/slope/quadratic/step/ACF noise limits are all required. These per-curve candidates do not establish a shared-family association or enter the causal position result.

- causal: 30/38 graph subsets and 13/41 fixed orphan time blocks have at least one passing independent candidate. 126 points lack four distinct times within their group and are not individually assigned.

- following: 30/38 graph subsets and 14/41 fixed orphan time blocks have at least one passing independent candidate. 126 points lack four distinct times within their group and are not individually assigned.


Following TLEs do not by themselves resolve the missing-evidence problem under the frozen RF endpoint/calibration. The following comparison separates the current shared phase plus fitted orbit correction from the nominal orbit at that same phase, and from an independently fitted nominal-orbit phase. These are conditional diagnostics, not three new estimators.

| Curve | Candidate | Retained curved family points | Current phase s | Independent phase s | Shared phase + orbit RMS Hz | Shared phase nominal RMS Hz | Independent phase nominal RMS Hz |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DS23-0268-RX1-CH3-T000-RF11440312500.000000 | 64923 | 116 | -1.470 | -1.500 | 168.328 | 168.500 | 159.276 |
| DS23-0268-RX1-CH5-T004-RF11940312500.000000 | 67935 | 0 | -1.111 | -2.500 | 926.302 | 926.302 | 164.537 |
| DS23-0268-RX1-CH7-T000-RF12440312500.000000 | 64333 | 0 | -0.157 | 0.000 | 243.631 | 243.631 | 199.182 |
| DS23-0268-RX1-CH2-T005-RF11190312500.000000 | 67953 | 0 | 0.467 | -3.000 | 1100.744 | 1100.744 | 178.879 |
| DS23-0268-RX1-CH5-T005-RF11940312500.000000 | 66797 | 0 | -0.257 | -0.250 | 254.591 | 254.591 | 255.283 |
| DS23-0268-RX1-CH6-T002-RF12190312500.000000 | 64923 | 116 | -1.470 | -1.750 | 198.262 | 198.411 | 164.213 |

![Shared-family residual discrepancy](DS23-0268_shared_family_residual.png)

**Diagnosis:** the longest unresolved graph subset is RX1 CH3 T000, 82 observations over 58.54 s. Its leading candidate is 64923. Causal RMS is 159.28 Hz and following-TLE RMS is 144.40 Hz, but both fail slope, quadratic, step and autocorrelation tests. For the causal fit, slope z=4.86, quadratic BIC gain=41.70 and step z=7.35. Low RMS is therefore insufficient. This is one persisted polynomial piece; a multi-piece join is not demonstrated as the cause. The earlier targeted improvements concern other curves and disputed 53923/67953 ownership, and are not reproduced by a generic signed phase-prior update. A useful next test is family-excluded, jointly calibrated reentry with gate-aware fitting and competing identities retained; neither a free per-track slope nor GPS-ranked family deletion is justified by this diagnostic.

| Graph subset | TLE | Points | Candidate | RMS Hz | All screens pass | Passing identities | Slope z |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DS23-0268-RX1-CH3-T000-RF11440312500.000000 | causal | 82 | 64923 | 159.276 | False | 0 | 4.862 |
| DS23-0268-RX1-CH3-T000-RF11440312500.000000 | following | 82 | 64923 | 144.401 | False | 0 | 3.810 |
| DS23-0268-RX1-CH5-T004-RF11940312500.000000 | causal | 71 | 67935 | 164.537 | False | 0 | 0.064 |
| DS23-0268-RX1-CH5-T004-RF11940312500.000000 | following | 71 | 67935 | 169.346 | False | 0 | 1.718 |
| DS23-0268-RX1-CH7-T000-RF12440312500.000000 | causal | 60 | 64333 | 199.182 | False | 0 | 1.997 |
| DS23-0268-RX1-CH7-T000-RF12440312500.000000 | following | 60 | 64333 | 208.103 | False | 0 | 1.771 |
| DS23-0268-RX1-CH2-T005-RF11190312500.000000 | causal | 62 | 67953 | 178.879 | False | 0 | 5.705 |
| DS23-0268-RX1-CH2-T005-RF11190312500.000000 | following | 62 | 67953 | 174.871 | False | 0 | 5.644 |
| DS23-0268-RX1-CH5-T005-RF11940312500.000000 | causal | 49 | 66797 | 255.283 | True | 2 | 1.179 |
| DS23-0268-RX1-CH5-T005-RF11940312500.000000 | following | 49 | 66797 | 260.026 | True | 2 | 1.465 |
| DS23-0268-RX1-CH6-T002-RF12190312500.000000 | causal | 35 | 64923 | 164.213 | False | 0 | 1.155 |
| DS23-0268-RX1-CH6-T002-RF12190312500.000000 | following | 35 | 64923 | 148.093 | False | 0 | 0.352 |
| DS23-0268-RX2-CH4-T001-RF11690312500.000000 | causal | 46 | 69445 | 129.945 | True | 1 | 1.907 |
| DS23-0268-RX2-CH4-T001-RF11690312500.000000 | following | 46 | 69445 | 138.616 | True | 2 | 2.477 |
| DS23-0268-RX2-CH5-T001-RF11940312500.000000 | causal | 53 | 59342 | 102.766 | True | 1 | 0.339 |
| DS23-0268-RX2-CH5-T001-RF11940312500.000000 | following | 53 | 59342 | 102.962 | True | 1 | 0.476 |

![Unassociated orbit comparison 1](DS23-0268_unassociated_01.png)


![Unassociated orbit comparison 2](DS23-0268_unassociated_02.png)


![Unassociated orbit comparison 3](DS23-0268_unassociated_03.png)


[Complete unassociated graph-curve gallery](DS23-0268_unassociated_orbits.pdf). Outside-graph blocks are fixed 20 s partitions, not found tracks. Many passing candidates on a short or linear block indicate ambiguity, not explained points. The screen keeps every unresolved observation; no point is trimmed to make a candidate pass.


## DS23-0405

| c arm | All original GLRT | Associated | Associated % | Tracks | Unassociated | In graph | Outside graph |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c0 | 2962 | 2036 | 68.737 | 67 | 926 | 597 | 329 |
| fitted_c | 2962 | 2036 | 68.737 | 67 | 926 | 597 | 329 |

All native lanes, exact partial masks and original point identities are retained. Gray is context; red is unassociated.


![Associated GLRT and polynomial tracks](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/associated_GLRT_fitted_c.png)


![Unassociated GLRT and polynomial tracks](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/unassociated_GLRT_fitted_c.png)


![Retained track residuals](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/track_residuals.png)


![Conditional loss and gradient](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/loss_gradient_10km.png)


![Regional starts and solver paths](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/convergence_10km.png)


![All family and individual-track ablations; generic controls](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/influence_and_controls.png)


![Reference versus endpoint loss decomposition](/srv/bulk/leo/research/dbg01-two-worst-fast-20261021/DS23-0405/loss_decomposition.png)

The upper loss views sample 317 locations at 1 km spacing in a 10 km regional disk; lower views sample 289 points at 0.25 km spacing over ±2 km around evaluation truth. Pixels refit nuisance means, robust precision and five phase refreshes with fixed observations/labels/aliases. They do not rerun acquisition or association. The 81 restart paths can switch curved nominations/aliases among a finite cold-discovered pool after accepted c0 steps; predictive labels remain fixed. Fitted c follows the same branch schedule.

Restart summary: `{'c0': {'error_range_km': [4.445852304499009, 4.44585232072411], 'endpoint_max_pairwise_distance_km': 1.6241904037451367e-08, 'final_modes': [5, 12], 'switches': 21, 'paired_valid_starts': 0, 'maximum_final_phase_change_s': 3.2136383332215246e-08}, 'fitted_c': {'error_range_km': [4.544845746296575, 4.5448457908916255], 'endpoint_max_pairwise_distance_km': 4.478335986449191e-08, 'final_modes': [5, 12], 'switches': 0, 'paired_valid_starts': 0, 'maximum_final_phase_change_s': 6.480096015337722e-09}}`.

**All 81 reassociating restart endpoints fail the unchanged paired residual gates.** They are diagnostic solver endpoints, not accepted positions. The saved ALGO02 incumbent remains the benchmark. For this scan the selected branches relabel RX1 CH3 T002 from 66150 to 63380; that curve then fails slope, curvature, step and autocorrelation screens despite RMS below 450 Hz. The agreement of endpoints therefore does not certify the replacement identity.

The fixed reference site has a worse normalized loss by 18.120 / 18.779 in c0 / fitted-c after refreshing phases and nuisances. This is evidence of a conditional model preference; it does not prove the transmitter identities or isolate a hardware defect.

Among gate-passing, phase-converged deletion diagnostics, the smallest fitted-c error is 3.809 km after removing 65936. No satellite is removed automatically based on this reference-error ranking.


### Satellite-family ablation

| Removed family | Error km | RMS Hz | Remaining GLRT % | Curved removed | Predictive removed | Both gates pass |
| --- | --- | --- | --- | --- | --- | --- |
| 57499 | 5.116 | 160.866 | 59.183 | 103 | 0 | False |
| 58545 | 4.325 | 158.673 | 67.589 | 34 | 0 | True |
| 59569 | 4.406 | 153.763 | 62.424 | 163 | 0 | True |
| 59582 | 4.549 | 160.529 | 62.390 | 177 | 0 | True |
| 60285 | 5.715 | 158.760 | 64.686 | 98 | 0 | True |
| 63380 | 4.369 | 156.886 | 66.543 | 93 | 0 | False |
| 63636 | 4.814 | 157.735 | 64.517 | 83 | 0 | False |
| 63640 | 4.278 | 157.598 | 66.239 | 49 | 0 | True |
| 63998 | 4.230 | 158.337 | 66.610 | 34 | 0 | True |
| 64011 | 5.085 | 155.992 | 61.242 | 222 | 0 | True |
| 64424 | 4.555 | 158.530 | 68.096 | 19 | 0 | True |
| 65910 | 4.586 | 156.290 | 66.070 | 51 | 0 | False |
| 65936 | 3.809 | 157.821 | 67.049 | 50 | 0 | True |
| 66150 | 5.459 | 157.074 | 67.319 | 42 | 0 | True |
| 66160 | 4.788 | 158.259 | 66.442 | 52 | 0 | True |
| 66458 | 5.648 | 155.245 | 54.220 | 263 | 0 | False |
| 69510 | 4.618 | 157.983 | 67.826 | 18 | 0 | True |
| 69957 | 4.322 | 156.594 | 65.361 | 64 | 0 | True |
| 101008 | 4.462 | 157.840 | 65.733 | 89 | 0 | True |

Each deletion removes that family from curved calibration and predictive evidence; the original nuisance design stays fixed. Remaining association is reconstructed at the ablated endpoint and the deleted family cannot reenter. Raw objectives with different masks are not ranked. A lower geographic error is an influence diagnostic, not a deletion rule.


### Unassociated evidence and following-TLE diagnostics

The exact inventory has 597 graph-owned and 329 outside-graph unresolved points. Both catalogue screens test 1432 candidate identities over ±15 s in 0.25 s steps. Following elements are unavailable for 1 candidates; those causal fallbacks are labeled.

The RF-estimated position, receiver/band drift, offsets and smooth coefficients are frozen. Only phase, integer pilot alias and a constant with 300 Hz prior are fitted per evidence group, using a matched 150 Hz diagnostic white-noise scale. RMS ≤450 Hz, |constant|≤3000 Hz, horizon and unchanged mean/slope/quadratic/step/ACF noise limits are all required. These per-curve candidates do not establish a shared-family association or enter the causal position result.

- causal: 21/26 graph subsets and 13/30 fixed orphan time blocks have at least one passing independent candidate. 116 points lack four distinct times within their group and are not individually assigned.

- following: 20/26 graph subsets and 13/30 fixed orphan time blocks have at least one passing independent candidate. 116 points lack four distinct times within their group and are not individually assigned.


Following TLEs do not by themselves resolve the missing-evidence problem under the frozen RF endpoint/calibration. The following comparison separates the current shared phase plus fitted orbit correction from the nominal orbit at that same phase, and from an independently fitted nominal-orbit phase. These are conditional diagnostics, not three new estimators.

| Curve | Candidate | Retained curved family points | Current phase s | Independent phase s | Shared phase + orbit RMS Hz | Shared phase nominal RMS Hz | Independent phase nominal RMS Hz |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DS23-0405-RX1-CH7-T000-RF12440312500.000000 | 66465 | 0 | -0.373 | 0.250 | 562.075 | 562.075 | 181.032 |
| DS23-0405-RX1-CH1-T002-RF10940312500.000000 | 66465 | 0 | -0.373 | 0.000 | 337.414 | 337.414 | 231.039 |
| DS23-0405-RX2-CH1-T001-RF10940312500.000000 | 68109 | 0 | -0.851 | -1.500 | 387.369 | 387.369 | 199.825 |
| DS23-0405-RX1-CH5-T000-RF11940312500.000000 | 65910 | 51 | -1.737 | -1.500 | 162.835 | 162.835 | 81.361 |
| DS23-0405-RX1-CH4-T001-RF11690312500.000000 | 69957 | 64 | -2.312 | -2.250 | 178.883 | 177.470 | 176.003 |
| DS23-0405-RX2-CH2-T000-RF11190312500.000000 | 68111 | 0 | -0.406 | -0.250 | 90.398 | 90.398 | 42.696 |

![Shared-family residual discrepancy](DS23-0405_shared_family_residual.png)

**Diagnosis:** the longest unresolved curve is RX1 CH7 T000, 82 observations over 74.19 s; the next-longest RX1 CH1 T002 also independently nominates 66465. The longest curve passes the causal independent screen at +0.25 s phase and 181.03 Hz RMS, while its current -0.373 s phase gives 562.08 Hz RMS. **Follow-up interpretation correction:** 66465 has zero retained curved points and no retained predictive entries. The -0.373 s value is the causal forecast prior, not a phase learned from an established associated family. Removing fitted orbit modes at that same shared phase leaves RMS unchanged, so this contrast is a phase/family-consistency issue under the frozen receiver calibration, rather than an effect of those orbit modes. The following element reaches 200.12 Hz RMS but fails structured-noise gates. The longest curve has one persisted polynomial piece, so a multi-piece join is not demonstrated. The parsimonious next prototype is coherent reentry of both RX1 curves with one common 66465 phase, testing 59582 as a competing family hypothesis and rechecking every existing associated curve. Independent per-track phases must not be adopted as if they established a common satellite. The new regional restart branches that choose 63380 for a different CH3 curve fail the original gates and must retain the incumbent.

| Graph subset | TLE | Points | Candidate | RMS Hz | All screens pass | Passing identities | Slope z |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DS23-0405-RX1-CH7-T000-RF12440312500.000000 | causal | 82 | 66465 | 181.032 | True | 1 | 2.341 |
| DS23-0405-RX1-CH7-T000-RF12440312500.000000 | following | 82 | 66465 | 200.124 | False | 0 | 4.748 |
| DS23-0405-RX1-CH1-T002-RF10940312500.000000 | causal | 44 | 66465 | 231.039 | True | 1 | 0.715 |
| DS23-0405-RX1-CH1-T002-RF10940312500.000000 | following | 44 | 66465 | 228.793 | False | 0 | 1.216 |
| DS23-0405-RX2-CH1-T001-RF10940312500.000000 | causal | 41 | 68109 | 199.825 | False | 0 | 4.089 |
| DS23-0405-RX2-CH1-T001-RF10940312500.000000 | following | 41 | 68109 | 160.911 | True | 1 | 1.862 |
| DS23-0405-RX1-CH5-T000-RF11940312500.000000 | causal | 16 | 65910 | 81.361 | True | 1 | 0.679 |
| DS23-0405-RX1-CH5-T000-RF11940312500.000000 | following | 16 | 65910 | 116.600 | True | 1 | 2.193 |
| DS23-0405-RX1-CH4-T001-RF11690312500.000000 | causal | 48 | 69957 | 176.003 | False | 0 | 3.159 |
| DS23-0405-RX1-CH4-T001-RF11690312500.000000 | following | 48 | 69957 | 166.822 | False | 0 | 2.054 |
| DS23-0405-RX2-CH2-T000-RF11190312500.000000 | causal | 33 | 68111 | 42.696 | False | 0 | 1.735 |
| DS23-0405-RX2-CH2-T000-RF11190312500.000000 | following | 33 | 68111 | 44.034 | False | 0 | 2.190 |
| DS23-0405-RX1-CH1-T006-RF10940312500.000000 | causal | 14 | 59569 | 132.672 | True | 3 | 0.880 |
| DS23-0405-RX1-CH1-T006-RF10940312500.000000 | following | 14 | 59569 | 134.248 | True | 2 | 1.029 |
| DS23-0405-RX1-CH1-T001-RF10940312500.000000 | causal | 16 | 66465 | 147.893 | True | 2 | 1.836 |
| DS23-0405-RX1-CH1-T001-RF10940312500.000000 | following | 16 | 66465 | 135.126 | True | 2 | 0.788 |

![Unassociated orbit comparison 1](DS23-0405_unassociated_01.png)


![Unassociated orbit comparison 2](DS23-0405_unassociated_02.png)


![Unassociated orbit comparison 3](DS23-0405_unassociated_03.png)


[Complete unassociated graph-curve gallery](DS23-0405_unassociated_orbits.pdf). Outside-graph blocks are fixed 20 s partitions, not found tracks. Many passing candidates on a short or linear block indicate ambiguity, not explained points. The screen keeps every unresolved observation; no point is trimmed to make a candidate pass.


## Reproduction and validation

Use `PYTHONPATH=/tmp/algo03-feasible-deps:src:tools`, single BLAS/OMP threads and the repository venv. Run `tools/run_dbg01_case.py --case CASE --stage STAGE` for prepare, audit, discover, bank, analyze, figures; then `tools/run_dbg01_unassociated.py --stage prepare`, `--stage screen`; then `tools/report_dbg01_two_worst_fast.py --stage coverage` and `--stage figures`. 0268 reuses hash-checked earlier numerical diagnostics and regenerates figures. All large artifacts are on local bulk storage.

[Full method comparison including matched c arms](method_comparison.csv) · [All satellite-family ablations](family_ablations.csv) · [All unassociated candidate diagnostics](unassociated_candidates.csv).
