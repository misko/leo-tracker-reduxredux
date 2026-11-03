# Atomic exact source-holdout execution plan

Status: preparation protocol only. It authorizes no numerical fits.

The whole-family index-0 pilot is preserved as an engineering measurement:
IID and `source_receiver_equal` completed all 14 folds, while t8/100 and
t4/200 reached the fixed 90-second family cap and produced no family result.
Those timeouts are incomplete execution attempts, not negative scientific fit
outcomes. Do not retry or reinterpret either old process.

This execution revision leaves the scientific question unchanged. Index 0 has
exactly 56 planned jobs: four frozen endpoint families times the same 14
training-frozen physical-NORAD folds. Job order is fixed by family order IID,
`source_receiver_equal`, t8/100, t4/200 and then ascending NORAD. Each future
atomic process handles one fold, starts once at that family's full-data
endpoint, uses the existing optimizer, bounds and qualification gates, has one
BLAS thread and a 90-second cap, and runs with at most three workers. There are
no within-job retries, extra starts, substitute folds, altered weights, or new
model variants.

The plan may cache only completed results with identical source hashes, input
configuration, full endpoint seed, frozen assignment, fold membership,
source-balanced full-scan weights, and common held scorer. Cache all 14 IID and
all 14 `source_receiver_equal` folds from the completed pilot family results.
Cache the two index-0 max/median t8/100 folds and two max/median t4/200 folds
from the prior exact influence audit. The remaining 24 robust folds are
pending. Never reuse a timeout, missing output, unqualified fold, or failed
influence approximation as an atomic fit result. The cached exact refits remain
valid even when their influence approximation failed; only the exact endpoint
and exact common held score are reused.

The common scorer remains original IID Student-t4/100. It profiles each
candidate CFO on the omitted track's training observations and computes held
score as joint-minus-training log mixture density with that same CFO. Candidate
mixtures remain complete. `source_receiver_equal` weights are the original
full-scan values subset without renormalization. No reference coordinate or
geographic error enters planning, fitting, caching, scoring, or selection.

The completed index-0 comparison is selectable only if all 56 jobs qualify and
all four families have identical source, track, and held-observation coverage.
Select maximum summed common held score, breaking exact ties in the fixed
family order above. A future full screen retains the preregistered gate: 8/8
selectable, at least five geographic wins over IID, at least 10% median error
reduction, and nonworse P90, followed by the frozen additional confirmation
panel without tuning.

