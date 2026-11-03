# Full previous-scan processing alongside recorded GLRT

All five downstream stages ran on ARM using the previous lossless replay's
local observations/support while the next 300-second recorded IQ workload ran
at original cadence. The chain regenerates seeds, tracks, native orbit
authority, exclusive-track location input, all 400 search points and full final
associations. It does not reuse precomputed track memberships or location input.

The numerical comparison passes, but the cadence gate fails. The full chain
takes **304.102742 wall / 288.817243 CPU seconds**. Detection rejects **13 of
2,215 dwells**, emitting 16,087 positives rather than 16,191. Its queue reaches
the 16-entry limit; maximum arrival-to-finish latency is 2.640054 seconds.
Detector exit code 3 explicitly reports rejected work.

| Stage, during overlap | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Seed generation | 3.849726 | 3.794222 | 9,908 |
| Track reconstruction | 4.110868 | 4.065567 | 10,660 |
| Native orbit + LOC1 authority | 5.665800 | 5.486890 | 58,828 |
| Exclusive-track conversion | 3.909694 | 3.644814 | 46,800 |
| Full search + final associations | 286.515052 | 271.772482 | 120,620 |
| Concurrent GLRT + projection | 301.327307 | 291.392049 | 69,292 |

Seed output and track memberships match host controls byte for byte. Native
orbit authority, converted input and support/membership evidence match the
qualified ARM references. Every search value is exactly equal to the qualified
ARM result and passes independent host tolerance. Full association JSON is
exactly equal to the host control. Every processed current-scan GLRT candidate
and emitted observation/support row is exact; missing work prevents lossless
qualification. See `chain-comparison.json`, `search-comparison.json`,
`detector-evaluation.json` and `checkpoint-comparison.json`.

The first 150 detector arrivals already reach 0.795 seconds queued, compared
with 0.124 seconds in the preceding search-only queue16 run. Later bursts
overflow the queue (4 drops in the first quarter, 9 in the second). The first
150 mean service times are both about 131.27 ms; additional early contention
therefore needs investigation beyond detector arithmetic. The file-based chain
also writes and rereads large orbit/LOC1 products while IQ is being read.
Eliminating those intermediate files through native memory ports is the next
implementation experiment. These single trials do not isolate disk, memory or
scheduling as the cause; do not claim a proven bottleneck from timing alone.

`protocol.json` pins every executable and immutable input. `chain.sh` is rendered
by `tools/render_arm_chain.py`, creates a fresh result directory, measures each
stage and stops on failure. Only successful completion publishes search stdout.
The chain/overlap harness tests pass (21 tests). `chain/` retains every stage's
output and timing. The outer job remains named `search` for harness compatibility
but its timing includes the entire downstream chain.

This is one overlap interval using the same recorded scan as a controlled load;
it is neither sustained successive-scan qualification nor live RF acquisition.
No RF was collected. All runtime IQ and derived products remained on ARM;
downloads occurred afterward for evaluation.
