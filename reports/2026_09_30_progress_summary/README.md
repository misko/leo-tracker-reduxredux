# Localization progress through September 30 2026

This consolidates the DS7 localization campaign and its DS8, DS9 and DS10 follow-ups, including earlier roof geometry pilots used in that campaign. Joint fitting produced several hundred-metre reference distances, but repeatable sub-kilometre accuracy remains unproven. Scan selection, model assumptions and transfer matter more than the best individual number.

All location values below are horizontal metres from the exposed, unsurveyed roof reference, not independently established true errors. The configured search center is already 809 m from that reference with zero observations. Most reports use great-circle distance; the separate reference audit uses an ellipsoidal metric. DS10 installation continuity remains unconfirmed. A dash means unmeasured. Numerical qualification means solver and audit gates passed, not scientific validation.

This is a synthesis of reported experiments, not a new fit or a claim to inventory every unrelated repository report. Tables preserve different observation budgets and aggregation levels. Rows are not all matched ablations. Source reports retain individual starts, failures, manifests and detailed controls. The source inventory binds the reports used here.

## Single scan results

| Method and population | DS7 median m | DS8 median m | DS9 median m | Qualification and interpretation |
|---|---:|---:|---:|---|
| Baseline first eight scans | 2873 | 3576 | 4778 | DS8 has 7 returned estimates from 8 attempts; one export timeout |
| Baseline all DS7 scans | 2571 | — | — | 88 returned; 87 qualify; qualified-only median 2515; 13/88 below 1 km |
| Free frequency slope, first eight | 3001 | — | — | No median improvement over initial DS7 baseline |
| Later shared-scale and q020 pooled models | — | — | — | Comparable full single-scan median campaign not measured |

Sources: [initial comparison](../2026_09_29_approach_summary/README.md), [full DS7](../2026_09_27_ds7_full88/REPORT.md). None of the later pooled results should be substituted for a single-scan median.

## Joint location progress

Each cell is one joint position unless the population explicitly says median of sets. Shared track scale is the older likelihood model; it is distinct from the later RX-derived variable observation-noise scales.

| Approach | Population per dataset | DS7 m | DS8 m | DS9 m | Result |
|---|---|---:|---:|---:|---|
| Baseline | First 8 | 2541 | 1424 | 1213 | Starting joint comparison |
| Receiver-specific slopes | First 8 | 2302 | 1551 | 1750 | Mixed; DS8 and DS9 worse |
| Shared track scale | First 8 | 2287 | 1391 | 683 | Improved all three initial panels |
| Shared scale plus 10 s correlation | First 8 | 2955 | 819 | 1647 | Not consistent |
| Baseline | 8 spread across time | 785 | 2187 | 1661 | Selection strongly changes result |
| Shared track scale | 8 spread across time | 527 | 1896 | 422 | Mixed geographic transfer |
| Shared scale plus correlation | 8 spread across time | 359 | 1904 | 2109 | Correlation can degrade substantially |
| Shared track scale | Union 15 | 497 | 386 | 319 | All below 1 km on this selection |
| Shared scale plus correlation | Union 15 | 996 | 868 | 1135 | Worse than shared scale |
| Shared track scale | Separate additional 15 | 564 | 875 | 1493 | DS9 fails to repeat union result |
| Shared scale plus correlation | Additional 15 | 1184 | 187 | 2588 | One attractive number does not transfer |
| Shared track scale | Combined 30 | 411 | 135 | 352 | Strong selected-panel results |
| Baseline | Complete DS7, 88 scans | 677 | — | — | 3/3 starts qualify |
| Shared track scale | Complete datasets, 88 / 65 / 105 | 527 | 736 | 229 | All below 1 km; DS7/DS8 worse than selected 30 |
| Shared track scale | Median of 3 consecutive N4 sets | 2590 | 2261 | 1167 | Sub-km counts 0/3, 0/3, 1/3 |
| Shared track scale | Median of 3 consecutive N8 sets | 2064 | 1762 | 870 | Sub-km counts 0/3, 0/3, 2/3 |

