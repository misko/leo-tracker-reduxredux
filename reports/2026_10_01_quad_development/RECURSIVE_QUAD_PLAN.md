# Recursive constituent starts for quads

Status: prepared while the full 32-pair study runs; no quad fits under this policy yet. Do not modify or replace the independent baseline or constituent-pair-v3 outcomes.

## Hypothesis and comparison

Fit a quad from its two disjoint constituent pairs, using only observations in that quad. Two starting positions come from the audited constituent-pair-v3 winners. Copy each scan's nuisance coordinates from its own pair, recompute all assignments against the target quad's ports, and jointly fit the unchanged shared-position Student-t4 model. The hypothesis is that pair estimates provide useful joint modes while avoiding a fresh quad acquisition. Bad pair modes and accumulated computation can instead cause accuracy or budget regressions.

This is an explicit recursive policy: singles → pairs → quad. Compare against the original quad baseline and its fixed bounded-continuation variant, separately. A future direct singles → quad arm would isolate hierarchy from initialization diversity; it is not silently mixed into this experiment.

## Fixed rules

1. Membership is all sixteen quads in selection.json. Initial implementation checks use the metadata-first quad of each dataset (DS9-B01-Q, DS10-B01-Q, DS11-B01-Q), retained as a separately identified pilot subgroup. Do not select pilots by error or replace failures.
2. Each quad uses exactly its disjoint D1 and D2 from constituent-pair-v3. Verify sealed receipt/audit/launch/source/input bindings, chronological scan order, common position prior, fixed height and nuisance priors. Require both constituent winners to pass their numerical audits. Missing or rejected constituents produce explicit policy failures; no fallback using baseline pair or true position.
3. Decompose each pair's fitted state into its two scan states using the saved local-to-pair column maps. Bind these states by scan identity to the target quad's local-to-global maps. Preserve scan-specific clock, receiver drift and catalogue epoch coordinates. Set common east/north to each pair's location in turn. Cover every target nuisance coordinate exactly once; reject duplicates, omissions, incompatible shapes or nonfinite values. Never copy association indices across ports.
4. Run at most 64 iterations from each of the two chronological pair positions, sharing the remaining deadline. Choose the lowest final objective among all scored fits, including an unresolved fit if it wins. Apply the same independent numerical audit; geographic reference is accessed only afterward.
5. The quad allowance is 360 seconds. Charge the sum of the two constituent pair launch totals, which already include their four singles and any single continuations. Add target process startup, preparation and fitting once. Do not double-count the singles; do not exclude pair work because it was done earlier. Less than ten seconds remaining is an explicit budget failure. Audits remain outside the inference allowance as in the baseline. This remains warm replay accounting, not measured fresh end-to-end latency.
6. Use a new output arm, immutable source/input receipts and the shared fit lock. Run bounded sequential batches. Preserve failures and all sixteen planned denominators. Keep acquisition optimization, shared clocks and extra continuation out of this arm.

## Verification and reporting

Before fitting, test transfer with unequal scan dimensions, pair and scan reordering by explicit identities, independent nuisance values, duplicated/missing scans and invalid maps. A real-data preflight should reconstruct every input scan state and verify prior/input bindings without fitting or reading geographic errors. Test recursive runtime accounting and early admission failures.

Report accepted/planned; median, p90 and maximum error; fractions within 1 and 3 km; charged runtime; matched objective/error changes and asymmetric failures; dataset and pilot/non-pilot strata. Show the same quad's first single, first pair and final quad, with missing outcomes explicit. All are exposed development data, and sixteen groups cannot establish calibrated uncertainty or geographic generalization.
