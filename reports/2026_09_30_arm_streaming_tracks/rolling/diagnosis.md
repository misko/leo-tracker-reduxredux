# Read-only diagnosis of ARM 39 versus server 58

This reviews the frozen outputs; no tracker settings or implementation were
changed. The physical ARM run passed in 1.119 seconds and was byte-identical to
the corresponding host result.

The 19-reference gap between server-input and ARM-input results decomposes
cleanly. Eleven references are input-limited on ARM (`5, 7, 8, 11, 30, 34,
47, 54, 60, 61, 62`): their CFO-consistent input ceilings are below the 80%
primary threshold. The remaining eight (`2, 12, 21, 22, 39, 48, 51, 52`) have
adequate ARM evidence but the rolling tracker does not assemble 80% of each
reference into one track. Best/union coverages are respectively 79.8%, 74.4%,
40.0%, 56.1%, 51.4%, 79.6%, 76.3%, and 67.6%. Refs 2 and 48 miss by one or a
few sources; the others are materially truncated or fragmented.

Fragmentation is the main adequate-input deficit. Across all ARM misses with
adequate evidence, refs 9, 12, 21, 22, 23, 39, 48, 51, and 52 have 2--12
consistent output fragments, but no fragment reaches 80% coverage. Ref29 has
98.1% consistent input and no consistent output fragment at all. These ten
references were recovered by the earlier curvature tracker, which is strong
evidence of an association/fragmentation regression rather than absent input.
It does not isolate the cause: the earlier implementation also differs in
seeding, hypothesis caps, branching, and deduplication, so this comparison is
not a controlled test of linear versus quadratic fitting. Refs 21, 22, 39,
and 52 have only 40.0--67.6% union coverage despite adequate input.

Source-membership purity is a separate disagreement, but it does not establish
a false join. Ref35 has 100% input and 91.7% union coverage, while its best
track has 52.4% in-span membership purity under the maintained server
segmentation. The comparator therefore rejects it, but this proxy alone cannot
show that the extra sources follow a different physical curve; prior curvature
review found its extras close to the interpolated curve. Ref23's best fragment
is large (232 sources for 32 consistent reference sources), although its
in-span purity remains 88.9%; its primary failure is still 74.4% coverage.
Several other low-overall-purity fragments contain long out-of-span
continuations, which do not by themselves fail the in-span purity criterion.

Duplicate alternatives are abundant but are mostly a reporting-cost symptom,
not the direct cause of the missing references. The ARM bank emits 327 tracks,
288 unmatched outputs, 37 references with multiple complete alternatives, and
14 outputs eligible for multiple references. Repeated fragments often have
identical membership metrics (for example refs 9, 12, 21, 23, 39, and 52).
The bank therefore emits many near-copies. No controlled ablation establishes
whether those alternatives consume the active capacity needed by the missing
references. The directly observed failures are incomplete associations, the
ref35 membership-purity disagreement, and no consistent fragment for ref29.
