# TLE-entry-age timing prior investigation

The archive supports a bounded orbital-update **consistency** comparison, but not a universal calibrated seconds-per-day uncertainty law. The newer same-provider element sets are not truth. All calibration snapshots precede the earliest DSX01 start; no radio measurements, fitted timing offsets, station/reference coordinates or target satellite IDs enter historical sampling or width estimation.

## Historical result

The fixed lookback/digest-deduplication rule selected12 Space-Track and8 Hugging Face snapshots. Comparison against each provider's latest causal reference produced18 old/new pairs and36 public propagator calls, zero localization objectives/fits, in2.28 seconds. It retained9209 valid ST object-pair records (4253 distinct objects) and7164 HF records (2786 objects). Invalid old propagations were22/9231 sampled ST entries and4/7168 HF; all newer-reference propagations were valid. There were no reversed epochs or negative ages in these selected records. Counts of unchanged entries—26152 across ST pairs and48 across HF pairs—remain separate from the updated-entry sample.

| Provider / old-entry age | Records / unique objects | MAD-based along-track core s | Absolute projected difference p95 s | Perpendicular difference p95 km |
|---|---:|---:|---:|---:|
| ST .25–.5 day | 12 / 6 | .556 | 11.582 | 4.046 |
| ST .5–1 day | 624 / 622 | .775 | 5.464 | 1.724 |
| ST 1–2 days | 2395 / 2231 | 1.945 | 12.487 | 3.613 |
| ST 2–4 days | 2065 / 1075 | 9.517 | 90.372 | 39.867 |
| HF 1–2 days | 1 / 1 | unsupported | .582 | .329 |
| HF 2–4 days | 3035 / 2287 | 8.418 | 54.589 | 20.136 |

Ages below.25day have no updated-entry comparisons in this sample. Young HF has only one1–2day record, so a narrow HF prior cannot be inferred. Longer-age discrepancies can include large perpendicular components and substantial orbital phase separation; their projected seconds are a local displacement summary, not proof that a scalar time shift repairs the orbit. Common reference snapshots and repeated objects make these samples dependent. Restricting primary rows to updated element epochs also conditions the sample on an update being available. Core MAD is not the physical error standard deviation, and heavy tails remain visible in calibration_v2.json.

