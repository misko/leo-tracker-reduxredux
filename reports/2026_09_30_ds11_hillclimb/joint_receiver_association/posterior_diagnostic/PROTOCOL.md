# Diagnose receiver-driven association changes

Use every recording in the frozen eleven-record acquisition position panel,
including unqualified fits. Do not refit parameters, select by reference error,
or treat posterior labels as verified satellite identities.

For each track, define its reference identity as the training-only Doppler MAP
candidate at its original IID solution, retaining that candidate's probability.
Evaluate exact whole-source posteriors at three saved estimates: the refitted
Doppler control, jointly fitted receiver geometry, and frozen-geometry
association model. Add zero-valued diagnostic parameter derivatives to the exact
partition to obtain each reference identity's marginal probability and the
joint assignment/ownership entropy. All candidate assignments remain in the
sum. Check probed partition score/source-count parity with the existing engine.

Report original confidence, reference-identity probability under each model,
expected changed-identity count, and entropy. Probability below 0.5 means the
original identity lost majority probability; it does not establish a different
MAP identity or a corrected association. Condition all conclusions on inferred
labels, finite candidate banks and saved-fit qualification. High-confidence
changes and persistently ambiguous tracks are diagnosis, not ground truth.

First verify the probe implementation against exhaustive tiny assignments.
One diagnostic child per record, ≤90 seconds, at most three single-thread
workers. Retain every failure. No new RF, target-error tuning or numerical
qualification changes. Preserve all previous experiment artifacts.