Sources and per-row provenance: [earlier consolidated comparison](../2026_09_29_approach_summary/README.md), [DS7 complete](../2026_09_28_ds7_full_shared/README.md), [DS8 complete](../2026_09_29_ds8_full_shared/README.md), [DS9 complete](../2026_09_29_ds9_full_shared/README.md).

The original DS7 baseline also evaluated **all eleven disjoint N8 groups**: joint median 1429 m, 3/11 below 1 km. Equal-position, inverse-RMS² and lowest-RMS-75% aggregation controls had medians 1122 / 1076 / 1182 m over 10 qualified groups each; each abstained on the group containing an unqualified single estimate. These differ from the later three-window panel experiment. [Full group table](../2026_09_27_ds7_full88/group-panels-v1.md).

Cross-dataset pooling estimates one common position from all datasets, not separate errors:

| Model | Total recordings | Joint reference distance m |
|---|---:|---:|
| Baseline first-eight panels | 24 | 862 |
| Shared scale union panels | 45 | 180 |
| Shared scale plus correlation union panels | 45 | 310 |
| Shared scale additional panels | 45 | 230 |
| Shared scale plus correlation additional panels | 45 | 1080 |
| Shared scale plus timing refinement additional panels | 45 | 202 |

Source: [cross-dataset comparison and original links](../2026_09_29_approach_summary/README.md).

## Later likelihood and scan selection comparisons

The q020 model includes a 20% unassociated linear-trend background. The checkpoint uses its documented multistart results; the earlier background experiment's DS9 contiguous N8 median was 876.1 m, versus 841.8 m in the later checkpoint. They are separate result versions.

| Method | Budget and aggregation | DS7 m | DS8 m | DS9 m | Interpretation |
|---|---|---:|---:|---:|---|
| q020 contiguous N8 | Median of 3 windows | 2023.6 | 1721.1 | 841.8 | Short-window accuracy remains limited |
| q020 time-balanced N8 | Median of 3 sets | 1416.6 | 1422.8 | 1042.8 | No dataset median below 1 km |
| q020 cumulative N16 | One fit | 643.8 | 1091.7 | 382.4 | DS8 remains above 1 km |
| q020 block-pooled N24 | One fit | 387.5 | 389.8 | 107.2 | Working research baseline |
| Geometry-selected N8 | Scout 24, retain 8 | 1831.6 | 987.6 | 395.8 | Not an eight-scan acquisition budget |
| Score-balanced N8 | Scout 24, retain 8 | 390.8 | 403.4 | 97.6 | Compression of a larger observed panel |
| Prefix score-balanced N8 | Scout 12, retain 8 | 1038.0 | 1231.6 | 534.2 | Compression benefit does not fully survive smaller budget |
| Shared curvature N24 | One fit | 340.5 | 372.5 | 134.9 | Outside-scan prediction wins only 6/15 |
| Equal chronological rank N24 | Different 24-scan selection | 453.9 | 1876.8 | 340.6 | DS8 sensitivity invalidates a blanket N24 claim |

Sources: [checkpoint](../2026_09_29_subkm_methods_checkpoint/table.md), [rank control](../2026_09_29_rank24_control/README.md), [curvature transfer](../2026_09_29_curvature_n24/README.md).

| Subsequent experiment | Location metric | Predictive or numerical evidence | Decision |
|---|---|---|---|
| DS8 union of conflicting N24 selections | N40: 416.8 and 534.3 m from two starts | Both qualify; endpoints 273.5 m apart | More coverage helps this case; budget rises 67% |
| DS8 timing reselection | N40: 424.6 m, 33.5 m movement | +25.57 held log-score versus original selected N40 | Retain timing safeguard |
| DS8 independent SLSQP | N40: 422.7 m | Qualifies; lower training score than 424.6 m fit | Keep training-selected 424.6 m result |
| DS8 corrected timing gradient refits | No qualified replacement | One gradient-gate failure; one abnormal solver exit | Failures retained, not promoted |
| DS10 frozen N24 | 1091.8 m | All 24 primary starts qualify | Later-dataset sub-km transfer fails |
| DS10 three interleaved N8 sets | 1076.1 / 1802.8 / 1846.8 m | All above 1 km | Shorter sets do not rescue transfer |
| DS10 N24 at 20 / 40 m height | 1104.5 / 1117.0 m | Worse than height-zero reference distance | Height sensitivity, not improvement |
| DS10 timing mode check | Existing 1091.8 m result retained | Held gain only 0.0000086; negligible timing changes | No refit trigger |
| DS10 scalar-derived constant / variable RX noise | 1089.7 / 1078.2 m | Native held changes +2.96 / −2.82 versus baseline | Variable weights not promoted |
| Direct conditional-likelihood noise calibration | No new location fit | DS10 constant +6.117, variable +2.481 held log-score | Variable loses matched constant control; stop recipe |

