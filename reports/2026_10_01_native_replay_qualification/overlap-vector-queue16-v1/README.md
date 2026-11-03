# Lossless single-scan detector/search overlap

The 16-entry queue accepts all 2,215 recorded dwells, reproducing all 16,191
positive observations and support rows exactly. No candidates differ from the
frozen GLRT control. The queue peaks at 9 entries; maximum arrival-to-finish
latency is 1.352514 seconds (p95 1.230324 seconds). Both processes exit zero.

| Concurrent process | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Detector/projection, nice 0, queue capacity 16 | 300.885304 | 289.205121 | 50,436 |
| One-worker vector search, 128 MiB bank, nice 19 | 283.610738 | 270.290370 | 120,624 |

All 400 search scores retain the previous ARM result and pass independent host
comparison at 1e-9 Hz tolerance. The only protocol change from
`../overlap-vector-bank128-v1/` is queue capacity 8→16, plus unique output paths.
The earlier eight-entry run rejected three dwells. This run demonstrates that
bounded buffering can absorb this scan's observed burst with the current search.
It does not establish a statistical loss rate or capacity for other recordings.

The scope remains one recorded scan overlapping a prior scan's location input.
Tracking, orbit generation, conversion and final associations are excluded.
This is not sustained full-chain or live acquisition qualification. Next add
the auxiliary stages and successive scans, measuring publication backlog and
memory in addition to detection loss. Search budget exhaustion is not global
convergence. No RF was collected and IQ processing remained on ARM.

Reproduce with `tools/run_arm_overlap.py` and a new report/unique device paths.
The pinned protocol, raw timings and checks are retained in this directory.
`detector-evaluation.json`, `search-comparison.json` and
`checkpoint-comparison.json` all pass their applicable comparison gates.
