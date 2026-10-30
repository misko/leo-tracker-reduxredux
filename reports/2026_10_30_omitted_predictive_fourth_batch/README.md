# Continuing omitted-track predictive recovery

**Capture-mode correction:** the all-adaptive interpretation below is superseded by the [acquisition-provenance audit](../2026_10_30_predictive_role_reassessment/README.md). Fast compatibility exports encode `capture_mode=adaptive`; this is not acquisition provenance. Across the full 53-curve queue, verified acquisition evidence gives 49 fast and four adaptive recordings. The four legacy DS24 aliases mapped to DS25 in this report remain adaptive; its nine AUTO cases are fast. The linked 69-row provenance table supersedes this report's capture-mode fields. Scientific trial outputs and position errors are unchanged.

This batch processes **13** candidates from the previous immutable remaining manifest. **8 tracks / 180 distinct points** qualify under the current predictive checks; **180 points** are additional to the prior reviewed set. **0 candidates remain** in this omitted-curve queue. The full 1,630-curve objective and the larger calibration-participating annotation backlog remain unfinished.

## Validation, scope and model

Selection is by descending point count, without GPS error or satellite labels. Every supported identity is revalidated using three distinct timestamp-selected random scanwide 12-second holdouts and two-second guards. The report replays the held point sets and requires three distinct sets. Targets remain predictive evidence and do not calibrate receiver offsets or drift. Causal TLEs, physical nuisance priors, the 25 × 25 km regional start, and matched c=0/fitted-c data and budgets are retained. Evaluation GPS is used only to report error.

Annotation outcomes: **{'insufficient_partitions': 3, 'conditionally_supported_identity': 10}**. Capture modes from raw tracking metadata: **{'adaptive': 13}**. Filenames and inherited sample-rate fields are not used as capture-mode evidence. [annotations.csv](annotations.csv) records the mode, sample rate, identity and validation state for every curve. Insufficient partitions mean unavailable validation evidence, not a noise classification.

## Position inclusion and retained failures

The frozen inventory retains four legacy DS24 aliases. Their actual source cases are adaptive DS25 recordings: **DS24-0074 → DS25-0055**, **DS24-0047 → DS25-0028**, **DS24-0052 → DS25-0033**, and **DS24-0028 → DS25-0009**. The native-curve plot titles show these DS25 source components. These rows must not be used as fast-scan results. All 13 cases in this batch are adaptive according to tracking metadata.

New-family trials integrate causal phase at 0.025-second spacing and orbital/receiver uncertainty. Shared-family trials use existing family evidence. Controls and additions start at the same regional center. Only numerical-only failures passing physical, phase, ownership and exact-orbit checks receive a separate matched Powell retry in both c arms. The residual limits remain unchanged. Every original and retry result is retained in [all_position_trials.csv](all_position_trials.csv), with objectives, position errors and residual diagnostics reported separately.

| scan | norad | points | qualified | status | c0_before_km | c0_after_km | fitted_c_before_km | fitted_c_after_km |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUTO-3dbe7ded | None | 28 | False | refreshed_identity_not_supported | None | None | None | None |
| AUTO-c9b43371 | 62754 | 27 | False | inclusion_rejected | 0.663 | 0.695 | 0.604 | 0.638 |
| AUTO-03f9876c | None | 27 | False | refreshed_identity_not_supported | None | None | None | None |
| AUTO-ab6bcf0a | None | 27 | False | refreshed_identity_not_supported | None | None | None | None |
| AUTO-fa9f2154 | 64603 | 25 | True | RF_verified_research_candidate | 1.486 | 1.437 | 1.497 | 1.474 |
| AUTO-dd3cc4da | 64368 | 24 | True | RF_verified_research_candidate | 0.539 | 0.539 | 0.622 | 0.620 |
| AUTO-49154edb | 66522 | 24 | True | RF_verified_research_candidate | 0.666 | 0.597 | 0.548 | 0.490 |
| DS24-0074 | 62433 | 23 | True | RF_verified_research_candidate | 1.516 | 1.531 | 1.359 | 1.367 |
| AUTO-89080200 | 57895 | 23 | False | inclusion_rejected | 0.576 | 0.705 | 0.514 | 0.663 |
| DS24-0047 | 59513 | 22 | True | RF_verified_research_candidate | 1.140 | 1.357 | 1.332 | 1.580 |
| DS24-0052 | 68387 | 21 | True | RF_verified_research_candidate | 1.026 | 0.575 | 0.742 | 0.466 |
| DS24-0028 | 57094 | 21 | True | RF_verified_research_candidate | 0.980 | 0.758 | 0.983 | 0.726 |
| AUTO-1bdd0cd7 | 67597 | 20 | True | RF_verified_research_candidate | 1.997 | 1.724 | 2.055 | 1.788 |

![Position comparisons](figures/position_comparison.png)

| scan | qualified | baseline_percent | proposed_percent | credited_points |
| --- | --- | --- | --- | --- |
| AUTO-c9b43371 | False | 77.615 | 78.171 | 0 |
| AUTO-fa9f2154 | True | 75.518 | 76.315 | 25 |
| AUTO-dd3cc4da | True | 68.524 | 69.029 | 24 |
| AUTO-49154edb | True | 73.786 | 74.304 | 24 |
| DS24-0074 | True | 62.247 | 63.381 | 23 |
| AUTO-89080200 | False | 64.279 | 64.796 | 0 |
| DS24-0047 | True | 57.055 | 58.742 | 22 |
| DS24-0052 | True | 69.439 | 71.470 | 21 |
| DS24-0028 | True | 65.596 | 67.001 | 21 |
| AUTO-1bdd0cd7 | True | 70.905 | 71.404 | 20 |

Proposed coverage is shown for rejected trials but receives no credited points. Passing trials preserve all incumbent IDs and owners in exact orbit replay. More associated points do not necessarily improve location; evaluation error never selects a recovery or relaxes a gate. Scores for different observation counts are not directly comparable accuracy measures.

## Native curves and residuals

![Curves 1](figures/curves_1.png)
![Curves 2](figures/curves_2.png)
![Curves 3](figures/curves_3.png)
![Curves 4](figures/curves_4.png)

Every selected curve is shown, including unresolved cases. No fitted satellite orbit is shown when refreshed identity validation does not authorize inclusion. Low RMS alone is insufficient; residual mean, slope, quadratic structure, steps and serial correlation remain checked.



## Cumulative state and simultaneous-fit limits

The omitted-curve series contains **823 distinct reviewed candidate points** after this batch, compared with 643 before. Earlier review reversals are preserved: the two 67653 curves with a common residual bend remain withheld. The cumulative union rejects conflicting satellite ownership and avoids duplicate credit. It is an inventory of per-curve research candidates, **not a single simultaneous solution or dataset-wide location-accuracy result**.

[joint_family_work.json](joint_family_work.json) records same-scan/same-satellite groups and whether they already have an approved common-residual joint audit. **0 groups in this series still need such a joint check**. Different recovered families within a scan also require a simultaneous treatment of shared receiver uncertainty before a final combined scan result can be claimed. No earlier partial qualification is silently promoted.

The [updated 1,630-row ledger](annotation_ledger.csv), [remaining candidate manifest](remaining_omitted_candidates.json), and [reviewed series](series_qualified_trials.json) retain the next work and its provenance. [Execution receipts](executions.csv), exact-replay source hashes and compact evidence accompany the results. Production is unchanged; no future TLE, new RF acquisition, threshold relaxation or ALGO promotion is introduced.
