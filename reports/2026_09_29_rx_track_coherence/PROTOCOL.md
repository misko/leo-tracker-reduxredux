# Cross-RX frequency coherence before shared-trajectory localization

This is a read-only diagnostic on the same nine nonoverlapping eight-scan
panels: 72 unique DS7/DS8/DS9 scans. Include every exported track, including
tracks excluded by a geographic bank. Report that denominator separately from
the earlier 4,328 bank-eligible tracks. No candidate bank, satellite identity,
pose or geographic error is used to select a pair.

For every same-scan/channel/exact-RF RX0/RX1 track pair, match observations
only when visit IDs agree and timestamps differ by ≤1 ms. Retain an edge only
if each endpoint has exactly one matching edge within that pair. Retain all
ambiguous, unmatched and mixed-mask counts. Use observations marked training
in both receivers for selection; use both-held observations for evaluation;
mixed partitions do neither. Never choose a timestamp match by frequency.

A pair is training-eligible with at least five matches spanning at least five
seconds. Its offset is the median RX0−RX1 frequency difference. Require median
absolute training residual ≤100 Hz and 90th percentile ≤300 Hz. Rank all
training-eligible peers by mean Student-t4 log density at fixed scale
100√2 Hz around that fitted offset. Select only reciprocal best tracks, with
a margin ≥0.1 nat per observation over the runner-up on each side. An endpoint
with no eligible alternative has no margin requirement; report this explicitly.
This produces one-to-one track pairs, not verified one-to-one physical emitters.

Held availability requires at least three both-held matches spanning five
seconds. Availability never changes training selection. Report held median and
90th-percentile absolute residual, offset shift, and the same 100/300 Hz shape
thresholds without retuning. The narrow Student-t conditional score is compared
with a 2000 Hz scale using the identical training offset and held observations.

For a temporal negative control, reverse the RX1 frequency sequence separately
within training and held matched observations. Refit only the training median
offset for that control, then compare held conditional densities for RX0 given
the held RX1 vector. This is a permutation diagnostic, not a causal forecasting
claim; it does not establish identity or direction. Every selected pair with
held availability is scored, including those failing held shape.

Test a shared receiver offset separately: for each selected pair with at least
two other selected pairs in the same scan/channel/RF, use the median of those
other pairs' training offsets. Score its held differences with that donor offset.
Do not include the target pair, any held values, another scan, or another RF in
the donor estimate. Preserve pairs lacking donors. Report common-offset transfer
separately from per-pair shape agreement; only the former can support a common
receiver-frequency nuisance, and neither proves satellite identity.

Before reading frequency agreement, test timestamp/visit matching and ambiguity,
train/held isolation, reciprocal selection and ties, known stable offsets,
drifting held offsets, and donor transfer. Freeze sources, this protocol, tests,
72 observation bindings and plan before execution. One process scores all 72
JSON exports, with BLAS1/nice19, 4 GiB memory and a 90-second wall cap. A failure
is preserved and not silently restarted. No RF, raw IQ, propagation, archive
reads, provider fetches, geographic optimization or production changes.

The corpus is already explored; thresholds are prototype diagnostic rules,
not calibrated hardware error bounds or independently confirmed associations.
Selected public track/index pairs cannot establish that upstream detections are
physically independent. Before a joint geographic model, require stable held
coherence, useful negative controls and common-offset transfer across enough
scans to justify a separately frozen experiment. No localization gain is claimed
by this census. Preserve all populations, rejected candidates and empty cases.
