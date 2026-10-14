# Current 023/025 matched A timing control: mixed result, no promotion

The intervention improves 023 from 7.758953 to 5.868672 km and worsens 025 from
6.049037 to 6.641096 km. The two-case median changes from 6.903995 to 6.254884 km;
neither treatment estimate is below 1 km or 0.5 km. This result does not meet the
localization goal and does not support a full-cohort promotion.

The scientific parents are the sealed current coverage 023/025 cached-v2 matrices,
which preserve original coverage-v1 numerical models and fitted-c budgets. The
new control source was frozen before qualification or calls. Independent baseline
start 0 repeats reproduced high/final seeds and options, vectors, nuisance,
objective, likelihood, frequency RMS and receiver offsets exactly in both cases
(maximum absolute difference 0). Starts 1–5 reused validated sealed baseline
high/final receipts; all starts inherited their own low fit. Both cases' two
conditions and implementation controls sealed before the configured reference
was read.

| Case | Condition | Selected start | Position error km | Objective | Likelihood NLL | Frequency RMS Hz |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 023 | Original | 0 | 7.758953 | 30973.522 | 30646.334 | 127.134 |
| 023 | Low timing locked high | 0 | 5.868672 | 29674.535 | 29389.715 | 108.488 |
| 025 | Original | 0 | 6.049037 | 30629.717 | 30296.455 | 121.067 |
| 025 | Low timing locked high | 3 | 6.641096 | 30556.965 | 30129.024 | 123.477 |

The total objective and likelihood improve in both cases, while 025 location
accuracy worsens. In 023 the selected basin remains start 0, so its improvement
does not depend on a changed winner. In 025 original selected start 0's locked-high
fit fails the unchanged stationarity test and is excluded, leaving start 3.
Its two-offset KKT residual is 0.001275435; 023 start 2 likewise fails at 0.001090920.
Both optimizers report success, neither hits a physical boundary, and their
scientific failures are preserved. No final fit or retry was attempted for either
failed high stage. A stricter convergence prototype would need its own matched
protocol; these outcomes cannot be relabeled stationary.

Actual accounting is 13 new calls per case (26 total), 10 reused high/final calls
per case (20 total), and 6 inherited low fits per case (12 total). All 44 stationary
high/final calls remain bound to their durable receipts; the two
nonstationary high calls remain explicit. No whole-unit timeout occurred. The
20 s and 600 iteration limits per numerical call, 90 s whole-unit/105 s TERM/110 s
KILL bounds, and fitted-c were preserved. Source freezes took 11.748/10.839 s;
both zero-fit cache qualifications and all ten metadata reuse units passed.
Fresh baseline controls took 9.312/10.415 s; the twelve locked units completed in
10.788 s with eight workers.

The bound JSON contains every individual path, objective and likelihood order,
stationarity status, source-protocol and original-parent bindings, and the
postseal-only errors. This audit keeps the original objective selector unchanged.
The objective and likelihood choose the same winning start in all four conditions.
The 023 baseline orders starts 0, 1, 5 first under both; the 025 baseline orders
0, 2 first under both. Both locked conditions have identical complete objective
and likelihood orders. Thus a prior-only ranking change does not explain the
selected inaccurate basins.

The selected 023 baseline assigns 1329.32 signal windows versus 1200.67 for
start 1, whose posterior frequency RMS is lower (108.82 versus 127.13 Hz).
The selected 025 baseline assigns 1545.31 signal windows versus 1194.79 for
start 4, the more accurate path in the postseal audit. Lower conditional RMS
and higher mixture likelihood can disagree because they summarize different
quantities. These counts establish that the selected basins recruit more signal
mass; they do not establish which individual associations are correct.
