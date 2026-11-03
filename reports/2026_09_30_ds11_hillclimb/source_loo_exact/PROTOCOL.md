# Fully exact source-holdout comparison

Status: prospective protocol. Only the index-0, four-family runtime pilot may
run after code review. No wider screen is authorized by this document alone.

The final intended screen is the eight original DS11 indices
`0,4,8,12,16,20,24,28`. Compare exactly four existing qualified full-data
endpoints in this deterministic tie order: original IID Student-t4/100,
`source_receiver_equal`, robust Student-t8/100, and robust Student-t4/200.
No new model variant or weight is introduced.

Freeze track membership independently for each scan from its original IID
training endpoint and the existing digest-bound candidate-ID-to-NORAD map. A
track belongs to a physical-NORAD fold only when its conditional candidate
probability is at least 0.90. Fold across every receiver and RF for that NORAD;
require at least two assigned tracks. Ambiguous tracks remain in every retained
objective. Preserve complete candidate mixtures. For `source_receiver_equal`,
derive weights once on the full scan and subset them without renormalization.

For each family and every eligible source, delete that source's tracks and run
one exact local L-BFGS-B refit from the corresponding qualified full-data
endpoint. Use unchanged E/N/timing bounds and `maxiter=100`, `maxfun=160`,
`ftol=1e-13`, `gtol=1e-6`, `maxls=25`. Qualification requires optimizer
success, finite state and score gradient, at least 0.001 native units from all
bounds, maximum absolute gradient at most 0.01, and central score-gradient
discrepancy at most 0.02 using `(1e-4 km,1e-4 km,1e-5 s)` steps. Do not add
starts, clip, retry, ridge, replace folds, or silently drop failures.

Score only the omitted tracks at the exact retained-data endpoint with one
common original IID Student-t4/100 rule. For each track and candidate, profile
the constant CFO on training observations only. Its held contribution is
`logsumexp(train + held density) - logsumexp(train)` using that same CFO. Sum
the common held score across every eligible source. No reference coordinate or
geographic error may be loaded by fitting or scoring code.

A scan is selectable only when all folds in all four families qualify and have
identical source, track, and held-observation coverage. Select the family with
maximum summed common held score; exact ties use the fixed order IID,
`source_receiver_equal`, t8/100, t4/200. Do not compare retained training
objectives across families or folds because their dimensions and weights
differ.

The final screen gate, evaluated later outside the reference-free runner, is
8/8 selectable scans, at least five geographic wins over original IID, at
least 10% median error reduction, and nonworse P90. Passing would require the
already frozen additional confirmation panel without tuning. The current pilot
runs index 0 only, one family per process, one worker, one BLAS thread, and a
90-second cap. It measures fit count, terminal coverage, and runtime before any
wider launch.

This runner version explicitly accepts index 0 only because it reuses the
immutable phase-one input validator, which was bounded to indices 0 and 16.
Wider-screen authorization requires a separately reviewed adapter/version; do
not edit the frozen phase-one helper to widen it.
