# Association audit and one-change refit

One objective-selected satellite assignment change gives a small geographic
improvement over the fixed-assignment calibrated refit. It still does not beat
the original all-data baseline on median error or meet the requested targets.

| Same12development scans | Median error (m) | p90 error (m) |
|---|---:|---:|
| Original all-data baseline | 1,892 | 3,998 |
| Calibrated, fixed assignments | 2,117 | 3,534 |
| Calibrated, one assignment change | 2,065 | 3,478 |

All12final scan results qualify. Nine scans have an improving tested assignment
alternative and receive a refit; the other three retain their parent result.
Six of the nine refits improve geographic error and three worsen it. Final
counts remain3/12within1km and9/12within3km. No selection uses the geographic
reference, and no failed or unfavorable outcome is removed.

![Paired geographic errors](calibrated-swap-panel-v1.png)

## What the audit establishes

At each sealed calibrated endpoint, test each track's best training-score
alternative excluding its incumbent. All12audits finish, covering545alternatives.
Of24full-objective improvements across9scans,16have negative track-only gain.
Ten improvements replace clutter with a satellite. Therefore restricting
proposals to positive track-only gains misses relevant changes. This is not
an exhaustive catalogue or simultaneous-assignment search.

The complete objective includes calibrated candidate-set terms, training terms,
and original nuisance priors. Newly unused epoch variables are profiled tozero;
shared epochs remain when another track still uses that satellite. Scalar and
vectorized evaluations agree for every tested alternative, and the prior-only
improvement is independently checked against the full likelihood difference.

The single-change rule selects the greatest audited positive full-objective gain
for each affected scan, then refits continuous parameters. All18control/candidate
fits pass source/input/height/membership checks, objective reproduction and
complete scalar finite-difference stationarity checks. Six derivative and epoch
profiling tests pass. These checks establish numerical consistency, not correct
satellite identity or a globally optimal location.

Median incremental refit runtime is5.25seconds, maximum6.95seconds for the nine
changed scans. These timings exclude the proposal audit, parent refit, acquisition
and preprocessing; they cannot establish cold90-second compliance. All work uses
existing cached observations, at most two fitting processes, unchanged Sacramento
support, fixed100ftMSLheight, and frozen excluded-dataset frequency calibration.

No64promotion, held-out recording evaluation, or new position-uncertainty result.
The original baseline remains unchanged. Next: a bounded alternating assignment
and continuous fit with a single total deadline, requiring both continuous
stationarity and absence of improving tested assignments. A one-change fit does
not establish either discrete stability or that association refinements are
exhausted. Retain any deadline or iteration failures rather than continuing them
outside the budget. Geographic improvement must still be demonstrated.

Evidence: `calibrated-proposal-audit-v1-summary.json`,
`calibrated-swap-v1-evaluation.json`, `calibrated-swap-panel-v1.json`, source
freezes, raw receipts and SHA256 sidecars. Reference remains operator-provided
and unsurveyed. This is an exposed development panel, not final validation.
