# Retain the baseline: the frozen R01 application does not meet promotion criteria

The coherent full-bin-floor candidate does not establish the predeclared held median, p90 and coverage requirements in both c arms. Capped and unavailable results remain in the intended cohort; complete-case accuracy cannot substitute for qualification coverage.

| Primary held outcome | c=0 | Fitted c |
|---|---:|---:|
|Audited baseline → treatment scans /12|8 → 8|8 → 8|
|All-scan median baseline → treatment (m)|1335.8 → 1338.1|1275.3 → 1278.1|
|Cohort median improvement|-0.17%|-0.22%|
|All-scan p90 baseline → treatment (m)|∞ → ∞|∞ → ∞|
|All release gates pass|False|False|
|Qualified scans at or below 500 m / all intended scans|1/12 → 1/12|1/12 → 1/12|

Infinity denotes conservative unavailable ranks, not a measured infinite geographic error. Median and p90 use all twelve intended scans. A non-finite comparison cannot establish promotion. Six scans have no eligible RF lane and retain baseline-equivalent treatment; they are not positive recovery-transfer examples. The 500 m count and CDF reference line describe the existing accuracy goal, without changing the frozen promotion rule.

Every numerical run uses the original 25 × 25 km region centered at 37.906, −122.545 and east/north start 0/0, with the full strictly causal TLE catalogue. Observations, candidate identities/aliases, other priors and search budgets are matched between c=0 and fitted c. The reporting-only reference is 37.849061591561885, −122.48574968092912, introduced after terminal/input/read audits; it never seeds inference.

![Held error distributions and paired scatter](figures/held_error_distributions.png)

![Held per-scan changes](figures/held_paired_changes.png)

| Complete-case result (descriptive) | Paired scans | Baseline median (m) | Treatment median (m) | Ratio-of-medians improvement | Median paired relative change |
|---|---:|---:|---:|---:|---:|
|Floor, c0|8|1073.3|1092.4|-1.78%|0.00%|
|Floor, fitted_c|8|1012.3|1058.2|-4.53%|0.00%|
|Proxy (secondary), c0|8|1073.3|1089.3|-1.49%|0.00%|
|Proxy (secondary), fitted_c|8|1012.3|1054.7|-4.18%|0.00%|

The ratio of cohort medians is the release estimand; the median of paired percentages is a different descriptive statistic. [Metrics](metrics.json) retain all scan IDs, failures, complete-case denominators and paired-scan bootstrap intervals (10,000 draws, seed 20261026). Interval summaries state their finite-replicate fraction; no GLRT-point bootstrap or secondary-weight selection is used.

| Held scan | Baseline c=0 (m) | Floor c=0 (m) | Baseline fitted c (m) | Floor fitted c (m) | Eligible RF lane |
|---|---:|---:|---:|---:|---|
|DS24-0015|capped|capped|capped|capped|yes|
|DS24-0016|capped|capped|capped|capped|no; baseline-equivalent|
|DS24-0019|1180.3|1180.3|1222.8|1222.8|no; baseline-equivalent|
|DS24-0075|1215.5|1215.5|1096.2|1096.2|no; baseline-equivalent|
|DS24-0077|1456.1|1460.7|1327.9|1333.5|yes|
|DS24-0081|capped|capped|capped|capped|yes|
|DS24-0083|capped|capped|capped|capped|no; baseline-equivalent|
|DS24-0085|793.2|731.9|928.5|862.4|yes|
|DS24-0089|2187.8|2187.8|2205.2|2205.2|no; baseline-equivalent|
|DS24-0091|966.2|1004.4|923.4|1020.1|yes|
|DS24-0093|707.4|707.1|766.1|765.9|yes|
|DS24-0095|360.2|360.2|438.6|438.6|no; baseline-equivalent|

Among audited paired c0 results, 2 scans improve and 2 regress. The largest measured gain is DS24-0085, 61.3 m. The largest measured regression is DS24-0091, 38.2 m. Capped or unaudited pairs have unknown accuracy; they are qualification failures, not measured accuracy regressions.

Among audited paired fitted_c results, 2 scans improve and 2 regress. The largest measured gain is DS24-0085, 66.1 m. The largest measured regression is DS24-0091, 96.7 m. Capped or unaudited pairs have unknown accuracy; they are qualification failures, not measured accuracy regressions.

The primary application exactly reproduces the RF-only coherent rule: sparse R01 nominations, top two eligible CH5–8 lanes, earliest curved seed, closed ±12-second blocks, both receivers, original earlier donors only. Position inputs contain originals plus coherent admissions only. R02 and sparse-only unions are excluded. The scope amendment preceded new geographic outcomes.