Sources: [DS8 union](../2026_09_29_ds8_union40/README.md), [timing](../2026_09_29_ds8_union_timing/README.md), [independent optimizer](../2026_09_30_ds8_independent_optimizer/README.md), [failed refits](../2026_09_30_ds8_validated_timing_refit/README.md), [DS10 locations](../2026_09_29_ds10_geographic/README.md), [DS10 timing](../2026_09_30_ds10_timing_transfer/README.md), [noise weighting](../2026_09_30_ds10_scale_weighting/README.md), [direct calibration](../2026_09_30_contrast_scale_calibration/README.md).

## Geometry and direction evidence

Geometry is informative in some reception tests. We have not established a calibrated compass-and-antenna model that consistently improves location. Nominal fixture tilt alone is not a measured satellite bearing.

| Experiment | Measured progress | Limit or decision |
|---|---|---|
| Roof direction reception model, 6 training and 4 held scans | Detection log loss 0.65337 → 0.47909, 26.7% reduction; receiver log-margin-ratio MSE 0.32169 → 0.17381, 46.0% reduction; all 4 held scans improve | Positive reception evidence; known-position features; not a location test or calibrated RF power |
| Geometry association pilot | Static geometry versus Doppler +1.0011 nats/window | Static loses to clutter by 0.01639; original benefit insufficient |
| Frozen geometry confirmation, 4 disjoint historical recordings | Static versus Doppler +1.0269; versus clutter only +0.00860 nats/window, 2/4 positive | Nominal tilt versus static −0.00525; do not enable association default |
| Soft cones, half-angles 20 / 30 / 40 / 50 degrees | 70/72 selected fits qualify; 49 lower reference distance, 29 better held Doppler | No width establishes sub-km performance across datasets |
| N8 cone median, baseline | DS7 / DS8 / DS9: 2064 / 1762 / 870 m | Median across 3 sets per dataset |
| N8 cone median, 20 degrees | 2072 / 1753 / incomplete m | Qualification failure remains explicit |
| N8 cone median, 30 degrees | 2071 / 1722 / 764 m | DS9 improvement; DS7 and DS8 remain above 1 km |
| N8 cone median, 40 degrees | 2061 / 1779 / 747 m | DS9 improvement; not general transfer |
| N8 cone median, 50 degrees | incomplete / 1767 / 829 m | No robust winner |
| Physical pose authority | Nominal 20-degree RX axis separation documented | World elevation, mapping and RF phase centers unverified; no calibrated beam response |

Sources: [reception direction](../2026_09_27_roof_direction_subset/REPORT.md), [association pilot correction](../2026_09_28_rx_geometry_association/README.md), [confirmation](../2026_09_28_rx_geometry_confirmation/README.md), [cone sweep](../2026_09_29_rx_cone_position/README.md), [pose documentation](../../docs/operations/radio20-roof-pose-20260926.md).

Soft cone floors can become locally constant across all candidates and then contribute no position gradient. Existing cone results therefore do not settle the value of calibrated antenna geometry, detection/nondetection modeling, or confirmed receiver order.

## Other model and transfer tests

Positive held-score deltas mean better predictive density. They are not metres and are comparable only within the stated experiment.

