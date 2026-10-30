# Shifted-origin annotation batch 4

The next **32** wholly unowned curves from the frozen timestamp-selected queue have complete predictive-only assessments. Outcomes: **{'conditionally_supported_identity': 13, 'ambiguous_identity': 10, 'unstable_identity': 3, 'prediction_mismatch': 6}**. There are **13 full position trials**, with **7 RF-qualified curves / 196 points** in separate trials. This is not a combined recovery or a production change.

All 13 initially supported identities were reassessed with a candidate cap of 12 before position inclusion. 0 lost conditional support. The original scores, c arms, aliases and physical partitions replay unchanged; [candidate_competition.csv](candidate_competition.csv) records both outcomes and actual candidate counts. This expands the existing geometry nomination shortlist; it is not an exhaustive all-catalogue likelihood search.

## Scope, validation and capture provenance

Selection follows native point count and immutable track ID without GPS ranking. The reconciled remaining-candidate file prevents repeating assessments completed in other queues. Every target has three distinct timestamp-selected physical holdout sets, with seeded block origins, 12-second blocks, two-second guards, at least eight training points and four held points. Sets overlap and are not independent replications. No target calibrates the receiver during annotation; the graph and incumbent identities remain conditioning assumptions.

Capture modes are **{'fast': 31, 'adaptive': 1}**. Adaptive records use their authoritative source case in tables, retaining historical inventory aliases separately. Direct scanner contracts and digest-verified acquisition manifests establish capture provenance; the fast adapter compatibility label does not. Canonical source identities prevent an adaptive recovery from being reported as a fast-scan result.

| scan | inventory_alias | capture_mode | points | status | norad | margin |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO-20cb1fdb | AUTO-20cb1fdb | fast | 29 | conditionally_supported_identity | 62894 | 13.604 |
| AUTO-f08da5cb | AUTO-f08da5cb | fast | 29 | ambiguous_identity | 63407 | 2.666 |
| V01 | V01 | fast | 29 | unstable_identity | None | 4.053 |
| AUTO-711ef0bb | AUTO-711ef0bb | fast | 29 | conditionally_supported_identity | 66473 | 37.662 |
| AUTO-9b822a70 | AUTO-9b822a70 | fast | 29 | conditionally_supported_identity | 56842 | 32.168 |
| AUTO-3ec63849 | AUTO-3ec63849 | fast | 28 | ambiguous_identity | 65693 | 0.085 |
| AUTO-e9398e7a | AUTO-e9398e7a | fast | 28 | conditionally_supported_identity | 62501 | 157.903 |
| AUTO-7ec14096 | AUTO-7ec14096 | fast | 28 | prediction_mismatch | 55674 | 53.792 |
| AUTO-c5358188 | AUTO-c5358188 | fast | 28 | conditionally_supported_identity | 68301 | 89.057 |
| AUTO-b5002270 | AUTO-b5002270 | fast | 28 | prediction_mismatch | 56695 | 167.569 |
| V06 | V06 | fast | 28 | ambiguous_identity | 64472 | 3.206 |
| AUTO-69e994bf | AUTO-69e994bf | fast | 28 | prediction_mismatch | 59488 | 29.758 |
| DS24-0016 | DS24-0016 | fast | 28 | conditionally_supported_identity | 59786 | 231.032 |
| AUTO-d9185bf9 | AUTO-d9185bf9 | fast | 28 | conditionally_supported_identity | 66350 | 19.244 |
| DS24-0097 | DS24-0097 | fast | 28 | conditionally_supported_identity | 58869 | 15.550 |
| AUTO-a3e1d854 | AUTO-a3e1d854 | fast | 28 | ambiguous_identity | 59647 | 0.254 |
| AUTO-f122bc7e | AUTO-f122bc7e | fast | 28 | prediction_mismatch | 65283 | 1185.643 |
| DS25-0069 | DS24-0102 | adaptive | 28 | ambiguous_identity | 61924 | 7.556 |
| AUTO-3dbe7ded | AUTO-3dbe7ded | fast | 28 | conditionally_supported_identity | 65070 | 19.814 |
| AUTO-dd3cc4da | AUTO-dd3cc4da | fast | 28 | ambiguous_identity | 64357 | 0.755 |
| V01 | V01 | fast | 28 | conditionally_supported_identity | 60335 | 270.666 |
| AUTO-a2303eb8 | AUTO-a2303eb8 | fast | 28 | prediction_mismatch | 67321 | 4.129 |
| AUTO-2e19f5b8 | AUTO-2e19f5b8 | fast | 28 | ambiguous_identity | 57523 | 2.868 |
| AUTO-11fd4ed1 | AUTO-11fd4ed1 | fast | 28 | ambiguous_identity | 52121 | 0.060 |
| AUTO-c2a62141 | AUTO-c2a62141 | fast | 28 | prediction_mismatch | 65074 | 49.561 |
| DS24-0019 | DS24-0019 | fast | 28 | conditionally_supported_identity | 48323 | 74.532 |
| AUTO-51b666f4 | AUTO-51b666f4 | fast | 27 | unstable_identity | None | 6.440 |
| AUTO-92ca44e2 | AUTO-92ca44e2 | fast | 27 | ambiguous_identity | 69313 | 9.189 |
| DS24-0016 | DS24-0016 | fast | 27 | conditionally_supported_identity | 69746 | 1127.103 |
| AUTO-270c8059 | AUTO-270c8059 | fast | 27 | conditionally_supported_identity | 64746 | 11.606 |
| AUTO-b1277aa8 | AUTO-b1277aa8 | fast | 27 | ambiguous_identity | 52096 | 0.388 |
| AUTO-ec89779a | AUTO-ec89779a | fast | 27 | unstable_identity | None | 77.017 |

