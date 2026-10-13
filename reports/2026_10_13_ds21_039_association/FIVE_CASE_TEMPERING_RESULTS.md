# Fixed likelihood-scale transfer: not promoted

Quarter-scale likelihood weighting did not improve the five-case development
comparison reliably. Three cases improved and two worsened; median error rose
from **1.957 to 4.061 km**, and maximum error rose from **4.899 to 5.216 km**.
Neither condition placed any case below 0.5 km. Do not promote this change as a
general localization fix.

All 60 prescribed fitted-c calls completed, with 58 stationary. Both conditions
produced estimates for all five cases. Reference coordinates were accessed only
after all five case selections and source/attempt receipts had been sealed and
validated. No per-case choice of whichever alpha is closer was made.

| Case | Alpha=1 error km | Alpha=0.25 error km | Change km | Stationary calls, alpha=1 / 0.25 |
| --- | ---: | ---: | ---: | ---: |
| DS21-001 | 1.424955 | 1.404831 | -0.020124 | 6 / 6 |
| DS21-003 | 1.956673 | 5.216294 | +3.259622 | 5 / 6 |
| DS21-005 | 1.556316 | 1.804199 | +0.247883 | 6 / 6 |
| DS21-023 | 4.899019 | 4.559147 | -0.339872 | 6 / 6 |
| DS21-039 | 4.291227 | 4.061201 | -0.230027 | 5 / 6 |
| Median | 1.956673 | 4.061201 | | |
| Maximum | 4.899019 | 5.216294 | | |

DS21-003 is the largest regression. The quarter-scale training selector changes
from original start 5 to start 4 and reaches that start's 25 km local search
boundary. Its projected stationarity is 1.014e-5, so this is a stationary bounded
solution, not an optimizer failure. The boundary limits interpretation; it does
not justify enlarging a particular case's search after seeing its position error.
The two retained nonstationary calls are alpha=1 start 4 for DS21-003 and start 2
for DS21-039. They were not retried or included as selected incumbents.

## Frequency and prior effects

Cross-alpha objective values have different scales and cannot establish
localization improvement. The table below uses the original, untempered NLL;
the native RMS retains branch second moments rather than cancelling ambiguity
through conditional-mean residuals.

| Case | Original NLL, alpha=1 → 0.25 | Physical prior penalty, alpha=1 → 0.25 | Native RMS Hz, alpha=1 → 0.25 |
| --- | ---: | ---: | ---: |
| DS21-001 | 29239.952 → 29241.270 | 162.709 → 160.756 | 106.976 → 107.036 |
| DS21-003 | 26791.949 → 26964.098 | 227.374 → 139.726 | 92.894 → 108.669 |
| DS21-005 | 21210.124 → 21153.733 | 163.085 → 155.706 | 98.300 → 100.004 |
| DS21-023 | 28600.416 → 28286.072 | 180.426 → 167.629 | 105.674 → 108.570 |
| DS21-039 | 32969.500 → 32968.611 | 202.924 → 198.429 | 104.396 → 104.514 |

The prior penalty decreases in every case, while native RMS increases in every
case. DS21-005 has a lower original NLL but worse position, again showing that
better in-sample frequency fit is not sufficient evidence of better localization.
The scale remains a fixed regularization sensitivity, not an estimate of noise
covariance or effective sample size.

DS21-039 here uses its six historical all-view endpoints, as prescribed for all
five cases. It does not receive the later seven-call refined initializer.
Therefore its 4.291 → 4.061 km comparison differs from the earlier two-start
4.073 → 3.930 km sensitivity. Both results are retained; neither meets the target.

## Execution and evidence

The [prespecified protocol](FIVE_CASE_TEMPERING_PROTOCOL.md) fixed case order,
six original endpoint/center pairs, alpha values, priors, native candidates,
candidate banks and 20-second/600-iteration fit budgets. Receiver sampling lifts
were not reapplied. All 30 actual saved-state source replay checks had maximum
absolute delta **exactly zero**, before optimization. Each case archived 400
Python/native/C++ source files. The five bounded slices took 226.090 seconds
in total, excluding freezing and evaluation; no slice needed continuation.

Historical archives remain incomplete dependency records and one orchestration
module differs from its saved version. This limitation is disclosed rather than
replaced by a claim of complete historical byte identity; the actual scalar,
gradient and posterior replay gates passed for every start.

The adapter's 17 owned tests passed in the worker and integration runs (integration
71.93 seconds); 28 compatibility tests passed. The evaluator's 19 tests passed
again in integration (1.38 seconds), including all-five-before-reference, distinct
condition winners, legacy incumbents, explicitly finalized failures as misses,
missing cases and tampering. Ruff passed. Implementations: `fb4bca9d4`,
`5688ff9ed` and `e0cc34f16`.

The [compact numerical report](FIVE_CASE_TEMPERING_RESULTS.json) includes all ten
selected outcomes, prior and frequency diagnostics, active bounds, per-case
timings and protocol/terminal bindings. Evaluation SHA-256:
`d4816eec8420808e1c932b50d4449d7dcb7146233de41b495959bf368e9f32f4`.
Local evidence is under
`reports/2026_10_13_ds21_039_root_cause/local/five-case-tempering-v1`.

Continue the observed-curvature investigation of position/calibration/timing
confounding and the missing development comparisons. This negative result does
not establish a corrected model. Full DS21 evaluation remains incomplete;
locked inference remains unopened and the configured reference is not surveyed
independently here.
