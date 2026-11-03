# Automatic local carrier segments and cold discovery

Recording: `fast8-auto-20261016-161535-99008d35-1-lower`.
This component uses the existing exported observations and pinned causal TLE archive. It does not collect RF, change production, or change the original target definitions.

The new extractor automatically recovers training segments that the existing longest-track bootstrap missed. The original five-second combined-discovery fits then fail their numerical gate. A controlled continuation shows that at least one such failure can be resolved with additional optimizer work. Full three-trajectory recovery remains unproven; track coverage must not be reported as satellite association or position accuracy.

## Extraction mechanism

`local_segments.py` has no satellite, location, calibration or target-membership input. It processes each receiver/channel/RF lane independently, using 20-second windows with 10-second stride. A deterministic set of 256 random triples proposes quadratic carrier curves, including integer frequency aliases. Hypotheses must have at least eight supporting observations over six seconds, no consecutive support gap above four seconds, and circular residuals within 300 Hz. The declared conservative proposal bounds are 20,000 Hz/s slope and 2,000 Hz/s² curvature; they are experimental bounds, not measured satellite dynamics. Up to three distinct supports are extracted per window.

The sampling initially required support in each third of the complete window. That excluded a real shorter segment ending before the final third. Uniform triples with distinct times and at least six seconds total span repair this failure; an independent synthetic interrupted-track regression test covers it.

Ranking uses curvature information relative to a 125 Hz measurement scale, with RMS and span tie-breaks. Two segments can enter each fixed 20-second time cell in a lane. A candidate must contribute at least eight rows not already represented by selected segments in that lane. Overlapping observations are deduplicated in the orbit query, and the final scan likelihood continues to contain exactly one row per original observation. These proposal groups do not themselves assert a satellite identity. A group's fraction inside the user-selected target interval is not a measured source purity: points outside that interval can be a continuation of the same signal.

The selection policy was iterated using target training-membership coverage in both development folds. No target membership enters the extractor, but the folds are not pristine external validation after that development. Subsequent carrier tests still require training-only fitting and explicit temporal holdouts.

## Measured coverage

| Fold | Training trajectory | Available points | Original combined bootstrap | Local proposals | Selected local segments |
| --- | --- | ---: | ---: | ---: | ---: |
| Forward | CH2, 50–75 s | 15 | 0 | 15 | 15 |
| Forward | CH4, 40–100 s | 37 | 35 | 37 | 35 |
| Forward | CH2, 170–190 s | 14 | 0 | 13 | 13 |
| Reverse | CH2, 50–75 s | 14 | 0 | 14 | 14 |
| Reverse | CH4, 40–100 s | 36 | 0 | 36 | 36 |
| Reverse | CH2, 170–190 s | 13 | 0 | 13 | 13 |

The final policy selects 231 forward and 232 reverse segments, taking approximately 0.56 seconds for extraction. Earlier four-slot and one-slot-per-cell policies are retained in the JSON receipts rather than silently replaced. One forward late-CH2 training point remains outside the proposals; two forward CH4 points are generated but excluded by selection.

![Training-point representation before and after local extraction](01_training_track_coverage.png)

## Bounded bootstrap work

The original bootstrap exceeded its five-second work allowance with 232 short segments, using either 12 or six samples per segment. Simply increasing proposal coverage is therefore not enough to integrate the extractor under the original runtime policy.

`fast_bootstrap.py` batches the existing independent pseudo-Huber location and shape calculations by segment sample count. Each segment retains its own original convergence test and catalogue-number/timing tie-break. At most four pure numerical timing queries run concurrently; timing cohorts are consumed in the original order. Receiver-line fitting, timing grid, robust scale and acceptance criteria are unchanged. The current research runner uses six evenly spaced samples per segment for bootstrap proposals; full observations remain in fitting.

The final reverse pilot completes all 1,035 candidates and 232 segments in **3.244 seconds**, within the same five-second allowance. Tests compare complete bootstrap candidate/timing choices, shape scores and receiver-calibration vectors against the original implementation on synthetic varied-length segments, as well as independent robust-location stopping. This establishes numerical compatibility on those fixtures, not a new physical association result.

## Discovery failure and controlled diagnosis

Two fresh v4 replays use identical derived training-input bytes, the pinned causal TLE, automatic segments and the original overall 480-second cap. Forward completes 14 discovery points and stops at 238.3 seconds; reverse completes 14 and stops at 247.1 seconds. Both are explicitly **unavailable** because three supported discovery basins could not be formed: none of the combined-band point fits passed stationarity. Individual lower/upper fits did pass. These failures are preserved in their terminal receipts.

A matched pilot uses the predeclared first reverse discovery point, (−150, −150) km in the prior chart, with the same observations, candidate bank and fixed position. It compares another 15-second optimizer allocation from the rejected combined endpoint against a seed formed by projecting the accepted lower/upper fitted calibration functions. Both treatments receive independently refitted fitted-c and c = 0 arms with identical priors and budgets, conditional on the same fitted-c band donors.

