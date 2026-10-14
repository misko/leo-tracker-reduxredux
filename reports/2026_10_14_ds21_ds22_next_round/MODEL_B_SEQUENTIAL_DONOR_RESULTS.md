# Exact A-final donor into B: nearby059 mode still loses

The authorized four-call donor/control experiment is **negative for training-selected localization**. Both donor fits and both incumbent continuations passed independent original-domain stationarity. The selector retained the original B mode in both cases. No priors, likelihood, clock model, candidate bank, observations, source functions or original proposal disks changed. All four calls and both cases were sealed before any reference join.

| Case/state | Objective | NLL | Prior | Independent KKT | Post-seal error km |
|---|---:|---:|---:|---:|---:|
| 053 A-final donor after B fit | 25257.978628 | 24817.370040 | 440.608587 | .000050253 | 225.506325 |
| 053 B-incumbent continuation, selected | 25147.777833 | 24603.323945 | 544.453888 | .000346203 | 242.261759 |
| 059 A-final donor after B fit | 34127.816163 | 33653.690698 | 474.125464 | .000029768 | 2.729593 |
| 059 B-incumbent continuation, selected | 33803.698786 | 33200.283991 | 603.414795 | .000284863 | 333.217856 |

059's near donor lowers its embedded starting objective34241.067353→34127.816163, but still loses by **324.117376 = NLL453.406707 − prior129.289331**. The fitted donor is closer than the original training-selected A final3.673872km, but this was learned only after the paired seal and cannot determine selection. It is an accepted stationary B state with the original bank/model and a valid original disk, not a reference-seeded location. Therefore neither absence of a nearby calibrated donor nor a prior-only penalty explains the remaining distant selected mode in this specific test. Other untested starts or models remain possible.

053's donor also lowers its embedded objective25296.636530→25257.978628, yet loses by110.200794 = NLL214.046095 − prior103.845301. It remains distant and does not repair the broader current after-stage regression. Both incumbent controls reproduce the original full objectives within5e-11 and positions within numerical precision. All six original full endpoints and their original accepted/rejected eligibility remained in each selector; new nonstationary endpoints would have remained excluded. This experiment did not alter baseline histogram rows.

## Source qualification and bounded execution

The donor is each case's **original training-selected A-final endpoint at start3**, with the same source path's explicit learned high-minus-low shifts. The component preserves its common-clock function and satellite timings, embeds shifts in B's centered group coordinates, and rebases receiver intercepts by high-fraction times shift. A-final nuisance alone would omit the fixed shift and was not used as a complete correction. No reference, clipping, alias relift or candidate reselection entered the transfer.

Both actual case qualifications passed before any fit:10 objective evaluations,4 explicit orbit calls,0 optimizers,22.867 seconds, whole120/135/140-second bounds. Full frozen correction closure maxima were0532.183e-11Hz and0592.910e-11Hz. Prediction, visibility, spatial and timing orbit arrays all matched exactly. Effective satellite timing closure and fitter initializer adjustment were exactly0. Physical/nuisance domain margins were positive (0532.865821/1076.590631;0593.891174/1643.458923). Added original B group priors were.796484/.459227, and source/common derivative closure passed. Complete B finite-difference directional errors were5.342e-7/1.440e-5.

The paired fit run completed in24.722 seconds including authority checks and preparation, exactly4 optimizer calls, one worker, whole180/195/200-second bounds. Each original B call retained20 seconds,600 iterations and its original25km proposal disk. Actual optimizer times were053 donor1.326s/control.096s;059 donor2.476s/control.197s. No time-cap failure, retry, extra-budget polishing or recentering occurred. Source A upstream work was six three-stage paths (18 original calls per case), and this intervention added two B calls per case; it is an extra-budget mechanism test, not a matched end-to-end replacement of the six original B fits.

## Remaining supported hypothesis

For059, the root issue now lies in **likelihood/association ranking among genuine accepted physical modes**, rather than simply a missing nearby training-derived seed. The previous frozen full/half audit showed strongly coupled calibration and orbital-timing states and nearly universal satellite changes among rows assigned signal in both fits. This donor experiment introduces a distinct nearby stationary full B mode, and its prior is lower, yet its NLL is worse. It strengthens the likelihood-ranking evidence; it does not prove a detector model bias, correct satellite identities, or failure of every possible global search.

059's donor has **better conditional posterior RMS119.906Hz versus121.843Hz**, but lower signal mass1185.466 versus1313.123 windows (127.657 fewer) under the same observations. Thus conditional frequency residual alone does not explain the likelihood ranking and cannot imply accuracy. For053 these values are donor128.219Hz/893.564 signal mass versus control125.009Hz/950.462. Signal/clutter masses are model probabilities, not truth labels.

A concrete next **zero-fit** discriminator, not launched here, is to decompose the unchanged Hard60 NLL at the two sealed059 endpoints into its conditional top-one detection/visibility normalization and residual-mixture terms, grouped by receiver and band; retain candidate occupancy, signal/clutter mass and window score differences. Its source computes `log_p0 = -clutter_rate + visible_count*log1p(-detection_budget/bank_count)` and conditions on at least one detection before summing signal-plus-clutter density. This would determine whether visibility normalization or low-density/missed signal rows dominate the453.407 NLL gap. It would also identify training-only score groups for a later calibrated detection/association hypothesis. No prior relaxation, score change or further fit follows automatically from that audit.

## Receipts

Source/protocol commit937b7be31. Fourteen tests passed, including synthetic physical/gradient/domain qualification, malformed support, wrong group derivative rejection, failed qualifier preservation and zero-fit gate, exact four-call accounting, original eligibility, unexpected optimizer-return receipts, no retry, preseal reference exclusion, metadata-only freeze, and the reused original real-fitter test. Ruff passed. Original scientific modules were unchanged.

Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-sequential-donor-control-v1`:

- qualification SHA256 `51fa8c0c2d5fdd1e54abcec90db99540f348fcf7906506e63a9a99c779a62ff1`
- qualification seal `520ce356834f71db3373ac4c88eb9fd58eb699f85e33dff1c5651717a2595587`
- paired terminal `ec84570aac96e122753c346e1230f56e986047f5fbc8d0bd8840311bf7fb7f39`
- paired scientific seal `f4c4f1efebe4a14af14a789165e85b3469b157ab8f9f9bcdd897664ec0a8724a`
- post-seal `evaluation.json` records both donor/control errors and the unchanged training-selected result; it performs no optimization.

The sub-km and full-versus-both-halves targets remain unmet. No additional fit is launched or recommended for repeating this donor test.