| Acquisition and graph accounting | Held 12 | Development 12 |
|---|---:|---:|
|Original whole-recording GLRT|53086|55514|
|Original + coherent additions|53162|55619|
|Added native owners|76|105|
|Added in RF graph|61|88|
|Added actively curved|56|69|

The held whole-recording GLRT count increases by 0.143%. This differs from the earlier sparse-panel10.56% relative CH5–8 coverage gain. Association percentages use the full original-plus-added GLRT denominator, and their numerators include compatible postfit points as well as likelihood points. Frequency RMS uses changed inference support and is not geographic accuracy.

![Reserved coherent blocks: original and recovered GLRT points](acquisition_visuals/reserved_glrt_blocks_v2.png)

Colors in the acquisition figure distinguish new curved RF graph members, other graph members and points outside the graph. They do not encode satellite identity or final likelihood acceptance. The [development blocks](acquisition_visuals/development_glrt_blocks_v3.png) are separately labeled.

![Association and frequency fit](figures/held_association_frequency.png)

![Acquisition-to-likelihood mechanism](figures/held_mechanisms.png)

Among all 76 held additions, 9 use the zero residual FFT bin, 57 have one original donor, and 53 have heuristic widths beyond the wrong-pilot control's 4,500 Hz range. Qualified primary runs accept 42 new curved and 5 new predictive likelihood owners; their zero-bin/donor distributions are in [metrics](metrics.json) and the [owner table](new_native_mechanism.csv). Unavailable likelihood membership is not counted as an observed rejection. This is a descriptive mechanism audit, not a new filter or a claim of calibrated independent frequency precision.

Graph/noise re-estimation changes incumbent input scales versus baseline in all 11 eligible scans. The [independent noise audit](incumbent_noise_audit.json) verifies, for example, −0.57 to +10.62 Hz in 0077, +1.03 to +9.81 Hz in 0091, and −0.89 to +34.95 Hz in 0010. Floor and proxy have exactly equal incumbent input scales; only new-owner input scales receive the floor. Association paths and likelihood membership may still differ. Attributing a geographic gain specifically to independent added frequencies would require a separate new-owner-only versus frozen-incumbent-weight ablation, which was not introduced into this frozen evaluation.

Runtime qualification is separate from scientific accuracy. [Runtime/cap accounting](runtime_caps.json) identifies the stage at each cap and retains failed attempts. No partial endpoint is treated as qualified. The original numerical budgets, causal candidates/priors and matched c-arm masks remain fixed; all valid endpoints and inference reads were independently audited before reporting errors.

| Runtime-capped stratum / variant | Active stage at cap | Scans |
|---|---|---:|
|development, additions_bin_floor|initial_association|1|
|development, additions_bin_floor|signed_phase_prior_or_family_nomination|1|
|development, additions_proxy|initial_association|1|
|development, additions_proxy|signed_phase_prior_or_family_nomination|1|
|development, baseline|algo02_refinement|1|
|development, baseline|initial_association|1|
|development, baseline|signed_phase_prior_or_family_nomination|2|
|held, additions_bin_floor|discovery|2|
|held, additions_proxy|discovery|2|
|held, baseline|algo02_refinement|1|
|held, baseline|discovery|2|
|held, baseline|initial_association|1|

The original DS24 inventory has 34 recordings: 24 usable and 10 unavailable. The unavailable members remain an explicit scope limit; no favorable replacement recording is selected. The other 12 usable scans are development evidence, including the reused 0011/0097 examples, and do not enter the promotion denominator. [Development error distributions](figures/development_error_distributions.png), [changes](figures/development_paired_changes.png), [association/RMS](figures/development_association_frequency.png) and [mechanisms](figures/development_mechanisms.png) are labeled separately. All scans were exposed in earlier studies; this is not new-site validation.

DS23 does not validate this unchanged candidate: all 207 fast recordings are 2.5 MS/s, while the frozen scorer explicitly requires 10 MS/s. Independent metadata checks verify 2,886 segment manifests; 204 recordings retain all original paths and three lack analysis inputs. The 206 adaptive recordings are a different acquisition regime. No resampling, rate-generalized port or DS23 recovery accuracy is claimed. This is an implementation-domain limit, not evidence that sample rate physically causes position error.

[Per-scan CSV](per_scan.csv) provides errors, qualification, runtime, original/added/associated point counts and RMS. [Provenance](provenance.json) binds evaluation protocols, implementation/source/input audits and terminal receipts. Native IQ and large inference trees remain outside this portable package.
