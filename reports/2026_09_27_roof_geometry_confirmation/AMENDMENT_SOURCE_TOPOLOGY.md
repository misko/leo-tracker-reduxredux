# Outcome-blind source-topology amendment and secondary search-guidance rule

Declared before reading any fresh-cohort distance errors. Original `PROTOCOL.md`, its three successful/ongoing search products, and the f147 failure receipt remain distinct and unchanged. The original primary is not retroactively declared successful or complete.

## Why a separate amendment is needed

The f147 recording has one exact source anchor shared by two distinct reconstructed tracks. The anchor is reserved in both tracks; there is no training/reserve crossover. The frozen endpoint uniqueness guard correctly refuses to count that physical observation twice. This is track-topology ambiguity, not evidence of raw recording corruption or an error-based exclusion.

## Uniform input-integrity rule

Before unblinding, audit **all six calibration and all four confirmation recordings** with `source_topology.py`. Every prepared training and reserved observation must resolve to one exact source candidate. Exclude every whole track containing a source candidate used more than once, including within-track repeats. This removes both sides of every collision rather than selecting an owner using duration, signal strength, satellite fit, reception outcome, or reference error. Retain all other tracks in their original order, with their exact measurements and training masks.

Apply the retained track set identically to prediction banks, frequency likelihoods, reception rows, and occupied-second weights. Preserve complete removal accounting and source/rule hashes. Do not replace any recording. If any of the six calibration scans loses tracks, the existing models are not automatically valid: halt amended confirmation until both frequency and reception calibration are recomputed under this same rule. If all calibration inputs are unchanged, keep the frozen model parameters exactly.

Run a homogeneous four-recording amended comparison under separate `topology-search-` artifacts, applying the same rule even where it is a no-op. Do not silently mix three original products with one amended product. Keep primary D versus D+geometry, independent Sacramento/Reno priors, 160 points per arm, and all original search/model settings. No test-reference coordinate enters a search. Do not unblind amended distance errors until all four amended searches are terminal and all provenance checks pass. If an amended recording still fails, disclose it rather than replacing it or claiming complete four-scan accuracy.

## Secondary, budget-matched geometry-guided final selection

Development—not confirmation—results show that geometry can guide a search into a useful region while Doppler gives a better fine-scale ranking once that region is explored. Therefore freeze this secondary method before confirmation unblinding:

1. Run the unchanged D+geometry search with its original160-point budget.
2. Among **only the points that this arm actually evaluated**, select the minimum Doppler-only D score.
3. Compare that selected coordinate against the independent160-point D-only search result.

Both scores were already computed at every evaluated point. This incurs no additional location evaluations and does not use the D/J union inventory, another prior's candidates, another recording's winners, or reference coordinates. Ties use D, east, north. The helper must validate that every selected-arm trace coordinate has exactly one finite score record and that counts match the trace receipt.

Report this as a secondary pre-unblinding comparison, not as the original joint-likelihood primary. Report every scan/prior case, including regressions, and distinguish search guidance from an improvement in the geometric likelihood's final ranking. Common-union diagnostics remain separate and do not inherit the budget-matched claim.

All coordinate, pose, dependence, and limited-cohort caveats in the original protocol continue to apply. A success claim still requires actual fresh-data distance improvement and the predeclared reception-dependence sensitivity; nominal grid refinement alone is not success.
