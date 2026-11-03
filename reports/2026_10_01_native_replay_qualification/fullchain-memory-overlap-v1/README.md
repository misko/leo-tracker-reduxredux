# Lossless in-memory full-chain overlap, still over cadence

The full previous-scan pipeline completes numerically on ARM while recorded
GLRT processes all 2,215 dwells without loss. All **16,191** positive observations
and support rows match exactly. The queue peaks at **14/16** entries, with
maximum arrival-to-finish latency **1.975182 seconds**. Both jobs exit zero.

However, the downstream chain takes **302.384756 seconds**, exceeding the
300-second scan interval by 2.384756 seconds. This fails the cadence gate and
does not demonstrate sustained successive-scan operation.

| Concurrent workload/stage | Wall seconds | CPU seconds | Peak RSS KiB |
|---|---:|---:|---:|
| Seed generation | 3.851128 | 3.797491 | 9,928 |
| Track reconstruction | 4.104358 | 4.069472 | 10,528 |
| In-memory conversion, orbit, search, associations | 294.383455 | 278.653242 | 151,584 |
| Whole downstream chain | 302.384756 | 286.559647 | 151,584 |
| Concurrent GLRT/projection | 301.192266 | 292.234886 | 62,108 |

Within the combined positioning stage, track conversion takes 2.492956 seconds
and native orbit generation 5.210856 seconds. Large orbit/LOC1 intermediate
files are eliminated. Peak positioning RSS increases because the live orbit
context retains its two state buffers; these are per-process peaks, not a
sampled aggregate device peak.

Seeds and tracks match independent host outputs byte for byte. Every search
score equals the qualified ARM trace exactly and passes independent host
tolerance. Full final associations equal the host control exactly. The current
detector's complete output passes both candidate and checkpoint comparison.
See `chain-comparison.json`, `detector-evaluation.json`,
`checkpoint-comparison.json` and `search-comparison.json`.

The previous file-based full chain took 304.102742 seconds and rejected 13
dwells. This trial is lossless and 1.717986 seconds faster, but the remaining
deadline miss and narrow queue margin require further work. Single trials do
not establish a statistical improvement or sustained capacity. Next reduce
compute/scheduling overhead, then test successive releases at fixed cadence.

The pinned protocol and generated `chain.sh` rebuild seeds/tracks from the
previous lossless scan's observations, then perform conversion, TLE propagation
and location analysis through public in-memory ports. `chain/` holds timing
and final outputs. No orbit/LOC1 files are produced by this chain. This is one
recorded overlap interval, not a genuine longer-history or live-RF qualification.
IQ stays on ARM; evaluation copies are retrieved after completion.
