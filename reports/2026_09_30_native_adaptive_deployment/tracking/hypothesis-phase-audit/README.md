# Tracking hypothesis-phase audit

This is one isolated host `perf` run over the final 11,747-candidate DS9
prefix. It changes neither production tracking nor scientific fixtures. The
host was shared with other builds, so wall time is retained only as diagnostic
metadata; the finding uses sampled cycle fractions and static work counts.

The output is the exact expected 64-track serialization, SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
There were 803 samples across the host's atom and core events and no lost
samples. Combining each event by its approximate cycle count,
`candidate_segments` accounts for 31.6% self and approximately 48.0% including
descendants. `one_per_source` accounts for 6.5% self and approximately 18.9%
including descendants. `fit_segment` is 0.9% self and approximately 7.1%
including descendants. Inclusive fractions overlap and are not additive.

The dominant work inside `candidate_segments` is the pair of complete
circular-residual scans. In the atom samples, the `fprem` instruction alone is
18.5% of local samples in the initial scan and 27.3% in the refined scan; in
the core samples the corresponding values are 26.9% and 27.0%. The existing
work-count audit records 4,096 `candidate_segments` calls, 5,827 initial fits,
5,835 refined fits and 3,924 exact refined-fit cache duplicates. The profile
therefore shows that production fit caching has made refitting secondary.
Source deduplication remains measurable, while hypothesis vector insertion and
winner selection did not appear as independent hotspots.

One bounded exact experiment is justified. The initial loop currently computes
a residual before checking availability and minimum weight. The refined loop
also computes a residual before checking those predicates and the initial
segment's time window. Moving those existing predicates before the pure
`circular_residual` call cannot change a residual that reaches `raw` or
`refined_raw`: admitted points retain the same calculation and point order, and
skipped residual-array elements are never read. The work is bounded by the
current work: at most one residual per eligible point in the first pass and at
most one per eligible in-window point in the refined pass. Any prototype must
still pass component tests and all 60 causal-prefix outputs bit-for-bit before
an ARM timing is considered.

No implementation or ARM run was performed here. Further top-64 Hough work,
solver changes, approximate residuals, or broader optimization searches are
outside this audit.
