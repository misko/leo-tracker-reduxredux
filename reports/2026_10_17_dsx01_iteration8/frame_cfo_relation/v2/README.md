# Circular CFO versus arrival-phase rate: local coupling, one decisive counterexample

Correct circular scoring shows substantial local empirical coupling: fixed **+RF/Fs** scaling improves **20/21 quadratic groups**, while −RF/Fs improves 1/21. On all208 odd points, however, the constant control is **0.762944 ppm**, +unit is **0.967482 ppm**, and −unit is **1.325948 ppm**. One reverse-sign S04 RX1/CH3 group dominates the pooled loss. A universal frame/carrier clock constraint is therefore unsupported, despite the positive local evidence. No clock model, orbit or localization fit was added.

This v2 corrects a measured representation error: the sealed v1 compared raw CFO even though its carrier linker uses circular CFO. Six groups/57 observations had raw jumps beyond half the227272.727Hz alias interval. Raw-v1 aggregate errors and raw alias-affected slopes must not be treated as decisive physical evidence. Every v1 source/output remains unchanged; no favorable group removal, unwrap path, new phase fit or regrouping was introduced.

## Controlled change

The new protocol was saved before computation. Reuse exactly the same49 eligible groups,442 observations,234 even/TRAIN points,208 odd points, positive-phase branch guards, phase fits and their predicted derivatives. All693 original observations across15 selected windows remain accounted;251 points in groups shorter than5 remain ineligible. Phase fitting uses only even first-frame anchors; degree2 requires at least5 even anchors, otherwise the existing linear fallback applies. Derivatives are evaluated at CFO support centers,8.816–9.483ms after first frames.

For each of the three fixed models, predictionHz = TRAIN intercept + sign*RF*x, where sign is0,+1,−1 and x=(positive phase derivative/Fs) minus its TRAIN mean. Fit each intercept using TRAIN CFO only by enumerating all sorted alias cuts, taking each lifted mean and evaluating its true wrapped SSE. This enumerates the circular least-squares stationary candidates and retains a global minimum. No held CFO enters that intercept, and no slope β is learned. Score principal wrapped held residualHz, divided by actual RF for ppm. Constant and both sign controls receive the same exact offset procedure.

There are147 scalar descriptive intercept fits,702 enumerated cuts and at most12 TRAIN points per group. Four component tests pass: seam behavior, exact global SSE versus a40001-point fine grid, whole-period/sample-permutation invariance, and held exclusion for every fixed sign. Calculation elapsed0.127s; phase refits, learned-beta fits and orbit/localization fits are all zero.

## Every source/receiver/channel stratum

| Stratum | Groups | Odd N | Constant ppm | +unit ppm | −unit ppm |
|---|---:|---:|---:|---:|---:|
|S01 RX1 CH2|5|22|0.731961|0.295400|1.388798|
|S01 RX1 CH4|9|33|0.496837|0.183882|0.943144|
|S02 RX1 CH1|5|16|0.368368|0.222531|0.622036|
|S02 RX1 CH3|2|6|0.271764|0.100431|0.495631|
|S02 RX2 CH2|3|19|1.209901|0.320288|2.387277|
|S03 RX1 CH4|5|28|0.809831|0.152667|1.639883|
|S03 RX1 CH5|3|9|0.392918|0.268744|0.631108|
|S04 RX1 CH3|5|23|1.081590|2.827636|0.767960|
|S04 RX2 CH3|3|16|0.800201|0.127001|1.593568|
|S04 RX2 CH5|4|18|0.690374|0.316619|1.275033|
|S05 RX1 CH2|1|3|0.450990|0.450990|0.450990|
|S05 RX1 CH3|1|7|0.721598|0.033029|1.415840|
|S05 RX1 CH4|3|8|0.349061|0.349061|0.349061|

The21 quadratic groups contain129 odd points: constant RMS 0.918814, +unit 1.189499, −unit 1.655444 ppm. Remaining linear-fallback groups have zero centered phase derivative, so their fixed-sign predictions equal the constant control. Across13 strata, +unit improves10, −unit improves the S04 RX1/CH3 stratum, and two linear-only strata tie. All strata and all49 groups are retained in JSON/CSV.

The same32 fixed-seed within-segment odd-CFO permutations preserve phase fits, masks and TRAIN intercepts. Observed +unit RMS is below all32 permuted values (conditional lower-tail1/33); observed −unit is above all32 (lower-tail1). Thus +unit captures real temporal coupling relative to this conditional null, while still failing to beat the constant predictor globally because of the counterexample. These are descriptive controls conditioned on CFO-selected windows/tracklets and phase quality, not unconditional significance or independent emitter evidence.

## Interpretation limits

Phase branches remain minimal numerical unwraps guarded at quarter period, not verified transmitted cycle counts. The original winning peak is retained, while the sealed inventory preserves many alternative anchors. CFO and phase come from the same acquisition and could share estimator effects. Neither positive local coupling nor its sign establishes a receiver clock, transmitter precompensation, beam identity or propagation-delay equation. The S04 reverse-sign group may reflect a distinct frame process or wrong continuity/peak choice; this assay does not decide among those explanations.

The v1 mathematical warning also remains: a quadratic phase has a linear derivative, so an arbitrary per-segment scale can reproduce an ordinary CFO time trend. v2 deliberately fits no such scale and evaluates the two fixed RF/Fs factors.

Independent literature reports frame/carrier rate differences, even in sign, and differing frame clocks across beams of one satellite. This supports caution about a universal equality, but does not identify the DSX mechanism. See sectionsIVB,IX,X of [Qin et al., Timing Properties of the Starlink Ku-Band Downlink](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_starlink_timing_properties.pdf). The previous [positive-phase/range audit](../../../2026_10_17_dsx01_iteration6/frame_phase_audit/README.md) is distinct; no old/tmp script was executed and no range-sign result is counted anew.

![Circular comparisons for every informative group and stratum](circular-phase-cfo.png)

protocol.json binds v1 manifest/data/code before computation. results.json retains all offsets, TRAIN SSE, cuts, fixed-sign residuals and null draws; groups.csv and cohort.json preserve all group/cohort accounting. The old manifest is reverified, and this directory is sealed separately. Stop here: no new universal clock constraint, alternate subset, tuned sign/scale or scientific fitting campaign is authorized by this evidence.
