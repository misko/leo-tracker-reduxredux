# Local timing recovers both confirmation regressions

The separate three-integer-point variant passes all 132 original/mirrored
constructed receiver policies and recovers both receiver identities lost by
single-integer early confirmation. It restores original native development
retention of 67/79. That remains insufficient for the requested small-loss 10x
replacement; this result improves a building block, not final qualification.

| Rate | Retained reference identities | Unmatched active outputs | Mean candidate CPU | Maximum candidate wall |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 33/37 | 3 | 14.09 ms | 20.10 ms |
| 5 MS/s | 34/42 | 1 | 26.45 ms | 39.27 ms |

All reference-positive visits retain an associated receiver. This replay uses
the prior full application inventory and fresh candidate processing, with
causal state independent per session/rate/edge and receiver cache key. It does
not remeasure the application, so no new paired speedup is claimed. The recorded
replay completes in 1.71 seconds; sources and inputs remain unchanged. There
are 1200 added confirmation calls, all included in whole-call candidate timing.

Both regression receivers recover: visit 1089 RX1 at 2.5 MS/s and visit 1104 RX0
at 5 MS/s. The wider local search also restores an unmatched RX0 output at
5 MS/s visit 1101. Compared with the original native baseline, the candidate
retains the same number of identities with one fewer unmatched output at 5 MS/s;
compared with the strict single-integer variant, it trades two recoveries for
one extra. These are reference disagreements, not independently proven physical
false alarms. Do not tune away the extra using this case's outcome.

The 66 control executions complete in 2.85 seconds with 52 truth-associated
positives and 80 correct negatives. Two new unit tests verify selection of an
adjacent valid point over a higher-margin point with failed frequency status,
fixed frequency inputs, center tie-breaking, and no guided drift learning.
The prior nuisance veto and cache-clear tests remain inherited behavior.

Before replay, an ambiguous module import selected a different reporting
adapter and raised ImportError. No IQ was read and no replay lock/result was
created in that attempt. The runner now loads the exact adapter path; the
completed run's source lock records that corrected runner and dependency.

Next address proposal coverage with a bounded, time-distributed acquisition
path. The current candidate still misses 12/79 identities and has no rescue.
Combine any new proposal mechanism with measured confirmation and explicit
negative/control gates before a new complete-call comparison. These are
development results; no new holdout is opened and earlier holdout failures
remain unchanged.
