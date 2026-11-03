# Prospective paired position confirmation

Freeze the five metadata-selected full-manifest indices 10,18,35,60,75 before
any position fit or reference-error inspection. The exported-bank census finds
no newer-epoch candidate in the first four banks, and NORAD53505 in thirteen
candidate slots on index75. Retain all five scans. Patch every changed element
record, including same-epoch rounding differences, without changing shortlists,
measurements, masks, catalogue divisors, the t4/100Hz likelihood or CFO prior.

Use only exact archived element bytes selected by the frozen three-day
capture-start inventory and supported by matching pre-capture publication
receipts. Reproduce original bank states before replacing them. Record any
historical-retention change separately from a new capture-window update.

For each original-bank baseline, run the three established seeds E=-2,0,+2km,
N=0,tau=0 with the unchanged +/-12km and +/-5s bounds. Refine the highest-scoring
qualified result as a fourth control start. The fresh fit uses the same three
fixed seeds plus that same pre-refinement baseline point. Select the highest
qualified training score only. Use the established optimizer and derivative
qualification rules; no reference coordinate enters fitting or selection.
If no baseline start qualifies, preserve its failure; the fresh arm may still
run the three fixed seeds, but no matched-error win is available for that scan.

If a patch has zero changed candidate slots, reuse the original result exactly
and label it as an unchanged output, not a new optimization or a win. Each
four-start job has a 90-second process cap and one BLAS thread. Preserve all
attempts, failures, source hashes, starts and terminal receipts. At most three
numerical workers may run concurrently.

The prospective confirmation gate requires all five matched outputs qualified,
at least max(100m,5% of baseline error) improvement on the independently
identified newer-epoch case75, nonworse five-scan mean, median and P90, and no
individual regression exceeding50m. This small, same-site confirmation cannot
establish general deployment accuracy. Do not pool its errors with the exposed
original32 to conceal a failure. Report exact paired results and coverage even
if the gate fails; no retuning or extra variant is permitted within this test.

Report native fresh-bank held prediction separately from old-bank diagnostics.
Those held observations share source and extraction errors with training and
are not independent geographic truth. Offline post-capture orbits remain a
separate category and cannot count toward this causal confirmation.
