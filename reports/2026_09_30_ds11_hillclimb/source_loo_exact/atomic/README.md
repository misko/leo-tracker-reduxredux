# Completed exact holdout comparison for scan 0

All 56 satellite-deletion folds qualify. The frozen, reference-free selector
chooses robust Student-t4 with a 200 Hz scale for this scan. No reference error
has been evaluated for this selection; it is not yet an accuracy result.

| Full-data endpoint family | Qualified source folds | Common omitted-source held log score |
|---|---:|---:|
| Original IID t4/100 | 14/14 | -7113.256023 |
| Source/receiver equal | 14/14 | -7119.547198 |
| Robust t8/100 | 14/14 | -7113.002728 |
| Robust t4/200 | 14/14 | -7111.989376 |

The score margin over IID is 1.266647 nats. The same 14 satellites, tracks and
held observations contribute in every family. The rule selects the existing
full-data endpoint of the winning family; the deletion fits themselves are
validation fits, not replacement position outputs.
Source labels and optimizer starts come from the full-scan training fits, so
this remains a conditional local diagnostic, not blind satellite identification
or a guarantee of global optimization. The recordings have been examined in
earlier experiments; geographic confirmation remains necessary.

This execution revision reuses 28 qualified folds from the completed IID and
source-weighted family pilot, plus four qualified robust exact fits from the
earlier approximation audit. Only their exact fits are reused, not the rejected
influence estimates. All 24 missing folds complete successfully under individual
90-second caps, using at most three single-threaded workers. Each new fit takes
6.31–18.64 seconds; summed job wall time is 214.68 seconds. No within-job retry
or optimizer change occurs.

Three execution tests cover stale dependencies, refusing cached-fit reexecution,
and retaining a timeout without retry. The unchanged numerical fit and scorer
reuse the previously tested components. A separate prelaunch audit verifies all
32 cache identities, terminal receipts, source hashes, full-data seeds and held
coverage. The final assessor verifies all 56 fits and seals selection before
any geographic assessment. Both original whole-family timeouts remain part of
the history; they are not turned into scientific fit failures or omitted.

A preparation-source edit was detected before execution. The initial plan and
verification are preserved in `prelaunch_archive/`. The replacement plan keeps
all jobs and non-source fields unchanged and binds the finalized preparation
source. Fresh verification passes before numerical launch. No numerical result
was used to revise the plan.

Evidence: [protocol](PLAN_PROTOCOL.md), [plan](plan.json),
[cache verification](plan-verification.json), and [sealed selection](selection.json).
The seven remaining screen scans and the geographic gate are still outstanding.
All inputs use the original causal orbit banks; no offline orbit data or new RF
collection enters this comparison.
