# CH5–8 temporal guidance and frequency continuity

Date: 2026-10-26. Bounded development study on existing DS24 recordings.

We implemented and evaluated the proposed work with three **SOL xhigh** workers. This iteration produced **no qualified new natural measurements and no demonstrated position improvement**. It identifies two limitations: consecutive detections are too sparse for the tested three-visit predictor, and a frequency estimator that helps some clean synthetic signals does not consistently improve recorded-background recovery. The current localization algorithm remains unchanged.

This is a completed development screen, not an ALGO promotion or a full DS24 benchmark. There was no new RF collection, production modification, or post-scan TLE use.

## Plan, delegation, and delivered work

| Worker | Question | Delivered implementation | Result |
| --- | --- | --- | --- |
| SOL xhigh: causal revisit guidance | Can earlier same-channel detections predict a later weak signal? | Frozen metadata-only panel; three-visit timing/CFO predictor; constant-carry control; original acquisition replay; disjoint target-half scoring | 5/96 receiver cells have compatible histories; neither forecast confirms a target |
| SOL xhigh: frequency estimation | Can a donor-informed estimator avoid final frequency-bin jumps without freezing genuine Doppler evolution? | Complex pilot likelihood with per-frame amplitude profiling, broad donor prior, preserved frequency modes; synthetic, null, and recorded-background controls | Helps a strong synthetic evolution case; 3/16 accurate recorded-background recoveries versus 4/16 unchanged |
| SOL xhigh: independent qualification | Is recovered evidence independent and reliable enough for localization? | Provenance and native-sample ownership audit; correction/new-detection adapter; matched c-arm baseline replay; independent qualification decision | No candidate approved; all eight unchanged baseline endpoints replay exactly |
| Primary agent | Are the conclusions supported and reproducible? | Interface coordination, source/result review, interval-reporting bug review, integrated report and publication | Preserve the negative result and specify the next bounded experiment |

The first two tasks ran concurrently. Qualification depended on their sealed outputs. One worker used a child agent; the session's child-thread limit required two separate user-authorized background tasks for the other workers. All three used `gpt-6.1-sol` with `xhigh` reasoning. Exact identities and the original plan are in [ORCHESTRATION.json](ORCHESTRATION.json) and [PLAN.md](PLAN.md).

## 1. Natural revisit guidance: the history requirement is the first bottleneck

The fixed panel contains DS24-0010 through DS24-0013, CH5–8 and CH1/4 controls, two consecutive target visits near each scan's midpoint, and both receivers: **48 paired windows / 96 receiver cells**, 16 cells per channel. Target selection used channel metadata and sample counters, not target scores, satellite identities, or GPS. Each target used exactly the preceding three same-channel/receiver/edge visits. Missing and ambiguous histories remained in the denominator.

All **48/48** raw windows reproduced the original exported acquisition candidates exactly under the historical runtime. The raw stage took **82.18 seconds**. Earlier-only predictions were sealed before the new target scores.

| Channel | Latest earlier visit has a donor | At least 2 of 3 visits have donors | All 3 have donors | Compatible three-visit history | Confirmed target |
| --- | ---: | ---: | ---: | ---: | ---: |
| CH1 | 5/16 | 4/16 | 2/16 | 1/16 | 0/16 |
| CH4 | 5/16 | 0/16 | 0/16 | 0/16 | 0/16 |
| CH5 | 5/16 | 5/16 | 1/16 | 1/16 | 0/16 |
| CH6 | 4/16 | 8/16 | 3/16 | 3/16 | 0/16 |
| CH7 | 3/16 | 2/16 | 0/16 | 0/16 | 0/16 |
| CH8 | 2/16 | 4/16 | 0/16 | 0/16 | 0/16 |
| Total | **24/96** | **23/96** | **6/96** | **5/96** | **0/96** |

