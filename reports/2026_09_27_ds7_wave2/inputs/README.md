# DS7 wave 2 frozen input preparation

This directory records a read-only, unscored preparation of the first
chronological DS7 captures.  The authoritative frozen input is
`inputs-prefix4-ready-v1.json`: it accounts for all 88 plan captures, with four
ready records and 84 explicitly unavailable records.  The first two artifacts
are the byte-identical wave-1 exports and banks.  The third and fourth were
created by the unchanged public `ScannerTrackingInputStore.load` export port and
the unchanged corrected five-anchor, training-only bank policy.

The fifth observation export completed, but its bank construction reached the
root-side 150-second cap.  No bank was created for it, and captures five through
eight remain unavailable in the frozen input.  Work stopped at that cap.

The third bank has one fewer bank track than the raw observation export because
that track has seven training points and zero held-out points.  The unchanged
bank exporter only admits tracks having at least two training and one held-out
point.  This is an explicit frozen-mask eligibility exclusion, not a candidate
selection change.  The prefix-four input remains immutable; loader validation
must compare banks to eligible observations and record exclusions.

All cached-source access was serialized.  Each export used CPU and BLAS thread
limits of one with `nice -n 19`.  No raw IQ, pose, reference, score artifact, or
QNAP write was used.

See `preparation-provenance.json` for commands, hashes, runtime versions, elapsed
times, and cap status.
