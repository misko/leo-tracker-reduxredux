# Shifted-origin annotation batch 2

The next **32** wholly unowned curves from the frozen timestamp-selected queue have complete predictive-only assessments. Outcomes: **{'conditionally_supported_identity': 17, 'unstable_identity': 6, 'ambiguous_identity': 7, 'prediction_mismatch': 2}**. There are **17 full position trials**, with **7 RF-qualified curves / 236 points** in separate trials. This is not a combined recovery or a production change.

## Scope, validation and capture provenance

Selection follows native point count and immutable track ID without GPS ranking. The reconciled remaining-candidate file prevents repeating assessments completed in other queues. Every target has three distinct timestamp-selected physical holdout sets, with seeded block origins, 12-second blocks, two-second guards, at least eight training points and four held points. Sets overlap and are not independent replications. No target calibrates the receiver during annotation; the graph and incumbent identities remain conditioning assumptions.

Capture modes are **{'fast': 30, 'adaptive': 2}**. Adaptive records use their authoritative source case in tables, retaining historical inventory aliases separately. Direct scanner contracts and digest-verified acquisition manifests establish capture provenance; the fast adapter compatibility label does not. Canonical source identities prevent an adaptive recovery from being reported as a fast-scan result.

| scan | inventory_alias | capture_mode | points | status | norad | margin |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO-74824694 | AUTO-74824694 | fast | 36 | conditionally_supported_identity | 64913 | 36.390 |
| V03 | V03 | fast | 35 | conditionally_supported_identity | 59189 | 217.386 |
| V02 | V02 | fast | 35 | unstable_identity | None | 346.613 |
| AUTO-acd7c83d | AUTO-acd7c83d | fast | 35 | conditionally_supported_identity | 62180 | 55.970 |
| DS24-0017 | DS24-0017 | fast | 35 | ambiguous_identity | 62571 | 1.921 |
| AUTO-69e994bf | AUTO-69e994bf | fast | 35 | conditionally_supported_identity | 66136 | 11.779 |
| AUTO-74824694 | AUTO-74824694 | fast | 35 | conditionally_supported_identity | 64913 | 33.005 |
| AUTO-8d229584 | AUTO-8d229584 | fast | 35 | ambiguous_identity | 58627 | 7.827 |
| AUTO-c0dd2487 | AUTO-c0dd2487 | fast | 35 | unstable_identity | None | 26.555 |
| AUTO-ec039c38 | AUTO-ec039c38 | fast | 34 | ambiguous_identity | 66793 | 6.255 |
| AUTO-181f6b0c | AUTO-181f6b0c | fast | 34 | conditionally_supported_identity | 64388 | 32.357 |
| AUTO-68de2bf0 | AUTO-68de2bf0 | fast | 34 | unstable_identity | None | 1.196 |
| AUTO-be763ba1 | AUTO-be763ba1 | fast | 34 | prediction_mismatch | 65062 | 118.750 |
| AUTO-5b808147 | AUTO-5b808147 | fast | 34 | ambiguous_identity | 66168 | 2.437 |
| AUTO-0c81fa24 | AUTO-0c81fa24 | fast | 34 | ambiguous_identity | 58969 | 5.883 |
| AUTO-68de2bf0 | AUTO-68de2bf0 | fast | 34 | unstable_identity | None | 1.835 |
| LATER4-0002 | LATER4-0002 | fast | 34 | conditionally_supported_identity | 58636 | 130.836 |
| AUTO-2794bb32 | AUTO-2794bb32 | fast | 34 | prediction_mismatch | 59012 | 373.254 |
| AUTO-a60b939e | AUTO-a60b939e | fast | 34 | conditionally_supported_identity | 67923 | 10.395 |
| AUTO-68de2bf0 | AUTO-68de2bf0 | fast | 34 | unstable_identity | None | 1.393 |
| DS25-0044 | DS24-0063 | adaptive | 33 | ambiguous_identity | 63956 | 2.158 |
| AUTO-a60b939e | AUTO-a60b939e | fast | 33 | conditionally_supported_identity | 68106 | 326.295 |
| AUTO-83539f7e | AUTO-83539f7e | fast | 33 | unstable_identity | None | 0.251 |
| AUTO-9fdf64ed | AUTO-9fdf64ed | fast | 33 | conditionally_supported_identity | 57851 | 10.007 |
| AUTO-b73e9d87 | AUTO-b73e9d87 | fast | 33 | conditionally_supported_identity | 57462 | 210.105 |
| AUTO-03f9876c | AUTO-03f9876c | fast | 32 | ambiguous_identity | 59963 | 9.087 |
| AUTO-5b808147 | AUTO-5b808147 | fast | 32 | conditionally_supported_identity | 48445 | 3927.459 |
| AUTO-5cf2a9a9 | AUTO-5cf2a9a9 | fast | 32 | conditionally_supported_identity | 64019 | 923.943 |
| AUTO-23cbdbf3 | AUTO-23cbdbf3 | fast | 32 | conditionally_supported_identity | 59740 | 32.356 |
| DS25-0004 | DS24-0023 | adaptive | 32 | conditionally_supported_identity | 56777 | 12.928 |
| AUTO-e9e5b047 | AUTO-e9e5b047 | fast | 32 | conditionally_supported_identity | 65204 | 77.232 |
| V03 | V03 | fast | 32 | conditionally_supported_identity | 58829 | 89.139 |