The first two availability columns are not nested: two earlier visits may have detections while the latest visit has none. Five eligible cells contain eight alternative candidate histories; these are not eight independent signals. The other 91 cells are unavailable, not discarded successes or failures.

![Earlier natural detection availability by channel](revisit/opportunity_funnel.png)

The actual revisit gap is about **0.354 s**, much longer than the adjacent 10 ms split used in the earlier synthetic demonstration. The eight compatible histories have apparent CFO slopes from −3856 to −2596 Hz/s. Their linear target prediction differs from carrying the latest CFO by about **993–1394 Hz**. This is a warning against blindly carrying a frequency across a real revisit, but there is no external identity truth establishing that each history belongs to one physical signal.

![Apparent CFO and timing evolution of the eligible histories](revisit/natural_drift.png)

Each forecast was tested at one predicted timing/CFO point in each disjoint 10 ms target half. The public conditioned GLRT retained its normal residual-frequency profiling. Confirmation required both margins at least 0.025 and inter-half CFO difference at most 100 Hz. **Neither constant nor linear prediction passes both margin gates for any eligible history**, before the frequency-agreement requirement matters.

The integration audit also found a reference-time limitation in the unused natural frequency packets: their second half keeps the target-start CFO prediction rather than adding the next 10 ms of fitted rate, an omitted change of about 26–39 Hz. No natural frequency estimator consumed these packets. A future experiment must propagate timing and CFO to a declared sample time consistently; this limitation does not turn the failed support screen into a success.

![Disjoint-half support from constant and linear forecasts](revisit/target_support.png)

This is specifically a negative result for **three preceding visits plus a point timing forecast**. It does not establish absence of natural signals or failure of every form of temporal guidance. The heuristic timing width is about eight samples, but this experiment did not search or integrate over that uncertainty. Across the whole panel, 26/96 original targets have a detection, and 11/96 have both a target detection and a latest-earlier detection; none of those eleven is in the five three-visit-eligible cells. These descriptive counts motivate a separately frozen shorter/sparser-history experiment, not a retrospective change to this one.

The predictor excluded target responses. The original full-window target acquisition was already present in archived data and used for parity and descriptive evaluation; this was not a previously unseen validation set. Adjacent targets also share donors. Disjoint target halves provide conditional support checks, not independent satellite identity truth. Full methods, counts, sources and plots: [revisit/FINDINGS.md](revisit/FINDINGS.md).

## 2. Frequency continuity: a mechanism benefit did not transfer to recorded backgrounds

The prototype profiles an unknown complex amplitude separately for each frame using known-pilot symbol correlations. It evaluates a 25 Hz grid over ±3000 Hz, estimates noise from within-symbol orthogonal residuals, and combines the later-data profile with a broad earlier-donor prior. Alternative modes and the raw later-data profile are retained. The public GLRT gate is unchanged.

The prior is 90% Gaussian plus 10% uniform, with uncertainty enlarged for elapsed time. Complex white noise is an explicit working model; recorded interference, interpolation, timing error and donor ambiguity can violate it. A donor-conditioned posterior cannot be inserted as a fresh independent Doppler point when its donors already contribute to localization. The later-data profile excludes the donor prior but is still conditional on the donor-proposed timing, frequency center and search domain.

| Known-truth development test | Unchanged final-bin estimate | Carry earlier frequency | Proposed estimate |
| --- | ---: | ---: | ---: |
| Strong synthetic signal, unbiased donor, nonzero evolution, zero-rate forecast | 0/16 within 100 Hz | 0/16 | **14/16** |
| Weak synthetic comparisons, all tested forecasts and donor errors | **78/144** | 16/144 | 75/144 |
| Injected signal on the same recorded backgrounds as the preceding study | **4/16** | **11/16** | 3/16 |

