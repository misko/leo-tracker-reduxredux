# Legacy detector import isolation on the weak all-visit fix

Deferring the legacy detector reduced the measured scanner first-load
subtree by **104 ms CPU** on the current saved DS30-0016 positive path.
The single deferred process still took **4.200 s through exit**, versus
**4.166 s** on the uninstrumented original. It preserved the complete
science and publication. There is no demonstrated launch-to-exit saving
on the current worker.

| Saved 8 ms scope | Uninstrumented original | Profiled original | Detector deferred |
|---|---:|---:|---:|
| Scanner first-load CPU (ms) | — | 221.306 | 117.357 |
| Position first-load CPU (ms) | — | 338.905 | 358.632 |
| Numerical solve CPU (s) | 2.097 | 2.074 | 2.138 |
| Eight-figure renderer CPU (s) | 0.478 | 0.485 | 0.517 |
| Other decision/publication CPU (s) | 1.090 | 1.066 | 1.096 |
| Complete wall / CPU (s) | 4.166 / 4.136 | 4.086 / 4.079 | 4.200 / 4.199 |
| Input blocks / major faults | 3,712 / 67 | 312 / 12 | 0 / 0 |

The first-load measurements charge each root's transitive loads once and
sit inside the publication work. The ordinary profile counted first
imports and nested calls across the entire phase. The deferred process
tracked just the scanner and position roots, through the same release
loader. These single launches have different dependency page states
and different numerical and rendering times. Elapsed differences cannot
be assigned solely to import isolation.

## Positive-path dependencies

The installed scanner still runs its real `analyze` and `scan_report`.
Its detector consumer is bypassed by the one verified saved handoff. The
source-pinned `--lazy-scanner-detector` option deferred that receiver at the
scanner's normal import boundary, then would have used the original
implementation on demand. There were zero original detector calls. The
legacy `blind_compact_run`, differential pilot and SciPy signal modules
were absent at exit. The historical 20/12 ms trace had charged 176.7 ms
to the legacy receiver subtree, including those offline dependencies.
[Earlier fresh exact transfer](active-imports.md)

The installed position wrapper still runs `solve`, native preparation and
`v5_core.infer` with its original numerical bindings and evidence callback.
Its active path retains SciPy stats for predictive models and Matplotlib
for standard presentation, including the position and track RMS figures.
Deferring such imports to their point of use would still charge the
positive worker. The witnessed orbit policy was stock, so the initially
imported `history_support` and `corner_support` functions were unused.
Their import roots were only 11.6 and 0.9 ms in the older trace. Those
numbers price older first loads, including dependencies that may be
used elsewhere in the current solve. No position import isolation was
attempted.

The candidate used the original archive, offer and 506-factor packet with
corrected portable orbit preparation and rank. Both (c) arms reproduced
the exact positions, RF residuals and ordered 115-owner rosters.
The 24-probe regional proof, accepted named finish, complete 179-point
scientific grid and path, and all eight encoded and decoded PNGs matched
the pinned prior publication. No original waveform path ran.

The [protocol](weak-positive-import-protocol.md) was frozen at
`9e4add039`. The [saved runner](weak_positive_import.py) ran at
`99a31bf14` under the shared low-priority Gauss lock with one numerical
thread. Three existing deferral tests and two attribution tests passed.
The [receipt](measurements/weak-positive-import.json.gz) preserves the
launch command, all clocks, loader witness and exact published evidence.
