# Receiver geometry and geographic error: development experiment

## Completed original comparison

Adding reception evidence changed the selected position in **0 of 8** scan/prior cases. The four-scan comparison is complete; the broader goal of demonstrating improved geographic accuracy remains unproven.

Distances below are kilometers to operator-supplied roof metadata, not independently surveyed GPS truth. Each entry is Doppler-only → Doppler plus receiver geometry.

| Scan | Sacramento | Reno |
|---|---:|---:|
| 00ff81dc09fc738a | 335.708 → 335.708 | 36.789 → 36.789 |
| 898b709fcf3dd978 | 251.933 → 251.933 | 248.261 → 248.261 |
| 3ebf3526172258af | 218.647 → 218.647 | 36.789 → 36.789 |
| 851486cc2a1acd99 | 134.501 → 134.501 | 297.597 → 297.597 |

The same-prior common-coordinate controls, including reversed receiver direction, select the same winners. All arms stop at their 160-point budget. Existing production estimates are much better on the three available comparison scans (roughly 4–7 km), but use different timing, association, scoring, and search settings; see `BASELINE_AUDIT.md`.

Machine-readable results and source hashes: `distance_results.json`. Original protocol: `PROTOCOL.md`. The earlier held-out reception-prediction improvements must not be described as improvements in geographic distance error.

## Two issues requiring separation

1. The fixed 100-Hz Gaussian frequency model is a poor match to calibration residual tails. At the first Sacramento winner, the ten largest track contributions account for 63.3% of frequency loss while carrying 21.7% of duration weight. See `DIAGNOSTIC_GAUSSIAN.md`.
2. The search gives unmeasured boundary-intersecting cells a default zero priority. At this budget it performs substantial boundary refinement before measured interior alternatives. All paired arms visited identical coordinate sets. This is a search-policy confound, not proof that RX geometry has no signal. See `SEARCH_DIAGNOSIS.md`, including the qualification that the original search does recover a simple synthetic bowl.

The follow-up isolates search policy first, retaining the original Gaussian scoring. Its artifacts use the `measured-search-` prefix. Do not mix those outputs with the original frozen experiment.

Completed four-scan repair-only comparison:

| Scan | Prior | Doppler-only km | With RX geometry km |
|---|---|---:|---:|
| 00ff81dc09fc738a | Sacramento | 165.751 | 165.751 |
| 00ff81dc09fc738a | Reno | 5.701 | 6.549 |
| 898b709fcf3dd978 | Sacramento | 257.091 | 257.091 |
| 898b709fcf3dd978 | Reno | 257.440 | 257.440 |
| 3ebf3526172258af | Sacramento | 218.647 | 218.647 |
| 3ebf3526172258af | Reno | 9.121 | 9.121 |
| 851486cc2a1acd99 | Sacramento | 134.991 | 134.991 |
| 851486cc2a1acd99 | Reno | 1.896 | 1.026 |

Thus search policy matters (first Reno Doppler-only improves from 36.789 to 5.701 km). Reception geometry improves one case by 0.870 km, worsens another by 0.847 km, and leaves six unchanged. Reno median error worsens from 7.411 to 7.835 km; Sacramento is unchanged. The tiny improvement in overall mean (0.00284 km) is not convincing evidence of a reliable gain. The common-inventory comparison gives the same conclusion. All searches remain budget-limited. Full machine-readable results: `measured_distance_results.json`.

## Separate robust prototype

The new pure core uses normalized Student-t residual likelihoods, training-only robust CFO and satellite shortlists, and one satellite identity shared across a track's frequency and reception observations. Candidate reception predictions are integrated directly rather than applying a nonlinear model to averaged directions.

Residual extraction covers only the six original calibration scans: 354 tracks and 1,062 candidate rows, with digest-verified sources. Conditional fitting at fixed seed-selected CFOs/shortlists gives scale 135.42 Hz and df 1.634, with neither parameter on its optimization bound. The fitted scale is **not** an RMS or standard deviation: this Student-t fit has df below 2. Leave-one-calibration-scan-out predictive loss improves in all six folds relative to seed scale100/df4. These are residual-prediction results, not location improvements.

