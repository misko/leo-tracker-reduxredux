# Centred arithmetic: bounded numerical qualification

Near an endpoint with objective about 40,000–58,000, subtracting two complete
float64 objectives can hide a small improvement. This experiment instead
passes the optimizer the sum of individual row-NLL differences plus the prior
difference from a fixed reference. It preserves the mathematical objective,
analytic gradients, physical constraints, priors and original acceptance
threshold. Final audit always evaluates the original unwrapped objective.

Three tests pass: unchanged gradients/objective differences, resolution below
the total-objective float64 spacing, and rejection of a changed row inventory.

One uniform remaining-budget attempt was applied to each failed pilot endpoint
that had already received the separate standard polish and still had budget.
The reference evaluation is charged. Counts include the original fit and all
subsequent numerical attempts, capped at 1,000; the wall accounting is separate
cumulative active time, not the original continuous deadline. No parent receipt
is overwritten and no scientific threshold is relaxed.

| Source / arm / method | Extra calls | Final projected KKT | Strict pass | Association changes |
|---|---:|---:|---|---:|
| S01 fitted-c continuation | 9 | 0.003968 | No | 0 |
| S01 c=0 annealing | 8 | 0.002206 | No | 0 |
| S01 c=0 continuation | 135 | 0.001362 | No | 0 |
| S04 fitted-c annealing | 8 | 0.001141 | No | 0 |

The 135-call entry includes one reference and the existing engine's 134-call
maximum. S01 c=0 continuation improves stationarity within its remaining
allowance, but none of these four attempts passes KKT ≤0.001. This does not
qualify the S04 annealing lead as a converged endpoint. Memberships remain
unchanged, and both raw and supplemental receipts are retained.
