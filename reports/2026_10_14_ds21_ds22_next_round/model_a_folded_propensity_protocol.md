# A035/A053: qualified folded port and proposed final-stage propensity control

The existing folded observation port is compatible with A's final model and preserves its frozen learned high-band shifts. The native C propensity wrapper is not compatible. Actual zero-fit qualification passes on both current A families; no propensity fit has been run or authorized by this report. The proposed fitting stages below require their own frozen protocol and source review.

The end-state aim remains better CH1–8 position accuracy with honest half-band comparisons. This check concerns a remaining frequency-likelihood assumption, and cannot establish better localization from lower frequency loss alone. A's sequential low/high stages are not independent half-band localization pipelines.

## Exact architecture and completed qualification

Both actual models are `GroupCalibrationObjective` around `JointClockObjective` / `Hard60Objective`, with folded CFO period **227272.727273 Hz**, σ=125 Hz, 18 common-clock coefficients and **zero free group coefficients**. The conditional-high stage's two learned uncentered receiver shifts are already fixed in the final baseline. A uses one folded measurement per observation and the Hard60 singleton clutter/satellite event likelihood. It does not have C's native branch families, lifted receiver offsets or `NativeReceiverClock` layout.

The immutable `model_b_observation_cv.ObservationModel` explicitly accepts this folded base and empty group layout. It preserves A's original calibration, fixed-shift baseline, clocks, observations, orbital predictor, priors and source fitter. The reused module name does not turn the experiment into B or add native C evidence. Its three relevant arms are:

| Arm | Folded frequency density | Extra parameters |
|---|---|---|
| legacy | Original joint-event density | none |
| conditional | Original density divided by its integrated selected-CFO mass | none |
| detectability | Conditional folded density with catalogue-specific detection probabilities | K−1 zero-sum coefficients |

The learned probabilities use the existing budget-constrained logistic port: `q_k = logistic(a + Z_k θ)` with the intercept solved so **Σq=1.6**, retaining the original full-bank budget. They do not use the native C softmax/clutter parameterization. At θ=0 they exactly recover the uniform-q conditional arm. The existing θ prior is N(0,1), coefficient box ±2 and fitter scale .5; these are inherited, not tuned against these cases or position truth. No additional dispersion/RF/clock model is introduced.

Actual families are the training-selected **fixed-55 union/locked-high A035** and **fixed-59 union/locked-high/expanded-50 km A053** states. They are separate from the historical replaced-bank after results and the original union/original-high pilots. [Complete actual qualification receipts](model_a_folded_propensity_qualification_results.json) bind their exact scientific parents and source `a5d815c70`.

| Certificate | A035 | A053 |
|---|---:|---:|
| Catalogue size | 55 | 59 |
| Source objective/NLL/physical gradient/clock gradient/posterior deltas, legacy full view | **all exactly 0** | **all exactly 0** |
| Zero-q conditional objective/gradient/posterior deltas, full and two parity masks | **exactly 0** | **exactly 0** |
| Maximum normalization-identity error | 5.457e−12 | 1.137e−12 |
| Maximum nonzero-tail q finite-difference error | 9.751e−8 | 7.832e−8 |
| FD coordinates | all 54 | all 58 |
| Actual objective evaluations | 122 | 130 |
| Scientific qualification seconds | 2.562 | 2.222 |

The exact call inventory is `2K+12` per case. Eight owned compatibility/qualification tests and Ruff pass, including the real folded predictor/likelihood, locked-shift preservation, excluded-measurement isolation, source-fitter tail labels and public serialization/no retry. One bounded synthetic fixture fit checks fitter metadata; **zero fits were made on the actual recordings**. No frozen numerical source was edited.

The two qualifiers ran in parallel, outer wave147 **5.515 seconds**, each within 120/135/140 seconds internal/TERM/KILL. The arbitrary nonzero test coefficients are deterministic `0.1*sin(1+i)`, not learned estimates. Priors and actual RF mappings remain unchanged. Original held/locked data and reference coordinates are not used.

The qualification's `floor(time/20)%2` masks are **numerical oracle checks only**, not randomized validation. Their A035 populations are 1891/1016; A053 populations are 873/997. They are not silently relabelled as the randomized folds proposed below.

## Proposed fitting stage: randomized conditional development CV

This is a concrete proposal for review, not an executed fitting protocol.

