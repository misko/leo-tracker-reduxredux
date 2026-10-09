# Prepared continuation: does recovering the ordinary region improve localization?

Preparation only; no continuation fit or accuracy claim. Wait for iteration96's
frozen curvature-polish result and parent review before freezing this continuation.
Do not launch solely because a zero-timing prefit qualified at a worse objective.
The original four iteration93 receipts and diagnostic-error supplement remain immutable.

Select the minimum same-model objective among independently qualified saved
prefits in a frozen inventory: all four iteration93 attempts and the final94
and96 polishes. Recompute objective/KKT, keep the0.001 threshold, and require the same
ordinary lowest-score retained calibration-failure position. No reference
position or error enters selection. The93supplement distinguishes a saved
qualified fit from the subsequent diagnostic exception without rewriting history.

Retain the original ordinary regional winner in each c arm using public checkpoint
reads of its calibration, association and all original final starts. The extractor
freezes these receipts. No new grid or reference-nearest seed is introduced.

## Matched downstream continuation

Compute receiver correction and run the bounded fixed-position postfit with
20seconds/600iterations. Require convergence, then use unchanged association
with60seconds. Run both c arms on the shared associated bank from association,
zero-timing and within-arm continuation starts, each20seconds/600iterations
under hard60 and the existing25km local disk. Keep every failure explicit.

Rank the recovered regional finals alongside the original ordinary winner with
unmodified `regional_winners`: objective plus external calibration penalty,
qualified fits only, strict improvement preserves original ties. This is the
current operational policy, including its bank/calibration differences; it is
not a claim that different candidate banks define an ideal common likelihood.
Do not compare raw scores across different downstream B7 models.

Feed the selected region into unmodified `run_joint_stages`, retaining90second/
600iteration per-arm budgets, priors and stage-specific fallbacks. Both c arms
retain static-c/RF-time locks. No new nuisance coefficients or geometric assumptions.
Replay the original ordinary winner through B7 separately, using a disjoint
baseline checkpoint namespace, before running candidate B7. Published B7 remains
an archived comparison; neither continuation is a fresh cold-grid rerun.

## Reproducibility and interpretation

Freeze source/native/input hashes, original-winner checkpoints, all prefit
attempts, polish source/protocol/result and the diagnostic supplement. Rebuild
the same ordinary inputs and causal TLE bank, verify evidence/bank order and the
coarse objective. New stage receipts are append-only under this report; no
production checkpoint writes. Each invocation is a500second checkpointed slice,
with at most6 slices planned to cover both baseline and candidate B7 replays.
The parent controls execution capacity and go/no-go.

Evaluate reference position only after inference. Report qualification through
calibration/association/finals, regional winner changes, accepted B7 stages,
both c errors, frequency fit and compute separately. A recovered region that
loses the operational score comparison or remains inaccurate is a negative
result, not grounds for reference-guided selection. This consumed single-scan
diagnostic proves neither cohort benefit nor independent generalization. No RF
collection, reserve access or deployment occurs here.
