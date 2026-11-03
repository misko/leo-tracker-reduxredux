# Single-worker vector search overlap

Changing only the search worker count from two to one does not qualify
sustained processing. The detector rejects 5/2,215 dwells and emits 16,156
positive observations (35 fewer than the frozen 16,191). All processed GLRT
candidates and emitted projection/support rows remain exactly equal to their
controls. The eight-entry queue reaches capacity; maximum arrival-to-finish
latency is 1.404889 seconds. Detector exit code 3 explicitly reports loss.

| Process | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Detector/projection, nice 0 | 301.203238 | 290.314958 | 50,644 |
| One-worker vector search, nice 19 | 317.171372 | 303.786746 | 94,732 |

The two-worker vector control took 301.590812 search wall seconds and rejected
14 dwells. Fewer workers improve detector loss in these single trials, but
worsen search backlog. Both settings fail; neither includes tracking, orbit
generation, conversion or final associations. The complete 400-point result
is exactly equal to the isolated ARM search and passes independent host
comparison at the original 1e-9 Hz tolerance.

This is an execution-strategy comparison, not an isolated scheduler experiment:
each scorer context owns a 64 MiB endpoint-bank cap, so one worker also has
less total cache capacity than two. The measured CPU increase cannot be
attributed solely to worker scheduling. Next isolate cache capacity and compute
cost; do not treat larger queues as proof of sustained throughput.

`protocol.json` pins the unchanged inputs/binary and records the worker count.
Run `tools/run_arm_overlap.py` with a new report and unique output paths to
repeat. `detector-evaluation.json`, `search-comparison.json` and
`checkpoint-comparison.json` contain independent checks. The new
`tools/compare_projection_subset.py` explicitly distinguishes exact emitted
subsets from complete lossless output, checks candidate IDs and order, and
fails its CLI on missing rows. Its eight component tests pass. It returned
exit code 1 for this incomplete replay, as intended.
