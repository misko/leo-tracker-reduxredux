# Algo07v4 baseline and algo07v5 goal

Algo07v4 preserves the full-budget native solver as a separately identified
implementation. Algo07v3 keeps its original solver. Algo07v5 is an investigation,
not an available runtime version.

## Proposed slash goal

```text
/goal Preserve the measured full-budget native implementation as algo07v4 on
upstream main. Develop algo07v5 toward at least 2x complete-worker speed versus
the frozen algo07v3 baseline, with another 2x versus algo07v4 as a stretch target.
Measure the speed versus localization-accuracy frontier before choosing an
approximation budget. Keep algo07v4 fixed as the rollback and comparison point.

Use tools/evaluate_algo07.py run --profile quick for DS26-0002/0066/0102,
and the same CLI with --profile full for the complete frozen DS26 inventory.
Pass --version algo07v4, --native-manifest FILE and a fresh --output DIR for
the fixed baseline. Register algo07v5 before selecting it as a candidate.
Use the documented pinned Python environment and plan before a full run.
Start every experiment with a bounded component replay, then
run the quick screen. Qualify finalists on the independent remaining scans.
Keep all 159 expected inventory members visible, including the currently
unavailable DS26-0172. Report completed, failed, timed-out and missing counts.
Never count an incomplete run as a speedup or silently shrink the denominator.

Report complete-worker wall and CPU time, stage costs, actual solver work,
and both c=0 and fitted-c results under matched data, candidate policies,
priors and search budgets. Report GPS error median/p90/p95/max, paired error
changes and all outliers separately from frequency fit, ownership and audit
changes. GPS may score completed inference; it must not select settings or
enter inference. Separate development scans from held-out qualification.

Prioritize predictive annotation, inclusion/retry, initial search and
admission. Look for repeated work that can be reused or moved earlier before
reducing budgets. Preserve negative experiments. Keep one change per measured
attempt and record its speed, accuracy, failures and decision. Use alternating
timing repeats on representative quick cases before claiming a stable win.
Stop when the target and chosen accuracy budget pass independent evaluation,
or report the measured frontier and the remaining bottleneck explicitly.
```

The accuracy budget is intentionally open. A measured frontier lets the operator
choose a useful tradeoff rather than assume that every numerical difference
invalidates a candidate. A candidate still has to produce valid, complete
scientific results and publication artifacts.

## Measured starting point

The original and native runs use the same full precision-update budget.
These are one sequential pair per development scan, not population estimates.

| Scan | Original wall seconds | Native wall seconds | Original/native ratio |
| --- | ---: | ---: | ---: |
| DS26-0002 | 184.391012 | 117.959557 | 1.563171 |
| DS26-0066 | 390.672137 | 238.859981 | 1.635570 |

Both calibration arms retain observation ownership, counts and selected
publication gates. Final positions move by micrometers on 0002 and about one
meter on 0066. The latter changes six internal audit flags. The unchanged
strict verifier reports numerical histories as `not_exact` in both cases.
These observations support a useful candidate, not DS26-wide accuracy or
repeatability qualification.

Raw comparison summaries are under
`/srv/bulk/leo-dev/algo07v3-speed-lever-20261110/` in
`native-0002-fused-pair-001/summary.json` and
`native-0066-fused-pair-001/summary.json`.

## Order the next experiments by remaining native cost

Use native stage clocks rather than the original pilot's percentages.
Numerical replay already costs only 0.162 seconds on 0066 and 5.471 seconds
on 0002. The table names hypotheses, not demonstrated speedups.

| Phase | Native wall seconds, 0002 / 0066 | First alternative to evaluate | Main tradeoff or proof needed |
| --- | ---: | --- | --- |
| Predictive annotation | 6.73 / 55.81 | Factor the shared receiver/noise covariance once and evaluate conditional orbital modes through low-rank systems. Census exactly identical training recipes before adding a fit cache. | Preserve held-out conditioning and mixture moments. Cache only identical masks and full fit recipes. |
| Inclusion and retry | 17.85 / 11.64 | Replace repeated cold Powell work with targeted feasibility restoration or continuation, followed by the full audit. | Optimizer trajectories and local minima can change. Measure gate and ownership changes. |
| Initial search | 13.41 / 37.32 | Check whether saved zero-reference first-round fits exactly replace the final zero-reference control refits. Then test paired coarse screening of branches. | Exact reuse requires whole-fit equality. Screening can miss a winning branch. |
| Conservative fit | 5.97 / 15.24 | Reuse symbolic layouts across mask changes; compare cold refits with continuation. | Numeric values must not survive a changed mask. Continuation is approximate. |
| Family policy | 8.12 / 8.16 | Check whether no-entry linear refits repeat an already saved fit. | Check result fields, objective, stops and work counts, not endpoints alone. |
| Admission | 6.48 / 19.92 | Use existing cavity/influence information to propose targets, then close the phase reference and run the full audit. | A ranking gradient is not an optimized omitted-family fit. Preserve fold independence. |
| Ranking | 4.91 / 3.53 | Apply static eligibility early; test influence shortlists before exact omission calculations. | Preserve candidate recall and account for changed audit rows. |
| Residual screen | 8.05 / 11.28 | Share candidate-independent covariance factors across predictive scores. | Do not leak full-data winners into training-fold candidate sets. |
| Additional and final repair | 0.04 / 30.11 | Share objective and constraint calculations; test derivative-assisted fitting. | Preserve explicit-family mutations, physical slacks and final orbit audits. |
| Signed and family cavity | 8.09 / 5.42 | Census duplicated phase-width/history queries and batch matching geometry queries. | Small scope. A previous geometry cache failed its representative cost screen. |

The first bounded experiment should capture a complete hard-case annotation.
Compare all conditional densities, mixture weights, covariance summaries and
nomination decisions before a complete-worker attempt. The exact initial-control
reuse check is a separate cheap experiment. Do not combine either with a precision
cap or an unqualified kernel change.
