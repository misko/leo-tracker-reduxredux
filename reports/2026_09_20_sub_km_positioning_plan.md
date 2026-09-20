# Toward sub-kilometre Doppler positioning: review and experiment plan

**Reference resolved (September 20):** the user confirmed all scanner data at 37.84903264307456°, −122.4856541910174°. Re-evaluation puts the historical nominal “669 m” fit **1.76 km from the antenna**, and the current “4.14 km” fit **5.43 km away**. The review below preserves the historical claims and qualifications; the [matched replay report](2026_09_20_matched_positioning.md) supersedes their absolute-accuracy interpretation.

Reviewed against remote main `029bb1bd`; the two new September 20 studies were then published as `faf42c5b` and `cff42f9b`. This document is a research plan, not an implemented positioning improvement. No capture or production changes are required for the first experiments.

## What the earlier reports actually achieved

| Report / experiment | Position result | What matters for a sub-km target |
|---|---|---|
| [September 7 eight-hour study](2026_09_07_eight_hour_scan_tracking_and_positioning.md), 19-scan pooled nominal TLE fit | **669 m** | Satellite selection used the configured site. No known-site orbit correction in this nominal fit. Useful conditional precedent, not blind positioning proof. |
| Same cohort, known-site orbit-timing calibration | **292 m** | Calibration used the answer. Demonstrates a potential benefit of external calibration, not independently achieved location accuracy. |
| [September 7 continental search](2026_09_07_blind_regional_doppler_positioning.md), 5,000 km square | **1.805 km**, unknown height; **2.179 km**, fixed height | Unknown satellite identities; nominal orbits. Whole-region 50 km sampling recovered a good basin that coarser searches missed. |
| [September 15 10 MS/s convergence study](2026_09_15_rx0_10msps_position_convergence.md) | **6.79 km** after eight hours | More data strengthened the geographical mode without removing bias. Fewer independent RF segments than the earlier low-rate study. |
| [September 15 limit diagnosis](2026_09_15_rx0_10msps_detection_and_position_limits.md) | Best RMS gate only **6.64 km** | Tightening RMS or elevation gates often reduced residuals but worsened location. 275/286 local catalogue assignments remained unchanged near the reference. |
| [September 20 wide-prior study](2026_09_20_sky_48h_location.md) | **4.14 km** FoV-assisted; **2.43 km** strong-ID conditional | Different identity/selection assumptions materially change the answer. The FoV was learned from site-conditioned matches. |
| [September 20 error budget](2026_09_20_doppler_error_budget.md) | **42 m** ideal bound / **70 m** synthetic fitting RMS at assumed 60 Hz independent noise | Conditional noise limit is far below observed bias; not a prediction of absolute performance with uncertain TLEs and timestamps. |

The [continental synthesis](2026_09_07_continental_positioning_synthesis.md) explicitly distinguishes the 669 m, 292 m and 1.805 km claims. The old reports used chronological TLE evaluation partitions; those historical results remain labelled as such. New replays must use the current deterministic randomized partition, without restoring chronological TLE gates or polynomial/wrong-time vetoes.

Two other historical findings matter. The [August 27 tracking/PNT synthesis](2026_08_27_satellite_tracking_association_and_pnt_synthesis.md) found that additional nuisance freedom can worsen identifiability and recommended carrying uncertainty and calibration authority explicitly. The [August 22 phase/Doppler comparison](2026_08_22_pnt_phase_doppler_comparison.md) did not establish carrier-phase continuity across seconds: its longest strict episodes were only tens of milliseconds. Existing phase code is therefore a measurement-refinement avenue, not an already available centimetre-positioning shortcut.

## First settle what “sub-km” means

Distinguish a score-map cell smaller than 1 km, a local precision estimate below 1 km, and an actual position within 1 km of an independently established coordinate. Our target should be **the third**, accompanied by uncertainty and repeated independent scan-group results. The current noise model already predicts sub-km precision; that is not the missing achievement.

There is an immediate reference issue: the earlier continental evaluation point was **37.8490428024417°, −122.48567437412359°**, while later reports used **37.858988°, −122.478103°**. They are **1,290.27 m apart**. Neither report establishes that this is explained by a receiver relocation or which coordinate has survey authority for every capture. Bind the actual antenna location, time validity and altitude datum to each recording interval. Do not select a reference because it agrees with the output. Numerical research can continue, but a sub-km absolute-accuracy claim needs this resolved.

## Direction A: reproduce the 669 m result and isolate what made it work

This is the highest-value matched comparison. It uses an existing successful conditional result rather than inventing a new estimator first.

1. Reproduce the published nominal 19-scan pooled fit from its sealed inputs and preserve the result as a historical reference.
2. Replay the same RF points under randomized partitions and the current solver, retaining historical versus new partition provenance separately.
3. Build a controlled matrix: older/current RF cohort × historical/current selection and grouping policy. Keep reference, fixed-height convention, offset model, TLE epoch policy and RMS definition explicit; do not treat changed recordings as a sample-rate ablation.
4. Isolate the old “longest passing episode per distinct NORAD per scan” selection, channel-consistency checks, upper/lower evidence combination and pass weighting. Keep separate source offsets when sharing physical Doppler dynamics.
5. Run both a labelled fixed-ID conditional arm and a location-blind identity-search arm. Any benefit from known-site satellite selection must remain visible.

**Decision:** if the same solver reproduces 669 m but the current cohort remains biased, prioritize data selection, timing/orbit state and geometry. If the same frozen old observations change substantially under the new solver, investigate that numerical/model difference before adding measurements. A better conditional result is useful but does not close blind identification.

The new pass experiment forced one constant across channels and failed at roughly 78.5 kHz RMS. That does not invalidate the earlier successful sharing of dynamics with **separate** per-source constants. These are different hypotheses; do not discard joint multi-channel fitting because the over-constrained constant-offset model failed.