## Matched position inclusion

All supported identities receive matched controls/additions and c=0/fitted-c tests using causal candidates, existing physical priors and the same regional initialization. New-family phase quadrature is 0.025 seconds. The numerical-only retry selector produces **3** follow-ups, with matched Powell controls/additions and unchanged physical gates. Original and follow-up outputs remain in [comparisons.csv](comparisons.csv).

| scan | norad | points | qualified | c0_before_km | c0_after_km | fitted_c_before_km | fitted_c_after_km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-20cb1fdb | 62894 | 29 | True | 0.494 | 0.483 | 0.478 | 0.467 |
| AUTO-711ef0bb | 66473 | 29 | False | 1.386 | 1.242 | 1.362 | 1.220 |
| AUTO-9b822a70 | 56842 | 29 | True | 0.478 | 0.492 | 0.371 | 0.373 |
| AUTO-e9398e7a | 62501 | 28 | True | 1.196 | 1.146 | 1.186 | 1.143 |
| AUTO-c5358188 | 68301 | 28 | False | 1.176 | 0.428 | 1.133 | 0.406 |
| DS24-0016 | 59786 | 28 | False | 0.588 | 0.318 | 0.586 | 0.336 |
| AUTO-d9185bf9 | 66350 | 28 | True | 0.770 | 0.719 | 0.791 | 0.739 |
| DS24-0097 | 58869 | 28 | True | 0.888 | 0.889 | 0.833 | 0.835 |
| AUTO-3dbe7ded | 65070 | 28 | False | 1.089 | 0.626 | 1.089 | 0.629 |
| V01 | 60335 | 28 | False | 1.073 | 1.023 | 1.078 | 1.024 |
| DS24-0019 | 48323 | 28 | False | 1.181 | 1.856 | 1.223 | 1.891 |
| DS24-0016 | 69746 | 27 | True | 0.588 | 0.634 | 0.586 | 0.631 |
| AUTO-270c8059 | 64746 | 27 | True | 0.121 | 0.076 | 0.072 | 0.038 |

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

**306 shifted-origin candidates and 828 older-role reassessments remain. These queues overlap and must not be added.** The [updated 1,630-row ledger](annotation_ledger.csv) preserves earlier ambiguity, rejections, native-IQ withholdings and joint-family results. Pass the corresponding `remaining_*_candidates.json` file to the next queue invocation using `--remaining-candidates`.

Continue bounded annotation/inclusion batches and independently supported model challenges. Research recoveries require joint consistency and cohort evaluation before promotion. Evaluation GPS never selects satellites or partitions; causal TLEs and physical gates remain unchanged. No new RF or production changes occurred. Source hashes, terminal receipts, physical partition assignments, compact scientific evidence and all figures accompany this report. The complete annotation-and-inclusion objective is unfinished.
