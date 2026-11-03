# Single-worker vector search with larger endpoint cache

The search now completes inside one 300-second scan interval, but this trial
still fails lossless qualification: the eight-entry detector queue rejects
3/2,215 dwells, all in the second scan quarter. There are 16,161 positive
observations rather than 16,191. Every processed GLRT candidate and emitted
observation/support row remains exact. Maximum arrival-to-finish latency is
1.376032 seconds. Detector exit code 3 reports the loss explicitly.

| Concurrent process | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Detector/projection, nice 0 | 300.894096 | 288.127419 | 50,604 |
| One-worker vector search, 128 MiB bank, nice 19 | 283.410619 | 270.163228 | 120,624 |

All 400 search scores and selected coordinates exactly match isolated ARM;
independent host comparison passes the predeclared 1e-9 Hz tolerance.
The previous single-worker 64 MiB PGO trial took 317.171 seconds and rejected
5 dwells. The new build includes a fresh single-worker PGO profile as well as
the larger cache; the ordinary ABBA experiment in `../vector-bank-capacity-v1/`
isolates the cache effect and saves 8.647% CPU on 16 held-out sites.

This overlap excludes seed/tracking, orbit generation, conversion and full
final associations. Its 16.6-second search wall margin is not a demonstrated
full-pipeline reserve. Next test a larger explicitly bounded detector queue
to absorb the observed burst, then include auxiliary stages and successive
scans. Do not infer full throughput from queue enlargement or this single scan.

The pinned `protocol.json` and `tools/run_arm_overlap.py` reproduce the run in
a new report with unique output paths. Detector and projection evaluators
confirm exact processed science while explicitly reporting incomplete output;
`compare_projection_subset.py` exits 1 as expected. Raw timing, terminal
accounting, search trace and checkpoints are retained. No new RF was collected.
