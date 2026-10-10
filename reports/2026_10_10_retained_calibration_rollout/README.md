# Retained-calibration recovery rollout

This change adds the bounded, reference-free recovery tested in
[iteration 107](../2026_10_09_position_error_iter107/FULL193_COMPLETE_SNAPSHOT.md)
to the standard B7 adaptive analysis path. It applies only when an ordinary
retained search region failed calibration. The three ordinary regional passes
and their qualified candidates remain available; the same regional score
chooses a winner before the unchanged B3–B7 stages. Known receiver coordinates
and position errors are evaluation-only.

## Evidence and limits

The sealed matched comparison covered all 193 consumed DS16/DS17/DS18/newer
development recordings. The recovery trigger fired 52 times and 47 recoveries
qualified, but only four fitted-c selections changed. Fitted-c mean error went
from 1.540 to 1.255 km; the median remained 0.893 km. The `ac11` scan accounted
for about 99.4% of the aggregate fitted-c improvement, falling from 55.685 to
1.031 km. DS18's 53.401 km failure remains. The result supports recovery of a
specific failed-calibration class; it is not evidence of a broad typical-error
improvement or an independent validation set.

| Dataset | Members | B7 fitted-c mean, km | Recovery mean, km | c=0 B7 mean, km | c=0 recovery mean, km |
|---|---:|---:|---:|---:|---:|
| DS16 | 63 | 0.979 | 0.974 | 1.321 | 1.314 |
| DS17 | 51 | 0.819 | 0.819 | 1.327 | 1.327 |
| DS18 | 34 | 2.692 | 2.692 | 2.816 | 2.816 |
| Newer development | 45 | 2.271 | 1.057 | 2.908 | 1.752 |
| All | 193 | 1.540 | 1.255 | 1.956 | 1.684 |

![Paired position errors for all 193 consumed scans](../2026_10_09_position_error_iter107/full193-complete.png)

The c=0 and fitted-c arms share calibration and association, then get matched
final-fit budgets. Frequency-fit changes are reported separately in the
[sealed comparison](../2026_10_09_position_error_iter107/FULL193_COMPLETE_SNAPSHOT.md);
a lower in-sample frequency residual alone does not establish a better position.

## Implementation

The recovery inventories calibration failures from all ordinary B7 passes and
deduplicates repeated physical starts. It verifies each saved coarse fit against
the current model, applies at most two reduced-Newton rounds and 100 objective
evaluations to an unqualified fixed-position calibration state, then runs fresh
receiver correction, bounded postfit, association and six final fits. All work
uses digest-bound checkpoints and the existing 500-second resumable worker
slices. A failed retry leaves every ordinary candidate available. The B7 policy
and source digests identify the new behavior; V3 and historical persisted
contracts are unchanged.

## Validation and deployment

Component, B7, CLI, contract, storage and API tests: **30 passed** on the
development Python 3.13 environment using the identical-source native orbit
extension, and **26 passed** on the active worker's pinned Python 3.14 release.
Ruff lint, formatting and `git diff --check` pass. Real-scan parity,
immutable staging, service activation, new-scan publication and WebUI PNG
verification are pending at this checkpoint.