| Direction | Metric and coverage | Outcome |
|---|---|---|
| Frequency contrast | Held prediction improves 17/18 panels; location 9/18; only 3/18 below 1 km | Predictive gain does not establish location gain |
| Unassociated trend q020 | Held improves 18/18; location 9/18; sub-km remains 3/18 | Useful baseline formulation; limited geographic improvement |
| Correlated contrast | Held improves 18/18 per arm; location 9/18 | DS9 N8 no-cone median degrades 876 → 2059 m |
| Shared candidate slope, small / large prior | Held improves 9/9 each; location 2/9 and 4/9 | Do not promote |
| Slope transfer to opposite RX | Small prior improves 12/18, total +159.9; large improves 9/18, total −292.9 | Smaller correction more promising, but not sufficient |
| Slope transfer to held scans | 12/18 positive but total −53.83; sub-km 3 → 2 of 18 | Fails stronger transfer test |
| Marginal timing | 15/18 qualify; held sum −31.61; sub-km 2 → 1 of qualified 15 | No promotion |
| Receiver-specific location fits | Median RX position separation 2658 m; opposite RX prediction worse 36/36 | Receiver disagreement is systematic, not solved by separate fits |
| Older orbit revision | 2815 of 3408 changed cases worsen; median worsening 260.1 Hz | Keep freshest orbit inputs |
| Donor-fitted orbit correction | Median gains DS7 / DS8 / DS9: −0.03074 / −0.00168 / +0.00015 Hz | Negligible; fails transfer gate |
| Shared candidate identity | 817/886 matched pairs agree versus 22/886 shuffled | Strong consistency diagnostic; not decoded identity truth |
| Identity coupling | Held gains only 7/18 at coupling 0.5 and 4/18 at 1 | No geographic launch |
| Source-consistent N8 filtering | DS7 1688 → 1895; DS8 722 → 821; DS9 2042 → 1811 m | All retained held scores improve, mixed location; no promotion |
| Same-candidate RX residual transfer, DS7–9 | 1847 supported tracks; 1171 improve; median gain 9.89 Hz | Positive candidate-conditioned prediction |
| Same-candidate RX residual transfer, DS10 | 696 supported; 430 improve; median gain 7.74 Hz; 21/24 scan medians positive | Transfers as residual prediction, not yet location |
| RX-difference scale calibration, DS10 | +0.06369 nats/observation; 24/24 scans improve | Strong for RX differences, which cancel common errors |
| Transfer of scale feature to common residual | +0.01449 nats/observation; 17/24 scans improve | Smaller gain on a different predictive target |
| Geographic noise-weighting score audit | Variable +6.737 summed individual scores but −1.555 joint conditional score | Marginal scoring benefit does not justify geographic weights |

Sources: [contrast](../2026_09_29_frequency_contrast/README.md), [background](../2026_09_29_unassociated_trend/README.md), [correlation](../2026_09_29_correlated_contrast/README.md), [candidate slope](../2026_09_29_shared_candidate_slope/README.md), [RX holdout](../2026_09_29_receiver_holdout/README.md), [scan holdout](../2026_09_29_scan_holdout/README.md), [timing marginalization](../2026_09_29_marginal_timing_fit/README.md), [RX positions](../2026_09_29_receiver_panels/README.md), [orbit revision](../2026_09_29_orbit_revision_prediction/README.md), [orbit transfer](../2026_09_29_orbit_revision_transfer/README.md), [identity](../2026_09_29_rx_shared_candidates/README.md), [coupling](../2026_09_29_rx_identity_coupling/README.md), [source consistency](../2026_09_29_source_consistent_n8/README.md), [RX transfer](../2026_09_29_candidate_rx_transfer/README.md), [DS10 transfer](../2026_09_30_ds10_rx_residual/README.md), [difference calibration](../2026_09_30_rx_difference_calibration/README.md), [common residual](../2026_09_30_rx_scale_common_transfer/README.md), [score audit](../2026_09_30_scale_score_diagnostic/README.md).

## Sequence and waveform estimation

These measure waveform prediction, not location. Lower NMSE is better; a positive NMSE gain means baseline minus new model.

