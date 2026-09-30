# Pilot-adjacent regions: revisit correlation and hierarchical clustering

The suspected STARLINK-30257 revisit pair S22/S23 groups together in the
discovery hierarchy, but the earliest-region similarity does not distinguish
that pair reliably from the different-identity comparisons on evaluation.
This is evidence of shared signal structure, not a decoded satellite identifier.

## Recordings and scope

We inspected the existing DS7/DS8/DS9 soft-symbol caches. Frames require both
receivers' held-pilot coherence above 0.5; visits require at least 16 qualified
decoder-evaluation frames. Selection uses pilots, not identity or cluster results.

| Visit | Rate | Edge | Qualified frames | Prior identity |
|---|---:|---|---:|---|
| S13 | 10 MS/s | Upper | 20 | STARLINK-31407 / NORAD 59250 |
| S22 | 10 MS/s | Upper | 32 | STARLINK-30257 / NORAD 57526 |
| S23 | 10 MS/s | Upper | 42 | STARLINK-30257 / NORAD 57526 |
| DS9-middle | 10 MS/s | Lower | 45 | Unknown |
| DS9-last | 10 MS/s | Lower | 45 | Unknown |
| S01 | 5 MS/s | Upper | 44 | Unknown |
| S02 | 5 MS/s | Upper | 41 | Unknown |

Identities are prior conditional geometric/Doppler matches, not decoded fields.
S22/S23 are revisits within the same recording session and encounter, not
independent orbital passes. S13 comes from a different session. The cached
STARLINK-31567 visits S06/S07/S18/S19 and DS9-first fail the visit gate.
This is a bounded cached subset, not an exhaustive reprocessing of the corpus.

The primary 10 MS/s upper comparison uses 24 common non-pilot carriers;
the lower comparison independently uses 24. A supplementary upper comparison
including S01/S02 uses only eight carriers shared by all five visits. Missing
coordinates are never zero-filled, and opposite edges are not aligned as if
they measured the same physical carriers.

We use original caches consistently across visits. The expanded atlas currently
exists for only S23 and DS9-middle and has a different channel fit; mixing it
with the original calibration would introduce another confound. Thus this
comparison does not yet test the four additional paired carriers from that atlas.

## Method

Four fixed regions cover OFDM symbols 2–7, 8–33, 34–129, and 130–301. The
first region targets the previously studied header-like structure; later regions
include varying mixtures of unresolved and known repeating structure. We do
not select individual unresolved cells based on the desired similarity result.

For each carrier/symbol coordinate, normalize each IQ value to unit amplitude
and average across selected frames. Its complex mean describes preferred phase
and phase concentration, including persistent sign bias. Concatenated real and
imaginary components form the visit profile. Pearson correlation compares these
profiles. This does not align messages from different times or measure bit agreement.

Discovery uses RX0 and the earlier half of qualified evaluation frames.
Evaluation uses RX1 and the later half. The profiles therefore use disjoint
frames and different receivers, but share a recording and fitted calibration;
these extensively studied recordings are not pristine holdouts.

Average-linkage hierarchical clustering uses Euclidean distances between centered,
unit-normalized profiles: distance = sqrt(2 × (1 − correlation)). This is a valid
distance geometry; Ward linkage is not applied to an arbitrary correlation matrix.
The displayed ordering is learned on discovery and retained for evaluation.
No satellite labels enter the distance or tree construction.

## Primary 10 MS/s results

Evaluation profile correlations across 24 common upper-edge data carriers:

| OFDM symbols | S22/S23: same tentative ID | S13/S22: different IDs | S13/S23: different IDs |
|---|---:|---:|---:|
| 2–7 | 0.466 | 0.472 | 0.390 |
| 8–33 | 0.209 | 0.053 | 0.058 |
| 34–129 | 0.335 | 0.194 | 0.195 |
| 130–301 | 0.489 | 0.383 | 0.434 |

In symbols 2–7, discovery correlations are 0.540 for S22/S23 versus 0.328
and 0.375 for the different-ID pairs. Thus the discovery tree first joins
S22/S23, but this ordering does not survive evaluation: S13/S22 slightly exceeds
S22/S23. Same-visit discovery/evaluation profile correlations are 0.468 for S13,
0.537 for S22, and 0.748 for S23, indicating unequal stability and quality.

We also draw 200 subsets of ten evaluation frames per visit, without replacement
within a draw. This balances frame counts; it is a sensitivity analysis, not an
independent replication or a confidence interval.

| Early-region pair | Mean balanced correlation | 2.5–97.5% subset range |
|---|---:|---:|
| S22/S23 | 0.355 | 0.220–0.492 |
| S13/S22 | 0.414 | 0.364–0.455 |
| S13/S23 | 0.343 | 0.300–0.390 |

S22/S23 are strictly more correlated than both alternative pairs in only
**19.5%** of subsets. There is no robust early-region identity separation.
The earliest supplementary eight-carrier comparison gives 0.551 for S22/S23
versus 0.471 and 0.535 for the alternatives; that narrower result should not
replace the fuller 24-carrier result. Its balanced ranking also varies.

The later regions favor S22/S23, but known repeat-state mixtures, reception
quality, calibration, and shared session conditions can produce this similarity.
Only one same-ID pair and one alternative labeled satellite pass the current
10 MS/s gate, so identity and session effects cannot be separated.

DS9-middle/DS9-last have early-region correlation 0.560 in discovery and 0.537
in evaluation; equal-count evaluation averages 0.425. Their identities remain
unknown. With only two qualified lower-edge visits, a dendrogram necessarily
joins them and cannot establish a meaningful group or a shared satellite.

![Discovery hierarchies and evaluation correlations](local/revisit-regions/clustering.png)

## Interpretation and next useful test

This analysis establishes computable, partially repeatable visit profiles.
It does not establish a satellite-specific fingerprint or additional message bits.
Mean profiles are insensitive to frame order and can hide changing information.
Nor have we subtracted the known repeating component: later-region comparisons
are deliberately contextual, not claimed correlations of purely unknown payload.

The next useful analysis is a known-state-conditioned comparison of early-region
residuals, followed by testing coordinate relationships that transfer between
receivers and visits. Additional qualifying revisits from independent sessions
would be needed before interpreting a cluster as satellite identity. Existing
recordings should be checked before any new collection is considered.

## Reproduction and artifacts

Run from the repository root:

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy --with matplotlib python reports/2026_09_28_sequence_semantics/revisit_region_clustering.py
uv run --no-project --with numpy --with scipy --with pytest python -m pytest -q reports/2026_09_28_sequence_semantics/test_revisit_region_clustering.py
```

Ignored `local/revisit-regions/results.json` contains input hashes, selected and
excluded visits, frame lists, all correlation matrices, discovery linkage trees,
pair labels, distances, and balanced-subset summaries. NPZ files retain the
profiles; `clustering.png` shows the primary 10 MS/s comparison. Raw and derived
numerical data are not committed. Three tests cover amplitude/frame-order
invariance, correlation-distance geometry, and constant-profile rejection.