## Direction B: identify the common bias with constrained, interpretable parameters

Use the current 599-track cohort and the historical nominal cohort as two independent diagnostic cases.

**Timing authority first.** Inspect retained first-sample bindings, firmware timestamps, host clock records and per-scan uncertainty intervals. Distinguish absolute UTC offset, host/device binding error, device sample-clock scale and satellite orbit-phase error. They must not share one arbitrary “time offset” parameter. Our current exact-state sweep shows roughly 6.7 km/s local east-position sensitivity to shared UTC; a 50 ms error can therefore correspond to about 0.34 km in this geometry. This motivates testing tens-of-milliseconds timing knowledge, not applying a fit-selected clock correction. Even −0.5 s leaves about 3.2 km northward displacement.

**Attribute the residual before adding freedom.** Project each pass's residual onto independently calculated east/north, UTC, orbit-phase and RF-scale derivatives. Examine the design matrix's small singular values: if two corrections cannot be separated, report their ambiguity instead of presenting a precise corrected position. Plot inferred pulls by satellite, TLE snapshot/age, scan, channel, sideband and pass direction. The previous eight pass-fold deletions are too coarse to identify a particular satellite or catalogue snapshot causing a shared pull.

**Use complementary geometries.** Compare pass-direction groups and leave-one-satellite and leave-one-snapshot fits. A timing error and a fixed receiver displacement do not produce identical signatures across arbitrary pass directions. Direction-dependent motion of the fitted point would provide a useful diagnostic; absence of it would not prove perfect timing. Select geometry with a projected information matrix, not merely elevation or lowest RMS.

**Fit a constrained hierarchy only if supported.** Candidate parameters are one UTC offset per scan bounded by recorded authority, receiver frequency behaviour shared over justified intervals, and satellite orbit corrections shared across repeat passes with independent priors. Retain per-source frequency constants. Include a gauge convention and nuisance/position covariance. The tested free segment and shared scan drifts reduced RMS while worsening position, so neither should be adopted simply because it fits better. Satellite/transmitter oscillator and receiver/LNB effects are not necessarily separable from one opportunistic receiver.

**Decision:** a correction needs a physical record or repeatable cross-pass signature, stable position across independent groups, and nuisance parameters away from unphysical limits. Being closer to the reference on the dataset used to tune it is not sufficient. Retain uncorrected results beside every corrected fit.

## Direction C: recover more independent geometric information from existing IQ

**Reconstruct longer same-lane trajectories.** The current longest-representative export cannot test all discarded fragments. Revisit the full GLRT candidate graph with RF-only joins, explicit alias choices, actual device times and retune boundaries. Preserve frequency offsets unless continuity is demonstrated. Prefer several surviving association alternatives to a forced long track. No interpolation across missing IQ should be counted as a new observation.

**Use more samples within retained visits.** On a bounded, diverse selection of stored passes, compare the current GLRT probes with additional non-overlapping probes or a joint physical-frequency fit across valid support. Measure frequency consistency with independent windows. Overlapping estimates share samples and must not inflate the effective count. Do not assume coherent phase across the hop or frame boundaries that failed historical continuity tests.

**Combine channel information through shared Doppler shape.** Link supported upper/lower or cross-channel observations while retaining channel-specific constants, RF normalization and independent ambiguity hypotheses. Where normalized Doppler cancels between the same satellite's lanes, the difference can diagnose differential hardware/transmitter effects; it is not an additional independent position observation.

**Balance by pass and geometry.** Tracks ≥30 s supplied about 64% of the ideal information trace from 37% of the current tracks. Favor useful length and complementary direction, but do not permanently select 30 s because that exploratory subset happened to approach the reference. Weight correlated lanes together and test sensitivity to one satellite/pass dominating the fit.

**Decision:** demonstrate improved frequency/association consistency at matched observation times, then show that the location result is stable across withheld pass groups and sample rates. Every TLE comparison inside those groups continues to use randomized partitions. Sample-rate comparisons must use the same native IQ with derived lower-rate streams to establish causality.

## If software-only replay does not get below 1 km

A known-location reference receiver observing the same spacecraft is the clearest architectural fallback for separating some transmitter and orbit-related errors from unknown receiver location. Its benefit depends on shared visibility, timing and baseline, and needs a different experiment. Archived surveyed reference observations would suffice for an initial replay if available. The current single-radio corpus cannot manufacture them.

Similarly, better independent orbit products and antenna pointing authority would strengthen the solve. Tighter FoV cuts alone have already failed to remove the bias. PSS precision is not absolute range without transmitter timing and ambiguity authority. Freeing height or fitting orbit parameters until the reference is reached would hide rather than solve the problem.

## Order and completion criteria

1. Reconcile capture-specific reference coordinates and reproduce the historical 669 m nominal result.
2. Run the matched old/current solver and cohort matrix; identify whether evidence selection or modelling accounts for most of the difference.
3. Audit recorded UTC and perform satellite/snapshot/channel/direction influence diagnostics.
4. Test longer RF-only trajectories and source-balanced shared dynamics with frozen selection rules.
5. Freeze the winning policy and evaluate independent scan groups; keep randomized within-track TLE evaluation. Report every result, median/tail horizontal error, failure rate and uncertainty coverage.

The first milestone is an independently referenced, reproducible **<1 km horizontal-error result without using that reference to select identities or calibrate orbit/time parameters**. A later operational claim needs repeated results and a justified coverage target, such as 95% within 1 km. No existing report demonstrates that operational guarantee. The 669 m precedent and the much smaller conditional noise bound make the target worth pursuing, but neither guarantees that the present TLEs and single-receiver data suffice.
