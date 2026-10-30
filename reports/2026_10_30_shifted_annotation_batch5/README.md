# Shifted-origin annotation batch 5

The next **32** wholly unowned curves from the frozen timestamp-selected queue have complete predictive-only assessments. Outcomes: **{'unstable_identity': 8, 'conditionally_supported_identity': 19, 'ambiguous_identity': 5}**. There are **19 full position trials**, with **15 RF-qualified curves / 399 points** in separate trials. This is not a combined recovery or a production change.

All 19 initially supported identities were reassessed with a candidate cap of 12 before position inclusion. 0 lost conditional support. The original scores, c arms, aliases and physical partitions replay unchanged; [candidate_competition.csv](candidate_competition.csv) records both outcomes and actual candidate counts. This expands the existing geometry nomination shortlist; it is not an exhaustive all-catalogue likelihood search.

## Scope, validation and capture provenance

Selection follows native point count and immutable track ID without GPS ranking. The reconciled remaining-candidate file prevents repeating assessments completed in other queues. Every target has three distinct timestamp-selected physical holdout sets, with seeded block origins, 12-second blocks, two-second guards, at least eight training points and four held points. Sets overlap and are not independent replications. No target calibrates the receiver during annotation; the graph and incumbent identities remain conditioning assumptions.

Capture modes are **{'adaptive': 4, 'fast': 28}**. Adaptive records use their authoritative source case in tables, retaining historical inventory aliases separately. Direct scanner contracts and digest-verified acquisition manifests establish capture provenance; the fast adapter compatibility label does not. Canonical source identities prevent an adaptive recovery from being reported as a fast-scan result.

| scan | inventory_alias | capture_mode | points | status | norad | margin |
| --- | --- | --- | --- | --- | --- | --- |
| AUTO-49154edb | AUTO-49154edb | fast | 27 | unstable_identity | None | 84.911 |
| AUTO-1ee2d79a | AUTO-1ee2d79a | fast | 27 | unstable_identity | None | 23.982 |
| AUTO-03f9876c | AUTO-03f9876c | fast | 27 | conditionally_supported_identity | 66152 | 42.366 |
| AUTO-16a2e9fd | AUTO-16a2e9fd | fast | 27 | conditionally_supported_identity | 100149 | 247.091 |
| DS25-0044 | DS24-0063 | adaptive | 27 | conditionally_supported_identity | 63404 | 13.503 |
| V07 | V07 | fast | 27 | conditionally_supported_identity | 63073 | 208.814 |
| DS25-0025 | DS24-0044 | adaptive | 27 | ambiguous_identity | 63578 | 0.783 |
| AUTO-26dcef1d | AUTO-26dcef1d | fast | 27 | conditionally_supported_identity | 57506 | 14.525 |
| AUTO-68de2bf0 | AUTO-68de2bf0 | fast | 27 | ambiguous_identity | 57771 | 3.167 |
| AUTO-b8d02b67 | AUTO-b8d02b67 | fast | 27 | conditionally_supported_identity | 56517 | 152.859 |
| AUTO-b5b6c39f | AUTO-b5b6c39f | fast | 27 | conditionally_supported_identity | 59898 | 553.988 |
| AUTO-ab6bcf0a | AUTO-ab6bcf0a | fast | 27 | conditionally_supported_identity | 69822 | 69.680 |
| AUTO-1bdd0cd7 | AUTO-1bdd0cd7 | fast | 27 | unstable_identity | None | 0.079 |
| DS24-0010 | DS24-0010 | fast | 27 | unstable_identity | None | 0.117 |
| DS25-0022 | DS24-0041 | adaptive | 27 | unstable_identity | None | 0.979 |
| AUTO-afec5a1f | AUTO-afec5a1f | fast | 27 | conditionally_supported_identity | 54862 | 22.856 |
| AUTO-5214b4d6 | AUTO-5214b4d6 | fast | 27 | unstable_identity | None | 1.355 |
| DS24-0017 | DS24-0017 | fast | 27 | conditionally_supported_identity | 62571 | 84.395 |
| AUTO-ff2429e3 | AUTO-ff2429e3 | fast | 27 | conditionally_supported_identity | 59685 | 76.622 |
| AUTO-c2a62141 | AUTO-c2a62141 | fast | 27 | unstable_identity | None | 4.178 |
| DS25-0015 | DS24-0034 | adaptive | 26 | ambiguous_identity | 67428 | 0.242 |
| AUTO-1b0bc73a | AUTO-1b0bc73a | fast | 26 | conditionally_supported_identity | 60094 | 34.575 |
| AUTO-f0255747 | AUTO-f0255747 | fast | 26 | ambiguous_identity | 59746 | 3.101 |
| AUTO-92ca44e2 | AUTO-92ca44e2 | fast | 26 | unstable_identity | None | 134.653 |
| AUTO-e565210d | AUTO-e565210d | fast | 26 | conditionally_supported_identity | 59340 | 22.337 |
| AUTO-a29c5f7d | AUTO-a29c5f7d | fast | 26 | conditionally_supported_identity | 68733 | 246.373 |
| AUTO-51b666f4 | AUTO-51b666f4 | fast | 26 | ambiguous_identity | 62495 | 1.877 |
| AUTO-dd3cc4da | AUTO-dd3cc4da | fast | 26 | conditionally_supported_identity | 64368 | 303.971 |
| AUTO-9e6dd08c | AUTO-9e6dd08c | fast | 26 | conditionally_supported_identity | 65324 | 103.952 |
| AUTO-0bda4436 | AUTO-0bda4436 | fast | 26 | conditionally_supported_identity | 65855 | 2484.904 |
| AUTO-89080200 | AUTO-89080200 | fast | 26 | conditionally_supported_identity | 59362 | 14.785 |
| DS24-0101 | DS24-0101 | fast | 26 | conditionally_supported_identity | 100494 | 566.406 |

