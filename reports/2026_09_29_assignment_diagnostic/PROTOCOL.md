# Candidate identity diagnostic for the twenty largest predictive losses

Freeze the top twenty negative track contributions from prediction_attribution
summary.json, without changing that ranking or claiming population coverage.
They span five targets. Reuse complete-scan timing posteriors at fixed N24 and
equal-prior N8 locations. Resolve candidate slots to physical catalogue numbers
using the audited catalogue_recurrence mapping; never compare local slots
across tracks as identities.

For each selected track, integrate its candidate-plus-background responsibilities
over the complete-scan timing/component posterior. Report candidate probability
conditional on signal, joint signal probability, top catalogue number, and
total variation between the two conditional candidate distributions. A stable
confident assignment requires the same top number with >=0.9 probability under
both arms; a changed MAP alone does not establish a handover or ground truth.

Use 32/64 nodes per bank interval. Require <=0.001 maximum candidate probability
change, <=0.01 log-evidence change, unchanged MAP labels, and scalar track-score
replay <1e-7. Replay against prior 32-node evidence <1e-7. Preserve failures;
do not change thresholds or fit target locations. Bound five subprocesses to
180 s each and three concurrent workers. No RF or production edits.
