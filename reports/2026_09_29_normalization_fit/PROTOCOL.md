# Frozen full-visible denominator fitting probe

Use the first four scans of each existing DS7/DS8/DS9 early-eight panel as
source and the last four as target, matching the existing chronological
holdout. Warm start each source fit at its qualified original q020 fit.
No target or geographic-reference tuning; no background-prior sweep.

At the original source fit, reconstruct the causal full catalogue and record
each track's full-visible count at its actual timing. Freeze those counts.
Optimize .8 times retained signal numerator divided by that frozen count,
plus .2 times original background. This is an unnormalized approximation,
not a new normalized probabilistic model. Missing numerator and changing
visibility counts are audited by exact full-catalogue evaluation at both
old and resulting source fits. The count-frozen expression is not guaranteed
to be a lower bound on the location-dependent exact expression.

Require existing optimizer/gradient gates. Preserve failed fits. Regardless
of geographic outcome, score all four target scans under the SAME original
q020 model with one shared timing integrated per scan at both positions.
Use existing 16/32-order timing checks and failure-only 64/128 refinement.
Report geographic errors only against the inherited exposed unsurveyed
reference; they are not blind accuracy validation.

Three dataset workers, capped at 300 seconds each. Reuse read-only archive
ports and pinned deployed numerical oracle. No new RF or production edits.
