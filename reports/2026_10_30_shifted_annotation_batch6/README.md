# Shifted-origin annotation batch 6

The next **32** wholly unowned curves from the frozen timestamp-selected queue have complete predictive-only assessments. Outcomes: **{'conditionally_supported_identity': 7, 'ambiguous_identity': 9, 'unstable_identity': 9, 'prediction_mismatch': 7}**. There are **7 full position trials**, with **4 RF-qualified curves / 103 points** in separate trials. This is not a combined recovery or a production change.

All 7 initially supported identities were reassessed with a candidate cap of 12 before position inclusion. 0 lost conditional support. The original scores, c arms, aliases and physical partitions replay unchanged; [candidate_competition.csv](candidate_competition.csv) records both outcomes and actual candidate counts. This expands the existing geometry nomination shortlist; it is not an exhaustive all-catalogue likelihood search.

## Scope, validation and capture provenance

Selection follows native point count and immutable track ID without GPS ranking. The reconciled remaining-candidate file prevents repeating assessments completed in other queues. Every target has three distinct timestamp-selected physical holdout sets, with seeded block origins, 12-second blocks, two-second guards, at least eight training points and four held points. Sets overlap and are not independent replications. No target calibrates the receiver during annotation; the graph and incumbent identities remain conditioning assumptions.

Capture modes are **{'adaptive': 3, 'fast': 29}**. Adaptive records use their authoritative source case in tables, retaining historical inventory aliases separately. Direct scanner contracts and digest-verified acquisition manifests establish capture provenance; the fast adapter compatibility label does not. Canonical source identities prevent an adaptive recovery from being reported as a fast-scan result.

| scan | inventory_alias | capture_mode | points | status | norad | margin |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO-0a6bb3b1 | AUTO-0a6bb3b1 | fast | 26 | conditionally_supported_identity | 68547 | 147.822 |
| AUTO-0c81fa24 | AUTO-0c81fa24 | fast | 26 | conditionally_supported_identity | 61975 | 36.795 |
| AUTO-03f9876c | AUTO-03f9876c | fast | 26 | conditionally_supported_identity | 64413 | 77.066 |
| AUTO-9efe3f9e | AUTO-9efe3f9e | fast | 26 | ambiguous_identity | 68975 | 3.086 |
| AUTO-6882410c | AUTO-6882410c | fast | 26 | unstable_identity | None | 0.170 |
| AUTO-93f98683 | AUTO-93f98683 | fast | 26 | unstable_identity | None | 2.450 |
| AUTO-4838aeea | AUTO-4838aeea | fast | 26 | ambiguous_identity | 62183 | 0.397 |
| AUTO-d073d275 | AUTO-d073d275 | fast | 26 | prediction_mismatch | 68810 | 4.217 |
| V02 | V02 | fast | 26 | unstable_identity | None | 0.160 |
| AUTO-5214b4d6 | AUTO-5214b4d6 | fast | 26 | ambiguous_identity | 54869 | 0.116 |
| AUTO-99d8b775 | AUTO-99d8b775 | fast | 26 | ambiguous_identity | 68917 | 0.971 |
| AUTO-5b808147 | AUTO-5b808147 | fast | 26 | prediction_mismatch | 59045 | 381.389 |
| V07 | V07 | fast | 26 | conditionally_supported_identity | 67942 | 10.047 |
| AUTO-75293458 | AUTO-75293458 | fast | 26 | prediction_mismatch | 59310 | 17.515 |
| DS25-0024 | DS24-0043 | adaptive | 26 | conditionally_supported_identity | 69456 | 39.063 |
| DS25-0049 | DS24-0068 | adaptive | 26 | unstable_identity | None | 0.226 |
| DS25-0028 | DS24-0047 | adaptive | 25 | ambiguous_identity | 52552 | 7.008 |
| AUTO-2a5238fb | AUTO-2a5238fb | fast | 25 | ambiguous_identity | 68164 | 3.393 |
| AUTO-5b808147 | AUTO-5b808147 | fast | 25 | prediction_mismatch | 59045 | 404.590 |
| AUTO-73338393 | AUTO-73338393 | fast | 25 | unstable_identity | None | 27.963 |
| AUTO-a3e1d854 | AUTO-a3e1d854 | fast | 25 | ambiguous_identity | 59243 | 1.263 |
| AUTO-2f13639a | AUTO-2f13639a | fast | 25 | unstable_identity | None | 2206.519 |
| AUTO-b845d6a4 | AUTO-b845d6a4 | fast | 25 | ambiguous_identity | 58248 | 1.724 |
| AUTO-64e97379 | AUTO-64e97379 | fast | 25 | unstable_identity | None | 1.000 |
| AUTO-15bba7a1 | AUTO-15bba7a1 | fast | 25 | prediction_mismatch | 65632 | 539.018 |
| AUTO-64e97379 | AUTO-64e97379 | fast | 25 | prediction_mismatch | 58370 | 51.107 |
| AUTO-7568639a | AUTO-7568639a | fast | 25 | prediction_mismatch | 66873 | 8.662 |
| AUTO-23731b0e | AUTO-23731b0e | fast | 25 | conditionally_supported_identity | 62162 | 226.397 |
| AUTO-d5e704b4 | AUTO-d5e704b4 | fast | 25 | ambiguous_identity | 52834 | 0.772 |
| AUTO-765d06ec | AUTO-765d06ec | fast | 25 | unstable_identity | None | 29.393 |
| AUTO-e9e5b047 | AUTO-e9e5b047 | fast | 25 | conditionally_supported_identity | 59201 | 151.431 |
| AUTO-8bdc2943 | AUTO-8bdc2943 | fast | 25 | unstable_identity | None | 1.248 |

