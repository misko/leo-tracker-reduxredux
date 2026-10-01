# Candidate: constituent fits as starts for a larger window

Status: proposed experiment; no fit results claimed. Preserve the frozen independent-clock baseline and its original outcomes.

## Evidence and hypothesis

The reference-free DS9-B03 diagnostic finds feasible states that improve both pair objectives, including a 5.54 objective reduction for the inaccurate second pair. The state came from the quad and is not available to a pair estimator. This establishes a missed search mode, not permission to use extra scans or geography.

A legal alternative is to initialize a pair using fits of its two constituent scans. For a quad, use fits of its two constituent pairs. Each candidate uses exactly the observations available to that window. The hypothesis is that subset fits expose useful association/location basins that the aggregate zero-nuisance acquisition misses. Sharing the final position and jointly refitting all nuisance coordinates remains essential; averaging locations is not this model.

## Frozen diagnostic rule for the first implementation

1. Begin with the two chronological constituent receipts. Use their lowest-objective converged, audited results, allowing only the separately defined bounded continuation for an iteration-limited winner. If either constituent is unavailable or fails its audit, retain a candidate-policy failure; do not choose an alternate constituent using location error.
2. Construct two starts, one at each constituent location. Copy scan-specific nuisance coordinates from their own constituent fits using explicit column maps. Replace the shared east/north entries with the chosen start location. Recompute all hard assignments against the complete target-window ports; never copy satellite array indices across different scan catalogues.
3. Fit the unchanged joint Student-t4 objective and unchanged priors, at most 64 iterations per start. Choose the lowest final objective and apply the unchanged convergence and numerical audit requirements. No reference coordinate is read until decisions are fixed.
4. Charge all constituent inference and continuation work, plus larger-window preparation and fitting, against the existing 90 seconds per scan allowance. Use the sum of measured constituent launch times for conservative diagnostic accounting. Do not count previous baseline pair or quad work unless it is actually a constituent input. Stop at the remaining budget; report insufficient-budget failures. This first warm replay is not a cold-pipeline latency measurement.
5. Keep each baseline result intact. Bind all input receipt hashes, column maps, source code, budgets and decisions. Report accepted/planned, paired objective changes, geographic errors after audit, and total charged time. Only a later integrated cold run can establish end-to-end timing and reproducibility.

## Scope and gates

First implement and numerically verify coordinate/state transfer on one pair from the first block of each dataset, fixed as DS9-B01-D1, DS10-B01-D1 and DS11-B01-D1. Also run DS9-B03-D2 as an explicitly failure-selected diagnostic; do not pool it into an unbiased improvement estimate. Do not use quad-derived starts in any reported pair estimator. Start fits only after the current baseline queue releases the shared fit lock.

If the pilot supports further evaluation, apply the unchanged rule across all planned pairs, preserving all failures, then test the recursive pair-to-quad version. Correlated starts can all enter the same wrong basin, subset fits can be biased, and spent constituent time can leave insufficient joint refinement budget. These are testable failure modes, not reasons to exclude bad windows.

The matrix-product acquisition experiment, common-clock ablation and bounded-continuation recovery are separate changes. Do not combine them with this pilot; otherwise an improvement cannot be attributed to the initialization policy.