| Initialization | c arm | Accepted | Objective | Stationarity | Fit + audit time |
| --- | --- | --- | ---: | ---: | ---: |
| Continue rejected combined fit | fitted | Yes | 63,210.736 | 0.000106 | 6.09 s |
| Continue rejected combined fit | zero | Yes | 63,432.026 | 0.000855 | 6.06 s |
| Merge accepted band fits | fitted | Yes | 63,367.745 | 0.000352 | 9.05 s |
| Merge accepted band fits | zero | Yes | 64,304.405 | 0.000350 | 6.98 s |

The original rejected combined fit had stationarity approximately 1,808. Additional optimizer work closes that gap without relaxing the 0.001 threshold. Merging fitted band corrections converges too, but does not outperform continuation in this control. This is evidence of an insufficient discovery-fit allowance at this point, not proof that separate-band calibration is the missing physical term. The objective improvement is a frequency-model result at fixed position, not improved localization.

The v5 runner changes only the combined discovery fit allocation to 15 seconds and 600 iterations, retains five seconds for the separate-band fits, and preserves the 240-second discovery slice and 480-second overall cap. Consequently fewer spatial points may finish. `attempt_summary.json` records the actual terminal states and completed point counts. A terminal without an accepted endpoint does not receive a position or association performance claim.

Both v5 replays complete **13 discovery points, with all 13 combined fits converged**, but remain unavailable: the source-admission check requires 210 seconds remaining for a source and the final-fit reserve. After discovery, shape proposals and bootstrapping, that condition fails, so **no A/B source fit is attempted**. Forward stops at 276.1 seconds and reverse at 285.6 seconds. This is a scheduling failure, not evidence that the final model does or does not explain the trajectories. The accepted discovery fits cannot substitute for a final endpoint.

The v6 replay keeps the original 480-second total limit and final reserve, but reduces the discovery slice to 180 seconds while retaining the larger combined-fit allowance. This is a bounded scheduling experiment to leave time for source generation and final inference. Its actual state is recorded separately; a running attempt is not an evaluated improvement.

Both v6 cold replays finish with strictly accepted final B-all solutions, at 405.85 seconds forward and 403.69 seconds reverse. Their stationarity is 4.87e−5 and 1.00e−4, respectively. Both final banks contain all three forward-consistent candidate hypotheses. The scheduling and numerical problems are resolved for these attempts. **The trajectory recovery problem is not resolved.**

### Actual held trajectory recovery

The new cold endpoints assign **zero of the 129 held points** to the supported training-selected label for their trajectory. This is worse than the original cold endpoints on the same coherence metric: 48/63 forward and 27/66 reverse. The original reverse CH4 label is 57149, rather than the forward hypothesis 69333, so even the baseline coherence count is not independent identity accuracy. Scattered point matches to other satellites do not constitute recovery of a coherent trajectory.

![Actual frozen classifier coherence before and after](03_actual_pipeline_coherence.png)

The separate full-regional candidate/timing diagnostic yields:

| Fold | Calibration | Early CH2 held RMS | CH4 held RMS | Late CH2 held RMS |
| --- | --- | ---: | ---: | ---: |
| Forward | Original cold | 131 Hz | 136 Hz | 173 Hz |
| Forward | Local-segment cold | 2,297 Hz | 1,125 Hz | 2,401 Hz |
| Reverse | Original cold | 1,475 Hz | 388 Hz | 2,147 Hz |
| Reverse | Local-segment cold | 633 Hz | 1,080 Hz | 264 Hz |

![Conditional candidate/timing diagnostic, not automatic recovery](04_diagnostic_temporal_rms.png)

Two reverse diagnostic residuals improve, but the actual pipeline still rejects the tracks. That difference is central to the remaining failure. The new reverse diagnostic selects 69433/69333/69522 with timings −0.45/−4.90/+2.25 seconds from their training halves; it does not mean the pipeline learned or used those timings.

### Matched RF-coefficient control

Both RF arms use the same new cold checkpoint, bank, observations, frozen band contrast, priors, local continuation disk and 60/65-second work allowances. The fitted-c continuations are accepted in both folds. The independently refitted zero-c continuation is accepted reverse (stationarity 0.000859) but rejected forward (4.23). The accepted reverse zero-c diagnostic RMS is 598/1,134/260 Hz, versus 633/1,080/264 Hz for fitted c. Neither recovers the three trajectories in the actual classifier. This control does not establish a localization gain from either RF coefficient treatment, and the rejected forward zero-c result is not promoted.

### Candidate timing conflict

`timing_conflicts.py` freezes the accepted reverse cold calibration and position, then audits the three forward-consistent hypotheses using training data only. The actual score has a **3-second common timing prior and 2-second relative timing prior**; the 0.15-second default V16 prior is not the live HARD60 configuration used here.

