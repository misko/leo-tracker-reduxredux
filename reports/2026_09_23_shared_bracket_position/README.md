# Shared host-bracket timing position comparison

This experiment constrains timing to one shared offset per scan inside the saved
host timing bracket. The 22 randomized validation timing authorities were read
through the public `ScannerTrackingInputStore` as the `leo` user and frozen in
`timing_metadata.json`; no retrospective-test source or array was opened. All 22
authorities are qualified, with bracket widths of approximately 363–366 ms.

At each receiver coordinate, the model evaluates a fixed 17-point inclusive grid
across each scan's bracket. Every track chooses its candidate and constant CFO
from training rows at the common scan tau. The scan tau and receiver coordinate
are then selected by either capped 800 Hz or pseudo-Huber 150 Hz training loss.
The control fixes shared tau to zero. Inference was sealed before reserved-row or
reference-coordinate scoring.

## Whole randomized groups

| group | method | train objective Hz | reserved capped RMS Hz | error km | bracket-edge scans |
|---|---|---:|---:|---:|---:|
| Sep 22 18Z, 10 scans | tau 0 capped | 241.72 | 261.83 | **1.836** | 0/10 |
| | shared bracket capped | 233.57 | **250.61** | 2.154 | 8/10 |
| | shared bracket robust | **176.22** | 251.34 | 2.335 | 8/10 |
| Sep 23 08Z, 12 scans | tau 0 capped | 261.72 | 278.38 | 6.717 | 0/12 |
| | shared bracket capped | 253.06 | 272.09 | 6.640 | 11/12 |
| | shared bracket robust | **193.21** | **271.33** | **6.148** | 9/12 |

The constrained shared timing model improves frequency objectives modestly but
does not yield accurate position. It worsens geographic error in the first group
and modestly improves it in the second; every result remains above 1 km. Most
scan offsets hit a bracket edge, which is direct evidence that the constrained
objective often prefers timing beyond the saved host uncertainty interval.

![Geographic errors](geographic_error.png)

The nested first-scan views show the same instability. Shared robust timing gives
1.432 km in the first scan versus 3.135 km for tau zero, while the other first
scan worsens from 7.042 to 8.171 km. They are sensitivity views, not independent
replicates.

## Limits

The 17-point grid is finite, with spacing near 23 ms. Edge hits prevent treating
the selected endpoints as resolved optima. The saved brackets constrain host
capture-start uncertainty; they do not bound absolute UTC error, TLE error, or
model mismatch. This is a constrained timing hypothesis, not timing ground truth.

The tau-zero control is a shared-timing control and therefore differs from the
earlier per-track integer ±5 s model. That earlier model remains an external
comparison and was not modified. The conditional candidate pool and seeds still
come from historically response-conditioned published analyses. Only two whole
randomized validation groups are available.

Inference took 120.8 seconds and post-seal evaluation took 1.3 seconds. Results
contain every coordinate, convergence diagnostic, per-scan selected tau,
boundary flag, source digest, and common reserved metric.
