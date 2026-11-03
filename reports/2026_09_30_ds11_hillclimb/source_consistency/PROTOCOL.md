# DS11 training-source-consistent single-scan screen

Use the pinned read-only provenance adapter to bind every exported point on the
fixed screen indices 0, 4, 8, 12, 16, 20, 24, and 28 to its raw probe source
group. The primary inventory and selector use training source groups only.
Held frequencies, held group membership, physical candidate identity,
geographic reference, and fit outcomes do not enter selection.

Within each scan, rank tracks by descending training-observation count then
track ID. Construct a greedy source-disjoint closure with no seed and with each
track as seed. Select the closure with greatest retained training-observation
count, breaking ties by its sorted track IDs. Freeze that track set before the
fit. Preserve every retained track's original observations, training mask,
independently profiled CFO, and full candidate mixture. Discarded-track
coverage is reported explicitly.

Run exactly one arm, `training_source_consistent`, with the shared hill-climb
budget: original same-scan IID endpoint plus three generic starts, 100
iterations and 160 evaluations per start, 90-second process cap, one BLAS
thread, and one worker. Preserve all failures. Qualification and selection use
the shared optimizer gates and highest qualified training score.

The family gate was declared in the coordinating record before any fit was
launched: all 8 attempts qualified, at least 5 paired geographic wins, at least
10% reduction in median position error, and P90 no worse than matched original
IID. Use all eight attempts in the denominator. Do not compare native training
or held likelihoods across all-track and subset models because their dimensions
differ. Common-IID held scores emitted by the shared harness concern the fitted
point under all original tracks and remain a diagnostic only.

This file was added while the already-declared sequential batch was running,
after indices 0, 4, and 8 had terminal process receipts. Their geographic
outcomes had not been summarized or used to change the arm, selector, budget,
or gate. The binding model and provenance files were already frozen and are
hash-recorded in every run result.

No replication is authorized unless the predeclared screen gate passes. No RF
collection, archive mutation, production change, golden change, or reference-
conditioned selection is permitted.
