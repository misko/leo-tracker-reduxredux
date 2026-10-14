# DS22-001 and DS22-019: sealed start audit

This read-only audit examines the already sealed per-start receipts. No fitting,
candidate selection, reference join or acceptance-rule change was performed.
The source matrices and their hashes are bound by
`local/ds22-band-geometry-v1/report.json`. Coordinates below are the original
optimizer chart in kilometres, not reference-derived coordinates.

## 019: different selected proposal basins

| View | Selected start | Original local center | Fitted position |
| --- | ---: | --- | --- |
| B all | 4 | (-40.638, 12.961) | (-35.74, 19.97) |
| B low | 2 | (43.750, 18.750) | (45.40, 19.80) |
| B high | 0 | (31.250, 18.750) | (35.29, 13.19) |
| C all | 0 | (31.250, 18.750) | (23.79, 7.97) |
| C low | 5 | (82.761, 71.578) | (65.82, 53.19) |
| C high | 5 | (82.761, 71.578) | (73.80, 61.32) |

The large combined-versus-half separation therefore includes selection of
different initial basins; it is not solely a large displacement within one
shared local fit. All six original physical proposals are shared across views,
but each view selects its own stationary minimum training objective. This does
not identify the correct basin. The next useful diagnostic is training-only
discovery coverage and candidate support, rather than averaging the final fits.

## 001: C has rejected lower-objective candidates

| View/start | Objective | Stationarity statistic | Seconds | Solver success | Accepted stationary |
| --- | ---: | ---: | ---: | --- | --- |
| C all / selected 2 | 41863.551059 | 0.000167776 | 19.222 | yes | yes |
| C all / rejected 5 | 41710.548869 | 3673.827092 | 20.066 | no | no |
| C low / selected 2 | 23219.722547 | 0.000782723 | 16.578 | yes | yes |
| C low / rejected 5 | 22553.712282 | 0.003116959 | 10.961 | yes | no |

The all-view start 5 reached its 20-second limit; the low-view start 5 returned
solver success but failed the independent stationarity test. Neither is an
acceptable replacement. Thus C's selected result cannot be interpreted solely
as the converged likelihood preferring the selected basin over every other
attempt: a lower-objective attempted state exists but remains unqualified.
The selected start 2 reports an active physical constraint in both views;
its geographic displacement is 23.433/20.330 km, below the 25 km local radius.
The generic boundary flag must not be read as proof of hitting that radius.

A future controlled convergence experiment should preserve these original
outcomes, declare a separate namespace and matched numerical budgets, select
only by training evidence, and seal results before evaluating reference error.
No retry, relaxed threshold, or promotion is authorized by this descriptive
audit itself. Independent half-band initialization remains underway.
