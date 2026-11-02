# RF execution and coverage

All 205 available recordings retain explicit paired policy decisions; 24 unavailable source members remain outside this denominator.

| Wave | Enqueued | Started or preserved | Wall seconds | Global partial starts |
|---|---:|---:|---:|---:|
| 1 | 205 | 124 | 1200.71 | 8 |
| 2 | 81 | 81 | 667.05 | 0 |

Complete raw fit pairs: A 87 (65 qualified), B 77 (73 qualified). C evaluates the same B endpoints and performs no additional position fit.

Policy-accepted pairs: A 65, A+B 73, A+B+C 0. Acceptance is distinct from completed raw fits and all fallback rows remain in the population.

Raw model-arm cell statuses: `{'complete': 334, 'cell_cap': 7}`. These cell caps are separate from interrupted starts at a global wave deadline.

Outer preparation/guard cap stages, classified from sealed tracebacks: `{'baseline_numerical_probe': 7, 'family_ranking': 21}`.

Summed elapsed time from terminal worker receipts is 17231.31 worker-seconds. This excludes worker time for global-deadline partial starts and is not a total-compute or speedup claim.

No attempted case or capped cell was retried. Additional waves admit only never-started queue placeholders. All pools were joined. Position accuracy is evaluated separately by the parent after the combined RF audit.

The [receipt archive](../evaluation_receipts.tar.gz) preserves exact component ledgers, case evidence, eligibility plans and the combined ledger. See [RF summary](rf_execution_summary.json), [case ledger](rf_case_ledger.csv) and [prospective completion methods](COVERAGE_COMPLETION.md).
