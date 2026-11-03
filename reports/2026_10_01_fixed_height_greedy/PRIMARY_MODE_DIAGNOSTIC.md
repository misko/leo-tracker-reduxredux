# Primary objective and seed diagnostic

Final snapshot: 2026-10-01. This read-only snapshot contains all 64 planned
units and 64 native receipts whose seals and source bindings pass
`evaluate_primary.load_attempts`: 51 receipts report `converged_local_mode`, 13
report `unresolved`, and all 51 native
convergences satisfy the stricter primary acceptance rule (seal, successful
launcher, and at most 90 seconds). The panel is fully accounted; unresolved
outcomes remain in its denominator.

For each receipt, the diagnostic compares the final objective and horizontal
mean from each of its three retained seed fits. The gap between the best and
second-best final objective ranges from 1.7e-11 to 421.3 (median 8.99). The
maximum distance between seed endpoints ranges from 0.000003 km to 369.9 km
(median 215.7 km). Thirty-nine of 64 receipts have endpoints separated by more
than 100 km. Eighteen have a best/second objective gap below 1; eight of those
also span more than 100 km. Those eight are direct evidence that materially
different geographic modes can have nearly indistinguishable recorded
objectives in some scans.

The pattern is not uniformly broad. Ten receipts have all seed endpoints
within 1 km, and several near-zero objective gaps reflect multiple seeds landing
on the same solution. Conversely, 61 of 64 receipts contain more than one final
association vector, so seed disagreement also includes discrete candidate and
background choices. Across accepted results, the recorded position error has a
median of 1.86 km and a range of 0.332--9.11 km. The simple Pearson correlations
of error with objective gap (0.25) and endpoint spread (0.23) are weak. These
descriptive correlations are not confidence calibration,
and recorded-roof error was not used to choose or alter the frozen fit.

Only eight scans have both an accepted new result and a finite, completed old
greedy result. On that matched subset, the new median error is 2.00 km and the
old median is 2.47 km; the new result is lower on four scans and higher on four.
This is a paired descriptive comparison, not an equal-criteria performance
claim: the old campaign used a different state, height treatment, optimizer,
gate, and acceptance semantics. Of all 64 old greedy attempts, only 12 were
complete (36 were gate failures and 16 errors), and four of those 12 correspond
to unresolved new fits.

The receipts therefore support broad or discrete multimodality as a real issue,
but they do not isolate it as the sole error source. Competing association
vectors, clock/receiver/satellite-epoch nuisances, and residual ranking are
jointly optimized, so an objective gap alone cannot distinguish location
ambiguity from nuisance or association ambiguity. `unresolved` also denotes a
numerical outcome, not a truth-based rejection.

The next model iteration should retain and report distinct seed modes rather
than only the single best mean, including each mode's objective, association
vector, nuisance solution, basin multiplicity, and pairwise geographic distance.
A held-out predictive or independently simulated calibration set can then test
mode ranking and coverage without tuning on recorded-roof errors. Association
and nuisance ablations on that frozen set would separate residual-ranking
failures from geographic ambiguity before changing the optimizer or prior.
