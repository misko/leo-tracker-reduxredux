# Training-count weighting: count-sqrt screen fails

The fixed count_sqrt screen is complete: eight qualified outputs, all 32 starts
qualified, and no timeouts or retries. Median error rises from 3108.162m to
3492.574m; P90 rises from 6046.037m to 6153.003m. Only two of eight scans improve.
It fails the frozen five-win, 10%-median-reduction and nonworse-P90 gate.
No additional-panel run or stronger weighting variant follows this failure.

Scan 16 improves substantially (2153.140m to 327.813m), while six scans worsen.
That isolated result is not used to create a scan-specific policy or choose
weights using reference errors. Original IID remains the default.

Four existing component tests pass. The assessor verifies frozen sources,
receipts, all start qualifications and highest-qualified training selections,
then seals all eight selections before geographic scoring. Maximum scan-job
wall time is 42.96s under a 90s cap, with two single-thread workers. Original
inputs and prepared model bytes are unchanged; optimization is not independently
replayed. See [protocol](SCREEN_PROTOCOL.md), [source-bound plan](screen-plan.json),
[all starts and selections](screen-selections.json), and [outcome](screen-outcome.json).

The other two variants below remain prepared only.

This separate family addresses track-length imbalance left untouched by the
frozen source-balance screen. All counts use training observations only. Raw
weights are multiplied by one global positive factor so their arithmetic mean
is one; this preserves each arm's optimum while keeping score and gradient
scales near the original IID objective.

- `count_sqrt`: track weight is proportional to its training count to power
  `-0.5`.
- `count_equal`: track weight is proportional to its training count to power
  `-1`.
- `source_count_equal`: every track for a training-frozen `(NORAD, exact RF)`
  source has weight proportional to the inverse of that source's total training
  observation count. Ambiguous tracks remain singleton sources.

Physical identities, the 0.90 threshold, the original same-scan IID freeze,
and the complete candidate mixtures are reused unchanged from `source_balance`.
These remain composite objectives, not normalized physical posteriors.