## Matched position inclusion

All supported identities receive matched controls/additions and c=0/fitted-c tests using causal candidates, existing physical priors and the same regional initialization. New-family phase quadrature is 0.025 seconds. The numerical-only retry selector produces **7** follow-ups, with matched Powell controls/additions and unchanged physical gates. Original and follow-up outputs remain in [comparisons.csv](comparisons.csv).

| scan | norad | points | qualified | c0_before_km | c0_after_km | fitted_c_before_km | fitted_c_after_km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-74824694 | 64913 | 36 | False | 1.351 | 1.136 | 1.214 | 1.029 |
| V03 | 59189 | 35 | False | 0.958 | 0.989 | 0.954 | 0.976 |
| AUTO-acd7c83d | 62180 | 35 | True | 1.197 | 1.626 | 1.142 | 1.499 |
| AUTO-69e994bf | 66136 | 35 | True | 1.516 | 1.442 | 1.534 | 1.437 |
| AUTO-74824694 | 64913 | 35 | False | 1.351 | 1.103 | 1.214 | 0.990 |
| AUTO-181f6b0c | 64388 | 34 | True | 0.638 | 0.620 | 0.693 | 0.669 |
| LATER4-0002 | 58636 | 34 | False | 0.876 | 0.813 | 0.795 | 0.726 |
| AUTO-a60b939e | 67923 | 34 | True | 0.943 | 0.959 | 0.936 | 0.959 |
| AUTO-a60b939e | 68106 | 33 | True | 0.943 | 0.956 | 0.936 | 0.958 |
| AUTO-9fdf64ed | 57851 | 33 | True | 1.243 | 1.233 | 1.271 | 1.240 |
| AUTO-b73e9d87 | 57462 | 33 | False | 1.520 | 1.463 | 1.508 | 1.451 |
| AUTO-5b808147 | 48445 | 32 | False | 0.447 | 4.548 | 0.297 | 4.578 |
| AUTO-5cf2a9a9 | 64019 | 32 | False | 1.052 | 1.157 | 1.184 | 1.294 |
| AUTO-23cbdbf3 | 59740 | 32 | False | 1.245 | 1.265 | 1.402 | 1.439 |
| DS25-0004 | 56777 | 32 | False | 1.676 | 1.861 | 1.609 | 1.855 |
| AUTO-e9e5b047 | 65204 | 32 | True | 1.217 | 1.088 | 1.271 | 1.101 |
| V03 | 58829 | 32 | False | 0.958 | 0.836 | 0.954 | 0.851 |

![Matched position comparison](figures/position_comparison.png)

Qualification requires acceptable residual structure, unchanged incumbent ownership, exact orbital/objective replay and numerical convergence. Qualified membership gains must equal exactly the independently tested target observations. [position_trials.csv](position_trials.csv) reports coverage percentages, point gains, target RMS, objectives and evaluation errors separately. Controls and additions contain different observations; lower raw objectives or more associated points do not prove improved position accuracy. [failed_gates.csv](failed_gates.csv) retains rejected results even if their position errors improve.

Any unscored automatic extension discoveries are excluded from the reviewed association gains using an explicit source-hashed membership audit. The raw membership remains unchanged, and raw versus reviewed counts are recorded separately. Such an audit must prove that incidental points never entered the position objective and that old owners and the tested target are preserved. It does not validate the incidental points themselves.

![Curves 1](figures/curves_1.png)
![Curves 2](figures/curves_2.png)
![Curves 3](figures/curves_3.png)
![Curves 4](figures/curves_4.png)
![Curves 5](figures/curves_5.png)
![Curves 6](figures/curves_6.png)
![Curves 7](figures/curves_7.png)
![Curves 8](figures/curves_8.png)

## Remaining work

**370 shifted-origin candidates and 859 older-role reassessments remain. These queues overlap and must not be added.** The [updated 1,630-row ledger](annotation_ledger.csv) preserves earlier ambiguity, rejections, native-IQ withholdings and joint-family results. Pass the corresponding `remaining_*_candidates.json` file to the next queue invocation using `--remaining-candidates`.

Continue bounded annotation/inclusion batches and independently supported model challenges. Research recoveries require joint consistency and cohort evaluation before promotion. Evaluation GPS never selects satellites or partitions; causal TLEs and physical gates remain unchanged. No new RF or production changes occurred. Source hashes, terminal receipts, physical partition assignments, compact scientific evidence and all figures accompany this report. The complete annotation-and-inclusion objective is unfinished.
