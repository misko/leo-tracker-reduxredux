# Exact source-holdout screen: complete, advancement failed

All eight scans supply complete qualified comparisons: **448/448 folds**,
including108 validated cached fits and340 new fits. The frozen selector reduces
median error by14.75%, but improves only3/8 positions and worsens P90. It fails
the predeclared advancement rule; no wider confirmation or model promotion
follows. No selection used geographic errors.

| Eight-scan screen | Original IID | Selected family |
|---|---:|---:|
| Median error |3108.162m|2649.740m|
| Mean error |3481.538m|2912.321m|
| P90 error |6046.037m|6088.620m|
| Maximum error |6345.775m|6345.775m|
| Sub-km outputs |1|2|

The gate required8/8 selectable scans, at least5 paired wins, at least10%
median reduction and nonworse P90. Coverage and median pass; wins and P90 fail.
Three estimates improve, two worsen and three are unchanged because IID wins
the held-score comparison. The reference is the existing unsurveyed roof
coordinate, not surveyed ground truth.

| Original scan index | Selected family | IID error,m | Selected error,m | Held-score margin over runner-up,nats |
|---|---|---:|---:|---:|
|0|t4/200|765.072|446.750|1.013352|
|4|IID t4/100|3510.342|3510.342|23.099123|
|8|t8/100|5270.648|5978.411|3.124823|
|12|IID t4/100|1183.767|1183.767|0.650657|
|16|t4/200|2153.140|534.044|37.590661|
|20|t4/200|2705.981|3049.797|106.091937|
|24|Source/receiver weights|5917.578|2249.684|24.700835|
|28|IID t4/100|6345.775|6345.775|5.625775|

This is a conditional local source-holdout experiment. Physical NORAD fold
membership is frozen from the original full-scan IID assignments, and each
family's full-data endpoint initializes its deletion fits. It is not a blind
satellite-identification test, a global optimum certificate or independent-site
validation. Common held scoring uses t4/100 for every family, with the omitted
track's CFO profiled from that track's training observations only. Complete
candidate mixtures and original full-scan weights remain intact. The selected
position is the family's original full-data endpoint, never a deletion fit.

## Numerical execution

The original failed screen and failed same-solver restart remain preserved.
This separate revision freezes one uniform recovery policy: only unsuccessful
finite/interior L-BFGS-B fits with sufficiently small gradient and audit error
may receive stable-curvature checks and one SLSQP continuation. The predicted
Newton EN correction must be below1cm; all original qualification requirements
and the90-second total process cap still apply. See [PROTOCOL.md](PROTOCOL.md).

All340 new processes exit0, with wall times5.32–27.94seconds and2788.00 summed
worker-seconds. They run two at a time, one scan at a time, with one BLAS thread.
Five new fits use the recovery path, and all qualify:
`08_iid_t4_scale100_64848`, `16_robust_t8_scale100_63890`,
`20_robust_t4_scale200_65512`, `28_source_receiver_equal_51130`, and
`28_robust_t8_scale100_63877`. The108 caches include the separately verified
index4 recovery. No fit or source is silently dropped.

Seventeen runner/assessor/recovery tests and three final-assessor tests pass.
The final assessor verifies plan and selection source bindings before scoring,
requires all eight selections to be complete, and verifies that scored full
endpoints match every planned initializer. Independent pre-execution review of
the final assessor passes. All six new batch receipts report exit0.

The frozen [plan](plan.json) SHA256 is
`1fd2869dc2952ba7ba3ed4f7fdab51889926da66726740391a0903f371cdfd6f`.
[outcome.json](outcome.json) binds every selection and scored endpoint;
`selections/`, `runs/`, and the batch receipts preserve the complete evidence.

The failure narrows the conclusion: these four existing families, selected by
this exact source-holdout score, do not satisfy the agreed screen criteria.
The median reduction is real on this exposed panel, but the frozen rule must
not be relaxed after observing it.
