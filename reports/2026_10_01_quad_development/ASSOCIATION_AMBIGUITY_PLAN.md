# Next diagnostic: is association marginalization worth its cost?

The shared-visibility pilots largely preserve locations and hard assignments. Existing-mode selection has limited sub-kilometer headroom. Before implementing another optimizer or doing a full-panel warm replay, measure whether substantial association ambiguity remains at the fitted positions.

Use the nine metadata-first accepted curvature-model states: three first singles and the first pair/quad of each DS9/DS10/DS11 dataset. Freeze the completed receipt identities before running. Keep the failure-selected boundary pair separate. Do not use geographic error to choose tracks, states or candidates.

At each saved state, reconstruct and verify the complete shared-threshold track scores. For each track compute normalized branch probabilities by log-sum-exp, best/second score gap, entropy, effective candidate count, background probability, and the mass outside the top1/top2/top4 branches. Aggregate by window size and dataset. Also report the correction from hard maximum score to log-sum-exp, without fitting any state. Verify sums and bounds synthetically, bind all source/input hashes, and use a bounded120second diagnostic per window with explicit unresolved outcomes.

These are conditional plug-in probabilities at fitted nuisance values, not calibrated posterior satellite probabilities. Selected satellite epochs have been fitted while many alternatives remain near prior values; that asymmetry may overstate certainty. The diagnostic can show whether a cheap marginalization prototype is plausible, but cannot prove alternate branches are unimportant after profiling or integration over their nuisance parameters.

If several branches carry appreciable conditional mass, consider a separately frozen soft-association objective `prior - sum_tracks logsumexp(branch_scores)`. Its gradient must consistently weight full branch gradients, including background visibility; no unacknowledged score/gradient truncation. Keep the same data, priors, starts, budget and audit for a matched model comparison. If conditional mass is already concentrated, first investigate residual structure or alternate-mode evidence rather than paying for full-catalogue gradient sums with little measured benefit.

This is a diagnostic plan, not a claim of model improvement or authorization to relabel prior results. Report failures and ambiguities before choosing the next fitted experiment.
