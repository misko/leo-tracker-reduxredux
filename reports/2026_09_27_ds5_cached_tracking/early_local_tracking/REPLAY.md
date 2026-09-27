# Development-only causal replay

After passing all 132 original/mirrored receiver policies, replay the original
64 development visits with separate causal state per session/rate/edge and
the existing per-receiver keys. Compare to the saved full application pair
inventory from the completed early-confirmed replay. That inventory is fixed
reference evidence, never a detector input. No reference-guided proposals or
state initialization. Both receivers process every fresh input.

Report receiver and visit agreement, unmatched outputs, candidate complete-call
CPU/wall, and extra confirmations. Do not divide current candidate timing by
the earlier application measurement and call it a new paired speedup. This
quick replay decides whether to pursue the variant before repeating expensive
application measurements. CPU0, numerical threads=1, 60-second bound. Save row
checkpoints outside timing. No holdout IQ is opened. Freeze membership and
sources before replay. Success on this development set is not qualification.