## Matched position inclusion

All supported identities receive matched controls/additions and c=0/fitted-c tests using causal candidates, existing physical priors and the same regional initialization. New-family phase quadrature is 0.025 seconds. The numerical-only retry selector produces **6** follow-ups, with matched Powell controls/additions and unchanged physical gates. Original and follow-up outputs remain in [comparisons.csv](comparisons.csv).

| scan | norad | points | qualified | c0_before_km | c0_after_km | fitted_c_before_km | fitted_c_after_km |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-03f9876c | 66152 | 27 | True | 8.038 | 7.771 | 8.046 | 7.779 |
| AUTO-16a2e9fd | 100149 | 27 | False | 0.379 | 0.293 | 0.633 | 0.499 |
| DS25-0044 | 63404 | 27 | True | 2.632 | 2.819 | 2.303 | 2.503 |
| V07 | 63073 | 27 | True | 1.210 | 1.227 | 1.273 | 1.291 |
| AUTO-26dcef1d | 57506 | 27 | False | 0.454 | 0.383 | 0.497 | 0.386 |
| AUTO-b8d02b67 | 56517 | 27 | True | 1.675 | 1.678 | 1.995 | 1.988 |
| AUTO-b5b6c39f | 59898 | 27 | True | 0.630 | 0.617 | 0.543 | 0.529 |
| AUTO-ab6bcf0a | 69822 | 27 | True | 1.081 | 0.897 | 1.096 | 0.916 |
| AUTO-afec5a1f | 54862 | 27 | True | 0.575 | 0.484 | 0.564 | 0.470 |
| DS24-0017 | 62571 | 27 | True | 1.904 | 1.867 | 1.854 | 1.816 |
| AUTO-ff2429e3 | 59685 | 27 | True | 1.021 | 1.028 | 1.053 | 1.044 |
| AUTO-1b0bc73a | 60094 | 26 | False | 0.647 | 0.810 | 0.733 | 0.907 |
| AUTO-e565210d | 59340 | 26 | True | 0.916 | 0.917 | 1.001 | 1.002 |
| AUTO-a29c5f7d | 68733 | 26 | True | 0.531 | 0.543 | 0.523 | 0.517 |
| AUTO-dd3cc4da | 64368 | 26 | True | 0.539 | 0.529 | 0.623 | 0.612 |
| AUTO-9e6dd08c | 65324 | 26 | True | 0.079 | 0.127 | 0.129 | 0.182 |
| AUTO-0bda4436 | 65855 | 26 | True | 0.670 | 0.672 | 0.745 | 0.748 |
| AUTO-89080200 | 59362 | 26 | False | 0.576 | 0.577 | 0.514 | 0.518 |
| DS24-0101 | 100494 | 26 | True | 2.089 | 2.053 | 2.141 | 2.088 |

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

**274 shifted-origin candidates and 821 older-role reassessments remain. These queues overlap and must not be added.** The [updated 1,630-row ledger](annotation_ledger.csv) preserves earlier ambiguity, rejections, native-IQ withholdings and joint-family results. Pass the corresponding `remaining_*_candidates.json` file to the next queue invocation using `--remaining-candidates`.

Continue bounded annotation/inclusion batches and independently supported model challenges. Research recoveries require joint consistency and cohort evaluation before promotion. Evaluation GPS never selects satellites or partitions; causal TLEs and physical gates remain unchanged. No new RF or production changes occurred. Source hashes, terminal receipts, physical partition assignments, compact scientific evidence and all figures accompany this report. The complete annotation-and-inclusion objective is unfinished.