Here, “unchanged” means the existing frequency-bin scorer at the same donor-conditioned timing/CFO, not blind acquisition. The synthetic sweep tests both signs of true frequency evolution and donor error. Its 288 comparisons reuse 48 independent later noise vectors across forecast/error alternatives. The correct-rate forecast is a labeled oracle mechanism control, not evidence that a causal predictor estimates the rate correctly. The strong zero-rate-forecast result shows the estimator can follow genuine evolution rather than merely return its donor. Its weak-signal and recorded-background results do not support deployment.

The recorded-background test has known injected-signal truth but remains a synthetic injection into actual recordings. Its donor/target separation is 10 ms, not the 0.354 s natural revisit. One of 16 receiver cells has no usable donor; it stays in the recovery denominator. Only 15 have proposed uncertainty intervals. The natural branch stops at its failed support screen, with no subsequent natural frequency-estimator calls.

![Recorded-background frequency errors and recovery counts](frequency/recorded_frequency_errors.png)

Frequency figures use native receiver IDs 0 and 1, corresponding to displayed RX1 and RX2. The frequency branch provides all synthetic strata and conditional-profile plots in [frequency/FINDINGS.md](frequency/FINDINGS.md).

There is a narrower positive result: on the eleven recorded-background cases whose primary donor is correct by injection truth, CFO RMSE falls from **350.1 Hz to 179.2 Hz**. Carrying that donor gives 16.3 Hz on this constant-frequency injection. The subset is identifiable only in evaluation, not by the operational estimator, and fewer than 100 Hz recovery does not improve overall. Thus smaller errors in this subset do not qualify a natural measurement or establish lower position error.

### Interval reporting correction

Review found that the original interval code interpolated cumulative grid mass at grid centers. This can shift reported quantiles downward even for a distribution concentrated at one grid point. The frozen estimator and outputs were preserved. A separate offline audit recalculated intervals using both literal discrete masses and uniform density within midpoint bins. **No frequency estimate, likelihood, prior, gate, or RF call changed.**

| Nominal 95% interval coverage | Frozen original reporting | Midpoint-bin density interpretation | Discrete-mass interpretation |
| --- | ---: | ---: | ---: |
| Synthetic comparisons | 267/288 | 262/288 | 267/288 |
| Recorded-background cases with a donor | 11/15 | 10/15 | 10/15 |

Neither numerical convention establishes calibrated uncertainty on natural RF. The interval correction is reported separately from model mismatch and does not rescue the estimator's frequency-accuracy result.

Null controls produced zero confirmations in each 64-trial primary and three-proposal stratum. These counts assess the unchanged conditioned GLRT gate, not posterior frequency correctness. The one-sided 95% upper bound is still about **4.57% per searched null target**. That small experiment cannot establish a low family-wise false-confirmation rate for a 96-cell search; this is insufficient evidence, not a measured natural false-positive rate. Details and compact per-trial results are in the frequency branch report.

## 3. Integration and the matched c ablation

The research adapter distinguishes a correction to an existing native observation from a genuinely new detection. It checks raw sample ownership, receiver/channel/band/actual RF, aliases, source hashes, donor overlap, and the independent qualification receipt. Multiple candidate modes from one raw target never become multiple independent observations. A donor-conditioned posterior is rejected as a fresh likelihood factor; future integration needs either a target-only likelihood or a joint dependence model.

The unchanged authority is **ALGO02-v1 plus the qualified causal signed phase prior and equal-prior family cavity**, using the frozen DS25 study engine and its DS24 case artifacts. The four-scan baseline was replayed at its saved endpoints in both c=0 and fitted-c arms. Observation masks, candidate sets, aliases, other model priors and regional search settings were matched. **All eight objective differences are exactly zero.** The table below records frequency-fit reproduction, not a new position estimate or a claim that fitted-c improves accuracy.

