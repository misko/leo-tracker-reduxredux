# Partial control audit: a real deadline-limited fit completes

At the38/63-source snapshot,76 new direct controls are comparable with iteration55.
One differs: source90, zero-c. Its old20-second run was unqualified; the fresh
90-second run converged after31.016 seconds. No gate or model changed.

| Control | Time seconds | Evaluations | Qualified | Stationarity | Objective |
|---|---:|---:|---|---:|---:|
| Historical55 | 20.027805 | 1151 | no | 43.013849 | 30994.030619 |
| New71 | 31.016088 | 1930 | yes | 0.000125625 | 30992.670416 |

The other75 controls match objective within1e-6 and convergence exactly. The
objective reduction1.360203 for this control is a compute-budget effect, not
evidence that the clock-proposal strategy improved this fit. Its direct new
control, rather than the historical truncated fit, remains the comparator for
all proposal/continuation comparisons. The full report does not substitute the
historical control into a matched current experiment.

This is evidence that the larger allowance can complete a fit that was actually
deadline-limited. It says nothing about globally optimal position or improved
reference error, and does not reinterpret solver-success-but-unqualified cases
as deadline failures. At this snapshot,95 fits are unqualified,94 of them report
optimizer success; those remain ineligible. Maximum current fit time46.450s,
zero90s deadlines. Two workers remain live; no settings have changed.

The [partial comparison and visualization](RESULTS.md) remain38/63 complete
sources and537 individual fit receipts. All64 planned source slots are reported,
including one unavailable source. These are hypotheses for one consumed scan,
not independent dataset samples. Full148 cohort means remain iteration65 values.