The initial robust geographic run was paused because using fitted parameters to reselect CFOs/shortlists would change the procedure on which the conditional residual parameters were fitted. A separate calibration-only fixed-point run now resolves this to a declared numerical tolerance: reselect the full visible catalogue and refit CFOs at updated parameters, then refit the residual density. It converges in two rounds at scale132.45057 Hz/df1.585959, with 354/354 MAP identities stable. A fresh final refit changes scale by0.0743% and df by0.1189%, again with100% MAP stability. Predictions remain float64, matching the geographic runner. This is an approximate conditional fixed point, not a global maximum-likelihood proof; the original conditional-fit leave-one-scan-out numbers must not be attributed to the fixed-point model.

`frequency_fixedpoint.json` contains the extraction and iteration evidence; `fixedpoint_parameters.json` binds the exact frozen pair to that extraction and the core/fitter code hashes. `ROBUST_PROTOCOL.md` records the model intent; `frequency_parameters.json` retains the initial conditional fit and its distinct fold results.

The four robust development searches are complete (`robust_distance_results.json`):

| Scan | Sacramento: D → joint km | Reno: D → joint km |
|---|---:|---:|
| 00ff81dc09fc738a | 161.422 → 1.958 | 0.575 → 1.026 |
| 898b709fcf3dd978 | 257.831 → 266.897 | 507.348 → 4.000 |
| 3ebf3526172258af | 223.956 → 14.690 | 6.166 → 7.094 |
| 851486cc2a1acd99 | 248.247 → 285.004 | 1.896 → 1.896 |

Three cases improve, four worsen, and one is unchanged. The large gains mostly indicate different search coverage: Doppler-only ranking over the common coordinate inventory can recover similarly good or better positions. That union diagnostic has up to twice the point budget and is not a budget-matched estimator. These results do not demonstrate consistent fine-position improvement or superiority to production.

## Outcome-blind source-integrity amendment and fresh confirmation

A source-anchor audit subsequently identified overlapping derived tracks in the calibration set. Some exact source observations occur across training/reserve splits. The development results above are retained as exploratory evidence, not clean confirmation.

The separately versioned amendment under `../2026_09_27_roof_geometry_confirmation/` excludes every whole track touching a repeated source anchor, uniformly across calibration and confirmation, without using location errors. It removes 10 of 354 calibration tracks and two tracks from each of two confirmation scans. The raw recordings are unchanged. Both frequency and reception models have been refitted using the retained calibration population; the frequency fixed point converges in two rounds at scale130.0352477523 Hz/df1.5307006393 over344 tracks, with100% MAP stability and a successful fresh-refit check.

The exact frozen four-recording confirmation cohort is b5604c3d838fa7ed, f147dd8a5bc99346, 609d7a8d9861f3db, and 40ebc07665464c7d. All four amended searches and all four reciprocal-pair sensitivities completed after the model-binding preflight and64 tests passed. Each whole cohort was unblinded only after completion and binding verification; partial original runs were not mixed into the amended cohort. Primary results improve2/worsen4/leave2 unchanged. Reciprocal-pair deduplication changes no selected coordinates. Full results are in `../2026_09_27_roof_geometry_confirmation/RESULTS.md`.

Primary comparison:160 evaluations each for Doppler-only and joint scoring, independently for each prior. A secondary frozen before unblinding uses RX geometry to guide search but selects the minimum Doppler score only among the joint arm's own160 evaluated points. It cannot borrow coordinates from the other arm or the other prior. This secondary improves1/worsens1/leaves6 unchanged. One large Sacramento recovery survives the sensitivity, but improved geographic resolution across both priors remains unproven.

No source recordings, QNAP data, production location models, or RF collection settings were changed. These four scans now serve as development data; final confirmation requires disjoint existing recordings selected without inspecting their location errors.