| Scan | Position-likelihood points | c=0 residual RMS (Hz) | Fitted-c residual RMS (Hz) | Objective replay difference, both arms |
| --- | ---: | ---: | ---: | ---: |
| DS24-0010 | 3186 | 91.588 | 91.489 | 0 |
| DS24-0011 | 2241 | 82.142 | 81.991 | 0 |
| DS24-0012 | 3231 | 73.038 | 72.949 | 0 |
| DS24-0013 | 3784 | 82.511 | 82.500 | 0 |

Post-fit-only associations are excluded from the position-likelihood count. In DS24-0011 those post-fit counts differ between arms; the actual position observations remain matched. Model precision matrices may also differ with the c parameterization and saved endpoint, without changing the matched data and base priors.

The independent decision is **do not advance to localization**: no supported natural target, no calibrated natural likelihood uncertainty, insufficient natural search-null evidence, and unresolved donor dependence. There are **zero admitted corrections and zero new detections**. No new regional search or position-error comparison was run. An empty candidate set preserves the existing baseline rather than manufacturing a geographic result from unqualified evidence. See [validation/FINDINGS.md](validation/FINDINGS.md), [validation/qualification.json](validation/qualification.json), and [validation/baseline_audit.json](validation/baseline_audit.json).

![Independent qualification and unchanged matched c-arm replay](validation/validation_summary.png)

The regional inference contract remains a 25×25 km box centered at 37.906, −122.545. The known site 37.849061591561885, −122.48574968092912 is reserved for final evaluation; it did not select or qualify RF hypotheses. No assumption of stationarity across scans was introduced.

## What to try next

The useful change in understanding is that CH7/8 cannot benefit from a predictor that requires three consecutive successful detections when that history is absent. Better frequency estimation alone also does not solve missing timing support.

1. **Make causal guidance tolerant of missed visits.** Freeze a new, broader metadata-selected panel. Permit nonconsecutive earlier donors in a bounded history, retain multiple timing/CFO hypotheses, and compare one-donor, two-donor and three-donor forecasts at matched search exposure. Separate opportunity coverage from conditional success. Do not select targets using the eleven already-observed overlaps above.
2. **Test timing uncertainty explicitly.** Compare the point forecast with a small predeclared timing search or marginalized timing likelihood, accounting for all searched proposals. Determine whether a failure is missing signal, wrong donor, or timing error. This is a hypothesis prompted by the current uncertainty width, not a demonstrated fix.
3. **Validate the target-only frequency profile on recorded backgrounds.** Preserve the strong synthetic evolution control, but require improvement over both unchanged estimation and donor carry on weak recorded signals, with uncertainty and false-confirmation calibration. Carry-only can be a prediction; it is not a new RF measurement.
4. **Propagate only qualified additional evidence.** Rebuild tracks and causal satellite associations without preselected identities, then run matched c=0/fitted-c regional localization. Use grouped randomized validation for any larger comparison. Measure median and tail position error separately from GLRT association percentage. A 500 m claim requires geographic performance evidence on independent scans and locations.

This iteration does not identify sample rate, receiver separation, wavelength scaling, or one satellite family as the cause of position error. It tests a narrower acquisition/measurement route to using CH5–8 more effectively. There is no basis here for a new ALGO release.

## Artifacts and reproduction

The publication contains the frozen protocols, sources/tests, compact outcomes, recorded frequency profiles, plots and hash receipts. Full synthetic/null frequency grids and baseline packets stay in the local study directory and are identified by hashes; no raw IQ is published. Branch reports give exact commands and historical runtime/source authority. The owned checks passed: 3 revisit tests, 11 frequency/mapping/interval tests, and 33 validation tests, plus the original-candidate and unchanged-objective replays. All new numerical work was bounded, used existing recordings and read-only raw access, and preserved the unrelated workspace changes.

Local study: `/srv/bulk/leo/research/ds24-ch58-continuity-r01`.

Preceding evidence: [guided acquisition and geometry study](../2026_10_26_ds24_guided_acquisition_geometry/README.md) and [per-channel coverage/wavelength audit](../2026_10_26_ds24_per_channel_audit/README.md).
