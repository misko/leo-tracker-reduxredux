# Numerical refinement amendment

The initial 16/32-node pass completed finite evidence scores, but DS7_1 and
DS7_3 failed the stricter attribution stability gate. Preserve original
outputs. After all original runs terminate, refine only failed targets using
64/128 nodes, with unchanged locations, tracks, probabilities and 0.01 gates.
Do not change the statistical comparison. Replay refined 128-node evidence
against original 32-node evidence to 0.01 (convergence, not identical-node
replay); require attribution reconstruction <1e-7. Bound each refinement to
180 seconds with at most three workers. Original scalar audits remain binding.
Additional failures discovered in the original batch follow the same rule.