| Prototype | Evaluation | Metric | Decision |
|---|---|---|---|
| Sequence-aware estimator versus strong pilot | 72 receiver frames | 37/72 wins; dataset median NMSE nearly unchanged | Advantage over a weaker short-pilot baseline does not survive strong baseline |
| Longer sequence support | 192 frames, 8 visits | 81 qualify, 111 fallback; 47 improve, 34 worsen | Small conditional benefit; limited coverage |
| Shared phase drift | 800 frames | 379 improve, 421 worsen; mean NMSE gain −0.0000279 | Do not promote |
| Waveform chirp | 160 target frames | 81 wins, 79 losses; mean gain −0.002015 | DS8 particularly worse |
| Donor-shrunk rate | 160 frames | 97 wins; mean gain +0.000864; DS8 −0.002463 | Some transfer, no consistent dataset benefit |
| Carrier-rate agreement weighting | 160 frames | 86 wins, 48 losses, 26 ties; +0.000688 versus constant | Worse than reduced-rate model by 0.000177 |
| Detector margin to residual-scale calibration | DS7–9 scan transfer | Equal-dataset mean −0.00032 nats | Margin not established as geographic precision |

Sources: [sequence estimator](../2026_09_29_sequence_estimator/README.md), [long support](../2026_09_29_sequence_long_support/README.md), [phase drift](../2026_09_29_shared_phase_drift/README.md), [chirp](../2026_09_29_waveform_chirp/README.md), [rate transfer](../2026_09_29_rate_transfer/README.md), [carrier agreement](../2026_09_29_rate_carrier_agreement/README.md), [margin calibration](../2026_09_29_margin_calibration/README.md).

## Validation progress and remaining priorities

| Validation question | Evidence now available | Consequence |
|---|---|---|
| Is the reference surveyed? | Accuracy unknown; configured center already 809 m away | Reference distance alone cannot certify accuracy |
| Are nominal confidence widths trustworthy? | Local curvature axes 46–76 m; scan-group axes 357–798 m; window-group axis up to 1259 m | Correlation/sampling sensitivity exceeds naive curvature; these are not calibrated confidence intervals |
| Can the solver recover a known displacement? | Conditional 1 km injections recovered with 9–67 m displacement errors | Numerical/model-conditioned validation, not field accuracy |
| Is altitude negligible? | 20–40 m height assumptions move horizontal fits 19–84 m; 300 m moves 287–769 m | Need antenna height and datum, not arbitrary height tuning |
| Do host capture brackets explain fitted timing? | 59/72 fitted offsets outside brackets; maximum exceedance 2.166 s | Fitted timing absorbs more than documented capture delay |
| Does current clock sync establish historical UTC? | Current sync plus sparse historical source-selection events; no regular chrony logs found | No capture-level historical UTC bound established |
| Is DS10 pose continuity evidenced at documented path? | 0/24 expected companions present in the current local check | Verify provenance; absence here does not exclude historical/off-host copies |
| Is there a reusable evaluation path? | Frozen input panels, held splits, multiple starts, explicit failures, derivative audits and source seals across reports | Enables controlled follow-ups; does not itself validate accuracy |

Sources: [reference gate](../2026_09_29_reference_accuracy_gate/README.md), [uncertainty](../2026_09_29_scan_uncertainty/README.md), [injections](../2026_09_29_position_injection/README.md), [near-ground height](../2026_09_29_near_ground_height/README.md), [height sweep](../2026_09_29_height_n24/README.md), [timing authority](../2026_09_29_timing_authority/README.md), [physical evidence check](../2026_09_30_physical_constraint_audit/README.md).

Recommended priorities, based on this synthesis:

1. Establish independent reference, installation pose/RX mapping, antenna height and capture timing authority. These are missing inputs, not parameters to select using location error.
2. Test calibrated geometry with detection and nondetection evidence, and explicit swapped-axis/clutter controls. Preserve the positive reception result without treating it as geolocation proof.
3. Improve trustworthy signal/candidate identity and common Doppler errors; RX residual transfer is a useful diagnostic but has not supplied a successful geographic weighting recipe.
4. Evaluate frozen methods across prespecified chronological panels and later datasets, scoring location and whole-scan prediction together. Keep matched scan budgets and failed fits visible.
5. Retain multistart/timing safeguards. Deprioritize more unconstrained slopes, correlation variants and RX-noise weighting without new independent evidence.

No new RF collection, model campaign, production change or remote publication was performed for this summary.