| Hypothesis | Learned timing | Target training RMS at learned timing | Assigned training points elsewhere |
| --- | ---: | ---: | ---: |
| Early CH2, 69433 | −1.055 s | 2,070 Hz | 9 |
| CH4, 69333 | −16.547 s | 41,355 Hz | 20 |
| Late CH2, 69522 | +2.838 s | 1,745 Hz | 94 |

For 69522, 82 of those 94 other assigned points are RX1 upper-channel observations. Its learned detectability is approximately 0.0615, so simple detectability starvation alone does not explain the lower trajectory rejection. For 69333, the selected timing fits a small collection of observations elsewhere while missing the large CH4 training group. These associations are themselves conditional on the fitted model; the audit does not independently identify those observations or prove which association is physically correct.

![Training-only candidate timing conflicts](results/reverse-timing-conflicts-v2/timing_profiles.png)

The measured issue now lies beyond initial track availability: coherent observations enter source proposals, but the final point mixture can reject them as clutter while fitting a candidate elsewhere. A generic all-candidate timing basin search is the next bounded test. It must use the unchanged normalized training objective, include its visibility normalizer and exact common/relative timing prior, accept only non-worsening coordinate moves, and receive no target membership or satellite labels. A successful optimization step alone still cannot establish held recovery or identity.

That [timing search has now been implemented and evaluated](../three-track-coordinate-timing-20261016/report.md). It lowers the original objective without new parameters, passes the strict gate in all matched RF arms and restores 31/129 coherent held matches with fitted c. This remains below the original cold pipeline's 75/129. It proves an optimizer limitation at the new stationary endpoints, but does not solve the full recovery task.

![Numerical stationarity at completed common discovery points](02_discovery_numerical_gate.png)

This plot compares only completed points present in both attempts with identical candidate banks. It measures numerical convergence, not physical correctness or held-out accuracy. The source receipts distinguish the changed wall-clock and iteration allowances; this control does not separately identify their individual contributions.

## Verification and replay

The evaluator now reports the **actual frozen pipeline classifier** separately from the full-regional diagnostic satellite/timing search. The frozen classifier uses the learned candidate bank, satellite timings, calibration and detectability without fitting a correction to any inspected target. Point association uses the original maximum-satellite-posterior versus clutter comparison. A coherent reporting label is selected by total training posterior mass only; if its mass does not exceed training clutter mass, the group has no supported label and its RMS is reported as missing. It does not inherit an arbitrary catalogue label from numerical underflow. Missing groups remain failures rather than disappearing from a performance denominator.

On the original accepted reverse endpoint, the actual classifier associates 0/15 early-CH2 held points to a supported training label, 27/37 CH4 points to training-selected candidate 57149, and 0/14 late-CH2 points. CH4's frozen-label held RMS is 367 Hz. That differs from a conditional full-regional search which fits a separate candidate timing to the inspected training group; the two measurements must not be substituted for each other. Candidate 57149 is not independently identified as correct here.

Transporting the actual classifier from its training metadata to the original full inventory reproduces training posteriors to 5.44e−13 and frequency calibration to 3.82e−11 Hz. A negative control adds 1,234,567 Hz to all 66 original reverse withheld observations: training label decisions remain unchanged and training RMS changes by exactly zero. This checks held isolation for the reporting procedure; it does not validate physical identities.

Eleven component tests cover aliases with clutter, crossing trajectories, partial-window support, lane isolation, long gaps, deterministic extraction, invalid inputs, observation-preserving contract replacement and numerical bootstrap compatibility. The portable evaluator was also qualified against the original accepted reverse endpoint: its objective and stationarity reproduce exactly, and frozen calibration transport differs by only 3.64e−12 Hz.

`rerun.py` rebuilds the original declared fold from the parent export, verifies its exact input digest and archived TLE, and uses process-local overrides only. The preparation receipt pins the actual executed source hashes. Exact v4 and v5 executed source bytes are preserved in `executed-v4-sources` and `executed-v5-sources`; current runner sources include the optional larger combined-fit allowance and shorter discovery slice. Every attempt uses a new directory and is capped; no failed attempt is overwritten or silently restarted.

`evaluate.py` verifies a completed attempt's stage bindings and strict endpoint replay before any continuation. It supports matched fitted-c and c = 0 continuations on identical observations, candidate bank, priors and 60-second solver/65-second total budgets. Those controls are conditional on the same fitted-c cold endpoint and frozen band contrast. It searches satellite and timing using only each original target's training observations against the complete regional bank, then reports withheld carrier residuals. Numerical failures remain failures. No independently known spacecraft labels or geographic position is supplied, and frequency fit cannot establish kilometer accuracy.

The recovery goal remains active: the final mechanism must recover all three trajectories reproducibly and generalize across the declared held observations. Automatic segment coverage alone does not satisfy that requirement.
