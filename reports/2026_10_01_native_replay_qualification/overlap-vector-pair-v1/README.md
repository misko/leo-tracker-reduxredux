# Vector search with original-cadence recorded GLRT

This trial fails lossless real-time qualification. All 2,215 arrivals are
accounted for, but the eight-entry queue rejects 14 dwells (0.63%). The detector
emits 16,068 positive observations rather than 16,191. Every processed GLRT
candidate and emitted observation/support row matches the frozen control
exactly. Rejections by scan quarter are 2, 12, 0, 0; maximum arrival-to-finish
latency is 1.396744 seconds. Exit code 3 explicitly reports rejected work.

| Concurrent process | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Detector/projection, nice 0 | 301.075639 | 293.784302 | 50,420 |
| Vector pair-bound search, nice 19 | 301.590812 | 289.167102 | 120,800 |

The full 400-point search is exactly equal to the isolated ARM result and
passes the independent host tolerance comparison. Search is faster than the
previous scalar nice-19 overlap (314.505 seconds), but this trial loses more
dwells (14 versus 4). These single trials do not establish statistical
significance. The vector search remains above one scan interval even before
tracking, orbit generation, conversion and full final associations are added.
The isolated CPU saving therefore does not establish sustained throughput.

The predeclared protocol pins binaries, IQ verification and input hashes.
Reproduce with `PYTHONPATH=src python tools/run_arm_overlap.py REPORT`, using
a new report directory and unique device output paths. This intentionally
overlaps a prior scan's location input with recorded IQ; it is neither a fresh
full-chain concurrency test nor live RF qualification. No new RF was collected.

Evaluation receipts: `detector-evaluation.json`, `search-comparison.json`,
`projection-comparison.json`. Raw process timing and results are retained.
Next work must address combined scheduling/compute and burst buffering, then
include auxiliary stages in sustained replay; increasing a buffer alone cannot
establish that the full pipeline keeps pace.
