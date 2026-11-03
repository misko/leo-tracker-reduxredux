# One-round timing re-selection at converged geography

For each N24 dataset use two qualified source endpoints: the original N24
solution and the highest-training-score wide-start endpoint. At each endpoint
and fixed geographic position, compare each scan's existing continuous timing
score with all 41 original grid nodes. Change timing only if the grid improves
the training score by more than 1e-7. Include the current value to prevent a
discretization-induced score loss. Run exactly one round, no outcome-driven retry.

If any timings change, rerun the original joint optimizer and qualification
checks. Preserve both arms and failures. Select among qualified endpoints and
the original N24 fit using training score only. If an endpoint exceeds original
N24 by more than 1e-6, evaluate it on all five frozen outside-pool scans under
the same timing-integrated q020 score and compare to original N24 predictions.
Otherwise retain original N24 and do not repeat its target computation.

Verify scalar/grid and summed source gain replay. Reference errors only appear
after selection. Three dataset workers capped at 300 seconds. This is an
optimization test inside the existing site-conditioned banks, not global
catalogue coverage or independent accuracy validation. No RF or production edits.
