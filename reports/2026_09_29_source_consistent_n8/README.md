# Source-consistent N8 selection has mixed geographic transfer

Enforcing source consistency across eight time-balanced scans improves reference distance on DS9 and worsens DS7 and DS8. Only DS8 is below 1 km, before and after selection. Held prediction improves on the retained tracks in all three datasets, but that does not establish a geographic improvement. Do not replace the all-track pooled baseline with this greedy subset rule.

| Dataset | Tracks before → after | Training retained | All-track reference distance (m) | Source-consistent distance (m) | Matched retained-track held change (nats) |
|---|---:|---:|---:|---:|---:|
| DS7 | 476 → 343 | 76.2% | 1,688.3 | 1,894.8 | +7.73 |
| DS8 | 478 → 365 | 79.5% | 722.1 | 820.5 | +28.07 |
| DS9 | 489 → 356 | 78.7% | 2,041.9 | 1,810.8 | +14.25 |

These are one eight-scan set per dataset, not dataset medians or independent blind trials. [Full-precision summary](summary.json) · [Frozen protocol](PROTOCOL.md)

## Fixed comparison

The three scan sets are exactly the existing `grid_DS*_balanced_0` memberships. All eight scans remain in each arm. The original all-track fit is reused only after ordered-session, qualification and score-replay checks. The selected-track arm uses the original six generic cold/grid starts, q=0.2 likelihood, bounds and numerical gates. All 18 new starts qualify.

Within each scan, apply the unchanged source-consistent selector from the [single-scan pilot](../2026_09_29_source_consistent_pilot/README.md). Rank tracks by training support and deterministic IDs, consider each seeded greedy closure, and choose greatest retained training coverage. No detector margin, held signal score, reference coordinate or fit result selects tracks. Selected tracks have no shared source-group IDs. All-point support identities are used, including held support; this remains support-aware exploratory selection.

The held-score comparison evaluates both parameter vectors on exactly the same retained tracks. Removed tracks constitute lost coverage and are not silently counted as held successes. Absolute likelihoods on unequal track sets are not compared as evidence of improvement.

## Provenance expansion

Reused the three previously verified first-scan quality sidecars and exported the remaining 21 through the same corrected pinned public read-only adapter. All 21 succeeded within their 60-second limits, with no replacement scans or retries. The 24 sidecars cover **65,891 exported observations in 1,444 exported tracks**. One DS8 exported track is excluded by the baseline loader's existing eligibility rule; the comparison starts from 1,443 eligible tracks.

Every sidecar binds track point identity, time, canonical dealiased frequency, receiver/channel/RF and visit to the existing export, plus capture and analysis manifest digests. Pinned runtime module hashes are checked by the shared exporter. [quality-seal.json](quality-seal.json) freezes all 24 sidecar hashes before fitting. Original exported observations, candidate banks and published contracts remain unchanged.

## Interpretation

The prior audit established a source-level conflict under the archived trajectory hypothesis rule: different track alternatives can reuse the same probe group. This study shows that a simple coverage-maximizing hard choice is not enough to obtain better geographic estimates. It discards 20–24% of training observations and can remove useful constraints together with conflicting alternatives.

This result does not validate treating all alternatives as independent. It distinguishes a provenance problem from the effectiveness of this particular remedy. Nor do the positive retained-track held changes certify accuracy: two of three reference distances worsen despite those gains.

The next modeling step should preserve competing interpretations with an explicit likelihood for the same underlying probe data, rather than merely dropping whole tracks. A naive mixture of track-set likelihoods with different observation dimensions would be invalid as a matched comparison unless it also models omitted data. Before implementation, establish that observation model and use the present source-group inventory to bound its scope. Continue retaining ordinary pooling as a mandatory control.

## Validation and artifacts

The unchanged selector's two tests passed in the preceding pilot. This run adds actual-data checks across all 24 scans for sidecar alignment, partition alignment, source-disjoint retained sets, original-score replay, timing-grid replay and optimizer/gradient qualification. Each dataset fit completed in 23–34 seconds under its 180-second cap. Metadata extraction and fitting failures would remain failures; none occurred.

[prepare.py](prepare.py), [export wrapper](export.py), [run.py](run.py), [fit_batch.py](fit_batch.py), [input/code hashes](manifest.json), all sidecars, selected and alternative subsets, optimizer starts, process receipts, and [summarize.py](summarize.py) are retained. Exclusive output creation prevents overwriting completed evidence.

Reference uncertainty remains unquantified, candidate banks remain site-conditioned, and these data were previously exposed. No IQ reads, new RF collection, production changes, golden-fixture edits or remote publication occurred.
