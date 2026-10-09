# Execution audit: eight-worker run stopped after control regressions

The first16 unchanged controls include **four convergence losses** relative to
iteration55. Each losing control ends just over20seconds, with fewer recorded
feasible evaluations and no solver-success flag. The fitter checks a monotonic
wall deadline before objective evaluations. These observations demonstrate that
equal nominal wall budgets did not provide reproducible numerical work in this
execution context. They do not establish that the new clock proposals worsen
localization.

| Source / arm | Old evaluations | New evaluations | Old seconds | New seconds | Old / new converged |
|---|---:|---:|---:|---:|---|
| 7 fitted | 1233 | 1009 | 19.818 | 20.038 | yes / no |
| 13 fitted | 600 | 486 | 10.182 | 20.081 | yes / no |
| 19 fitted | 662 | 466 | 11.159 | 20.075 | yes / no |
| 19 zero | 656 | 466 | 10.777 | 20.059 | yes / no |

Eight new single-thread workers were active alongside the two older fit jobs.
The controls show a substantial evaluation-rate change during this run. Exact
attribution among CPU/memory contention, host activity, numerical path sensitivity
and other execution effects has not been isolated. The evidence is sufficient
to reject this execution setup as a faithful extension of the historical
20-second controls. No convergence tolerance is relaxed and no failed candidate
is retroactively accepted.

All eight workers were explicitly terminated; their tool sessions confirmed
exit143. Partial receipts and completed-source summaries are preserved. Missing
receipts represent work not completed before termination, not scientific input
exclusions. Do not resume this protocol or treat its partial localization results
as the outcome of the proposed method.

The eight-worker interval overlapped the tails of iteration55 and60. Their
first-attempt results must remain intact, but budget sensitivity must be disclosed
when interpreting late failures or differences. The smooth pilot has completed;
the direct sweep remains live. Any controlled repeat needs separate receipts and
a new frozen protocol, rather than replacing inconvenient first attempts.

Iteration70 qualifies the first eight frozen source indices, both arms, using two
workers and a90-second emergency wall allowance with the same600-iteration limit,
model and convergence test. These are all16 controls, not only the four that
regressed. This is explicitly a larger allowance, not an equal-compute claim.
Report objective/parameter differences, convergence and evaluations against both
historical controls. Only then choose an execution policy for a full rerun.
No source is chosen using reference accuracy. No production change is implied.