## Matched position inclusion

All supported identities receive matched controls/additions and c=0/fitted-c tests using causal candidates, existing physical priors and the same regional initialization. New-family phase quadrature is 0.025 seconds. The numerical-only retry selector produces **0** follow-ups, with matched Powell controls/additions and unchanged physical gates. Original and follow-up outputs remain in [comparisons.csv](comparisons.csv).

| scan | norad | points | qualified | c0_before_km | c0_after_km | fitted_c_before_km | fitted_c_after_km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-0a6bb3b1 | 68547 | 26 | True | 0.974 | 0.941 | 1.063 | 1.021 |
| AUTO-0c81fa24 | 61975 | 26 | False | 0.384 | 0.375 | 0.420 | 0.422 |
| AUTO-03f9876c | 64413 | 26 | True | 8.038 | 7.779 | 8.046 | 7.792 |
| V07 | 67942 | 26 | False | 1.210 | 1.142 | 1.273 | 1.222 |
| DS25-0024 | 69456 | 26 | True | 0.930 | 1.084 | 0.872 | 1.024 |
| AUTO-23731b0e | 62162 | 25 | True | 3.539 | 3.425 | 3.529 | 3.435 |
| AUTO-e9e5b047 | 59201 | 25 | False | 1.218 | 1.199 | 1.270 | 1.252 |

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

**242 shifted-origin candidates and 817 older-role reassessments remain. These queues overlap and must not be added.** The [updated 1,630-row ledger](annotation_ledger.csv) preserves earlier ambiguity, rejections, native-IQ withholdings and joint-family results. Pass the corresponding `remaining_*_candidates.json` file to the next queue invocation using `--remaining-candidates`.

Continue bounded annotation/inclusion batches and independently supported model challenges. Research recoveries require joint consistency and cohort evaluation before promotion. Evaluation GPS never selects satellites or partitions; causal TLEs and physical gates remain unchanged. No new RF or production changes occurred. Source hashes, terminal receipts, physical partition assignments, compact scientific evidence and all figures accompany this report. The complete annotation-and-inclusion objective is unfinished.
