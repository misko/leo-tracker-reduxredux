# Exact deletion audit protocol

Status: prospective protocol. Writing this file does not authorize refits.

The immutable phase-one results at indices 0 and 16 define, for each of the
four existing endpoint families, the physical NORAD folds with largest and
lower-median predicted E/N displacement. Audit exactly those selections, at
most 16 family/fold jobs. Do not replace a failed job or select another fold.

For each job, remove every track assigned to the selected NORAD by the frozen
original-IID training-only assignment. Preserve every candidate mixture and
every ambiguous or other-source track. The `source_receiver_equal` family
uses the weights derived on the full scan and subsets those values without
renormalizing. Start one bounded L-BFGS-B refit at the corresponding full-data
endpoint. Use no extra starts, `maxiter=100`, `maxfun=160`, `ftol=1e-13`,
`gtol=1e-6`, and `maxls=25`, with the unchanged E/N/timing bounds. Each job
has one BLAS thread and a 90-second process cap; run at most three jobs at once.

Qualification requires optimizer success, finite state and gradient, at least
0.001 native units from every bound, maximum absolute gradient at most 0.01,
and central score-gradient discrepancy at most 0.02 using steps `(1e-4 km,
1e-4 km, 1e-5 s)`. Preserve every timeout, failure and unqualified result.

For the omitted tracks only, compute a common original IID Student-t4/100 held
score at both the exact endpoint and phase-one influence endpoint. Each
candidate's constant CFO is profiled using that track's training observations;
the held contribution is `logsumexp(train + held density) - logsumexp(train)`
with that same CFO. Do not reprofile on all observations. No reference
coordinate or geographic error may be loaded or recorded.

An exact audit passes only when the refit qualifies, E/N distance between exact
and influence endpoints is at most `max(0.05 km, 10% of the exact deletion E/N
shift)`, timing discrepancy is at most 0.02 seconds, and absolute omitted held
score discrepancy is at most 0.1 nat. All planned jobs must pass before the
influence approximation advances.