1. Retain each current family's exact bank, native receive times, folded observations, fixed learned high shifts, full-training RF/time frame, clock nodes, priors and original disk (**035:25 km; 053:50 km**).
2. Use two training-derived fixed XY roles per case: the current accepted full endpoint, and its own inherited low-stage geography. A contributes no independent high-geography role. Both starts use the current full endpoint's identical **complete non-position vector and clock state**; θ starts at zero. Taking low-stage XY does not import its differently centered calibration coefficients.
3. Randomize whole original **20-second blocks** reproducibly with seed **20261014**, using the shared pure port `model_a_randomized_block_folds.split(times_s)` (source `413560688`, seven component tests). It sorts unique `floor(time/20)` group IDs, permutes once with `default_rng(20261014)` per case, and alternates the permuted groups into folds. Save the complete block→fold mapping and exact window IDs before fitting, shared by both positions/all models. Do not redraw for fit, frequency score, support or error. Keep simultaneous/correlated receiver windows in the same group. Unsupported units remain explicit rather than triggering another split.
4. Qualify these exact randomized masks and both exact XY/common-state plans before any fit. The completed parity qualification establishes port correctness but does not substitute for this plan qualification.
5. Fit all three arms independently from that common state at fixed XY, preserving original fitted-`c` freedom. **2 cases × 2 folds × 2 positions × 3 arms = 24 new calls maximum**. Each call keeps 20 seconds / 600 iterations and independent strict KKT ≤0.001. A case/fold/position unit has three calls, bounded to 120/135/140 seconds, with ≥30 seconds remaining before admitting a call. No retry, failed-fit fallback, hidden alias repair or new geography proposal is allowed.
6. Seal every prescribed outcome before opposite-fold prediction. Report each arm's raw event NLL, conditional-CFO NLL, integrated emission mass, receiver/band/block results and common/relative timing, clock and θ penalties separately. Aggregate only complete accepted matched fold pairs, and retain all failed predictions as explicitly ineligible diagnostics. The direct q effect is **detectability minus conditional**; legacy versus conditional isolates normalization. Do not compare their MAP objectives as though they were one likelihood.

Full-training discovery, bank, initializers, fixed learned shifts, clock nodes and both geographies leak information into these folds. This remains **conditional development CV**, despite randomized group assignment. It is not untouched validation or an independent half-band localization result. No original held or locked observations, configured position reference, or RF collection is part of this proposed stage.

## Preserve complete fold states before any later full-training claim

The B059 evidence rules out treating one common-start q failure as decisive model evidence. Root found a much lower full-training objective at a fold-trained near state than at the common-start selected far state; continuing that **complete** fold state later reversed training selection. The successful state carries geography, timing, RF, clock, group and propensity coordinates together. Resetting its non-geographic coordinates would discard the relevant basin. Lower cross-fold frequency loss also did not by itself establish correct position.

Accordingly, a later full-training A stage must retain, for **each fixed position and each own model**, the common source start **and every accepted complete fold-trained state**, including its full physical vector, clock nuisance and θ tail. The full-training bank, calibration frame and catalogue basis are identical, so transport is exact; validate physical constraints and original disk without projection. Nonstationary fold endpoints are not silently admitted or retried. No best-by-reference, best-fold-only or non-position reset is permitted.

An explicit optional follow-up would profile **conditional and q** models at both prescribed positions from the common source and both accepted fold states: **at most 24 further calls** (2 cases × 2 positions × 2 models × 3 starts), each retaining 20 seconds / 600 iterations and strict fixed-position KKT. This cost is additional to the 24 CV calls. Profile/rank only within each own full-training likelihood. Keep normalized-control and q costs matched, retain original incumbents as separately named baselines, report any feasible zero-tail baseline with lower objective than the q result, and preserve all failures. Such a follow-up requires separate review after the CV results; it is not automatically launched by a positive or negative fold score.

Neither stage authorizes a free-position fit or position-reference evaluation. Any future release must retain source-domain bounds, complete nuisance starts and a newly prespecified matched control, seal first, then report frequency evidence separately from accuracy.

## Remaining sequential-A disconnect

These controls hold the high-band contrast at a point estimate; `group_count=0` remains deliberate. They do not propagate uncertainty or multiple alias-compatible modes of the learned shift. A053's inherited RX1 shift is exactly at +ALIAS/2. If final-stage q sensitivity fails, repeating native-likelihood adapters cannot fix that architectural assumption.

A distinct next causal direction would first inspect the original conditional-high likelihood's one-dimensional receiver-offset profiles, including branch boundaries and training-block stability, while preserving the low common/timing function. Any uncertainty-aware final model must then use the original shift prior/data exactly once: inserting a high-data posterior as a new prior and scoring the same high data again would double count evidence. It must be declared as a new A model, rather than silently freeing the frozen shift or calling a centered group coefficient the same object. No uncertainty propagation or additional fit is implemented or authorized here.
