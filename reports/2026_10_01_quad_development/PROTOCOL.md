# Expanded development panel: 16 chronological quads

This is a new 64-scan development panel, not a replacement for the old frozen 64-scan regression panel. Select six DS9 blocks, five DS10 blocks and five DS11 blocks (24/20/20 scans), spreading blocks chronologically within each dataset. DS12 is not used. All outcomes remain development evidence.

## Selection and continuity

Use only frozen source membership, candidate inventories, timestamps and hardware IDs. Scan the full candidate inventory in capture order; an inadmitted candidate breaks continuity. Form non-overlapping runs of four on the same radio and receiver set, with end-to-next-start gaps in [0,180] seconds. The 180 s ceiling accommodates the observed approximately 122 s gaps while rejecting interrupted runs. Floor-spaced selection across eligible blocks fixes membership without using geographic errors, satellite assignments, signal quality or convergence. Keep sample-rate changes and record them.

“Back to back” means consecutive recordings in the frozen candidate inventory, including the normal capture gaps. It does not mean continuous IQ or verified absence of unlisted recordings. Source manifests certify complete historical analysis, not current accessibility. DS10/DS11 pose companions were not collected; constant position within a quad is a model assumption requiring an independent metadata audit before a stationary-location interpretation. Do not filter blocks based on resulting location errors. Failed input admission remains visible and does not trigger replacement scans.

## Evaluation units

For each quad A,B,C,D, evaluate all four singles, two disjoint adjacent pairs AB/CD, and the quad ABCD: 64 single, 32 dual and 16 quad results per model, 112 in total. A dual means two scans, not two receivers; both receivers remain available within each scan.

The primary paired progression uses A, AB and ABCD from each of the 16 blocks, giving 16 matched comparisons at each size. The 64/32/16 aggregate views use all observations once per size and describe broader performance; they are not 112 independent trials. Optional rolling pairs BC are exploratory and excluded from primary counts.

Treat whole quads as grouping units for tuning, calibration, resampling or cross-validation. Never split neighboring scans from one quad between fitting and checking sets. Leave-one-dataset-out experiments use DS9/DS10/DS11 groups as a stronger transfer check. These exposed datasets cannot become untouched test data by assigning fold names.

## Models to implement and run

1. Reproduce the existing cold single-scan baseline on the new 64 scans: uniform 250 km Sacramento disk, height 30.48 m MSL, Student-t4 residuals, 1 s clock prior, 0.5 s satellite-epoch priors and 0.5 Hz/s receiver-drift priors. Preserve the old benchmark separately.
2. Joint position with independent scan nuisance blocks: all scans in a window share east/north; each retains its clock, receiver drifts, satellite epoch offsets and association variables. Each scan keeps its actual UTC reference and causal orbit input. Do not concatenate relative times or silently assume common TLE state order. Count the position prior once. Reuse the hard-association/joint-continuous solver architecture with explicit scan-to-global column maps.
3. Only after the independent-nuisance model is validated, ablate shared satellite timing across the same NORAD and TLE snapshot. A shared clock across scans is a separate hypothesis, not an automatic consequence of common hardware. Its physical stability and clock/epoch ambiguity must be assessed.

For the first multi-scan model minimize the sum over scans of robust negative track log likelihood plus each scan's clock, drift and epoch penalties, with one common location. This profiles nuisance variables jointly; it is not exact Bayesian marginalization. Association updates use radio likelihoods only. Acquisition scores must aggregate the scans available to that evaluation unit, never later scans or GPS.

Each single, pair and quad restarts from the uniform regional prior. No fitted parameters carry between evaluation units. If single-scan solutions are later used for multistart seeds, their full acquisition/fitting work must be charged to that window and identified as a different arm.

## Budgets, audit and reporting

Start with one metadata-selected block per dataset (the first selected block), implementing and validating all seven unit views. Expand unchanged to the remaining blocks after the numerical audit. At most two fits run concurrently; single-thread BLAS. Initial external limits are 90/180/360 s for singles/duals/quads, with internal limits 5 s shorter. This is a proportional-compute first comparison, not a claim of equal latency. Report total wall/CPU time, time per scan and recording span separately. Preserve failures and stop at budgets; no uncharged retries or continuation.

Before geographic scoring verify input/source seals, selected physical observations, no double use within a window, actual-time/orbit support, finite states, objective consistency, convergence, numerical derivatives and the known visibility-boundary behavior. Synthetic tests must include scan-order invariance, correct time-origin mapping, one-scan parity, conflicting per-scan clocks and repeated satellite identities across different orbit snapshots.

Report accepted/planned, median/p90/max horizontal error, counts within 1 km and 3 km using all planned units as denominators, paired changes for the 16 prefixes, results by dataset, runtime and uncertainty coverage. Quantiles are conditional on acceptance; never hide failures. Reference locations are evaluation-only, with their provenance and uncertainty disclosed. Bootstrap or other uncertainty calculations must resample complete quads, with temporal correlation limitations stated. Do not promote a model based only on improved residual objective or a subset's median.

## Current stage

This freeze creates metadata membership and evaluation units. No new single/dual/quad model fits are claimed. Observation/orbit preparation, stationary-site audit, the shared-position implementation and its benchmark runs are subsequent execution stages. No new RF collection is needed or authorized by this protocol.
