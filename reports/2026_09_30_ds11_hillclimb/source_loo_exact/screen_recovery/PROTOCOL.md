# Source-holdout screen with one uniform numerical recovery rule

This separate execution revision preserves the failed original screen and
same-solver restart. Its scientific population, four families, source folds,
full-data initializers, frozen weights, causal orbit banks, common held scorer,
tie order and geographic advancement rule are exactly those of
`../screen/PROTOCOL.md`. No reference errors have been evaluated by either
source-holdout screen. No reference error may be evaluated before all eight
new selections are sealed and selectable.

Run the original L-BFGS-B invocation first. A successful qualified fit is final.
For an unsuccessful, finite, interior fit with maximum gradient at most0.01
and audit discrepancy at most0.02, apply the frozen local precision checks:
positive-definite loss Hessians at original and half steps, relative asymmetry
and step-halving discrepancy at most0.005, condition at most1e10, predicted
Newton EN displacement at most0.01m and timing displacement at most1e-5s.
Only if these pass, make one SLSQP continuation from the failed endpoint,
using maxiter100 and ftol1e-12. Require the unchanged optimizer success,
finite/interior/gradient/audit checks and objective nonworsening within1e-7
nats. Preserve both attempts. No other continuation, start, fold deletion or
failure override is allowed. An ineligible or unrecovered failure remains a
failed fold. One90-second process cap includes the initial fit and any checks
and continuation. At most three single-thread workers, one scan at a time.

Reuse the original plan's64 validated caches and43 qualified index-4 fits.
The separately recorded SLSQP diagnostic supplies the remaining index-4
fold after verifying all prerequisites and its successful qualification.
Its original fit, precision diagnostic and SLSQP process times total less
than90seconds; the unrelated failed restart remains separately reported.
Thus108 jobs are cached and340 remain pending. Completed L-BFGS-B successes
require no precision diagnostic or continuation under this rule.

This rule is an engineering revision motivated by an observed numerical
failure, not a blinded solver comparison. Newly attempted folds all receive
the same rule. Preserve all eight scans and all448 folds in the plan. If any
scan cannot supply a complete qualified four-family comparison, stop later
scans and report their not-attempted status. Do not inspect geographic errors
on a selectively successful subset.

After eight selectable scans, select the existing full-data endpoint of the
family with greatest summed common held score per scan. Advancement still
requires at least five wins, at least10% median-error reduction and nonworse
P90 against IID on all eight scans. No geography-based tuning or selection.
