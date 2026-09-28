# Conditional candidate generalization across frozen panels

Audit all first-eight chronological baseline records for DS7, DS8 and DS9.
Keep DS8-008 as unavailable because its candidate export timed out; do not
replace it. Reuse qualified, sealed independent positions and original inputs.
No position, timing, noise scale, mask, shortlist or track-selection changes.
No geographical reference is read by the numerical audit.

At each frozen point, replay the original Student-t(4,100 Hz) offset profiles
and candidate training weights. Select the MAP and runner-up by training score
only (catalogue-number ascending tie break). Compare their held densities using
their own training-profiled offsets. Also compare the original candidate mixture
with a counterfactual mixture excluding its training MAP candidate, reweighting
the remaining training candidates. Report every track, visibility coverage,
training concentration, training gap, held differences and all denominators.
The high-concentration subgroup is fixed at MAP weight >=0.99. A held advantage
means a strictly positive score difference; retain unrounded numeric values.

These are conditional discrimination diagnostics at an already fitted position.
The runner-up is not known to be wrong; neither candidate has independent truth
labels. Do not call a runner-up held win an identity error, use held winners to
refit location, claim calibrated correctness probabilities, or interpret this
as a leave-one-candidate-out position refit. Frozen shortlist incompleteness and
profiled nuisance parameters remain limitations.

Additionally match DS9's independent and eight-record joint candidate weights
by exact track ID and candidate ordering, using existing sealed joint outputs.
Report MAP changes without imposing that simultaneous receiver tracks must name
the same object. Existing receiver grouping/coexistence audits and motion
controls are reviewed rather than repeated here.

Each dataset audit runs in at most 120 seconds, 4 GiB, one thread, nice19;
at most two execute concurrently. No retries, propagation, IQ or RF work.
Seal outputs and preserve failures before any aggregate interpretation.