This caution is consistent with [CelesTrak's 2025 SDA TAP Lab discussion](https://www.celestrak.org/publications/SDA-TAP-Lab/2025/), which distinguishes age from orbit behavior and maneuver effects. No fresh catalogue or radio collection was made.

Version1 failed before producing a propagated result because the public propagation API requires at least three grid instants. Its source and launch receipt remain unchanged; calibration_v1_failure.json records the failure. Version2 uses three strictly past-or-reference instants[-.002,-.001,0]s and reports only the exact final reference epoch. Two new contract tests pass; the original three sampling/projection tests also pass. No scientific threshold or sample selection was changed by that API correction.

## Prespecified conservative sensitivity

Use provider-specific historical age bins only where at least100 distinct objects contribute. The relative-timing width is that bin's MAD core, clipped to a declared.5s floor and original2s cap. Unsupported ages/providers retain2s. Thus ST .5–1day uses.775488s and1–2days uses1.945240s; older adequate bins cap at2s. Ages below.5day and young HF retain2s. The unsupported fallback is nonmonotonic and explicitly flagged. This is a conservative history-anchored sensitivity, not calibrated physical Gaussian truth, and does not automatically broaden priors for fitted large shifts.

Widths are fixed from each candidate's ORIGINAL causal TLE entry epoch at measurement start. Only the relative penalty changes: .5 sum(delta_s squared/sigma_s squared), delta=B times the relative timing coordinates. Common recording-clock sigma remains3s. The likelihood, candidate bank, q, frequency calibration, clocks, fixed band contrasts, constraints and classification remain identical. Exact weighted profile proposals include the effect of changing the mean on every relative offset. Different-prior J omits Gaussian normalizers and is not Bayesian model evidence.

Seven component tests pass, covering exact scalar2 nesting, unchanged likelihood/posterior/common/nuisance gradients, relative-gradient finite differences, gauge, held-CFO/profile invariance, weighted profile oracle, width fallback policy and actual-objective accounting. Source and concrete protocol freeze in pilot_plan.json before actual qualification. S01 is an exact2s HF nesting oracle with zero localization fits. Only S03 has the8-call matched localization pilot: scalar2 versus age, fitted-c versus c=0, continuation versus exact timing-profile search, each1000 objectives/120 seconds. All8 outcomes must seal before position/window evaluation; no all-five/all15 performance aggregate is inferred from this one-source pilot.

## Actual warm-start pilot

Qualification passes: S01HF has46/46 widths exactly2s and nests the original objective/gradients/posterior, with3 additional objectives and zero fits. S03ST has40 candidates:14 widths.775488s, one1.945240s and25 baseline2s. Seven additional objectives include3 feasible exact weighted-profile comparisons. Source-loader replay/preparation is additional. Both original-model and heterogeneous-profile gradients are covered by the component tests; no actual-data all-coordinate FD claim is made.

All8 S03 inference outcomes sealed before evaluation. The source/candidate/calibration functions and paired initial vectors are identical except zero-c's c coefficient. No endpoint numerical retry is applied. All raw feasible endpoints remain visible, including two rejected scalar2 profile results. Cross-family J is not used to select a model.

| Prior / arm / method | Data NLL | All associated /3988 | Diagnostic /138 | Configured-reference km | Relative timing RMS s | KKT / strict |
|---|---:|---:|---:|---:|---:|---|
| Scalar2 fitted-c continuation | 40676.094 | 3467 | 136 | 3.282 | 3.423 | .0003055 / yes |
| Age fitted-c continuation | 40676.498 | 3466 | 136 | 3.221 | 3.420 | .0002520 / yes |
| Scalar2 fitted-c profile | 40438.318 | 3552 | 136 | 3.098 | 1.873 | .0021468 / no |
| Age fitted-c profile | 40454.838 | 3550 | 137 | 3.158 | 1.660 | .0000761 / yes |
| Scalar2 c=0 continuation | 45943.287 | 2493 | 120 | 4.318 | 3.413 | .0001599 / yes |
| Age c=0 continuation | 45976.190 | 2473 | 121 | 3.707 | 3.339 | .0007883 / yes |
| Scalar2 c=0 profile | 45866.125 | 2497 | 121 | 3.129 | 3.603 | .0011251 / no |
| Age c=0 profile | 45950.478 | 2506 | 121 | 2.920 | 2.323 | .0005062 / yes |

The age prior reduces profile relative-timing RMS and yields strict endpoints, but does not deliver sub-kilometer localization or a substantial fitted-c support gain. The scalar2 profile has better data NLL and slightly better position but fails strict stationarity; excluding it would create a misleading accepted-only model comparison. The one extra fitted-c diagnostic association is not a reason to select a prior or discard failures. Different associated populations also require the retained intersection-RMS metrics, rather than inferring localization quality from overall RMS alone.

`pilot_evaluation.json` and `eval_S03_*.npz` retain all raw outcomes and original-fitted-reference overlap. `pilot_comparison.png/.pdf` hatch rejected endpoints. The pilot is one-source research evidence, not an all-five/all15 replacement; all other sources remain untested under a changed prior. No source/reference seeding, posterior-label truth, production change, new RF, historical-result overwrite or promotion occurs.

## Separately predeclared blocked comparison

The4 continuations use only the public TRAIN-derived S03 blocked context and its complete original terminal endpoint, with the same frozen age policy, scalar2 control, both RF arms and1000-objective/120s allowance. There are no profiles, multistarts or warm/full-data seeds in this comparison. All4 fits sealed, then all4 plain-base metadata-only predictions sealed, before held CFO was scored. True conditional row-NLL sums distinguish2073 training,1909 held and6 boundary rows, and the fixed80-row requested held subset. c=0 remains conditional on fitted-c training-only discovery. Source and prediction authority remain frozen in blocked_plan.json and blocked_prediction_seal.json.

**Domain erratum recorded before held scoring:** the reused common.refit port enforces the broad250km regional prior, but not the original production endpoint's extra25km local disk. The frozen BLOCKED_PROTOCOL.md phrase "original bounds" therefore requires this correction: parameter bounds and regional prior are preserved; the extra local disk is not. All4 comparisons have the same research domain, so the prior comparison remains matched within that domain. They are not production-domain continuation controls. Original local center is[-58.45781953638532,-65.56600492081635]km, radius25km. Three endpoints fall outside that disk, as shown below; all4 independently pass the regional-domain audit. The original source's795/1909 held and66/80 requested coverage is only a descriptive anchor because additional optimization and domain differ. No retry, threshold change or hidden source overwrite was applied.

| Prior / arm | Training NLL | Held NLL /1909 | Held assigned /1909 | Requested held /80 | Configured-reference km | Regional feasible / strict | Original local-disk distance km / feasible |
|---|---:|---:|---:|---:|---:|---|---|
| Scalar2 fitted c | 24220.856 | 23226.281 | 788 | 68 | 7.346 | yes / yes | 26.747 / no |
| Age fitted c | 24199.308 | 23224.897 | 791 | 67 | 7.934 | yes / yes | 26.103 / no |
| Scalar2 c=0 | 25594.685 | 24809.195 | 478 | 37 | 11.698 | yes / yes | 21.018 / yes |
| Age c=0 | 25752.524 | 24732.870 | 482 | 25 | 7.280 | yes / yes | 26.685 / no |

All4 outcomes are strict: KKT scalar fitted.00006530, age fitted.00004434, scalar c=0.00018342 and age c=0.00002605. They use287/352/431/524 actual inference objectives respectively,1594 total, plus4 independent terminal audits, source preparation/qualification and4 post-seal training-NLL closure checks. All meet the original1000/120 per-call cap; no endpoint finishing was used. The age policy changes17/45 TRAIN candidates:15 widths.775488s, two1.945240s,28 baseline2s. Common-clock width stays3s.

Fitted-c age sensitivity improves held NLL by only1.384 and gains3 held associations, while losing one requested association and worsening configured-reference distance by.588km. c=0 improves held NLL by76.325 but loses12 requested associations despite gaining4 across the full held denominator. Thus NLL, point coverage and position do not move together. Each boundary arm assigns2/6; these rows are not silently included in training or held results. Requested held per-window scalar→age counts are21→20/26,21→21/28,26→26/26 for fitted c and22→3/26,10→15/28,5→7/26 for c=0. These window labels are evaluation strata, not verified satellite labels or fitting inputs.

The configured position diagnostic is computed only after all fits/predictions seal, using the existing station metadata with matching radio serial and validity interval. It is operator-supplied WGS84 roof coordinates with unknown survey/altitude uncertainty; it never seeds or selects a fit. The age prior receives no promotion and no all-five campaign. The other4 sources,555 requested points outside S03 and16096 full observations outside S03 remain untested under this policy. blocked_summary.json carries domain flags, exact source hashes and the complete denominator ledger; blocked_comparison.png/.pdf shows the held and position comparison. Neither warm nor blocked results justify claiming that entry age alone calibrates physical timing uncertainty.
